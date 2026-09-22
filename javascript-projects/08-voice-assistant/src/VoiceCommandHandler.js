const fs = require('fs');
const path = require('path');

/**
 * Voice Command Handler - Pattern matching and command execution
 */
class VoiceCommandHandler {
  constructor(commandRegistryPath, options = {}) {
    this.commandRegistryPath = commandRegistryPath || path.join(__dirname, '../commands/commands.json');
    this.commands = this.loadCommands();
    this.timers = new Map(); // Store active timers
    this.llmService = options.llmService || null; // NEW: Inject LLM service
    this.weatherService = options.weatherService || null;
    this.f1Service = options.f1Service || null;
  }

  /**
   * Load command registry from JSON
   */
  loadCommands() {
    try {
      const data = fs.readFileSync(this.commandRegistryPath, 'utf8');
      return JSON.parse(data);
    } catch (error) {
      console.error('Failed to load command registry:', error.message);
      return {};
    }
  }

  /**
   * Parse command from transcript
   * @param {string} transcript - User's speech transcript
   * @returns {Promise<Object>} - { command, parameters, confidence }
   */
  async parseCommand(transcript) {
    const normalizedTranscript = transcript.toLowerCase().trim();

    // Evaluate every command/pattern and keep the highest-confidence
    // match across all of them, rather than returning the first match
    // found in commands.json's key order. Word-overlap fuzzy matching
    // means a phrase can legitimately match several commands at once
    // (e.g. "what day is it" scores 75% against "time"'s pattern purely
    // from shared stopwords, but 100% against "date"'s own pattern) -
    // first-match-wins made the result depend on registry ordering
    // instead of which command actually fits best.
    let bestMatch = null;

    for (const [commandId, commandConfig] of Object.entries(this.commands)) {
      for (const pattern of commandConfig.patterns) {
        const match = this.matchPattern(normalizedTranscript, pattern);
        if (!match.matched) continue;

        // "what is {expression}" (and similar) is broad enough to match
        // almost any "what is ___" question - only accept it as a real
        // calculation if the captured text actually looks like math.
        if (match.parameters.expression && !/\d/.test(match.parameters.expression)) {
          continue;
        }

        if (!bestMatch || match.confidence > bestMatch.match.confidence) {
          bestMatch = { commandId, commandConfig, match };
        }
      }
    }

    if (!bestMatch) {
      return { command: null, handler: null, parameters: {}, confidence: 0 };
    }

    return {
      command: bestMatch.commandId,
      handler: bestMatch.commandConfig.handler,
      parameters: bestMatch.match.parameters,
      confidence: bestMatch.match.confidence,
      name: bestMatch.commandConfig.name
    };
  }

  /**
   * Match transcript against pattern
   * @param {string} transcript - Normalized transcript
   * @param {string} pattern - Command pattern
   * @returns {Object} - { matched, parameters, confidence }
   */
  matchPattern(transcript, pattern) {
    // Normalize pattern
    const normalizedPattern = pattern.toLowerCase().trim();

    // Exact match
    if (transcript === normalizedPattern) {
      return { matched: true, parameters: {}, confidence: 1.0 };
    }

    // Check if pattern contains parameters (e.g., {duration}, {expression})
    if (normalizedPattern.includes('{')) {
      return this.matchParameterizedPattern(transcript, normalizedPattern);
    }

    // Fuzzy match (contains check) - word-boundary aware, so a short
    // pattern like "hi" only matches the actual word "hi", not a
    // substring buried inside an unrelated word ("history", "high").
    const escapedPattern = normalizedPattern.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const patternInTranscript = new RegExp(`\\b${escapedPattern}\\b`).test(transcript);
    const transcriptInPattern = new RegExp(`\\b${transcript.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`).test(normalizedPattern);
    if (patternInTranscript || transcriptInPattern) {
      return { matched: true, parameters: {}, confidence: 0.8 };
    }

    // Word-level similarity. Confidence scales with the actual overlap
    // ratio (not a flat value) so that when a phrase matches multiple
    // commands' patterns via shared stopwords (e.g. "what day is it"
    // overlaps both "date"'s own pattern at 100% and "time"'s pattern at
    // 75% purely from "what"/"is"/"it"), the more specific/complete match
    // outranks the coincidental one instead of tying with it.
    //
    // Precision alone isn't enough: a short pattern like "what is today"
    // can hit 100% precision against a much longer, unrelated sentence
    // that merely happens to contain those words somewhere ("what is the
    // latest news about the stock market today"). Also require recall -
    // the matched words must account for a real share of what the user
    // actually said - so a short pattern can't "find itself" buried
    // inside an unrelated longer utterance.
    const transcriptWords = transcript.split(/\s+/);
    const patternWords = normalizedPattern.split(/\s+/);
    const matchedWords = patternWords.filter(word => transcriptWords.includes(word));
    const precision = matchedWords.length / patternWords.length;
    const recall = matchedWords.length / transcriptWords.length;

    // Recall threshold matches precision's - confirmed live that 0.5 was
    // still loose enough for a short, mostly-stopword pattern like
    // "when is the next race" to match "when is the next iphone release"
    // (4/5 precision, 4/6=0.67 recall). A contiguous phrase with a few
    // extra filler words is already caught by the substring check above,
    // which doesn't have this issue - this tier is the scattered-word
    // fallback, so it can afford to be conservative.
    if (precision >= 0.7 && recall >= 0.7) {
      return { matched: true, parameters: {}, confidence: precision };
    }

    return { matched: false, parameters: {}, confidence: 0 };
  }

