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
    this.isAvailable = false;

    this.checkAvailability();
  }

  /**
   * Check if Ollama is running and model is available
   */
  async checkAvailability() {
    try {
      // Check if Ollama server is running
      const response = await axios.get(`${this.baseURL}/api/tags`, {
        timeout: 5000
      });

      // Check if our model is pulled
      const models = response.data.models || [];
      const modelExists = models.some(m => m.name.includes(this.model.split(':')[0]));

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
            temperature: options.temperature || 0.7,
            top_p: options.top_p || 0.9,
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
      throw new Error(`Local LLM failed: ${error.message}`);
    }
  }

  /**
   * Parse natural language math expression using LLM
   * @param {string} transcript - User's spoken math query
   * @returns {Promise<Object>} - { expression, result, explanation }
   */
  async parseMathExpression(transcript) {
    const messages = [
      {
        role: 'system',
        content: 'You are a math assistant. Parse natural language math expressions and return ONLY a valid JavaScript expression. Examples:\n"five plus three" → "5 + 3"\n"calculate 10 minus 2" → "10 - 2"\n"what is 7 times 8" → "7 * 8"\nReturn ONLY the expression, no explanation.'
      },
      {
        role: 'user',
        content: transcript
      }
    ];

    const result = await this.generateResponse(messages, { temperature: 0.1, max_tokens: 50 });
    const expression = result.response.trim();

    // Safely evaluate using Function (already validated by LLM)
    // Strip any non-math characters for safety
    const safeExpression = expression.replace(/[^0-9+\-*/().\s]/g, '');
    const calculationResult = Function(`'use strict'; return (${safeExpression})`)();

    return {
      expression: safeExpression,
      result: calculationResult,
      explanation: `${safeExpression} = ${calculationResult}`
    };
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
