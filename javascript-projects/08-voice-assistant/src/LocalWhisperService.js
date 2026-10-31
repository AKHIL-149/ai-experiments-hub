const { spawn } = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');

// A recording whose loudest sample is quieter than this is treated as silence (dBFS).
// Real speech peaks far above it; digital silence reads about -91 dB.
const SILENCE_THRESHOLD_DB = -50;

/**
 * Pull the actionable tail out of ffmpeg's output. Its full output leads
 * with a version/build-config banner that's noise for an error message -
 * the actual failure reason is always in the last few lines.
 */
function extractFfmpegError(output) {
  const lines = (output || '').trim().split('\n').filter(line => line.trim());
  return lines.slice(-5).join('\n');
}

/**
 * Whisper describes non-speech sounds in brackets - "[BLANK_AUDIO]", "(airplane engine
 * roaring)", "*music*", "♪ ... ♪" - and those are not something the user said. Remove them;
 * an empty result means there was no speech.
 * @param {string} text - Raw whisper output
 * @returns {string}
 */
function cleanTranscript(text) {
  return (text || '')
    .replace(/\[[^\]]*\]/g, ' ')
    .replace(/\([^)]*\)/g, ' ')
    .replace(/\*[^*]*\*/g, ' ')
    .replace(/[♪♫]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Local Whisper Service - Wrapper for whisper.cpp CLI
 * Provides offline speech-to-text using local Whisper models
 */
class LocalWhisperService {
  constructor(options = {}) {
    this.whisperPath = options.whisperPath || 'whisper';
    this.modelPath = options.modelPath || './models/ggml-base.en.bin';
    this.language = options.language || 'en';
    this.threads = options.threads || 4;
    this.ffmpegPath = options.ffmpegPath || process.env.FFMPEG_PATH || 'ffmpeg';
    this.maxConcurrent = options.maxConcurrent || parseInt(process.env.WHISPER_CONCURRENCY) || 2;
    this.isAvailable = false;

    // Whisper is CPU-heavy: ten at once make each one ten times slower, so extra
    // requests wait their turn instead.
    this.running = 0;
    this.waiting = [];

    this.checkAvailability();
  }

  /**
   * Check if whisper.cpp is available
   */
  async checkAvailability() {
    try {
      // Check if model file exists
      if (!fs.existsSync(this.modelPath)) {
        console.warn(`⚠️  Whisper model not found at ${this.modelPath}`);
        console.warn('   Download models from: https://huggingface.co/ggerganov/whisper.cpp');
        this.isAvailable = false;
        return;
      }

      // Try to run whisper to check if it's available
      await this.testWhisper();
      this.isAvailable = true;
      console.log('✓ Local Whisper service available');
    } catch (error) {
      console.warn('⚠️  Local Whisper not available:', error.message);
      this.isAvailable = false;
    }
  }

  /**
   * Test if whisper executable works
   */
  testWhisper() {
    return new Promise((resolve, reject) => {
      const process = spawn(this.whisperPath, ['--help']);
      const timer = setTimeout(() => {
        process.kill();
        reject(new Error('Whisper test timeout'));
      }, 5000);

      process.on('error', (error) => {
        clearTimeout(timer);
        reject(new Error('Whisper executable not found'));
      });

      process.on('close', (code) => {
        clearTimeout(timer);
        if (code === 0 || code === null) {
          resolve();
        } else {
          reject(new Error(`Whisper test failed with code ${code}`));
        }
      });
    });
  }

  /**
   * Wait for a free transcription slot
   */
  async acquireSlot() {
    if (this.running < this.maxConcurrent) {
      this.running++;
      return;
    }
    await new Promise(resolve => this.waiting.push(resolve));
  }

  releaseSlot() {
    const next = this.waiting.shift();
    if (next) {
      next(); // the slot passes straight to the next waiter
    } else {
      this.running--;
    }
  }

  /**
   * Convert any audio file/format to 16 kHz mono WAV with ffmpeg (no shell involved), and
   * measure its loudest sample on the way.
   * @param {string} inputPath
   * @param {string} wavPath
   * @returns {Promise<number|null>} - max volume in dB, or null if ffmpeg did not report one
   */
  convertToWav(inputPath, wavPath) {
    return new Promise((resolve, reject) => {
      const args = [
        '-nostdin', '-hide_banner',
        '-i', inputPath,
        '-af', 'volumedetect',
        '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le',
        '-y', wavPath
      ];
      const ffmpeg = spawn(this.ffmpegPath, args);
      let output = '';

      ffmpeg.stderr.on('data', (data) => { output += data.toString(); });
      ffmpeg.stdout.on('data', () => {});

      const timer = setTimeout(() => {
        ffmpeg.kill();
        const error = new Error('Audio conversion timed out');
        error.status = 504;
        reject(error);
      }, 30000);

      ffmpeg.on('error', (error) => {
        clearTimeout(timer);
        const failure = new Error(error.code === 'ENOENT'
          ? 'ffmpeg is not installed, so recordings cannot be converted. Install it or set FFMPEG_PATH.'
          : `Could not run ffmpeg: ${error.message}`);
        failure.status = 503;
        reject(failure);
      });

      ffmpeg.on('close', (code) => {
        clearTimeout(timer);
        if (code !== 0 || !fs.existsSync(wavPath)) {
          // The detail (ffmpeg's own message, internal paths) goes to the log, not to the client
          console.error(`❌ FFmpeg conversion failed:`, extractFfmpegError(output));
          const failure = new Error('That recording could not be read as audio');
          failure.status = 400;
          reject(failure);
          return;
        }
        const match = output.match(/max_volume:\s*(-?[\d.]+|-inf)\s*dB/);
        resolve(match ? (match[1] === '-inf' ? -Infinity : parseFloat(match[1])) : null);
      });
    });
  }

  /**
   * Transcribe audio file using whisper.cpp
   * @param {string|Buffer} audioInput - Path to audio file or Buffer
   * @param {Object} options - Transcription options
   * @returns {Promise<Object>} - { text, duration, noSpeech }
   */
  async transcribeAudio(audioInput, options = {}) {
    if (!this.isAvailable) {
      throw new Error('Local Whisper service not available. Using cloud fallback.');
    }
    if (!Buffer.isBuffer(audioInput) && typeof audioInput !== 'string') {
      throw new Error('Invalid audio input type. Expected Buffer or file path string.');
    }

    const id = crypto.randomBytes(6).toString('hex');
    const tempFiles = [];
    const startTime = Date.now();

    await this.acquireSlot();
    try {
      let inputPath = audioInput;
      if (Buffer.isBuffer(audioInput)) {
        inputPath = path.join(os.tmpdir(), `whisper_input_${id}`);
        fs.writeFileSync(inputPath, audioInput);
        tempFiles.push(inputPath);
      }

      const wavPath = path.join(os.tmpdir(), `whisper_${id}.wav`);
      tempFiles.push(wavPath, `${wavPath}.txt`);

      const maxVolume = await this.convertToWav(inputPath, wavPath);

      // Pure silence makes whisper invent words ("you", "Thank you.") - do not even ask it
      if (maxVolume !== null && maxVolume < SILENCE_THRESHOLD_DB) {
        return { text: '', duration: Date.now() - startTime, noSpeech: true };
      }

      const text = cleanTranscript(await this.runWhisper(wavPath, options));

      return {
        text,
        duration: Date.now() - startTime,
        noSpeech: text.length === 0
      };
    } finally {
      this.releaseSlot();
      for (const file of tempFiles) {
        try {
          if (fs.existsSync(file)) fs.unlinkSync(file);
        } catch (error) {
          console.error(`Failed to remove temp file ${file}:`, error.message);
        }
      }
    }
  }

  /**
   * Run whisper.cpp process
   * @param {string} audioPath - Path to audio file
   * @param {Object} options - Whisper options
   * @returns {Promise<string>} - Transcribed text
   */
  runWhisper(audioPath, options = {}) {
    return new Promise((resolve, reject) => {
      const args = [
        '-m', this.modelPath,
        '-f', audioPath,
        '-l', options.language || this.language,
        '-t', String(this.threads),
        '--output-txt',
        '--no-timestamps'
      ];

      // Add optional parameters
      if (options.translate) {
        args.push('--translate');
      }

      console.log(`🎤 Running Whisper with args:`, args.join(' '));

      let output = '';
      let errorOutput = '';

      const process = spawn(this.whisperPath, args);
      const timer = setTimeout(() => {
        console.error(`⏱️  Whisper transcription timeout after 60 seconds`);
        process.kill();
        reject(new Error('Whisper transcription timeout'));
      }, 60000);

      process.stdout.on('data', (data) => {
        const chunk = data.toString();
        output += chunk;
        console.log(`[Whisper stdout]: ${chunk.trim()}`);
      });

      process.stderr.on('data', (data) => {
        const chunk = data.toString();
        errorOutput += chunk;
        console.log(`[Whisper stderr]: ${chunk.trim()}`);
      });

      process.on('error', (error) => {
        clearTimeout(timer);
        console.error(`❌ Whisper process error:`, error.message);
        reject(new Error(`Whisper process error: ${error.message}`));
      });

      process.on('close', (code) => {
        clearTimeout(timer);
        console.log(`🏁 Whisper process exited with code: ${code}`);

        if (code !== 0) {
          console.error(`❌ Whisper failed with error output:`, errorOutput);
          reject(new Error(`Whisper failed (exit code ${code}): ${errorOutput}`));
          return;
        }

        // Whisper with --output-txt writes to a .txt file
        const txtFilePath = `${audioPath}.txt`;

        try {
          if (fs.existsSync(txtFilePath)) {
            console.log(`📄 Reading transcription from: ${txtFilePath}`);
            const text = fs.readFileSync(txtFilePath, 'utf8').trim();

            // Clean up the txt file
            fs.unlinkSync(txtFilePath);

            // Empty output simply means nothing intelligible was said
            console.log(`✓ Whisper heard: "${text}"`);
            resolve(text);
          } else {
            console.error(`❌ Output text file not found: ${txtFilePath}`);
            console.log(`📄 Raw stdout (${output.length} chars):`, output.substring(0, 500));
            reject(new Error('No transcription output file created'));
          }
        } catch (error) {
          console.error(`❌ Failed to read transcription file:`, error.message);
          reject(new Error(`Failed to read transcription: ${error.message}`));
        }
      });
    });
  }

  /**
   * Extract transcribed text from whisper output
   * @param {string} output - Raw whisper output
   * @returns {string} - Cleaned transcribed text
   */
  extractTextFromOutput(output) {
    // Whisper outputs the transcription after certain markers
    // Look for lines that don't start with brackets or special characters
    const lines = output.split('\n');
    const textLines = [];

    for (const line of lines) {
      const trimmed = line.trim();
      // Skip empty lines, timestamps, and system messages
      if (trimmed &&
          !trimmed.startsWith('[') &&
          !trimmed.startsWith('whisper_') &&
          !trimmed.includes('processing') &&
          !trimmed.includes('system_info')) {
        textLines.push(trimmed);
      }
    }

    return textLines.join(' ').trim();
  }

  /**
   * Check if service is available
   * @returns {boolean}
   */
  available() {
    return this.isAvailable;
  }

  /**
   * Get service information
   * @returns {Object}
   */
  getInfo() {
    return {
      available: this.isAvailable,
      modelPath: this.modelPath,
      language: this.language,
      threads: this.threads
    };
  }
}

module.exports = LocalWhisperService;
module.exports.cleanTranscript = cleanTranscript;
