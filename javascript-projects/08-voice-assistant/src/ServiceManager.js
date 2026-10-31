const OpenAIService = require('./OpenAIService');
const LocalWhisperService = require('./LocalWhisperService');
const LocalTTSService = require('./LocalTTSService');
const LocalLLMService = require('./LocalLLMService');
const WebSearchService = require('./WebSearchService');
const WeatherService = require('./WeatherService');
const F1Service = require('./F1Service');
const ConnectivityService = require('./ConnectivityService');

/**
 * An error for "this service is not available" - answered as 503 by the server
 */
function unavailable(message) {
  const error = new Error(message);
  error.status = 503;
  return error;
}

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
    this.localLLMService = null;
    this.webSearchService = null;
    this.weatherService = null;
    this.f1Service = null;
    this.connectivityService = null;

    this.initializeServices(options);
  }

  /**
   * Initialize all available services
   */
  initializeServices(options) {
    // Internet reachability - built first so it's checking in the
    // background while everything else initializes
    this.connectivityService = new ConnectivityService();

    // Web search (used by cloud tool-calling) - built before the cloud
    // service so it can be handed to OpenAIService directly. Always
    // reports available: Tavily is used when configured (better
    // quality), otherwise falls back to DuckDuckGo's free Instant
    // Answer API (no signup, but much narrower coverage - mostly
    // definitions/infobox facts, not general search results).
    this.webSearchService = new WebSearchService({
      apiKey: options.tavilyApiKey
    });
    console.log(`✓ Web search service available (${this.webSearchService.getInfo().mode})`);

    // Weather (dedicated command, independent of tool-calling) - always
    // available: OpenWeatherMap when configured, wttr.in (free, no key)
    // otherwise
    this.weatherService = new WeatherService({
      apiKey: options.openWeatherApiKey,
      defaultLocation: options.defaultWeatherLocation
    });
    console.log(`✓ Weather service available (${this.weatherService.getInfo().mode})`);

    // F1 schedule - free, no key required, always available
    this.f1Service = new F1Service();

    // Cloud service (OpenAI)
    if (options.openaiApiKey) {
      try {
        this.cloudService = new OpenAIService(options.openaiApiKey, {
          whisperModel: options.whisperModel || 'whisper-1',
          ttsModel: options.ttsModel || 'tts-1',
          ttsVoice: options.ttsVoice || 'alloy',
          webSearchService: this.webSearchService,
          weatherService: this.weatherService,
          f1Service: this.f1Service
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

    // Local LLM service - always built (not only in local/hybrid mode) so that
    // switching the mode at runtime does not leave it missing
    try {
      this.localLLMService = new LocalLLMService({
        model: options.llmModel || 'llama3.2:3b',
        baseURL: options.llmBaseURL || 'http://localhost:11434',
        timeout: options.llmTimeout || 30000
      });
    } catch (error) {
      console.warn('Failed to initialize local LLM:', error.message);
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
        throw unavailable('Local speech recognition is not available. Check the Whisper setup, or switch modes.');
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
        throw unavailable('No speech recognition service is available');
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
        return await this.localTTSService.synthesizeSpeech(text, this.localTTSOptions(options));
      } else {
        throw unavailable('Local text-to-speech is not available. Check the TTS setup, or switch modes.');
      }
    }

    // Hybrid or cloud mode with fallback
    try {
      if (useLocal && this.localTTSService && this.localTTSService.available()) {
        console.log('Using local TTS for synthesis');
        return await this.localTTSService.synthesizeSpeech(text, this.localTTSOptions(options));
      } else if (this.cloudService) {
        console.log('Using cloud (OpenAI) for synthesis');
        return await this.cloudService.synthesizeSpeech(text, options);
      } else {
        throw unavailable('No text-to-speech service is available');
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
   * Options for the local engine: a voice is only passed on if that engine has it
   * (cloud voice names such as "alloy" mean nothing to espeak)
   */
  localTTSOptions(options = {}) {
    const localOptions = { ...options };
    if (localOptions.voice && !this.localTTSService.getAvailableVoices().includes(localOptions.voice)) {
      delete localOptions.voice;
    }
    return localOptions;
  }

  /**
   * Generate chat response
   * @param {Array} messages - Chat messages
   * @param {Object} options - Generation options
   * @returns {Promise<Object>} - { response, usage }
   */
  async generateResponse(messages, options = {}) {
    // Try local LLM first in local/hybrid mode. If Ollama was not running when the server
    // started (or has come back since), look again instead of staying unavailable forever.
    if ((this.mode === 'local' || this.mode === 'hybrid') && this.localLLMService) {
      await this.localLLMService.refreshIfStale();
    }
    if ((this.mode === 'local' || this.mode === 'hybrid') &&
        this.localLLMService &&
        this.localLLMService.available()) {
      console.log('Using local LLM for response generation');
      try {
        return await this.localLLMService.generateResponse(messages, options);
      } catch (error) {
        console.error('Local LLM failed:', error.message);
        // In pure local mode, don't fallback
        if (this.mode === 'local') {
          throw unavailable('The local language model failed to answer. Check that Ollama is running.');
        }
      }
    }

    // Fallback to cloud in hybrid mode, or use cloud in cloud mode
    if (this.cloudService) {
      console.log('Using cloud (OpenAI) for response generation');
      return await this.cloudService.generateResponse(messages, options);
    }

    if (this.mode === 'local' || this.mode === 'hybrid') {
      throw unavailable(`The local language model is not available. Start Ollama and pull ${this.localLLMService ? this.localLLMService.model : 'a model'}.`);
    }
    throw unavailable('No AI service is available. Set OPENAI_API_KEY, or switch to local mode.');
  }

  /**
   * Generate a chat response with access to real-data tools (web search,
   * weather, F1 schedule). Always uses cloud - a 3B local model is not
   * reliable at deciding when/how to call a tool. Individual tools
   * degrade gracefully if their own service isn't configured (see
   * OpenAIService._executeTool) - only cloud itself is a hard requirement.
   * @param {Array} messages - Chat messages
   * @param {Object} options - Generation options
   * @returns {Promise<Object>} - { response, usage, usedTools }
   */
  async generateResponseWithTools(messages, options = {}) {
    if (!this.cloudService) {
      throw unavailable('Cloud service not configured - AI fallback with tools requires OPENAI_API_KEY');
    }

    console.log('Using cloud (OpenAI) with tools');
    return await this.cloudService.generateResponseWithTools(messages, options);
  }

  /**
   * Whether cloud (OpenAI) is configured
   * @returns {boolean}
   */
  isCloudAvailable() {
    return !!this.cloudService;
  }

  /**
   * Best-known internet reachability. Not a hard guarantee (DNS/routing
   * can change between the check and the next real call), but avoids
   * attempting a cloud/search/weather call we already know will just
   * time out - skip straight to local instead of paying that latency.
   * @returns {boolean}
   */
  isInternetAvailable() {
    if (!this.connectivityService) return true;
    this.connectivityService.recheckIfStale(); // not awaited: the next request sees the result
    return this.connectivityService.available();
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
   * Why a mode could not work right now, or null if it can. Used to refuse a switch that
   * would otherwise make every later request fail.
   * @param {string} mode - 'cloud', 'local', or 'hybrid'
   * @returns {string|null}
   */
  modeProblem(mode) {
    const whisper = !!(this.localWhisperService && this.localWhisperService.available());
    const tts = !!(this.localTTSService && this.localTTSService.available());

    if (mode === 'cloud' && !this.cloudService) {
      return 'Cloud mode needs an OpenAI API key. Set OPENAI_API_KEY and restart the server.';
    }
    if (mode === 'local' && !(whisper && tts)) {
      const missing = [!whisper && 'speech recognition (Whisper)', !tts && 'text-to-speech'].filter(Boolean).join(' and ');
      return `Local mode needs local ${missing}, which ${!whisper && !tts ? 'are' : 'is'} not available.`;
    }
    if (mode === 'hybrid' && !this.cloudService && !(whisper && tts)) {
      return 'Hybrid mode needs either an OpenAI API key or local Whisper and text-to-speech.';
    }
    return null;
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
        },
        llm: {
          available: this.localLLMService ? this.localLLMService.available() : false,
          info: this.localLLMService ? this.localLLMService.getInfo() : null
        }
      },
      webSearch: {
        available: this.webSearchService ? this.webSearchService.available() : false,
        info: this.webSearchService ? this.webSearchService.getInfo() : null
      },
      weather: {
        available: this.weatherService ? this.weatherService.available() : false,
        info: this.weatherService ? this.weatherService.getInfo() : null
      },
      internet: {
        available: this.isInternetAvailable(),
        info: this.connectivityService ? this.connectivityService.getInfo() : null
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
