# Voice Assistant

AI-powered voice assistant with speech-to-text and text-to-speech capabilities using OpenAI's Whisper and TTS APIs.

## Features

### Phase 1: Core MVP ✅
- 🎤 **Voice Recording** - Browser-based audio capture with push-to-talk
- 🗣️ **Speech-to-Text** - OpenAI Whisper API for accurate transcription
- 🔊 **Text-to-Speech** - Natural voice responses with multiple voice options
- 💬 **Conversation Interface** - Chat-style UI showing dialogue history
- ⚡ **Real-time Processing** - Fast audio transcription and synthesis
- 🎨 **Modern UI** - Clean, responsive interface with visual feedback

### Phase 2: Voice Commands ✅ (Current)
- 🎯 **Pattern Matching** - Intelligent command recognition with fuzzy matching
- 🤖 **8 Built-in Commands** - Time, date, jokes, calculations, timers, weather, help, greetings
- 📝 **Parameterized Commands** - Extract values from voice input (e.g., "timer for 5 minutes")
- 🔄 **AI Fallback** - Seamless fallback to conversational AI for unrecognized commands
- 📋 **Extensible Registry** - Easy-to-add custom commands via JSON configuration
- 🎭 **Natural Language** - Understands variations and natural phrasing

### Upcoming Features
- **Phase 3**: Conversation context and memory
- **Phase 4**: Real-time streaming and audio visualization
- **Phase 5**: Local model integration (Whisper.cpp)

## Quick Start

