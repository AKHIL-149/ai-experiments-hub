const { spawn } = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');

const MIN_WPM = 80;   // espeak's slowest setting; anything lower is clamped to it
const MAX_WPM = 450;

/**
 * Prepare model output for a speech engine: markdown marks and links are not words,
 * and a leading "-" must not look like a command-line option.
 * @param {string} text
 * @returns {string}
 */
function cleanForSpeech(text) {
  return String(text)
    .replace(/https?:\/\/\S+/g, 'link')
    .replace(/[*_`#>~]+/g, ' ')
    .replace(/^\s*[-•]\s+/gm, '')
    .replace(/[\u0000-\u001f]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Local TTS Service - Wrapper for local text-to-speech engines
 * Supports multiple TTS backends: espeak, piper, festival
 */
class LocalTTSService {
  constructor(options = {}) {
    this.engine = options.engine || 'espeak'; // espeak, piper, festival
    this.voice = options.voice || 'en';
    this.speed = options.speed || 175; // words per minute for espeak
    this.outputDir = options.outputDir || os.tmpdir();
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
      const timer = setTimeout(() => {
        process.kill();
        reject(new Error('espeak test timeout'));
      }, 3000);

      process.on('error', () => {
        clearTimeout(timer);
        reject(new Error('espeak not found. Install: apt-get install espeak'));
      });

      process.on('close', (code) => {
        clearTimeout(timer);
        if (code === 0) resolve();
        else reject(new Error('espeak test failed'));
      });
    });
  }

  /**
   * Test piper availability
   */
  testPiper() {
    return new Promise((resolve, reject) => {
      const process = spawn(this.piperPath, ['--version']);
      const timer = setTimeout(() => {
        process.kill();
        reject(new Error('piper test timeout'));
      }, 3000);

      process.on('error', () => {
        clearTimeout(timer);
        reject(new Error('piper not found'));
      });

      process.on('close', (code) => {
        clearTimeout(timer);
        if (code === 0) resolve();
        else reject(new Error('piper test failed'));
      });
    });
  }

  /**
   * Test festival availability
   */
  testFestival() {
    return new Promise((resolve, reject) => {
      const process = spawn(this.festivalPath, ['--version']);
      const timer = setTimeout(() => {
        process.kill();
        reject(new Error('festival test timeout'));
      }, 3000);

      process.on('error', () => {
        clearTimeout(timer);
        reject(new Error('festival not found'));
      });

      process.on('close', (code) => {
        clearTimeout(timer);
        if (code === 0 || code === null) resolve();
        else reject(new Error('festival test failed'));
      });
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

    text = cleanForSpeech(text);
    if (!text) {
      throw new Error('There is nothing to say');
    }

    // Unique per request - two requests in the same millisecond must not share (and delete) a file
    const outputPath = path.join(
      this.outputDir,
      `tts_${crypto.randomBytes(8).toString('hex')}.wav`
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
      // options.speed is a multiplier (1.0 = normal, as in the settings panel and the OpenAI API);
      // espeak wants words per minute
      const multiplier = Number(options.speed) > 0 ? Number(options.speed) : 1;
      const wpm = Math.max(MIN_WPM, Math.min(MAX_WPM, Math.round(this.speed * multiplier)));
      const voice = options.voice || this.voice;

      // "--" ends the options, so the text can never be read as a flag
      const args = [
        '-v', voice,
        '-s', String(wpm),
        '-w', outputPath,
        '--',
        text
      ];

      const process = spawn(this.espeakPath, args);
      const timer = setTimeout(() => {
        process.kill();
        reject(new Error('espeak timeout'));
      }, 30000);

      let errorOutput = '';

      process.stderr.on('data', (data) => {
        errorOutput += data.toString();
      });

      process.on('error', (error) => {
        clearTimeout(timer);
        reject(new Error(`espeak error: ${error.message}`));
      });

      process.on('close', (code) => {
        clearTimeout(timer);
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
      const timer = setTimeout(() => {
        process.kill();
        reject(new Error('piper timeout'));
      }, 30000);

      // Pipe text to stdin
      process.stdin.write(text);
      process.stdin.end();

      let errorOutput = '';

      process.stderr.on('data', (data) => {
        errorOutput += data.toString();
      });

      process.on('error', (error) => {
        clearTimeout(timer);
        reject(new Error(`piper error: ${error.message}`));
      });

      process.on('close', (code) => {
        clearTimeout(timer);
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
      // The text sits inside a Scheme string literal: escape the backslash first, then the quote,
      // or crafted text could close the string and run its own Scheme (which can run commands)
      const quoted = text.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
      const scheme = `(begin (utt.save.wave (utt.synth (Utterance Text "${quoted}")) "${outputPath}") (quit))`;

      const process = spawn(this.festivalPath, ['--batch']);
      const timer = setTimeout(() => {
        process.kill();
        reject(new Error('festival timeout'));
      }, 30000);

      process.stdin.write(scheme);
      process.stdin.end();

      let errorOutput = '';

      process.stderr.on('data', (data) => {
        errorOutput += data.toString();
      });

      process.on('error', (error) => {
        clearTimeout(timer);
        reject(new Error(`festival error: ${error.message}`));
      });

      process.on('close', (code) => {
        clearTimeout(timer);
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
module.exports.cleanForSpeech = cleanForSpeech;
