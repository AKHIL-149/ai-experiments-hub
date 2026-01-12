const express = require('express');
const cors = require('cors');
const path = require('path');
const multer = require('multer');
require('dotenv').config();

const OpenAIService = require('./src/OpenAIService');
const AudioProcessor = require('./src/AudioProcessor');
const VoiceCommandHandler = require('./src/VoiceCommandHandler');

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
let openAIService;
let audioProcessor;
let commandHandler;

try {
  openAIService = new OpenAIService(process.env.OPENAI_API_KEY, {
    whisperModel: process.env.WHISPER_MODEL || 'whisper-1',
    ttsModel: process.env.TTS_MODEL || 'tts-1',
    ttsVoice: process.env.TTS_VOICE || 'alloy'
  });

  audioProcessor = new AudioProcessor(openAIService, {
    tempDir: process.env.AUDIO_TEMP_DIR || './data/audio-cache',
    maxAudioSizeMB: parseInt(process.env.MAX_AUDIO_SIZE_MB) || 25
  });

  commandHandler = new VoiceCommandHandler(
    path.join(__dirname, 'commands/commands.json')
  );

  console.log('✓ Services initialized');
  console.log(`✓ Loaded ${Object.keys(commandHandler.listCommands()).length} voice commands`);
} catch (error) {
  console.error('Failed to initialize services:', error.message);
  process.exit(1);
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
    const openaiConnected = await openAIService.testConnection();
    const tempStats = audioProcessor.getTempDirStats();

    res.json({
      status: 'ok',
      openai: openaiConnected ? 'connected' : 'disconnected',
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
    const { transcript } = req.body;

    if (!transcript) {
      return res.status(400).json({
        error: 'Transcript is required'
      });
    }

    console.log(`Processing command: "${transcript}"`);

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
      // No command recognized - use AI chat as fallback
      console.log('ℹ No command recognized, using AI fallback');

      const messages = [
        {
          role: 'system',
          content: 'You are a helpful voice assistant. Provide concise, natural responses suitable for speech. Keep responses under 100 words.'
        },
        {
          role: 'user',
          content: transcript
        }
      ];

      const chatResult = await openAIService.generateResponse(messages);
      responseText = chatResult.response;
    }

    console.log(`✓ Response: "${responseText.substring(0, 50)}..."`);

    // Generate audio response
    const audioResult = await audioProcessor.generateAudioResponse(responseText);

    // Return both text and audio
    res.json({
      understood: true,
      commandRecognized: commandRecognized,
      command: transcript,
      response: responseText,
      audio: audioResult.audioBuffer.toString('base64'),
      audioFormat: 'mp3'
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
  const voices = openAIService.getAvailableVoices();
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

// Periodic cleanup of temp files
setInterval(() => {
  const cleanupInterval = parseInt(process.env.CLEANUP_INTERVAL_MS) || 3600000;
  audioProcessor.cleanupOldFiles(cleanupInterval);
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
