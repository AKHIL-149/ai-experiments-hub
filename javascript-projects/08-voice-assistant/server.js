const express = require('express');
const cors = require('cors');
const path = require('path');
const multer = require('multer');
require('dotenv').config();

const AudioProcessor = require('./src/AudioProcessor');
const VoiceCommandHandler = require('./src/VoiceCommandHandler');
const ConversationManager = require('./src/ConversationManager');
const ServiceManager = require('./src/ServiceManager');

const MAX_TRANSCRIPT_CHARS = 2000;
const MAX_TTS_CHARS = 4096;
const LANGUAGE_PATTERN = /^(auto|[a-z]{2,3})$/;

/**
 * An error that carries the HTTP status to answer with and a message that is safe to show.
 * Anything thrown without a `status` is treated as unexpected: it is logged in full but
 * the client only sees a generic message (no file paths or stack details).
 */
class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

/**
 * Ground the model in the real current date/time - it has no other way
 * to know this, and guessing at it produces confident wrong answers
 * ("what is today?" hallucinating a date) that no hedge-detection could
 * ever catch, since the model isn't hedging - it's just wrong.
 */
function buildDateTimeContext() {
  const now = new Date();
  return `Current date and time: ${now.toLocaleString('en-US', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
    hour: 'numeric', minute: '2-digit', timeZoneName: 'short'
  })}.`;
}

/**
 * Build the AI-fallback system prompt: date/time grounding plus an
 * explicit instruction not to state unconfirmed guesses as fact. Tool
 * access and grounding reduce *opportunities* to hallucinate, but don't
 * stop the model from confidently guessing when a tool doesn't cover the
 * question (or wasn't asked) - this instructs it to say so instead.
 * @param {boolean} hasTools - whether this call has live tool access (cloud path)
 */
function buildSystemPrompt(hasTools) {
  const honesty = hasTools
    ? "If you are not confident a fact is current and accurate (specific dates, schedules, prices, recent events, releases, etc.), use your tools to check rather than guessing. If your tools don't turn up the answer, say plainly that you don't have reliable current information on it - never state an unconfirmed guess as settled fact."
    : "You do not have internet access right now, so your knowledge of anything time-sensitive (recent events, schedules, prices, releases) may be outdated or wrong. If a question needs current information you can't be sure of, say plainly that you don't have up-to-date information on that, rather than guessing at specifics.";

  return `You are a helpful voice assistant. Provide concise, natural responses suitable for speech. Keep responses under 100 words. ${buildDateTimeContext()} ${honesty}`;
}

/**
 * A fixed-window limit on requests per client address. The endpoints that call paid
 * services (speech, language model) are the ones worth protecting.
 */
function rateLimiter(windowMs, max) {
  const clients = new Map();

  return (req, res, next) => {
    const now = Date.now();
    let entry = clients.get(req.ip);
    if (!entry || now >= entry.resetAt) {
      entry = { count: 0, resetAt: now + windowMs };
      clients.set(req.ip, entry);
    }
    entry.count++;

    if (clients.size > 1000) {
      for (const [client, other] of clients) {
        if (now >= other.resetAt) clients.delete(client); // forget finished windows
      }
    }

    if (entry.count > max) {
      res.set('Retry-After', String(Math.ceil((entry.resetAt - now) / 1000)));
      return next(new HttpError(429, 'Too many requests. Please slow down and try again shortly.'));
    }
    next();
  };
}

/**
 * Read a positive integer query parameter, clamped to [1, max]
 */
function positiveInt(value, fallback, max = 200) {
  const parsed = parseInt(value, 10);
  if (!Number.isInteger(parsed) || parsed < 1) return fallback;
  return Math.min(parsed, max);
}

/**
 * Validate the optional voice/speed settings sent by the client
 */
function readVoiceOptions(body) {
  const options = {};

  if (body.voice !== undefined && body.voice !== null && body.voice !== '') {
    if (typeof body.voice !== 'string' || body.voice.length > 32) {
      throw new HttpError(400, 'Voice must be a short string');
    }
    options.voice = body.voice;
  }

  if (body.speed !== undefined && body.speed !== null && body.speed !== '') {
    const speed = Number(body.speed);
    if (!Number.isFinite(speed) || speed < 0.25 || speed > 4) {
      throw new HttpError(400, 'Speed must be a number between 0.25 and 4');
    }
    options.speed = speed;
  }

  return options;
}

