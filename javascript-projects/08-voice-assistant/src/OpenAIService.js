const OpenAI = require('openai');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

/**
 * A failed call to OpenAI: the message says what failed, and the status tells the server
 * to answer 502 (bad gateway) rather than a generic 500
 */
function upstreamError(message) {
  const error = new Error(message);
  error.status = 502;
  return error;
}

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
    this.webSearchService = options.webSearchService || null;
    this.weatherService = options.weatherService || null;
    this.f1Service = options.f1Service || null;
  }

  /**
   * Transcribe audio to text using OpenAI Whisper API
   * @param {Buffer|string} audioInput - Audio buffer or file path
   * @param {Object} options - Transcription options
   * @returns {Promise<Object>} - { text, duration }
   */
  async transcribeAudio(audioInput, options = {}) {
    let tempPath = null;
    try {
      const startTime = Date.now();

      // Handle different input types
      let audioFile;
      if (typeof audioInput === 'string') {
        // File path provided
        audioFile = fs.createReadStream(audioInput);
      } else if (Buffer.isBuffer(audioInput)) {
        // Buffer provided - save to temp file (removed again in the finally block below)
        tempPath = path.join(__dirname, '../data/audio-cache', `temp_${crypto.randomBytes(8).toString('hex')}.webm`);
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
        text: (transcription.text || '').trim(),
        duration: duration
      };
    } catch (error) {
      console.error('Transcription error:', error.message);
      throw upstreamError(`Failed to transcribe audio: ${error.message}`);
    } finally {
      if (tempPath && fs.existsSync(tempPath)) {
        fs.unlinkSync(tempPath);
      }
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
      throw upstreamError(`Failed to synthesize speech: ${error.message}`);
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
      throw upstreamError(`Failed to generate response: ${error.message}`);
    }
  }

  /**
   * Build the tool definitions available to generateResponseWithTools,
   * based on which real-data services were actually configured.
   */
  _buildToolDefinitions() {
    const tools = [];

    tools.push({
      type: 'function',
      function: {
        name: 'web_search',
        description: 'Search the web for current information (news, schedules, prices, releases, or anything that may have changed since training). Use this for anything you are not certain is still accurate.',
        parameters: {
          type: 'object',
          properties: {
            query: { type: 'string', description: 'The search query' }
          },
          required: ['query']
        }
      }
    });

    tools.push({
      type: 'function',
      function: {
        name: 'get_weather',
        description: 'Get real current weather conditions for a location.',
        parameters: {
          type: 'object',
          properties: {
            location: { type: 'string', description: 'City name, e.g. "Austin,TX,US". Omit to use the default configured location.' }
          }
        }
      }
    });

    tools.push({
      type: 'function',
      function: {
        name: 'get_f1_schedule',
        description: 'Get the real next upcoming Formula 1 race (name, circuit, date). Use this instead of guessing at F1 schedules from memory.',
        parameters: { type: 'object', properties: {} }
      }
    });

    return tools;
  }

  /**
   * Execute one tool call by name and return its result as plain text
   * for feeding back to the model. Never throws - a tool failure becomes
   * a text result the model can react to (e.g. apologize, try another tool).
   */
  async _executeTool(name, args) {
    try {
      if (name === 'web_search') {
        if (!this.webSearchService || !this.webSearchService.available()) {
          return 'Web search is not configured on this server.';
        }
        const results = await this.webSearchService.search(args.query);
        return results.length
          ? results.map(r => `${r.title} (${r.url}): ${r.content}`).join('\n\n')
          : 'No results found.';
      }

      if (name === 'get_weather') {
        if (!this.weatherService || !this.weatherService.available()) {
          return 'Weather service is not configured on this server.';
        }
        const weather = await this.weatherService.getCurrentWeather(args.location);
        return `${weather.tempF}°F and ${weather.description} in ${weather.location}, feels like ${weather.feelsLikeF}°F, ${weather.humidity}% humidity.`;
      }

      if (name === 'get_f1_schedule') {
        if (!this.f1Service) {
          return 'F1 schedule service is not configured on this server.';
        }
        const race = await this.f1Service.getNextRace();
        return race
          ? `Next F1 race: ${race.raceName} at ${race.circuit} on ${race.dateFormatted}.`
          : 'No upcoming F1 race scheduled.';
      }

      return `Unknown tool: ${name}`;
    } catch (error) {
      return `Tool "${name}" failed: ${error.message}`;
    }
  }

  /**
   * Generate a chat completion with access to real-data tools (web
   * search, weather, F1 schedule). Single round-trip tool loop (not a
   * multi-step agent): if the model requests one or more tools, run
   * them, feed the results back, and make one follow-up call for the
   * final answer.
   * @param {Array} messages - Chat messages array
   * @param {Object} options - Completion options
   * @returns {Promise<Object>} - { response, usage, usedTools }
   */
  async generateResponseWithTools(messages, options = {}) {
    try {
      const tools = this._buildToolDefinitions();
      const model = options.model || 'gpt-4o-mini';

      const first = await this.openai.chat.completions.create({
        model,
        messages,
        tools,
        temperature: options.temperature || 0.7,
        max_tokens: options.maxTokens || 300
      });

      const choice = first.choices[0];
      const toolCalls = choice.message.tool_calls;

      if (!toolCalls || toolCalls.length === 0) {
        return {
          response: choice.message.content,
          usage: first.usage,
          usedTools: []
        };
      }

      // Execute every requested tool call, feed all results back
      const toolMessages = [];
      for (const toolCall of toolCalls) {
        const args = JSON.parse(toolCall.function.arguments || '{}');
        const result = await this._executeTool(toolCall.function.name, args);
        toolMessages.push({
          role: 'tool',
          tool_call_id: toolCall.id,
          content: result
        });
      }

      const followUpMessages = [...messages, choice.message, ...toolMessages];

      const final = await this.openai.chat.completions.create({
        model,
        messages: followUpMessages,
        temperature: options.temperature || 0.7,
        max_tokens: options.maxTokens || 300
      });

      return {
        response: final.choices[0].message.content,
        usage: final.usage,
        usedTools: toolCalls.map(tc => tc.function.name)
      };
    } catch (error) {
      console.error('Tool-calling completion error:', error.message);
      throw upstreamError(`Failed to generate response with tools: ${error.message}`);
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
