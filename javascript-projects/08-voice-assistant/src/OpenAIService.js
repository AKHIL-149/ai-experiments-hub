const OpenAI = require('openai');
const fs = require('fs');
const path = require('path');

/**
 * OpenAI Service - Handles speech-to-text and text-to-speech operations
 */
class OpenAIService {
  constructor(apiKey, options = {}) {
    if (!apiKey) {
      throw new Error('OpenAI API key is required');
    }

    this.openai = new OpenAI({ apiKey });
    this.whisperModel = options.whisperModel || 'whisper-1';
    this.ttsModel = options.ttsModel || 'tts-1';
    this.ttsVoice = options.ttsVoice || 'alloy';
  }

  /**
   * Transcribe audio to text using OpenAI Whisper API
   * @param {Buffer|string} audioInput - Audio buffer or file path
   * @param {Object} options - Transcription options
   * @returns {Promise<Object>} - { text, duration }
   */
  async transcribeAudio(audioInput, options = {}) {
    try {
      const startTime = Date.now();

      // Handle different input types
      let audioFile;
      if (typeof audioInput === 'string') {
        // File path provided
        audioFile = fs.createReadStream(audioInput);
      } else if (Buffer.isBuffer(audioInput)) {
        // Buffer provided - save to temp file
        const tempPath = path.join(__dirname, '../data/audio-cache', `temp_${Date.now()}.webm`);
        fs.writeFileSync(tempPath, audioInput);
        audioFile = fs.createReadStream(tempPath);
      } else {
        throw new Error('Invalid audio input type. Expected Buffer or file path.');
      }

      // Call OpenAI Whisper API
      const transcription = await this.openai.audio.transcriptions.create({
        file: audioFile,
        model: options.model || this.whisperModel,
        language: options.language || undefined,
        response_format: options.responseFormat || 'json'
      });

      const duration = Date.now() - startTime;

      return {
        text: transcription.text,
        duration: duration
      };
    } catch (error) {
      console.error('Transcription error:', error.message);
      throw new Error(`Failed to transcribe audio: ${error.message}`);
    }
  }

  /**
   * Synthesize speech from text using OpenAI TTS API
   * @param {string} text - Text to convert to speech
   * @param {Object} options - TTS options
   * @returns {Promise<Object>} - { audioBuffer, format }
   */
  async synthesizeSpeech(text, options = {}) {
    try {
      if (!text || text.trim().length === 0) {
        throw new Error('Text is required for speech synthesis');
      }

      // Limit text length (OpenAI has 4096 character limit)
      if (text.length > 4096) {
        text = text.substring(0, 4096);
        console.warn('Text truncated to 4096 characters for TTS');
      }

      const voice = options.voice || this.ttsVoice;
      const model = options.model || this.ttsModel;
      const speed = options.speed || 1.0;

      // Call OpenAI TTS API
      const mp3 = await this.openai.audio.speech.create({
        model: model,
        voice: voice,
        input: text,
        speed: speed
      });

      // Get audio buffer
      const arrayBuffer = await mp3.arrayBuffer();
      const audioBuffer = Buffer.from(arrayBuffer);

      return {
        audioBuffer: audioBuffer,
        format: 'mp3'
      };
    } catch (error) {
      console.error('TTS error:', error.message);
      throw new Error(`Failed to synthesize speech: ${error.message}`);
    }
  }

  /**
   * Generate chat completion (for command interpretation and responses)
   * @param {Array} messages - Chat messages array
   * @param {Object} options - Completion options
   * @returns {Promise<Object>} - { response, usage }
   */
  async generateResponse(messages, options = {}) {
    try {
      const completion = await this.openai.chat.completions.create({
        model: options.model || 'gpt-4o-mini',
        messages: messages,
        temperature: options.temperature || 0.7,
        max_tokens: options.maxTokens || 300
      });

      return {
        response: completion.choices[0].message.content,
        usage: completion.usage
      };
    } catch (error) {
      console.error('Chat completion error:', error.message);
      throw new Error(`Failed to generate response: ${error.message}`);
    }
  }

  /**
   * Test API connectivity
   * @returns {Promise<boolean>}
   */
  async testConnection() {
    try {
      await this.openai.models.list();
      return true;
    } catch (error) {
      console.error('API connection test failed:', error.message);
      return false;
    }
  }

  /**
   * Get available TTS voices
   * @returns {Array<string>}
   */
  getAvailableVoices() {
    return ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer'];
  }
}

module.exports = OpenAIService;
