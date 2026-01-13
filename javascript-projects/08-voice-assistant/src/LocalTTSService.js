const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

/**
 * Local TTS Service - Wrapper for local text-to-speech engines
 * Supports multiple TTS backends: espeak, piper, festival
 */
class LocalTTSService {
  constructor(options = {}) {
    this.engine = options.engine || 'espeak'; // espeak, piper, festival
    this.voice = options.voice || 'en';
    this.speed = options.speed || 175; // words per minute for espeak
    this.outputDir = options.outputDir || '/tmp';
    this.isAvailable = false;

    // Engine-specific paths
    this.espeakPath = options.espeakPath || 'espeak';
    this.piperPath = options.piperPath || 'piper';
    this.festivalPath = options.festivalPath || 'festival';

    this.checkAvailability();
  }

  /**
   * Check if TTS engine is available
   */
  async checkAvailability() {
    try {
      switch (this.engine) {
        case 'espeak':
          await this.testEspeak();
          break;
        case 'piper':
          await this.testPiper();
          break;
        case 'festival':
          await this.testFestival();
          break;
        default:
          throw new Error(`Unknown TTS engine: ${this.engine}`);
      }

      this.isAvailable = true;
      console.log(`✓ Local TTS service available (${this.engine})`);
    } catch (error) {
      console.warn(`⚠️  Local TTS (${this.engine}) not available:`, error.message);
      this.isAvailable = false;
    }
  }

  /**
   * Test espeak availability
   */
  testEspeak() {
    return new Promise((resolve, reject) => {
      const process = spawn(this.espeakPath, ['--version']);

      process.on('error', () => {
        reject(new Error('espeak not found. Install: apt-get install espeak'));
      });

      process.on('close', (code) => {
        if (code === 0) resolve();
        else reject(new Error('espeak test failed'));
      });

      setTimeout(() => {
        process.kill();
        reject(new Error('espeak test timeout'));
      }, 3000);
    });
  }

  /**
   * Test piper availability
   */
  testPiper() {
    return new Promise((resolve, reject) => {
      const process = spawn(this.piperPath, ['--version']);

      process.on('error', () => {
        reject(new Error('piper not found'));
      });

      process.on('close', (code) => {
        if (code === 0) resolve();
        else reject(new Error('piper test failed'));
      });

      setTimeout(() => {
        process.kill();
        reject(new Error('piper test timeout'));
      }, 3000);
    });
  }

  /**
   * Test festival availability
   */
  testFestival() {
    return new Promise((resolve, reject) => {
      const process = spawn(this.festivalPath, ['--version']);

      process.on('error', () => {
        reject(new Error('festival not found'));
      });

      process.on('close', (code) => {
        if (code === 0 || code === null) resolve();
        else reject(new Error('festival test failed'));
      });

      setTimeout(() => {
        process.kill();
        reject(new Error('festival test timeout'));
      }, 3000);
    });
  }

  /**
   * Synthesize speech from text
   * @param {string} text - Text to synthesize
   * @param {Object} options - TTS options
   * @returns {Promise<Object>} - { audioBuffer, format }
   */
  async synthesizeSpeech(text, options = {}) {
    if (!this.isAvailable) {
      throw new Error(`Local TTS (${this.engine}) not available. Using cloud fallback.`);
    }

    const outputPath = path.join(
      this.outputDir,
      `tts_${Date.now()}.wav`
    );

    try {
      switch (this.engine) {
        case 'espeak':
          await this.generateWithEspeak(text, outputPath, options);
          break;
        case 'piper':
          await this.generateWithPiper(text, outputPath, options);
          break;
        case 'festival':
          await this.generateWithFestival(text, outputPath, options);
          break;
      }

      // Read generated audio file
      const audioBuffer = fs.readFileSync(outputPath);

      // Cleanup
      if (fs.existsSync(outputPath)) {
        fs.unlinkSync(outputPath);
      }

      return {
        audioBuffer: audioBuffer,
        format: 'wav'
      };
    } catch (error) {
      // Cleanup on error
      if (fs.existsSync(outputPath)) {
        fs.unlinkSync(outputPath);
      }
      throw error;
    }
  }

