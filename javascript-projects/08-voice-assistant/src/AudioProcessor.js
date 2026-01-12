const fs = require('fs');
const path = require('path');

/**
 * Audio Processor - Coordinates audio input/output operations
 */
class AudioProcessor {
  constructor(openAIService, options = {}) {
    if (!openAIService) {
      throw new Error('OpenAIService instance is required');
    }

    this.openAIService = openAIService;
    this.tempDir = options.tempDir || path.join(__dirname, '../data/audio-cache');
    this.maxAudioSizeMB = options.maxAudioSizeMB || 25;

    // Ensure temp directory exists
    if (!fs.existsSync(this.tempDir)) {
      fs.mkdirSync(this.tempDir, { recursive: true });
    }
  }

  /**
   * Process audio input and transcribe to text
   * @param {Buffer} audioBlob - Audio data as buffer
   * @param {Object} options - Processing options
   * @returns {Promise<Object>} - { transcript, confidence }
   */
  async processAudioInput(audioBlob, options = {}) {
    try {
      // Validate audio size
      const audioSizeMB = audioBlob.length / (1024 * 1024);
      if (audioSizeMB > this.maxAudioSizeMB) {
        throw new Error(`Audio file too large (${audioSizeMB.toFixed(2)}MB). Max size: ${this.maxAudioSizeMB}MB`);
      }

      // Save audio to temp file
      const tempFilePath = path.join(this.tempDir, `audio_${Date.now()}.webm`);
      fs.writeFileSync(tempFilePath, audioBlob);

      try {
        // Transcribe audio using OpenAI Service
        const result = await this.openAIService.transcribeAudio(tempFilePath, options);

        // Clean up temp file
        this.cleanupTempFile(tempFilePath);

        return {
          transcript: result.text,
          confidence: 1.0, // OpenAI Whisper doesn't return confidence scores
          duration: result.duration
        };
      } catch (error) {
        // Clean up temp file on error
        this.cleanupTempFile(tempFilePath);
        throw error;
      }
    } catch (error) {
      console.error('Audio processing error:', error.message);
      throw new Error(`Failed to process audio: ${error.message}`);
    }
  }

  /**
   * Generate audio response from text
   * @param {string} text - Text to convert to speech
   * @param {Object} voiceOptions - Voice settings
   * @returns {Promise<Object>} - { audioBuffer, duration, format }
   */
  async generateAudioResponse(text, voiceOptions = {}) {
    try {
      if (!text || text.trim().length === 0) {
        throw new Error('Text is required to generate audio response');
      }

      const startTime = Date.now();

      // Synthesize speech using OpenAI Service
      const result = await this.openAIService.synthesizeSpeech(text, voiceOptions);

      const duration = Date.now() - startTime;

      return {
        audioBuffer: result.audioBuffer,
        duration: duration,
        format: result.format
      };
    } catch (error) {
      console.error('Audio generation error:', error.message);
      throw new Error(`Failed to generate audio: ${error.message}`);
    }
  }

  /**
   * Validate audio format
   * @param {Buffer} audioBlob - Audio data
   * @returns {Object} - { valid, error }
   */
  validateAudioFormat(audioBlob) {
    if (!Buffer.isBuffer(audioBlob)) {
      return { valid: false, error: 'Invalid audio data: not a buffer' };
    }

    if (audioBlob.length === 0) {
      return { valid: false, error: 'Audio data is empty' };
    }

    const audioSizeMB = audioBlob.length / (1024 * 1024);
    if (audioSizeMB > this.maxAudioSizeMB) {
      return {
        valid: false,
        error: `Audio file too large (${audioSizeMB.toFixed(2)}MB). Max: ${this.maxAudioSizeMB}MB`
      };
    }

    return { valid: true };
  }

  /**
   * Clean up temporary audio file
   * @param {string} filePath - Path to temp file
   */
  cleanupTempFile(filePath) {
    try {
      if (fs.existsSync(filePath)) {
        fs.unlinkSync(filePath);
      }
    } catch (error) {
      console.error(`Failed to cleanup temp file ${filePath}:`, error.message);
    }
  }

  /**
   * Clean up old temporary files
   * @param {number} maxAgeMs - Max age in milliseconds
   */
  cleanupOldFiles(maxAgeMs = 3600000) {
    try {
      const files = fs.readdirSync(this.tempDir);
      const now = Date.now();

      files.forEach(file => {
        const filePath = path.join(this.tempDir, file);
        const stats = fs.statSync(filePath);
        const fileAge = now - stats.mtimeMs;

        if (fileAge > maxAgeMs) {
          fs.unlinkSync(filePath);
          console.log(`Cleaned up old temp file: ${file}`);
        }
      });
    } catch (error) {
      console.error('Error cleaning up old files:', error.message);
    }
  }

  /**
   * Get temp directory statistics
   * @returns {Object} - { fileCount, totalSizeMB }
   */
  getTempDirStats() {
    try {
      const files = fs.readdirSync(this.tempDir);
      let totalSize = 0;

      files.forEach(file => {
        const filePath = path.join(this.tempDir, file);
        const stats = fs.statSync(filePath);
        totalSize += stats.size;
      });

      return {
        fileCount: files.length,
        totalSizeMB: (totalSize / (1024 * 1024)).toFixed(2)
      };
    } catch (error) {
      console.error('Error getting temp dir stats:', error.message);
      return { fileCount: 0, totalSizeMB: 0 };
    }
  }
}

module.exports = AudioProcessor;