### Prerequisites
- Node.js 16+ and npm
- OpenAI API key ([Get one here](https://platform.openai.com/api-keys))
- Modern web browser (Chrome, Firefox, Safari, or Edge)
- Microphone access

### Installation

1. **Install dependencies**
```bash
npm install
```

2. **Configure environment**
```bash
cp .env.example .env
```

Edit `.env` and add your OpenAI API key:
```bash
OPENAI_API_KEY=your_api_key_here
```

3. **Start the server**
```bash
npm start
```

For development with auto-reload:
```bash
npm run dev
```

4. **Open in browser**
```
http://localhost:3000
```

## Usage

1. **Allow Microphone Access** - Your browser will request permission on first use
2. **Push to Talk** - Click and hold the record button while speaking
3. **Release to Send** - Release the button to process your audio
4. **Listen to Response** - The assistant will respond with both text and voice
5. **Continue Conversation** - Speak again to continue the dialogue

### Settings
Click the ⚙️ icon to customize:
- **Voice**: Choose from 6 different voices (alloy, echo, fable, onyx, nova, shimmer)
- **Speed**: Adjust playback speed (0.75x - 1.5x)

### Voice Commands

The assistant recognizes these built-in commands (speak naturally - variations are understood):

**Utility Commands:**
- 🕐 "What time is it?" - Get current time
- 📅 "What's the date?" - Get current date
- 🧮 "Calculate 25 times 4" - Perform math calculations
- ⏲️ "Set a timer for 5 minutes" - Start countdown timer

**Information:**
- 🌤️ "What's the weather?" - Get weather info (placeholder - API integration needed)

**Entertainment:**
- 😄 "Tell me a joke" - Random joke

**System:**
- ❓ "Help" or "What can you do?" - List available commands
- 👋 "Hello" or "Hi" - Greeting response

**Natural Language Examples:**
- "What is 50 plus 32?"
- "Timer for 10 minutes"
- "Calculate 100 divided by 4"
- "Good morning"

If a command isn't recognized, the assistant falls back to conversational AI mode.

## Project Structure

```
08-voice-assistant/
├── server.js                    # Express server (main entry)
├── package.json                 # Dependencies
├── .env.example                 # Configuration template
├── README.md                    # Documentation
├── public/                      # Frontend assets
│   ├── index.html              # UI
│   ├── styles.css              # Styling
│   └── app.js                  # Frontend logic
├── src/                        # Backend modules
│   ├── OpenAIService.js        # OpenAI API wrapper
│   ├── AudioProcessor.js       # Audio coordination
│   └── VoiceCommandHandler.js  # Command recognition & execution
├── commands/                   # Voice commands
│   └── commands.json           # Command registry & patterns
└── data/                       # Persistent storage
    ├── conversations/          # Conversation history (Phase 3)
    └── audio-cache/            # Temporary audio files
```

## API Endpoints

### Health Check
```
GET /api/health
```
Returns server status and OpenAI connection status.

### Transcribe Audio
```
POST /api/transcribe
Body: FormData with 'audio' field (audio/webm)
Returns: { transcript, duration, confidence }
```

### Synthesize Speech
```
POST /api/synthesize
Body: { text, voice?, speed? }
Returns: Audio stream (audio/mpeg)
```

### Process Voice Command
```
POST /api/command
Body: { transcript }
Returns: { understood, commandRecognized, command, response, audio, audioFormat }
```
Processes transcribed text through command handler or AI fallback.

### Get Available Voices
```
GET /api/voices
Returns: { voices: [...] }
```

### Get Available Commands
```
GET /api/commands
Returns: { commands: [{ id, name, description, category, examples }] }
```
Lists all registered voice commands with examples.

## Configuration

Environment variables (`.env`):

```bash
# Server
PORT=3000
NODE_ENV=development

# OpenAI
OPENAI_API_KEY=your_key_here
WHISPER_MODEL=whisper-1
TTS_MODEL=tts-1
TTS_VOICE=alloy

# Audio
MAX_AUDIO_SIZE_MB=25
AUDIO_TEMP_DIR=./data/audio-cache
CLEANUP_INTERVAL_MS=3600000

# CORS
ALLOWED_ORIGINS=http://localhost:3000
```

## Browser Compatibility

- ✅ Chrome 60+
- ✅ Firefox 55+
- ✅ Safari 14+
- ✅ Edge 79+

**Requirements**:
- Web Audio API support
- MediaRecorder API support
- HTTPS (for production deployment)

## Technical Details

### Audio Processing
- **Input Format**: WebM (captured via MediaRecorder API)
- **Sample Rate**: 16kHz (optimized for speech)
- **Transcription**: OpenAI Whisper API
- **Output Format**: MP3 (from TTS API)

### Architecture
- **Backend**: Node.js + Express.js
- **Frontend**: Vanilla JavaScript (no frameworks)
- **Audio Handling**: Web Audio API + MediaRecorder
- **API Integration**: OpenAI Node.js SDK

## Troubleshooting

### Microphone Not Working
- Ensure microphone permission is granted in browser settings
- Check that your microphone is not being used by another application
- Try using HTTPS (required for production)

### API Errors
- Verify your OpenAI API key is correct
- Check your API key has sufficient credits
- Ensure you have access to Whisper and TTS models

### Audio Quality Issues
- Minimize background noise
- Speak clearly at normal pace
- Ensure stable internet connection
- Try different voices in settings

## Development

### Phase 1 Complete ✅
- [x] Project structure
- [x] OpenAI service integration
- [x] Audio recording and playback
- [x] Basic transcription and TTS
- [x] Web interface
- [x] Settings management

### Phase 2 Complete ✅
- [x] Command pattern matching with fuzzy logic
- [x] Intent recognition and parameter extraction
- [x] 8 custom command handlers
- [x] Command registry system (JSON)
- [x] AI fallback for unrecognized commands
- [x] GET /api/commands endpoint

### Phase 3: Conversation Memory
- [ ] Context tracking
- [ ] Multi-turn dialogue
- [ ] History persistence
- [ ] Session management

## Security Notes

- API keys are server-side only (never exposed to client)
- CORS configured for specific origins
- Audio file size limits enforced
- Temporary files automatically cleaned up
- Rate limiting on API endpoints

## Contributing

This is part of the [AI Experiments Hub](https://github.com/yourusername/ai-experiments-hub) repository.

## License

MIT

## Links

- [OpenAI Whisper API Documentation](https://platform.openai.com/docs/guides/speech-to-text)
- [OpenAI TTS API Documentation](https://platform.openai.com/docs/guides/text-to-speech)
- [MediaRecorder API](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder)
- [Web Audio API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API)

---

**Project 8** of AI Experiments Hub | Built with OpenAI APIs