  /**
   * Generate speech with espeak
   * @param {string} text - Text to speak
   * @param {string} outputPath - Output WAV file path
   * @param {Object} options - Options
   */
  generateWithEspeak(text, outputPath, options = {}) {
    return new Promise((resolve, reject) => {
      const speed = options.speed || this.speed;
      const voice = options.voice || this.voice;

      const args = [
        '-v', voice,
        '-s', String(speed),
        '-w', outputPath,
        text
      ];

      const process = spawn(this.espeakPath, args);

      let errorOutput = '';

      process.stderr.on('data', (data) => {
        errorOutput += data.toString();
      });

      process.on('error', (error) => {
        reject(new Error(`espeak error: ${error.message}`));
      });

      process.on('close', (code) => {
        if (code !== 0) {
          reject(new Error(`espeak failed (code ${code}): ${errorOutput}`));
          return;
        }

        if (!fs.existsSync(outputPath)) {
          reject(new Error('espeak did not generate output file'));
          return;
        }

        resolve();
      });

      // Timeout after 30 seconds
      setTimeout(() => {
        process.kill();
        reject(new Error('espeak timeout'));
      }, 30000);
    });
  }

  /**
   * Generate speech with piper
   * @param {string} text - Text to speak
   * @param {string} outputPath - Output WAV file path
   * @param {Object} options - Options
   */
  generateWithPiper(text, outputPath, options = {}) {
    return new Promise((resolve, reject) => {
      const args = [
        '--model', options.model || './models/piper/en_US-lessac-medium.onnx',
        '--output_file', outputPath
      ];

      const process = spawn(this.piperPath, args);

      // Pipe text to stdin
      process.stdin.write(text);
      process.stdin.end();

      let errorOutput = '';

      process.stderr.on('data', (data) => {
        errorOutput += data.toString();
      });

      process.on('error', (error) => {
        reject(new Error(`piper error: ${error.message}`));
      });

      process.on('close', (code) => {
        if (code !== 0) {
          reject(new Error(`piper failed (code ${code}): ${errorOutput}`));
          return;
        }

        if (!fs.existsSync(outputPath)) {
          reject(new Error('piper did not generate output file'));
          return;
        }

        resolve();
      });

      setTimeout(() => {
        process.kill();
        reject(new Error('piper timeout'));
      }, 30000);
    });
  }

  /**
   * Generate speech with festival
   * @param {string} text - Text to speak
   * @param {string} outputPath - Output WAV file path
   * @param {Object} options - Options
   */
  generateWithFestival(text, outputPath, options = {}) {
    return new Promise((resolve, reject) => {
      // Festival uses scheme commands
      const scheme = `(begin (utt.save.wave (utt.synth (Utterance Text "${text.replace(/"/g, '\\"')}")) "${outputPath}") (quit))`;

      const process = spawn(this.festivalPath, ['--batch']);

      process.stdin.write(scheme);
      process.stdin.end();

      let errorOutput = '';

      process.stderr.on('data', (data) => {
        errorOutput += data.toString();
      });

      process.on('error', (error) => {
        reject(new Error(`festival error: ${error.message}`));
      });

      process.on('close', (code) => {
        if (code !== 0 && code !== null) {
          reject(new Error(`festival failed (code ${code}): ${errorOutput}`));
          return;
        }

        if (!fs.existsSync(outputPath)) {
          reject(new Error('festival did not generate output file'));
          return;
        }

        resolve();
      });

      setTimeout(() => {
        process.kill();
        reject(new Error('festival timeout'));
      }, 30000);
    });
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
      engine: this.engine,
      voice: this.voice,
      speed: this.speed
    };
  }

  /**
   * List available voices (engine-specific)
   * @returns {Array<string>}
   */
  getAvailableVoices() {
    // This would require calling the respective engine's voice list command
    // For simplicity, return common defaults
    switch (this.engine) {
      case 'espeak':
        return ['en', 'en-us', 'en-gb', 'es', 'fr', 'de'];
      case 'piper':
        return ['en_US-lessac', 'en_GB-alan', 'en_US-amy'];
      case 'festival':
        return ['voice_kal_diphone', 'voice_rab_diphone'];
      default:
        return [];
    }
  }
}

module.exports = LocalTTSService;