  /**
   * Match pattern with parameters
   * @param {string} transcript - User transcript
   * @param {string} pattern - Pattern with {param} placeholders
   * @returns {Object} - { matched, parameters, confidence }
   */
  matchParameterizedPattern(transcript, pattern) {
    // Extract parameter names from pattern
    const paramRegex = /\{(\w+)\}/g;
    const params = [];
    let match;
    while ((match = paramRegex.exec(pattern)) !== null) {
      params.push(match[1]);
    }

    // Convert pattern to regex
    let regexPattern = pattern
      .replace(/[.*+?^${}()|[\]\\]/g, '\\$&') // Escape special chars
      .replace(/\\{(\w+)\\}/g, '(.+?)'); // Replace {param} with capture groups

    const regex = new RegExp('^' + regexPattern + '$', 'i');
    const regexMatch = transcript.match(regex);

    if (regexMatch) {
      const parameters = {};
      params.forEach((param, index) => {
        parameters[param] = regexMatch[index + 1].trim();
      });
      return { matched: true, parameters, confidence: 0.9 };
    }

    // Try partial match
    const partialRegex = new RegExp(regexPattern, 'i');
    const partialMatch = transcript.match(partialRegex);

    if (partialMatch) {
      const parameters = {};
      params.forEach((param, index) => {
        parameters[param] = partialMatch[index + 1]?.trim() || '';
      });
      return { matched: true, parameters, confidence: 0.7 };
    }

    return { matched: false, parameters: {}, confidence: 0 };
  }

  /**
   * Execute command
   * @param {Object} parsedCommand - Parsed command from parseCommand()
   * @param {Object} context - Additional context (userId, conversationId, etc.)
   * @returns {Promise<Object>} - { success, response, data }
   */
  async executeCommand(parsedCommand, context = {}) {
    try {
      if (!parsedCommand.handler) {
        return {
          success: false,
          response: "I didn't understand that command. Try saying 'help' to see what I can do.",
          data: null
        };
      }

      // Execute handler
      const handler = this[parsedCommand.handler];
      if (typeof handler !== 'function') {
        return {
          success: false,
          response: `Command handler '${parsedCommand.handler}' not implemented yet.`,
          data: null
        };
      }

      const result = await handler.call(this, parsedCommand.parameters, context);
      return result;

    } catch (error) {
      console.error('Command execution error:', error);
      return {
        success: false,
        response: `Sorry, I encountered an error: ${error.message}`,
        data: null
      };
    }
  }

  // Command Handlers

