const OpenAIService = require('./OpenAIService');
const LocalWhisperService = require('./LocalWhisperService');
const LocalTTSService = require('./LocalTTSService');

/**
 * Service Manager - Handles switching between cloud and local AI services
 * Provides unified interface for STT and TTS regardless of backend
 */
class ServiceManager {
  constructor(options = {}) {
    this.mode = options.mode || 'cloud'; // 'cloud', 'local', 'hybrid'
    this.fallbackToCloud = options.fallbackToCloud !== false;

    // Initialize services
    this.cloudService = null;
    this.localWhisperService = null;
    this.localTTSService = null;

    this.initializeServices(options);
  }

  /**
   * Initialize all available services
   */
  initializeServices(options) {
    // Cloud service (OpenAI)
    if (options.openaiApiKey) {
      try {
        this.cloudService = new OpenAIService(options.openaiApiKey, {
          whisperModel: options.whisperModel || 'whisper-1',
          ttsModel: options.ttsModel || 'tts-1',
          ttsVoice: options.ttsVoice || 'alloy'
        });
        console.log('✓ Cloud service (OpenAI) initialized');
      } catch (error) {
        console.error('Failed to initialize cloud service:', error.message);
      }
    }

    // Local Whisper service
    try {
      this.localWhisperService = new LocalWhisperService({
        whisperPath: options.whisperPath,
        modelPath: options.whisperModelPath,
        language: options.language || 'en',
        threads: options.whisperThreads || 4
      });
    } catch (error) {
      console.warn('Failed to initialize local Whisper:', error.message);
    }

    // Local TTS service
    try {
      this.localTTSService = new LocalTTSService({
        engine: options.ttsEngine || 'espeak',
        // Don't pass ttsVoice - let LocalTTSService use its own defaults (en for espeak)
        // options.ttsVoice is for OpenAI voices (alloy, echo, etc) which don't work with espeak
        speed: options.ttsSpeed || 175
      });
    } catch (error) {
      console.warn('Failed to initialize local TTS:', error.message);
    }
  }

  /**
   * Transcribe audio using current mode
   * @param {string|Buffer} audioInput - Audio file path or Buffer
   * @param {Object} options - Transcription options
   * @returns {Promise<Object>} - { text, duration }
   */
  async transcribeAudio(audioInput, options = {}) {
    const useLocal = this.shouldUseLocal('stt');

    // Pure local mode - no fallback
    if (this.mode === 'local') {
      if (this.localWhisperService && this.localWhisperService.available()) {
        console.log('Using local Whisper for transcription (local mode)');
        return await this.localWhisperService.transcribeAudio(audioInput, options);
      } else {
        throw new Error('Local Whisper not available. Cannot transcribe in local mode.');
      }
    }

    // Hybrid or cloud mode with fallback
    try {
      if (useLocal && this.localWhisperService && this.localWhisperService.available()) {
        console.log('Using local Whisper for transcription');
        return await this.localWhisperService.transcribeAudio(audioInput, options);
      } else if (this.cloudService) {
        console.log('Using cloud (OpenAI) for transcription');
        return await this.cloudService.transcribeAudio(audioInput, options);
      } else {
        throw new Error('No transcription service available');
      }
    } catch (error) {
      // Fallback to cloud if local fails (only in hybrid mode)
      if (useLocal && this.fallbackToCloud && this.mode === 'hybrid' && this.cloudService) {
        console.warn('Local transcription failed, falling back to cloud:', error.message);
        return await this.cloudService.transcribeAudio(audioInput, options);
      }
      throw error;
    }
  }

  /**
   * Synthesize speech using current mode
   * @param {string} text - Text to synthesize
   * @param {Object} options - TTS options
   * @returns {Promise<Object>} - { audioBuffer, format }
   */
  async synthesizeSpeech(text, options = {}) {
    const useLocal = this.shouldUseLocal('tts');

    // Pure local mode - no fallback
    if (this.mode === 'local') {
      if (this.localTTSService && this.localTTSService.available()) {
        console.log('Using local TTS for synthesis (local mode)');
        // Remove cloud-specific options (like OpenAI voice names) for local TTS
        const localOptions = { ...options };
        delete localOptions.voice; // espeak uses default voice
        return await this.localTTSService.synthesizeSpeech(text, localOptions);
      } else {
        throw new Error('Local TTS not available. Cannot synthesize in local mode.');
      }
    }

    // Hybrid or cloud mode with fallback
    try {
      if (useLocal && this.localTTSService && this.localTTSService.available()) {
        console.log('Using local TTS for synthesis');
        // Remove cloud-specific options (like OpenAI voice names) for local TTS
        const localOptions = { ...options };
        delete localOptions.voice; // espeak uses default voice
        return await this.localTTSService.synthesizeSpeech(text, localOptions);
      } else if (this.cloudService) {
        console.log('Using cloud (OpenAI) for synthesis');
        return await this.cloudService.synthesizeSpeech(text, options);
      } else {
        throw new Error('No TTS service available');
      }
    } catch (error) {
      // Fallback to cloud if local fails (only in hybrid mode)
      if (useLocal && this.fallbackToCloud && this.mode === 'hybrid' && this.cloudService) {
        console.warn('Local TTS failed, falling back to cloud:', error.message);
        return await this.cloudService.synthesizeSpeech(text, options);
      }
      throw error;
    }
  }

