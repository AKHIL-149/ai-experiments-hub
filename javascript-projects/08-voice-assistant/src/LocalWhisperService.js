const { spawn } = require('child_process');
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
    let cleanupRequired = false;

    // Handle Buffer input
    if (Buffer.isBuffer(audioInput)) {
      audioPath = path.join('/tmp', `whisper_${Date.now()}.wav`);
      fs.writeFileSync(audioPath, audioInput);
      cleanupRequired = true;
    } else {
      audioPath = audioInput;
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

      let output = '';
      let errorOutput = '';

      const process = spawn(this.whisperPath, args);

      process.stdout.on('data', (data) => {
        output += data.toString();
      });

      process.stderr.on('data', (data) => {
        errorOutput += data.toString();
      });

      process.on('error', (error) => {
        reject(new Error(`Whisper process error: ${error.message}`));
      });

      process.on('close', (code) => {
        if (code !== 0) {
          reject(new Error(`Whisper failed (exit code ${code}): ${errorOutput}`));
          return;
        }

        // Extract transcribed text from output
        const text = this.extractTextFromOutput(output);

        if (!text) {
          reject(new Error('No transcription output'));
          return;
        }

        resolve(text);
      });

      // Timeout after 60 seconds
      setTimeout(() => {
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
