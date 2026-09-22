const express = require('express');
const cors = require('cors');
const path = require('path');
const multer = require('multer');
require('dotenv').config();

const OpenAIService = require('./src/OpenAIService');
const AudioProcessor = require('./src/AudioProcessor');
const VoiceCommandHandler = require('./src/VoiceCommandHandler');
const ConversationManager = require('./src/ConversationManager');
const ServiceManager = require('./src/ServiceManager');

// Initialize Express app
const app = express();
const PORT = process.env.PORT || 3000;

// Configure multer for file uploads
const upload = multer({
  storage: multer.memoryStorage(),
  limits: {
    fileSize: (parseInt(process.env.MAX_AUDIO_SIZE_MB) || 25) * 1024 * 1024
  }
});

// Middleware
app.use(cors({
  origin: process.env.ALLOWED_ORIGINS?.split(',') || '*'
}));
app.use(express.json());
app.use(express.static('public'));

// Initialize services
let serviceManager;
let audioProcessor;
let commandHandler;
let conversationManager;

try {
  // Phase 5: Initialize ServiceManager for cloud/local/hybrid mode
  serviceManager = new ServiceManager({
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

    // Phase 5.5: Local LLM config
    llmBaseURL: process.env.LLM_BASE_URL || 'http://localhost:11434',
    llmModel: process.env.LLM_MODEL || 'llama3.2:3b',
    llmTimeout: parseInt(process.env.LLM_TIMEOUT) || 30000,

    // Web search + weather (real API integrations)
    tavilyApiKey: process.env.TAVILY_API_KEY,
    openWeatherApiKey: process.env.OPENWEATHER_API_KEY,
    defaultWeatherLocation: process.env.DEFAULT_WEATHER_LOCATION
  });

  audioProcessor = new AudioProcessor(serviceManager, {
    tempDir: process.env.AUDIO_TEMP_DIR || './data/audio-cache',
    maxAudioSizeMB: parseInt(process.env.MAX_AUDIO_SIZE_MB) || 25
  });

  // Phase 5.5: Pass LLM service to command handler
  commandHandler = new VoiceCommandHandler(
    path.join(__dirname, 'commands/commands.json'),
    {
      llmService: serviceManager.localLLMService,
      weatherService: serviceManager.weatherService,
      f1Service: serviceManager.f1Service
    }
  );

  conversationManager = new ConversationManager({
    storageDir: process.env.CONVERSATIONS_DIR || './data/conversations',
    maxConversationLength: parseInt(process.env.MAX_CONVERSATION_LENGTH) || 50,
    contextWindow: parseInt(process.env.CONTEXT_WINDOW) || 10
  });

  console.log('✓ Services initialized');
  console.log(`✓ Service mode: ${serviceManager.getMode()}`);
  console.log(`✓ Loaded ${Object.keys(commandHandler.listCommands()).length} voice commands`);
  console.log(`✓ Conversation manager ready`);
} catch (error) {
  console.error('Failed to initialize services:', error.message);
  process.exit(1);
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
    res.status(500).json({
      status: 'error',
      error: error.message
    });
  }
});

/**
 * Transcribe audio to text
 */
app.post('/api/transcribe', upload.single('audio'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({
        error: 'No audio file provided'
      });
    }

    console.log(`Transcribing audio (${(req.file.size / 1024).toFixed(2)} KB)...`);

    // Validate audio format
    const validation = audioProcessor.validateAudioFormat(req.file.buffer);
    if (!validation.valid) {
      return res.status(400).json({
        error: validation.error
      });
    }

    // Process audio
    const result = await audioProcessor.processAudioInput(req.file.buffer, {
      language: req.body.language
    });

    console.log(`✓ Transcribed: "${result.transcript.substring(0, 50)}..."`);

    res.json({
      transcript: result.transcript,
      duration: result.duration,
      confidence: result.confidence
    });
  } catch (error) {
    console.error('Transcription error:', error.message);
    res.status(500).json({
      error: error.message
    });
  }
});

/**
 * Synthesize speech from text
 */