  /**
   * Generate chat response
   * @param {Array} messages - Chat messages
   * @param {Object} options - Generation options
   * @returns {Promise<Object>} - { response, usage }
   */
  async generateResponse(messages, options = {}) {
    // In local mode, return a helpful message instead of using cloud AI
    if (this.mode === 'local') {
      console.log('ℹ Local mode: AI chat not available, returning command-only message');
      return {
        response: "I can help you with voice commands like: What time is it? Tell me a joke. Calculate 5 plus 3. Set a timer. Say 'help' to hear all available commands.",
        usage: null
      };
    }

    // In cloud or hybrid mode, use cloud service
    if (!this.cloudService) {
      throw new Error('Cloud service required for chat responses');
    }

    return await this.cloudService.generateResponse(messages, options);
  }

  /**
   * Determine if local service should be used
   * @param {string} serviceType - 'stt' or 'tts'
   * @returns {boolean}
   */
  shouldUseLocal(serviceType) {
    switch (this.mode) {
      case 'local':
        return true;
      case 'cloud':
        return false;
      case 'hybrid':
        // In hybrid mode, prefer local if available
        if (serviceType === 'stt') {
          return this.localWhisperService && this.localWhisperService.available();
        } else if (serviceType === 'tts') {
          return this.localTTSService && this.localTTSService.available();
        }
        return false;
      default:
        return false;
    }
  }

  /**
   * Set operation mode
   * @param {string} mode - 'cloud', 'local', or 'hybrid'
   */
  setMode(mode) {
    if (!['cloud', 'local', 'hybrid'].includes(mode)) {
      throw new Error(`Invalid mode: ${mode}. Use 'cloud', 'local', or 'hybrid'`);
    }

    this.mode = mode;
    console.log(`✓ Service mode set to: ${mode}`);
  }

  /**
   * Get current mode
   * @returns {string}
   */
  getMode() {
    return this.mode;
  }

  /**
   * Get service status
   * @returns {Object}
   */
  getStatus() {
    return {
      mode: this.mode,
      cloud: {
        available: !!this.cloudService,
        service: 'OpenAI'
      },
      local: {
        whisper: {
          available: this.localWhisperService ? this.localWhisperService.available() : false,
          info: this.localWhisperService ? this.localWhisperService.getInfo() : null
        },
        tts: {
          available: this.localTTSService ? this.localTTSService.available() : false,
          info: this.localTTSService ? this.localTTSService.getInfo() : null
        }
      },
      fallbackEnabled: this.fallbackToCloud
    };
  }

  /**
   * Test connection to all available services
   * @returns {Promise<Object>}
   */
  async testServices() {
    const results = {
      cloud: false,
      localWhisper: false,
      localTTS: false
    };

    // Test cloud
    if (this.cloudService) {
      try {
        results.cloud = await this.cloudService.testConnection();
      } catch (error) {
        console.error('Cloud service test failed:', error.message);
      }
    }

    // Test local Whisper
    if (this.localWhisperService) {
      results.localWhisper = this.localWhisperService.available();
    }

    // Test local TTS
    if (this.localTTSService) {
      results.localTTS = this.localTTSService.available();
    }

    return results;
  }

  /**
   * Get available voices for current mode
   * @returns {Array<string>}
   */
  getAvailableVoices() {
    const useLocalTTS = this.shouldUseLocal('tts');

    if (useLocalTTS && this.localTTSService && this.localTTSService.available()) {
      return this.localTTSService.getAvailableVoices();
    } else if (this.cloudService) {
      return this.cloudService.getAvailableVoices();
    }

    return [];
  }

  /**
   * Check if local services are ready
   * @returns {Object}
   */
  isLocalReady() {
    return {
      whisper: this.localWhisperService ? this.localWhisperService.available() : false,
      tts: this.localTTSService ? this.localTTSService.available() : false,
      ready: (this.localWhisperService && this.localWhisperService.available()) &&
             (this.localTTSService && this.localTTSService.available())
    };
  }

  /**
   * Get recommended mode based on available services
   * @returns {string}
   */
  getRecommendedMode() {
    const localReady = this.isLocalReady();

    if (localReady.ready) {
      return 'hybrid'; // Both available, use hybrid
    } else if (this.cloudService) {
      return 'cloud'; // Only cloud available
    } else if (localReady.whisper || localReady.tts) {
      return 'local'; // Partial local available
    }

    return 'cloud'; // Default to cloud
  }
}

module.exports = ServiceManager;
