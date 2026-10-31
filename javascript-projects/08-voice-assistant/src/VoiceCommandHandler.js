const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { solve, formatNumber } = require('./MathParser');
const { parseDuration, formatDuration, MAX_SECONDS } = require('./DurationParser');

// Words that say nothing about which command was meant. A fragment made only of these
// ("it", "the", "what") must never trigger a command.
const STOPWORDS = new Set([
  'what', 'is', 'it', 'the', 'a', 'an', 'me', 'tell', 'how', 'who', 'where', 'when', 'do', 'you',
  'can', 'i', 'to', 'of', 'in', 'on', 'at', 'for', 'and', 'now', 'there', 'this', 'that', 'so',
  'ok', 'okay', 'are', 'am', 'my', 'your', 'be', 's'
]);

// Words that may surround a command without changing what it means ("hello there",
// "what time is it please", "what is the date today")
const FILLER_AROUND = /^(?:(?:hey|ok|okay|um|uh|so|please|kindly|can you|could you|would you|will you|i want to know|i would like to know|do you know|let me know)\s+)+/;
const FILLER_TRAILING = /(?:\s+(?:please|now|right now|today|thanks|thank you|for me|currently))+$/;
const IGNORABLE_EXTRA = new Set(['a', 'an', 'the', 'there', 'is', 'it', 'again']);

const TIME_QUALIFIER = /\b(tomorrow|tonight|yesterday|weekend|next week|this week|monday|tuesday|wednesday|thursday|friday|saturday|sunday|forecast|later)\b/i;

/**
 * Lower-case a spoken/typed phrase and strip what speech recognition adds and a command
 * pattern does not care about: punctuation, "what's" vs "what is", extra spaces.
 * @param {string} text
 * @returns {string}
 */