/**
 * Build the Express app. Dependencies can be injected (used by the tests); by default
 * everything is built from the environment.
 * @param {Object} deps - { serviceManager, audioProcessor, commandHandler, conversationManager }
 * @returns {Object} - { app, serviceManager, audioProcessor, commandHandler, conversationManager, stop }
 */
function createApp(deps = {}) {
  const app = express();

  // Configure multer for file uploads
  const upload = multer({
    storage: multer.memoryStorage(),
    limits: {
      fileSize: (parseInt(process.env.MAX_AUDIO_SIZE_MB) || 25) * 1024 * 1024
    }
  });

  // The page and the API are served from the same origin, so cross-origin access is off
  // unless ALLOWED_ORIGINS lists origins to allow ("*" allows any - only do that on purpose).
  const allowedOrigins = (process.env.ALLOWED_ORIGINS || '')
    .split(',').map(o => o.trim()).filter(Boolean);
  if (allowedOrigins.length > 0) {
    app.use(cors({ origin: allowedOrigins.includes('*') ? '*' : allowedOrigins }));
  }
  app.use(express.json());
  app.use(['/api/command', '/api/transcribe', '/api/synthesize'], rateLimiter(
    parseInt(process.env.RATE_LIMIT_WINDOW_MS) || 60000,
    parseInt(process.env.RATE_LIMIT_MAX_REQUESTS) || 60
  ));
  app.use(express.static(path.join(__dirname, 'public')));

  // Initialize services
  const serviceManager = deps.serviceManager || new ServiceManager({
    mode: process.env.SERVICE_MODE || 'cloud',
    fallbackToCloud: process.env.FALLBACK_TO_CLOUD !== 'false',

    // Cloud config
    openaiApiKey: process.env.OPENAI_API_KEY,
    whisperModel: process.env.WHISPER_MODEL || 'whisper-1',
    ttsModel: process.env.TTS_MODEL || 'tts-1',
    ttsVoice: process.env.TTS_VOICE || 'alloy',

    // Local Whisper config
    whisperPath: process.env.WHISPER_CPP_PATH || 'whisper',
    whisperModelPath: process.env.WHISPER_MODEL_PATH || './models/ggml-base.en.bin',
    whisperThreads: parseInt(process.env.WHISPER_THREADS) || 4,

    // Local TTS config
    ttsEngine: process.env.TTS_ENGINE || 'espeak',
    ttsSpeed: parseInt(process.env.TTS_SPEED) || 175,

    // Local LLM config
    llmBaseURL: process.env.LLM_BASE_URL || 'http://localhost:11434',
    llmModel: process.env.LLM_MODEL || 'llama3.2:3b',
    llmTimeout: parseInt(process.env.LLM_TIMEOUT) || 30000,

    // Web search + weather (real API integrations)
    tavilyApiKey: process.env.TAVILY_API_KEY,
    openWeatherApiKey: process.env.OPENWEATHER_API_KEY,
    defaultWeatherLocation: process.env.DEFAULT_WEATHER_LOCATION
  });

  const audioProcessor = deps.audioProcessor || new AudioProcessor(serviceManager, {
    tempDir: process.env.AUDIO_TEMP_DIR || path.join(__dirname, 'data/audio-cache'),
    maxAudioSizeMB: parseInt(process.env.MAX_AUDIO_SIZE_MB) || 25
  });

  const commandHandler = deps.commandHandler || new VoiceCommandHandler(
    path.join(__dirname, 'commands/commands.json'),
    {
      weatherService: serviceManager.weatherService,
      f1Service: serviceManager.f1Service
    }
  );

  const conversationManager = deps.conversationManager || new ConversationManager({
    storageDir: process.env.CONVERSATIONS_DIR || path.join(__dirname, 'data/conversations'),
    maxConversationLength: parseInt(process.env.MAX_CONVERSATION_LENGTH) || 50,
    contextWindow: parseInt(process.env.CONTEXT_WINDOW) || 10
  });

  /**
   * Read the conversation id from a request, or throw 400 if it is malformed
   */
  function readConversationId(value) {
    if (value === undefined || value === null || value === '') return null;
    if (!ConversationManager.isValidId(value)) {
      throw new HttpError(400, 'Invalid conversation id');
    }
    return value;
  }

  // Routes

  /**
   * Serve main page
   */
  app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'public/index.html'));
  });

  /**
   * Health check endpoint
   */
  app.get('/api/health', async (req, res) => {
    try {
      const serviceStatus = serviceManager.getStatus();
      const tempStats = audioProcessor.getTempDirStats();

      res.json({
        status: 'ok',
        mode: serviceStatus.mode,
        services: serviceStatus,
        timestamp: new Date().toISOString(),
        tempCache: tempStats
      });
    } catch (error) {
      console.error('Health check error:', error);
      res.status(500).json({
        status: 'error',
        error: 'Health check failed'
      });
    }
  });

  /**
   * Transcribe audio to text
   */
  app.post('/api/transcribe', upload.single('audio'), async (req, res, next) => {
    try {
      if (!req.file) {
        throw new HttpError(400, 'No audio file provided');
      }

      const language = req.body.language;
      if (language !== undefined && language !== '' &&
          (typeof language !== 'string' || !LANGUAGE_PATTERN.test(language))) {
        throw new HttpError(400, 'Language must be a short code such as "en", or "auto"');
      }

      console.log(`Transcribing audio (${(req.file.size / 1024).toFixed(2)} KB)...`);

      // Validate audio format
      const validation = audioProcessor.validateAudioFormat(req.file.buffer);
      if (!validation.valid) {
        throw new HttpError(400, validation.error);
      }

      // Process audio
      const result = await audioProcessor.processAudioInput(req.file.buffer, {
        language: language || undefined
      });

      if (result.noSpeech) {
        console.log('ℹ No speech detected in audio');
      } else {
        console.log(`✓ Transcribed: "${result.transcript.substring(0, 50)}..."`);
      }

      res.json({
        transcript: result.transcript,
        duration: result.duration,
        confidence: result.confidence,
        noSpeech: !!result.noSpeech
      });
    } catch (error) {
      next(error);
    }
  });

  /**
   * Synthesize speech from text
   */
  app.post('/api/synthesize', async (req, res, next) => {
    try {
      const { text } = req.body;

      if (typeof text !== 'string' || text.trim().length === 0) {
        throw new HttpError(400, 'Text is required');
      }
      if (text.length > MAX_TTS_CHARS) {
        throw new HttpError(400, `Text is too long (max ${MAX_TTS_CHARS} characters)`);
      }
      const options = readVoiceOptions(req.body);

      console.log(`Synthesizing speech: "${text.substring(0, 50)}..."`);

      // Generate audio
      const result = await audioProcessor.generateAudioResponse(text, {
        voice: options.voice || process.env.TTS_VOICE,
        speed: options.speed || 1.0
      });

      console.log(`✓ Generated audio (${(result.audioBuffer.length / 1024).toFixed(2)} KB)`);

      // Send audio as response, labelled with what it really is (mp3 from OpenAI, wav from local engines)
      res.set({
        'Content-Type': result.format === 'wav' ? 'audio/wav' : 'audio/mpeg',
        'Content-Length': result.audioBuffer.length
      });
      res.send(result.audioBuffer);
    } catch (error) {
      next(error);
    }
  });

  /**
   * Process voice command (combines command matching / AI fallback + TTS)
   */
  app.post('/api/command', async (req, res, next) => {
    try {
      const { transcript } = req.body;

      if (typeof transcript !== 'string' || transcript.trim().length === 0) {
        throw new HttpError(400, 'Transcript is required');
      }
      if (transcript.length > MAX_TRANSCRIPT_CHARS) {
        throw new HttpError(400, `Transcript is too long (max ${MAX_TRANSCRIPT_CHARS} characters)`);
      }
      const conversationId = readConversationId(req.body.conversationId);
      const voiceOptions = readVoiceOptions(req.body);

      console.log(`Processing command: "${transcript}"`);

      // Parse command using VoiceCommandHandler
      const parsedCommand = await commandHandler.parseCommand(transcript);

      let responseText;
      let commandRecognized = false;
      let timer = null;

      if (parsedCommand.command && parsedCommand.confidence >= 0.7) {
        // Execute recognized command
        console.log(`✓ Recognized command: ${parsedCommand.name} (${(parsedCommand.confidence * 100).toFixed(0)}% confidence)`);

        const result = await commandHandler.executeCommand(parsedCommand, {
          originalTranscript: transcript
        });

        // A command can decline a request it recognised but cannot answer
        // (e.g. "what is python 3" is not arithmetic) - that goes to the AI instead.
        if (!result.fallThrough) {
          responseText = result.response;
          commandRecognized = true;
          timer = (result.data && result.data.timer) || null;
          console.log(`✓ Command result: ${result.success ? 'Success' : 'Failed'}`);
        } else {
          console.log(`ℹ ${parsedCommand.name} declined the request, using AI fallback`);
        }
      }

      if (!commandRecognized) {
        // No command recognized - use AI chat with conversation context.
        // Current date/time is injected so the model never has to guess
        // at "what is today" style questions, and the prompt explicitly
        // asks it to admit uncertainty rather than guess at anything else
        // time-sensitive its tools (if any) don't cover.
        console.log('ℹ No command recognized, using AI fallback with context');

        // Local mode never sends anything to the cloud, even when a key is configured.
        // Also skip a cloud attempt when we already know we're offline - avoids paying
        // the timeout for a call that can only fail.
        const cloudAllowed = serviceManager.getMode() !== 'local' && serviceManager.isCloudAvailable();
        if (cloudAllowed && !serviceManager.isInternetAvailable()) {
          console.log('No internet connectivity detected, skipping cloud attempt');
        }
        const hasTools = cloudAllowed && serviceManager.isInternetAvailable();

        // History first, then this message (it is saved to the conversation only once
        // the whole exchange succeeds, so a failed request leaves no dangling message)
        const messages = [
          { role: 'system', content: buildSystemPrompt(hasTools) },
          ...(conversationId ? conversationManager.getContext(conversationId) : []),
          { role: 'user', content: transcript }
        ];

        // Prefer cloud + tools (web search, weather, F1) for every
        // fallback turn - a 3B local model can't reliably tell the
        // difference between something it actually knows and something
        // it's confidently making up, so hedge-detection alone can't
        // catch that. Falls back to the local LLM if cloud isn't
        // configured OR if the cloud call itself fails (bad/expired key,
        // network issue, etc.) - a broken cloud key should degrade the
        // answer, not break the whole response.
        if (hasTools) {
          try {
            console.log('Using cloud + tools for AI fallback');
            const toolResult = await serviceManager.generateResponseWithTools(messages);
            responseText = toolResult.response;
          } catch (cloudError) {
            console.warn('Cloud + tools failed, falling back to local LLM:', cloudError.message);
            const chatResult = await serviceManager.generateResponse(messages);
            responseText = chatResult.response;
          }
        } else {
          console.log('Using the local LLM for AI fallback (no live tool access)');
          const chatResult = await serviceManager.generateResponse(messages);
          responseText = chatResult.response;
        }
      }

      if (typeof responseText !== 'string' || responseText.trim().length === 0) {
        throw new HttpError(502, 'The assistant did not produce an answer. Please try again.');
      }

      console.log(`✓ Response: "${responseText.substring(0, 50)}..."`);

      // Save the exchange to the conversation
      if (conversationId) {
        conversationManager.addMessage(conversationId, 'user', transcript);
        conversationManager.addMessage(conversationId, 'assistant', responseText);
      }

      // Generate audio response. If only the voice fails, still return the text answer.
      let audio = null;
      let audioFormat = null;
      let audioError = null;
      try {
        const audioResult = await audioProcessor.generateAudioResponse(responseText, voiceOptions);
        audio = audioResult.audioBuffer.toString('base64');
        audioFormat = audioResult.format || 'mp3';
      } catch (ttsError) {
        console.error('Speech synthesis failed, returning text only:', ttsError.message);
        audioError = 'Voice output is unavailable right now';
      }

      // Return both text and audio
      res.json({
        understood: true,
        commandRecognized: commandRecognized,
        command: transcript,
        response: responseText,
        audio,
        audioFormat,
        audioError,
        timer,
        conversationId: conversationId
      });
    } catch (error) {
      next(error);
    }
  });

  /**
   * Get available TTS voices
   */
  app.get('/api/voices', (req, res) => {
    const voices = serviceManager.getAvailableVoices();
    res.json({ voices });
  });

  /**
   * Get available voice commands
   */
  app.get('/api/commands', (req, res) => {
    const commands = commandHandler.listCommands();

    // Format commands for frontend display
    const formattedCommands = Object.entries(commands).map(([id, cmd]) => ({
      id: id,
      name: cmd.name,
      description: cmd.description,
      category: cmd.category,
      examples: cmd.patterns.slice(0, 2) // Show first 2 patterns as examples
    }));

    res.json({ commands: formattedCommands });
  });

  /**
   * Create new conversation
   */
  app.post('/api/conversations', (req, res, next) => {
    try {
      const { userId } = req.body;
      if (userId !== undefined && typeof userId !== 'string') {
        throw new HttpError(400, 'userId must be a string');
      }
      const result = conversationManager.createConversation(userId);
      res.json({
        success: true,
        ...result
      });
    } catch (error) {
      next(error);
    }
  });

  /**
   * Get conversation statistics
   * (declared before '/api/conversations/:id' so that "stats" is not read as an id)
   */
  app.get('/api/conversations/stats', (req, res, next) => {
    try {
      const stats = conversationManager.getStats();
      res.json({
        success: true,
        stats: stats
      });
    } catch (error) {
      next(error);
    }
  });

  /**
   * List all conversations
   */
  app.get('/api/conversations', (req, res, next) => {
    try {
      const limit = positiveInt(req.query.limit, 50);
      const conversations = conversationManager.listConversations(limit);

      res.json({
        success: true,
        conversations: conversations
      });
    } catch (error) {
      next(error);
    }
  });

  /**
   * Get conversation history
   */
  app.get('/api/conversations/:id', (req, res, next) => {
    try {
      const conversationId = readConversationId(req.params.id);
      const limit = req.query.limit === undefined ? null : positiveInt(req.query.limit, null, 1000);

      const info = conversationManager.getConversationInfo(conversationId);

      if (!info) {
        throw new HttpError(404, 'Conversation not found');
      }

      res.json({
        success: true,
        conversation: info,
        messages: conversationManager.getHistory(conversationId, limit)
      });
    } catch (error) {
      next(error);
    }
  });

  /**
   * Delete conversation
   */
  app.delete('/api/conversations/:id', (req, res, next) => {
    try {
      const conversationId = readConversationId(req.params.id);
      const deleted = conversationManager.deleteConversation(conversationId);

      if (!deleted) {
        throw new HttpError(404, 'Conversation not found');
      }

      res.json({
        success: true,
        message: 'Conversation deleted'
      });
    } catch (error) {
      next(error);
    }
  });

  /**
   * Clear conversation messages
   */
  app.post('/api/conversations/:id/clear', (req, res, next) => {
    try {
      const conversationId = readConversationId(req.params.id);
      const cleared = conversationManager.clearMessages(conversationId);

      if (!cleared) {
        throw new HttpError(404, 'Conversation not found');
      }

      res.json({
        success: true,
        message: 'Conversation cleared'
      });
    } catch (error) {
      next(error);
    }
  });

  /**
   * Phase 5: Get service mode and status
   */
  app.get('/api/service/status', (req, res, next) => {
    try {
      const status = serviceManager.getStatus();
      res.json({
        success: true,
        ...status
      });
    } catch (error) {
      next(error);
    }
  });

  /**
   * Phase 5: Set service mode
   */
  app.post('/api/service/mode', (req, res, next) => {
    try {
      const { mode } = req.body;

      if (typeof mode !== 'string' || !['cloud', 'local', 'hybrid'].includes(mode)) {
        throw new HttpError(400, 'Invalid mode. Use: cloud, local, or hybrid');
      }

      // Refuse a mode that could not work, instead of accepting it and then failing every request
      const problem = serviceManager.modeProblem(mode);
      if (problem) {
        throw new HttpError(409, problem);
      }

      serviceManager.setMode(mode);

      res.json({
        success: true,
        mode: serviceManager.getMode(),
        status: serviceManager.getStatus()
      });
    } catch (error) {
      next(error);
    }
  });

  /**
   * Clean up old temp files
   */
  app.post('/api/cleanup', (req, res, next) => {
    try {
      const maxAgeMs = parseInt(req.body.maxAgeMs) || 3600000; // 1 hour default
      audioProcessor.cleanupOldFiles(maxAgeMs);
      const stats = audioProcessor.getTempDirStats();
      res.json({
        success: true,
        message: 'Cleanup completed',
        stats: stats
      });
    } catch (error) {
      next(error);
    }
  });

  // Periodic cleanup of temp files and conversations
  const cleanupTimer = setInterval(() => {
    const cleanupInterval = parseInt(process.env.CLEANUP_INTERVAL_MS) || 3600000;
    audioProcessor.cleanupOldFiles(cleanupInterval);
    conversationManager.cleanupOldConversations(7 * 24 * 60 * 60 * 1000); // 7 days
    conversationManager.unloadInactive(30 * 60 * 1000); // 30 minutes
  }, 3600000); // Run every hour
  cleanupTimer.unref();

  // Unknown API routes answer in JSON, like every other API response
  app.use('/api', (req, res) => {
    res.status(404).json({ error: 'Not found' });
  });

  // Error handling middleware: known problems get their real status and message;
  // anything unexpected is logged in full and reported generically.
  app.use((error, req, res, next) => {
    let status = error.status;
    let message = error.message;

    if (error.type === 'entity.parse.failed') {
      status = 400;
      message = 'Request body is not valid JSON';
    } else if (error.type === 'entity.too.large') {
      status = 413;
      message = 'Request body is too large';
    } else if (error.code === 'LIMIT_FILE_SIZE') {
      status = 413;
      message = `Audio file too large. Max size: ${parseInt(process.env.MAX_AUDIO_SIZE_MB) || 25}MB`;
    } else if (error.name === 'MulterError') {
      status = 400;
      message = 'The upload could not be read';
    } else if (!Number.isInteger(status) || status < 400 || status > 599) {
      console.error('Server error:', error);
      status = 500;
      message = 'Something went wrong on the server';
    }

    if (res.headersSent) {
      return next(error);
    }
    res.status(status).json({ error: message, understood: false });
  });

  return {
    app,
    serviceManager,
    audioProcessor,
    commandHandler,
    conversationManager,
    stop() {
      clearInterval(cleanupTimer);
    }
  };
}

