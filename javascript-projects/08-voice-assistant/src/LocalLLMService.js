const axios = require('axios');

/**
 * Local LLM Service - Wrapper for Ollama API
 * Provides offline AI reasoning for natural language understanding
 */
class LocalLLMService {
  constructor(options = {}) {
    this.baseURL = options.baseURL || 'http://localhost:11434';
    this.model = options.model || 'llama3.2:3b';
    this.timeout = options.timeout || 30000;
    this.recheckMs = options.recheckMs ?? 15000; // how often to look again while unavailable
    this.isAvailable = false;
    this.lastCheck = 0;
    this.checkPromise = null;

    this.checkAvailability();
  }

  /**
   * If the service was unavailable at the last look and that was a while ago, look again
   * (Ollama may have been started since). Resolves quickly when there is nothing to do.
   */
  async refreshIfStale() {
    if (this.isAvailable) return;
    if (this.checkPromise) {
      await this.checkPromise;
      return;
    }
    if (Date.now() - this.lastCheck >= this.recheckMs) {
      await this.checkAvailability();
    }
  }

  /**
   * Check if Ollama is running and model is available
   */
  async checkAvailability() {
    this.checkPromise = this._check().finally(() => {
      this.lastCheck = Date.now();
      this.checkPromise = null;
    });
    return this.checkPromise;
  }

  async _check() {
    try {
      // Check if Ollama server is running
      const response = await axios.get(`${this.baseURL}/api/tags`, {
        timeout: 5000
      });

      // Check if our model is pulled
      const models = response.data.models || [];
      const wanted = this.model.includes(':') ? this.model : `${this.model}:latest`;
      const modelExists = models.some(m => m.name === wanted || m.model === wanted);

      if (!modelExists) {
        console.warn(`⚠️  Model ${this.model} not found. Run: ollama pull ${this.model}`);
        this.isAvailable = false;
        return;
      }

      this.isAvailable = true;
      console.log(`✓ Local LLM service available (${this.model})`);
    } catch (error) {
      console.warn('⚠️  Local LLM not available:', error.message);
      console.warn('   Start Ollama: ollama serve');
      this.isAvailable = false;
    }
  }

  /**
   * Generate chat completion
   * @param {Array} messages - OpenAI-format messages
   * @param {Object} options - Generation options
   * @returns {Promise<Object>} - { response, usage }
   */
  async generateResponse(messages, options = {}) {
    if (!this.isAvailable) {
      throw new Error('Local LLM service not available');
    }

    try {
      const response = await axios.post(
        `${this.baseURL}/api/chat`,
        {
          model: this.model,
          messages: messages,
          stream: false,
          options: {
            temperature: options.temperature ?? 0.7,
            top_p: options.top_p ?? 0.9,
            num_predict: options.max_tokens || 500
          }
        },
        { timeout: this.timeout }
      );

      return {
        response: response.data.message.content,
        usage: {
          prompt_tokens: response.data.prompt_eval_count || 0,
          completion_tokens: response.data.eval_count || 0,
          total_tokens: (response.data.prompt_eval_count || 0) + (response.data.eval_count || 0)
        }
      };
    } catch (error) {
      console.error('Local LLM generation error:', error.message);
      if (!error.response) {
        this.isAvailable = false; // no answer at all (Ollama stopped?) - look again on the next request
        this.lastCheck = 0;
      }
      throw new Error(`Local LLM failed: ${error.message}`);
    }
  }

  /**
   * Check if service is available
   */
  available() {
    return this.isAvailable;
  }

  /**
   * Get service information
   */
  getInfo() {
    return {
      available: this.isAvailable,
      baseURL: this.baseURL,
      model: this.model,
      timeout: this.timeout
    };
  }
}

module.exports = LocalLLMService;