app.post('/api/synthesize', async (req, res) => {
  try {
    const { text, voice, speed } = req.body;

    if (!text) {
      return res.status(400).json({
        error: 'Text is required'
      });
    }

    console.log(`Synthesizing speech: "${text.substring(0, 50)}..."`);

    // Generate audio
    const result = await audioProcessor.generateAudioResponse(text, {
      voice: voice || process.env.TTS_VOICE,
      speed: speed || 1.0
    });

    console.log(`✓ Generated audio (${(result.audioBuffer.length / 1024).toFixed(2)} KB)`);

    // Send audio as response
    res.set({
      'Content-Type': 'audio/mpeg',
      'Content-Length': result.audioBuffer.length
    });
    res.send(result.audioBuffer);
  } catch (error) {
    console.error('TTS error:', error.message);
    res.status(500).json({
      error: error.message
    });
  }
});

/**
 * Process voice command (combines transcribe + command + TTS)
 */
app.post('/api/command', async (req, res) => {
  try {
    const { transcript, conversationId } = req.body;

    if (!transcript) {
      return res.status(400).json({
        error: 'Transcript is required'
      });
    }

    console.log(`Processing command: "${transcript}"`);

    // Add user message to conversation
    if (conversationId) {
      conversationManager.addMessage(conversationId, 'user', transcript);
    }

    // Parse command using VoiceCommandHandler
    const parsedCommand = await commandHandler.parseCommand(transcript);

    let responseText;
    let commandRecognized = false;

    if (parsedCommand.command && parsedCommand.confidence >= 0.7) {
      // Execute recognized command
      console.log(`✓ Recognized command: ${parsedCommand.name} (${(parsedCommand.confidence * 100).toFixed(0)}% confidence)`);

      const result = await commandHandler.executeCommand(parsedCommand, {
        originalTranscript: transcript
      });

      responseText = result.response;
      commandRecognized = true;

      console.log(`✓ Command result: ${result.success ? 'Success' : 'Failed'}`);
    } else {
      // No command recognized - use AI chat with conversation context.
      // Current date/time is injected so the model never has to guess
      // at "what is today" style questions, and the prompt explicitly
      // asks it to admit uncertainty rather than guess at anything else
      // time-sensitive its tools (if any) don't cover.
      console.log('ℹ No command recognized, using AI fallback with context');

      const hasTools = serviceManager.isCloudAvailable();
      const messages = [
        {
          role: 'system',
          content: buildSystemPrompt(hasTools)
        }
      ];

      // Add conversation context if available
      if (conversationId) {
        const context = conversationManager.getContext(conversationId);
        messages.push(...context);
      } else {
        // No context, just add current message
        messages.push({
          role: 'user',
          content: transcript
        });
      }

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
        console.log('Cloud not configured, using local LLM for AI fallback (no live tool access)');
        const chatResult = await serviceManager.generateResponse(messages);
        responseText = chatResult.response;
      }
    }

    console.log(`✓ Response: "${responseText.substring(0, 50)}..."`);

    // Add assistant response to conversation
    if (conversationId) {
      conversationManager.addMessage(conversationId, 'assistant', responseText);
    }

    // Generate audio response
    const audioResult = await audioProcessor.generateAudioResponse(responseText);

    // Return both text and audio
    res.json({
      understood: true,
      commandRecognized: commandRecognized,
      command: transcript,
      response: responseText,
      audio: audioResult.audioBuffer.toString('base64'),
      audioFormat: 'mp3',
      conversationId: conversationId
    });
  } catch (error) {
    console.error('Command processing error:', error.message);
    res.status(500).json({
      error: error.message,
      understood: false
    });
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
app.post('/api/conversations', (req, res) => {
  try {
    const { userId } = req.body;
    const result = conversationManager.createConversation(userId);
    res.json({
      success: true,
      ...result
    });
  } catch (error) {
    res.status(500).json({
      error: error.message
    });
  }
});

/**
 * Get conversation history
 */
app.get('/api/conversations/:id', (req, res) => {
  try {
    const conversationId = req.params.id;
    const limit = parseInt(req.query.limit) || null;

    const history = conversationManager.getHistory(conversationId, limit);
    const info = conversationManager.getConversationInfo(conversationId);

    if (!info) {
      return res.status(404).json({
        error: 'Conversation not found'
      });
    }

    res.json({
      success: true,
      conversation: info,
      messages: history
    });
  } catch (error) {
    res.status(500).json({
      error: error.message
    });
  }
});

/**
 * List all conversations
 */
app.get('/api/conversations', (req, res) => {
  try {
    const limit = parseInt(req.query.limit) || 50;
    const conversations = conversationManager.listConversations(limit);

    res.json({
      success: true,
      conversations: conversations
    });
  } catch (error) {
    res.status(500).json({
      error: error.message
    });
  }
});

/**
 * Delete conversation
 */
app.delete('/api/conversations/:id', (req, res) => {
  try {
    const conversationId = req.params.id;
    const deleted = conversationManager.deleteConversation(conversationId);

    if (deleted) {
      res.json({
        success: true,
        message: 'Conversation deleted'
      });
    } else {
      res.status(404).json({
        error: 'Conversation not found'
      });
    }
  } catch (error) {
    res.status(500).json({
      error: error.message
    });
  }
});

/**
 * Clear conversation messages
 */
app.post('/api/conversations/:id/clear', (req, res) => {
  try {
    const conversationId = req.params.id;
    const cleared = conversationManager.clearMessages(conversationId);

    if (cleared) {
      res.json({
        success: true,
        message: 'Conversation cleared'
      });
    } else {
      res.status(404).json({
        error: 'Conversation not found'
      });
    }
  } catch (error) {
    res.status(500).json({
      error: error.message
    });
  }
});

/**
 * Get conversation statistics
 */
app.get('/api/conversations/stats', (req, res) => {
  try {
    const stats = conversationManager.getStats();
    res.json({
      success: true,
      stats: stats
    });
  } catch (error) {
    res.status(500).json({
      error: error.message
    });
  }
});

/**
 * Phase 5: Get service mode and status
 */
app.get('/api/service/status', (req, res) => {
  try {
    const status = serviceManager.getStatus();
    res.json({
      success: true,
      ...status
    });
  } catch (error) {
    res.status(500).json({
      error: error.message
    });
  }
});

/**
 * Phase 5: Set service mode
 */
app.post('/api/service/mode', (req, res) => {
  try {
    const { mode } = req.body;

    if (!mode || !['cloud', 'local', 'hybrid'].includes(mode)) {
      return res.status(400).json({
        error: 'Invalid mode. Use: cloud, local, or hybrid'
      });
    }

    serviceManager.setMode(mode);

    res.json({
      success: true,
      mode: serviceManager.getMode(),
      status: serviceManager.getStatus()
    });
  } catch (error) {
    res.status(500).json({
      error: error.message
    });
  }
});

/**
 * Clean up old temp files
 */
app.post('/api/cleanup', (req, res) => {
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
    res.status(500).json({
      error: error.message
    });
  }
});

// Periodic cleanup of temp files and conversations
setInterval(() => {
  const cleanupInterval = parseInt(process.env.CLEANUP_INTERVAL_MS) || 3600000;
  audioProcessor.cleanupOldFiles(cleanupInterval);
  conversationManager.cleanupOldConversations(7 * 24 * 60 * 60 * 1000); // 7 days
  conversationManager.unloadInactive(30 * 60 * 1000); // 30 minutes
}, 3600000); // Run every hour

// Error handling middleware
app.use((error, req, res, next) => {
  console.error('Server error:', error);
  res.status(500).json({
    error: 'Internal server error',
    message: error.message
  });
});

// Start server
app.listen(PORT, () => {
  console.log('\n🎤 Voice Assistant Server');
  console.log('═══════════════════════════════════════');
  console.log(`🌐 Web interface:  http://localhost:${PORT}`);
  console.log(`📊 Health check:   http://localhost:${PORT}/api/health`);
  console.log(`🔑 OpenAI API:     ${process.env.OPENAI_API_KEY ? 'Configured' : 'NOT CONFIGURED'}`);
  console.log('═══════════════════════════════════════\n');

  if (!process.env.OPENAI_API_KEY) {
    console.warn('⚠️  Warning: OPENAI_API_KEY not set in environment variables');
    console.warn('   Create a .env file based on .env.example\n');
  }
});

module.exports = app;