/**
 * Start listening. Loopback only by default - set HOST=0.0.0.0 to expose it on the network.
 */
function start() {
  const PORT = process.env.PORT || 3000;
  const HOST = process.env.HOST || '127.0.0.1';

  let services;
  try {
    services = createApp();
    console.log('✓ Services initialized');
    console.log(`✓ Service mode: ${services.serviceManager.getMode()}`);
    console.log(`✓ Loaded ${Object.keys(services.commandHandler.listCommands()).length} voice commands`);
    console.log(`✓ Conversation manager ready`);
  } catch (error) {
    console.error('Failed to initialize services:', error.message);
    process.exit(1);
  }

  return services.app.listen(PORT, HOST, () => {
    console.log('\n🎤 Voice Assistant Server');
    console.log('═══════════════════════════════════════');
    console.log(`🌐 Web interface:  http://localhost:${PORT}`);
    console.log(`📊 Health check:   http://localhost:${PORT}/api/health`);
    console.log(`🔒 Listening on:   ${HOST}`);
    console.log(`🔑 OpenAI API:     ${process.env.OPENAI_API_KEY ? 'Configured' : 'NOT CONFIGURED'}`);
    console.log('═══════════════════════════════════════\n');

    if (!process.env.OPENAI_API_KEY) {
      console.warn('⚠️  Warning: OPENAI_API_KEY not set in environment variables');
      console.warn('   Create a .env file based on .env.example\n');
    }
  });
}

if (require.main === module) {
  start();
}

module.exports = { createApp, start, HttpError, buildSystemPrompt, rateLimiter };