  /**
   * Get current time
   */
  async getTime(params, context) {
    const now = new Date();
    const timeStr = now.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    });

    return {
      success: true,
      response: `The current time is ${timeStr}.`,
      data: { time: timeStr, timestamp: now.toISOString() }
    };
  }

  /**
   * Get current date
   */
  async getDate(params, context) {
    const now = new Date();
    const dateStr = now.toLocaleDateString('en-US', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });

    return {
      success: true,
      response: `Today is ${dateStr}.`,
      data: { date: dateStr, timestamp: now.toISOString() }
    };
  }

  /**
   * Tell a joke
   */
  async tellJoke(params, context) {
    const jokes = [
      "Why don't scientists trust atoms? Because they make up everything!",
      "Why did the scarecrow win an award? Because he was outstanding in his field!",
      "I told my wife she was drawing her eyebrows too high. She looked surprised.",
      "Why don't skeletons fight each other? They don't have the guts!",
      "What do you call a bear with no teeth? A gummy bear!",
      "Why did the bicycle fall over? Because it was two tired!",
      "What do you call a fake noodle? An impasta!",
      "Why did the coffee file a police report? It got mugged!",
      "What's the best thing about Switzerland? I don't know, but the flag is a big plus!"
    ];

    const randomJoke = jokes[Math.floor(Math.random() * jokes.length)];

    return {
      success: true,
      response: randomJoke,
      data: { joke: randomJoke }
    };
  }

  /**
   * Calculate math expression
   */
  async calculate(params, context) {
    try {
      const transcript = context.originalTranscript || '';

      // If LocalLLMService is available, use it for parsing
      if (this.llmService && this.llmService.available()) {
        console.log('Using LLM to parse math expression');
        try {
          const result = await this.llmService.parseMathExpression(transcript);

          return {
            success: true,
            response: `The result is ${result.result}.`,
            data: {
              expression: result.expression,
              result: result.result,
              method: 'llm-parsed'
            }
          };
        } catch (llmError) {
          console.warn('LLM math parsing failed, falling back to pattern matching:', llmError.message);
          // Fall through to pattern-based fallback
        }
      }

      // Fallback to original pattern-based parsing
      let expression = params.expression;

      // Handle natural language math
      if (params.num1 && params.num2) {
        const num1 = parseFloat(params.num1);
        const num2 = parseFloat(params.num2);

        // Determine operation from original transcript
        const transcriptLower = transcript.toLowerCase();

        if (transcriptLower.includes('plus') || transcriptLower.includes('add')) {
          expression = `${num1} + ${num2}`;
        } else if (transcriptLower.includes('minus') || transcriptLower.includes('subtract')) {
          expression = `${num1} - ${num2}`;
        } else if (transcriptLower.includes('times') || transcriptLower.includes('multiply')) {
          expression = `${num1} * ${num2}`;
        } else if (transcriptLower.includes('divided by') || transcriptLower.includes('divide')) {
          expression = `${num1} / ${num2}`;
        }
      }

      // Clean expression
      expression = expression
        .replace(/[^\d+\-*/().\s]/g, '')
        .replace(/\s+/g, '');

      // Simple evaluation (safe for basic math)
      const result = Function(`'use strict'; return (${expression})`)();

      if (isNaN(result) || !isFinite(result)) {
        throw new Error('Invalid calculation');
      }

      return {
        success: true,
        response: `The result is ${result}.`,
        data: { expression, result, method: 'pattern-matched' }
      };

    } catch (error) {
      console.error('Calculate error:', error.message);
      return {
        success: false,
        response: "I couldn't calculate that. Please try a simple math expression.",
        data: null
      };
    }
  }

  /**
   * Set timer
   */
  async setTimer(params, context) {
    try {
      const duration = params.duration.toLowerCase();

      // Parse duration
      let seconds = 0;

      // Extract numbers and units
      const minutesMatch = duration.match(/(\d+)\s*(minute|min)/);
      const secondsMatch = duration.match(/(\d+)\s*(second|sec)/);
      const hoursMatch = duration.match(/(\d+)\s*(hour|hr)/);

      if (hoursMatch) seconds += parseInt(hoursMatch[1]) * 3600;
      if (minutesMatch) seconds += parseInt(minutesMatch[1]) * 60;
      if (secondsMatch) seconds += parseInt(secondsMatch[1]);

      if (seconds === 0) {
        // Try to extract just a number (assume minutes)
        const numMatch = duration.match(/(\d+)/);
        if (numMatch) {
          seconds = parseInt(numMatch[1]) * 60;
        }
      }

      if (seconds === 0) {
        throw new Error('Could not parse duration');
      }

      const timerId = Date.now().toString();
      const endTime = Date.now() + (seconds * 1000);

      // Store timer (in a real app, you'd use a proper timer service)
      this.timers.set(timerId, {
        duration: seconds,
        endTime: endTime,
        started: Date.now()
      });

      // Format duration for response
      const minutes = Math.floor(seconds / 60);
      const remainingSeconds = seconds % 60;
      let durationStr = '';
      if (minutes > 0) durationStr += `${minutes} minute${minutes !== 1 ? 's' : ''}`;
      if (remainingSeconds > 0) {
        if (durationStr) durationStr += ' and ';
        durationStr += `${remainingSeconds} second${remainingSeconds !== 1 ? 's' : ''}`;
      }

      return {
        success: true,
        response: `Timer set for ${durationStr}. I'll let you know when time is up!`,
        data: { timerId, duration: seconds, endTime }
      };

    } catch (error) {
      return {
        success: false,
        response: "I couldn't set that timer. Try saying something like 'set a timer for 5 minutes'.",
        data: null
      };
    }
  }

  /**
   * Get current weather via OpenWeatherMap
   */
  async getWeather(params, context) {
    if (!this.weatherService || !this.weatherService.available()) {
      return {
        success: true,
        response: "I don't have access to weather data yet - set OPENWEATHER_API_KEY to enable this.",
        data: { placeholder: true }
      };
    }

    try {
      const transcript = context.originalTranscript || '';
      const locationMatch = transcript.match(/weather\s+(?:in|for|of)\s+(.+?)[.?!]?$/i);
      const location = locationMatch ? locationMatch[1].trim() : null;

      const weather = await this.weatherService.getCurrentWeather(location);

      return {
        success: true,
        response: `It's currently ${weather.tempF}°F and ${weather.description} in ${weather.location}, feels like ${weather.feelsLikeF}°F, with ${weather.humidity}% humidity.`,
        data: weather
      };
    } catch (error) {
      console.error('Weather lookup error:', error.message);
      return {
        success: false,
        response: "I couldn't get the weather right now. Try naming a specific city, like 'weather in Austin'.",
        data: null
      };
    }
  }

  /**
   * Get the next upcoming F1 race via the free Jolpica-F1 API (Ergast's successor)
   */
  async getF1Schedule(params, context) {
    if (!this.f1Service) {
      return {
        success: false,
        response: "I couldn't reach the F1 schedule right now. Try again in a moment.",
        data: null
      };
    }

    try {
      const race = await this.f1Service.getNextRace();
      if (!race) {
        return {
          success: true,
          response: "There's no upcoming race scheduled right now - the season may be over.",
          data: null
        };
      }

      return {
        success: true,
        response: `The next F1 race is the ${race.raceName} at ${race.circuit}, on ${race.dateFormatted}.`,
        data: race
      };
    } catch (error) {
      console.error('F1 schedule lookup error:', error.message);
      return {
        success: false,
        response: "I couldn't reach the F1 schedule right now. Try again in a moment.",
        data: null
      };
    }
  }

  /**
   * Show help
   */
  async showHelp(params, context) {
    const commandList = Object.values(this.commands)
      .map(cmd => `${cmd.name}: ${cmd.description}`)
      .join('. ');

    return {
      success: true,
      response: `Here's what I can do: ${commandList}. Just speak naturally and I'll understand!`,
      data: { commands: this.commands }
    };
  }

  /**
   * Greeting
   */
  async greeting(params, context) {
    const greetings = [
      "Hello! How can I help you today?",
      "Hi there! What can I do for you?",
      "Hey! I'm ready to assist you.",
      "Good to hear from you! What would you like to know?",
      "Hello! Ask me anything."
    ];

    const randomGreeting = greetings[Math.floor(Math.random() * greetings.length)];

    return {
      success: true,
      response: randomGreeting,
      data: { greeting: true }
    };
  }

  /**
   * Register a custom command
   * @param {string} commandId - Unique command identifier
   * @param {Object} config - Command configuration
   */
  registerCommand(commandId, config) {
    this.commands[commandId] = config;
  }

  /**
   * List all available commands
   * @returns {Object} - Commands registry
   */
  listCommands() {
    return this.commands;
  }
}

module.exports = VoiceCommandHandler;
