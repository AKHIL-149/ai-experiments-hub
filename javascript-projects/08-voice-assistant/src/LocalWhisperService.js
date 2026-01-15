const { spawn, execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

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
    this.isAvailable = false;

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

      process.on('error', (error) => {
        reject(new Error('Whisper executable not found'));
      });

      process.on('close', (code) => {
        if (code === 0 || code === null) {
          resolve();
        } else {
          reject(new Error(`Whisper test failed with code ${code}`));
        }
      });

      // Timeout after 5 seconds
      setTimeout(() => {
        process.kill();
        reject(new Error('Whisper test timeout'));
      }, 5000);
    });
  }

  /**
   * Transcribe audio file using whisper.cpp
   * @param {string|Buffer} audioInput - Path to audio file or Buffer
   * @param {Object} options - Transcription options
   * @returns {Promise<Object>} - { text, duration }
   */
  async transcribeAudio(audioInput, options = {}) {
    if (!this.isAvailable) {
      throw new Error('Local Whisper service not available. Using cloud fallback.');
    }

    let audioPath;
    let wavPath;
    let cleanupRequired = false;

    // Handle Buffer input
    if (Buffer.isBuffer(audioInput)) {
      // Save WebM buffer to temp file
      const webmPath = path.join('/tmp', `whisper_input_${Date.now()}.webm`);
      fs.writeFileSync(webmPath, audioInput);
      console.log(`📝 Saved WebM audio: ${webmPath} (${(audioInput.length / 1024).toFixed(2)} KB)`);

      // Convert WebM to WAV using ffmpeg
      wavPath = path.join('/tmp', `whisper_${Date.now()}.wav`);
      try {
        console.log(`🔄 Converting WebM to WAV: ${webmPath} → ${wavPath}`);
        const ffmpegOutput = execSync(
          `/opt/homebrew/bin/ffmpeg -i "${webmPath}" -ar 16000 -ac 1 -c:a pcm_s16le "${wavPath}" -y 2>&1`,
          { encoding: 'utf8' }
        );
        console.log(`✓ FFmpeg conversion complete`);

        // Check if output file was created
        if (!fs.existsSync(wavPath)) {
          throw new Error('WAV file was not created by ffmpeg');
        }

        const wavStats = fs.statSync(wavPath);
        console.log(`✓ WAV file created: ${wavPath} (${(wavStats.size / 1024).toFixed(2)} KB)`);

        fs.unlinkSync(webmPath); // Clean up WebM file
      } catch (error) {
        console.error(`❌ FFmpeg conversion failed:`, error.message);
        if (fs.existsSync(webmPath)) fs.unlinkSync(webmPath);
        throw new Error(`Audio conversion failed: ${error.message}`);
      }

      audioPath = wavPath;
      cleanupRequired = true;
    } else if (typeof audioInput === 'string') {
      // Handle file path input
      const inputPath = audioInput;

      // Check if it's a WebM file that needs conversion
      if (inputPath.endsWith('.webm')) {
        console.log(`📁 Input is WebM file: ${inputPath}`);

        // Convert WebM to WAV using ffmpeg
        wavPath = path.join('/tmp', `whisper_${Date.now()}.wav`);
        try {
          console.log(`🔄 Converting WebM to WAV: ${inputPath} → ${wavPath}`);
          execSync(
            `/opt/homebrew/bin/ffmpeg -i "${inputPath}" -ar 16000 -ac 1 -c:a pcm_s16le "${wavPath}" -y 2>&1`,
            { encoding: 'utf8' }
          );
          console.log(`✓ FFmpeg conversion complete`);

          // Check if output file was created
          if (!fs.existsSync(wavPath)) {
            throw new Error('WAV file was not created by ffmpeg');
          }

          const wavStats = fs.statSync(wavPath);
          console.log(`✓ WAV file created: ${wavPath} (${(wavStats.size / 1024).toFixed(2)} KB)`);

          audioPath = wavPath;
          cleanupRequired = true;
        } catch (error) {
          console.error(`❌ FFmpeg conversion failed:`, error.message);
          throw new Error(`Audio conversion failed: ${error.message}`);
        }
      } else {
        // Already a WAV file or other supported format
        console.log(`📁 Input file: ${inputPath}`);
        audioPath = inputPath;
      }
    } else {
      throw new Error('Invalid audio input type. Expected Buffer or file path string.');
    }

    const startTime = Date.now();

    try {
      const text = await this.runWhisper(audioPath, options);
      const duration = Date.now() - startTime;

      return {
        text: text.trim(),
        duration: duration
      };
    } finally {
      // Cleanup temp file
      if (cleanupRequired && fs.existsSync(audioPath)) {
        fs.unlinkSync(audioPath);
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
        console.error(`❌ Whisper process error:`, error.message);
        reject(new Error(`Whisper process error: ${error.message}`));
      });

      process.on('close', (code) => {
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

            if (!text) {
              console.error(`❌ Text file is empty`);
              reject(new Error('No transcription output'));
              return;
            }

            console.log(`✓ Transcription successful: "${text}"`);
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

      // Timeout after 60 seconds
      setTimeout(() => {
        console.error(`⏱️  Whisper transcription timeout after 60 seconds`);
        process.kill();
        reject(new Error('Whisper transcription timeout'));
      }, 60000);
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