function normalize(text) {
  return String(text)
    .toLowerCase()
    .replace(/[‘’]/g, "'")
    .replace(/\b(what|who|where|when|how|that|there|it|here|today)'s\b/g, (m, w) => (w === 'today' ? "today's" : `${w} is`))
    .replace(/[?!,;:"“”()]/g, ' ')
    .replace(/(?<!\d)\.|\.(?!\d)/g, ' ')                 // sentence periods, but not decimals
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * normalize() plus the filler words that can surround a command
 */
function clean(text) {
  let s = normalize(text);
  let previous;
  do {
    previous = s;
    s = s.replace(FILLER_AROUND, '').replace(FILLER_TRAILING, '').trim();
  } while (s !== previous);
  return s;
}

/**
 * Index of the first place `needle` appears as a run of whole words inside `haystack`, or -1
 */
function indexOfWords(haystack, needle) {
  if (needle.length === 0 || needle.length > haystack.length) return -1;
  for (let i = 0; i <= haystack.length - needle.length; i++) {
    if (needle.every((word, k) => haystack[i + k] === word)) return i;
  }
  return -1;
}

/**
 * Voice Command Handler - Pattern matching and command execution
 */
class VoiceCommandHandler {
  constructor(commandRegistryPath, options = {}) {
    this.commandRegistryPath = commandRegistryPath || path.join(__dirname, '../commands/commands.json');
    this.commands = this.loadCommands();
    this.timers = new Map(); // Active timers by id
    this.maxTimers = 50;
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
    const none = { command: null, handler: null, parameters: {}, confidence: 0 };
    if (typeof transcript !== 'string' || transcript.trim().length === 0) {
      return none;
    }

    const normalizedTranscript = normalize(transcript);
    if (normalizedTranscript.length === 0) {
      return none;
    }

    // Evaluate every command/pattern and keep the highest-confidence
    // match across all of them, rather than returning the first match
    // found in commands.json's key order.
    let bestMatch = null;

    for (const [commandId, commandConfig] of Object.entries(this.commands)) {
      for (const pattern of commandConfig.patterns) {
        const match = this.matchPattern(normalizedTranscript, pattern, commandConfig);
        if (!match.matched) continue;

        // "what is {expression}" (and similar) is broad enough to match almost any
        // "what is ___" question - only accept it as a calculation if the phrase really is
        // arithmetic ("what is python 3" and "what is the capital of france" are not).
        if (commandConfig.handler === 'calculate' && solve(normalizedTranscript).reason === 'not-math') {
          continue;
        }

        if (!bestMatch || match.confidence > bestMatch.match.confidence) {
          bestMatch = { commandId, commandConfig, match };
        }
      }
    }

    if (!bestMatch) {
      return none;
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
   * @param {Object} commandConfig - The command the pattern belongs to
   * @returns {Object} - { matched, parameters, confidence }
   */
  matchPattern(transcript, pattern, commandConfig = {}) {
    const normalizedPattern = normalize(pattern);

    // Exact match
    if (transcript === normalizedPattern) {
      return { matched: true, parameters: {}, confidence: 1.0 };
    }

    // Check if pattern contains parameters (e.g., {duration}, {expression})
    if (normalizedPattern.includes('{')) {
      return this.matchParameterizedPattern(transcript, normalizedPattern);
    }

    const noMatch = { matched: false, parameters: {}, confidence: 0 };
    const said = clean(transcript).split(' ').filter(Boolean);
    const wanted = clean(pattern).split(' ').filter(Boolean);
    if (said.length === 0 || wanted.length === 0) return noMatch;

    if (said.join(' ') === wanted.join(' ')) {
      return { matched: true, parameters: {}, confidence: 1.0 };
    }

    // The pattern appears as whole words inside what was said
    const at = indexOfWords(said, wanted);
    if (at !== -1) {
      if (commandConfig.anywhere) {
        // Commands that take free-form extras ("weather in Austin") match wherever the words are
        return { matched: true, parameters: {}, confidence: 0.8 };
      }
      // Otherwise only harmless extras may surround it. "tell me a joke about cats",
      // "help me with my homework" and "what time is it in tokyo" ask for something this
      // command cannot do, so they go to the AI instead of being answered wrongly.
      const extras = [...said.slice(0, at), ...said.slice(at + wanted.length)];
      if (extras.every(word => IGNORABLE_EXTRA.has(word))) {
        return { matched: true, parameters: {}, confidence: 0.9 };
      }
      return noMatch;
    }

    // Part of the pattern was said ("time" for "what time is it") - but only if something
    // meaningful was said, not just "it", "the" or "what"
    if (indexOfWords(wanted, said) !== -1 && said.some(word => !STOPWORDS.has(word))) {
      return { matched: true, parameters: {}, confidence: 0.8 };
    }

    // Word-level similarity for scattered words. Confidence scales with the actual overlap
    // ratio, and recall is required too so a short pattern cannot "find itself" inside an
    // unrelated longer sentence. Single-word patterns never get here.
    if (wanted.length >= 2 && !commandConfig.anywhere) {
      const matchedWords = wanted.filter(word => said.includes(word));
      const precision = matchedWords.length / wanted.length;
      const recall = matchedWords.length / said.length;
      if (precision >= 0.7 && recall >= 0.7) {
        return { matched: true, parameters: {}, confidence: Math.min(precision, 0.85) };
      }
    }

    return noMatch;
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
   * Calculate math expression. Arithmetic is evaluated exactly by MathParser; a question
   * that is not arithmetic is handed back (fallThrough) so the AI can answer it.
   */
  async calculate(params, context) {
    const outcome = solve(normalize(context.originalTranscript || ''));

    if (outcome.ok) {
      return {
        success: true,
        response: `The result is ${formatNumber(outcome.value)}.`,
        data: { expression: outcome.expression, result: outcome.value }
      };
    }

    if (outcome.reason === 'divide-by-zero') {
      return { success: true, response: "I can't divide by zero.", data: null };
    }
    if (outcome.reason === 'too-large') {
      return { success: true, response: 'That number is too large for me to work out.', data: null };
    }

    return { success: false, fallThrough: true, response: '', data: null };
  }

  /**
   * Set timer. The page is told about it (data.timer) and sounds the alarm when it ends;
   * the server only keeps a short list of the timers that are still running.
   */
  async setTimer(params, context) {
    const spoken = String(params.duration || '');
    const parsed = parseDuration(spoken);

    if (!parsed.ok) {
      const reasons = {
        'too-long': `I can only set timers up to ${MAX_SECONDS / 3600} hours.`,
        zero: "A timer needs to be longer than zero. Try 'set a timer for 5 minutes'."
      };
      return {
        success: false,
        response: reasons[parsed.reason] ||
          "I couldn't set that timer. Try saying something like 'set a timer for 5 minutes'.",
        data: null
      };
    }

    const now = Date.now();
    for (const [id, timer] of this.timers) {
      if (timer.endTime <= now) this.timers.delete(id); // finished - forget it
    }
    if (this.timers.size >= this.maxTimers) {
      return {
        success: false,
        response: 'You already have a lot of timers running. Let a few finish first.',
        data: null
      };
    }

    // "remind me in 5 minutes to call mom" -> label "call mom"
    const labelMatch = spoken.match(/\bto\s+(.+)$/i);
    const label = labelMatch ? labelMatch[1].trim().slice(0, 80) : null;

    const timer = {
      id: crypto.randomBytes(6).toString('hex'),
      duration: parsed.seconds,
      endTime: now + parsed.seconds * 1000,
      label
    };
    this.timers.set(timer.id, timer);

    const durationText = formatDuration(parsed.seconds);
    return {
      success: true,
      response: label
        ? `OK, I'll remind you to ${label} in ${durationText}.`
        : `Timer set for ${durationText}. I'll let you know when time is up!`,
      data: { timer }
    };
  }

  /**
   * Get current weather (OpenWeatherMap when configured, wttr.in otherwise)
   */
  async getWeather(params, context) {
    // Always available in practice - this only fires if the handler
    // was somehow constructed without a weather service at all.
    if (!this.weatherService) {
      return {
        success: true,
        response: "I don't have access to weather data right now.",
        data: { placeholder: true }
      };
    }

    try {
      const transcript = context.originalTranscript || '';
      const location = this.extractWeatherLocation(transcript);

      const weather = await this.weatherService.getCurrentWeather(location);

      // Only current conditions are available - say so rather than pass them off as a forecast
      const caveat = TIME_QUALIFIER.test(transcript) ? 'I can only check current conditions. ' : '';

      return {
        success: true,
        response: `${caveat}It's currently ${weather.tempF}°F and ${weather.description} in ${weather.location}, feels like ${weather.feelsLikeF}°F, with ${weather.humidity}% humidity.`,
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
   * The place named in a weather question, or null to use the default location:
   * "weather in Austin", "what is the weather like in Austin today", "forecast for Boston"
   * @param {string} transcript
   * @returns {string|null}
   */
  extractWeatherLocation(transcript) {
    const match = String(transcript).match(
      /\b(?:weather|forecast|conditions)(?:\s+(?:forecast|report|conditions?|like|looking))?\s+(?:out\s+)?(?:in|for|at|of|near)\s+(.+)$/i
    );
    if (!match) return null;

    let place = match[1].trim();
    let previous;
    do {
      previous = place;
      place = place
        .replace(/[?!.,\s]+$/, '')
        .replace(/\s+(?:today|right now|now|currently|tonight|tomorrow|this (?:morning|afternoon|evening)|please)$/i, '');
    } while (place !== previous);

    return place.length > 0 && place.length <= 80 ? place : null;
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
module.exports.normalize = normalize;
