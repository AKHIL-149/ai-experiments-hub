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

### Phase 2: Voice Commands ✅
- 🎯 **Pattern Matching** - Intelligent command recognition with fuzzy matching
- 🤖 **8 Built-in Commands** - Time, date, jokes, calculations, timers, weather, help, greetings
- 📝 **Parameterized Commands** - Extract values from voice input (e.g., "timer for 5 minutes")
- 🔄 **AI Fallback** - Seamless fallback to conversational AI for unrecognized commands
- 📋 **Extensible Registry** - Easy-to-add custom commands via JSON configuration
- 🎭 **Natural Language** - Understands variations and natural phrasing

### Phase 3: Conversation Memory ✅
- 🧠 **Context Tracking** - Remembers conversation history across messages
- 💾 **Persistent Storage** - Conversations saved to disk and survive restarts
- 🔄 **Session Management** - Automatic conversation creation and management
- 📊 **Multi-turn Dialogue** - Maintains context for follow-up questions
- 🗂️ **Conversation API** - Full CRUD operations on conversations
- 🧹 **Automatic Cleanup** - Old conversations cleaned up periodically

### Phase 4: Enhanced UX ✅
- 📊 **Real-time Visualization** - Live audio frequency visualization using Web Audio API
- ⌨️ **Keyboard Shortcuts** - Spacebar for push-to-talk, Ctrl+H for conversation history
- 💬 **Conversation Manager** - Visual UI to browse, load, and delete conversations
- 📈 **Conversation Stats** - Track total conversations and message counts
- 🎯 **Active Indicators** - Visual feedback for current conversation
- 🔄 **Quick Switching** - Seamlessly switch between conversations

### Phase 5: Local Models ✅
- 🏠 **Local STT** - Offline speech-to-text with Whisper.cpp
- 🔊 **Local TTS** - Offline text-to-speech with espeak/piper/festival
- 🔀 **Hybrid Mode** - Smart fallback between local and cloud services
- 🎛️ **Mode Switching** - Runtime toggle between cloud, local, and hybrid modes
- 📊 **Service Status** - Real-time display of available services
- 💾 **No API Costs** - Run completely offline with local models

### Phase 6: Voice Activation Detection ✅ (Current)
- 🎙️ **Hands-free Mode** - Automatic recording without push-to-talk
- 🔊 **Voice Activity Detection** - Smart detection of speech vs silence
- 🎚️ **Adjustable Sensitivity** - Fine-tune detection threshold for your environment
- 👁️ **Visual Feedback** - Real-time visualization of voice activity levels
- ⚡ **Automatic Start/Stop** - Recording starts when you speak, stops after silence
- 🎨 **Mode Indicators** - Clear visual distinction between push-to-talk and hands-free

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
- 🧮 "Calculate 25 times 4" - Exact arithmetic: `+ - × ÷`, parentheses, "squared", "to the power of", "square root of", "15 percent of 200", "10 mod 3", number words ("five plus three"). Division by zero gets a plain answer, huge results are spoken as "1 times 10 to the 22". Anything that is not arithmetic ("what is Python 3") goes to the AI.
- ⏲️ "Set a timer for 5 minutes" - Countdown timer: "1 hour 30 minutes", "1.5 hours", "an hour", "half an hour", "five minutes", "remind me in 10 minutes to call mom" (up to 24 hours). The page sounds the alarm (message, beep and spoken alert) and keeps running timers across a reload.

**Information:**
- 🌤️ "What's the weather in Austin?" / "What is the weather like in Austin today?" - Real current conditions via OpenWeatherMap (with `OPENWEATHER_API_KEY`) or wttr.in (no key); uses `DEFAULT_WEATHER_LOCATION` if no city is named. Only current conditions exist: asking about "tomorrow" or a forecast gets the current weather with a note saying so.
- 🏎️ "When is the next F1 race?" - Next upcoming Formula 1 race via the free Jolpica-F1 API (no key required)

**General Questions:**
- Anything the local model doesn't know (news, schedules, current events) automatically escalates to a cloud web search (requires `OPENAI_API_KEY`, optionally `TAVILY_API_KEY`) instead of returning a "check the official site" non-answer. **In `local` mode nothing is ever sent to the cloud**, even if a key is configured.

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

**How a phrase is matched.** Punctuation, "what's"/"what is" and filler words ("please", "can you", "now", "today") are ignored, so "What time is it, please?" and "what's the time" both work. A command only answers when the request is really *for that command*: "tell me a joke about cats", "help me with my homework", "what time is it in Tokyo" and "funny cat videos" are open-ended, so they go to the AI instead of getting a random joke, the help list, or the local time. Fragments such as "it", "the" or "what" never trigger a command.

If a command isn't recognized, the assistant falls back to conversational AI mode.

## Phase 5: Local Model Setup

### Cloud Mode (Default)
Works out of the box with OpenAI API key. No additional setup required.

### Local Mode Setup

**1. Install Whisper.cpp (for STT)**

```bash
# Clone whisper.cpp
git clone https://github.com/ggerganov/whisper.cpp
cd whisper.cpp

# Build
make

# Download a model (base.en recommended for balance of speed/accuracy)
bash ./models/download-ggml-model.sh base.en

# Copy to your project
cp main /path/to/08-voice-assistant/whisper
cp models/ggml-base.en.bin /path/to/08-voice-assistant/models/
```

**Also needed: ffmpeg** (converts the browser's recording to the format Whisper reads): `brew install ffmpeg` / `apt-get install ffmpeg`. It is found on your `PATH`, or set `FFMPEG_PATH`.

**2. Install Local TTS**

**Option A: espeak (Recommended - lightweight)**
```bash
# Linux
sudo apt-get install espeak

# macOS
brew install espeak

# Test
espeak "Hello world"
```

**Option B: Piper (Better quality)**
```bash
# Download from https://github.com/rhasspy/piper/releases
wget https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_linux_x86_64.tar.gz
tar -xzf piper_linux_x86_64.tar.gz

# Download a voice model
wget https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx
```

**Option C: Festival**
```bash
# Linux
sudo apt-get install festival

# macOS
brew install festival
```

**3. Update .env**
```bash
SERVICE_MODE=local  # or 'hybrid' for automatic fallback
WHISPER_CPP_PATH=/path/to/whisper
WHISPER_MODEL_PATH=./models/ggml-base.en.bin
TTS_ENGINE=espeak
```

### Hybrid Mode (Recommended)
Best of both worlds - uses local models when available, falls back to cloud if needed:

```bash
SERVICE_MODE=hybrid
FALLBACK_TO_CLOUD=true
```

### Switching Modes at Runtime
Use the settings panel (⚙️) in the UI to switch between cloud, local, and hybrid modes without restarting the server. A mode that could not work is refused with the reason (HTTP 409): `cloud` needs `OPENAI_API_KEY`, `local` needs working local Whisper *and* text-to-speech. The voice list in the settings panel follows the active engine (espeak voices locally, OpenAI voices in the cloud), and the voice and speed you pick are used for every answer.

## Phase 6: Hands-free Mode

### Using Voice Activation Detection

**What is Hands-free Mode?**
Instead of holding a button to talk (push-to-talk), hands-free mode automatically detects when you start speaking and stops recording after you finish.

**How to Enable:**

1. **Open Settings** - Click the ⚙️ icon
2. **Enable Hands-free Mode** - Check the "Hands-free Mode" checkbox
3. **Adjust Sensitivity** - Use the slider to set detection threshold
   - Lower = more sensitive (picks up quieter sounds, may trigger on background noise)
   - Higher = less sensitive (requires louder speech, ignores background noise)
4. **Start Speaking** - Just talk naturally, recording starts automatically
5. **Stop Speaking** - Pause for 1 second, recording stops and processes

**Visual Feedback:**
- Button changes to purple gradient when hands-free is active
- Visualizer bars show real-time voice activity level
- Button text changes to "Speak Anytime"

**Sensitivity Tips:**
- **Quiet environment**: 20-40% sensitivity works well
- **Noisy environment**: 50-70% sensitivity to avoid false triggers
- **Very noisy**: Consider using push-to-talk mode instead

Hands-free always starts **off** after a page load (it needs the microphone, which the browser only grants on request). While the assistant is thinking or speaking, detected "speech" is ignored so it cannot answer its own voice.

**Troubleshooting:**
- **Not detecting speech**: Lower sensitivity
- **Triggering on background noise**: Raise sensitivity
- **Recording stops too early**: System detects 1 second of silence - speak continuously

## Project Structure

```
08-voice-assistant/
├── server.js                        # Express server (main entry)
├── package.json                     # Dependencies
├── .env.example                     # Configuration template
├── README.md                        # Documentation
├── public/                          # Frontend assets
│   ├── index.html                  # UI
│   ├── styles.css                  # Styling
│   ├── app.js                      # Main frontend logic
│   ├── voice-activation-detector.js # Voice activity detection (Phase 6)
│   └── conversation-manager-ui.js  # Conversation manager component
├── src/                            # Backend modules
│   ├── ServiceManager.js           # Service mode manager (Phase 5)
│   ├── OpenAIService.js            # OpenAI API wrapper
│   ├── LocalWhisperService.js      # Local Whisper.cpp wrapper (Phase 5)
│   ├── LocalTTSService.js          # Local TTS wrapper (Phase 5)
│   ├── AudioProcessor.js           # Audio coordination
│   ├── VoiceCommandHandler.js      # Command recognition & execution
│   └── ConversationManager.js      # Context & history management
├── commands/                       # Voice commands
│   └── commands.json               # Command registry & patterns
└── data/                           # Persistent storage
    ├── conversations/              # Conversation history
    └── audio-cache/                # Temporary audio files
```

## API Endpoints

### Errors and limits

Every error is JSON, `{ "error": "<message>" }`, with a meaningful status: `400` bad input (missing/blank/oversized fields, malformed JSON, malformed conversation id, unreadable audio), `404` unknown conversation or route, `409` a service mode that cannot work, `413` upload or body too large, `429` rate limit (`Retry-After` is set), `502` the cloud provider failed, `503` a local service is unavailable (the message says how to fix it), `500` anything unexpected (logged in full, reported generically). Limits: transcript 2000 characters, speech text 4096 characters, `speed` 0.25-4, audio `MAX_AUDIO_SIZE_MB`, and by default 60 requests per minute per client on `/api/command`, `/api/transcribe` and `/api/synthesize`.

### Health Check
```
GET /api/health
```
Returns server status and the state of every service.

### Transcribe Audio
```
POST /api/transcribe
Body: FormData with 'audio' field (webm, mp4, ogg, wav - anything ffmpeg reads), optional 'language' ("en", "auto", ...)
Returns: { transcript, duration, confidence, noSpeech }
```
Silence, background noise and non-speech sounds return `{ transcript: "", noSpeech: true }` (HTTP 200) rather than a made-up transcript - Whisper otherwise "hears" words like "you" in silence, or writes "(airplane engine roaring)".

### Synthesize Speech
```
POST /api/synthesize
Body: { text, voice?, speed? }   (speed is a multiplier: 1.0 normal, 0.25-4)
Returns: Audio stream (audio/wav from local engines, audio/mpeg from OpenAI - the Content-Type says which)
```

### Process Voice Command
```
POST /api/command
Body: { transcript, conversationId?, voice?, speed? }
Returns: { understood, commandRecognized, command, response, audio, audioFormat, audioError, timer, conversationId }
```
Processes transcribed text through command handler or AI fallback. Maintains conversation context if conversationId is provided (a well-formed id the server no longer has is recreated, so a chat survives cleanup). The exchange is saved only after it succeeds. If only the voice fails, you still get the text: `audio` is `null` and `audioError` says why. `timer` is set when a timer was started (`{ id, duration, endTime, label }`).

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

### Conversation Management

**Create Conversation**
```
POST /api/conversations
Body: { userId? }
Returns: { success, conversationId, createdAt }
```

Conversation ids look like `conv_<timestamp>_<8 hex>`; anything else is a `400` (ids are file names, so a malformed one could otherwise reach files outside `data/conversations`). Unknown (well-formed) ids are `404`. Conversations are created when the first message is sent, not when the page opens.

**Get Conversation History**
```
GET /api/conversations/:id
Query: ?limit=10
Returns: { success, conversation, messages }
```

**List All Conversations**
```
GET /api/conversations
Query: ?limit=50
Returns: { success, conversations }
```

**Delete Conversation**
```
DELETE /api/conversations/:id
Returns: { success, message }
```

**Clear Conversation Messages**
```
POST /api/conversations/:id/clear
Returns: { success, message }
```

**Get Conversation Statistics**
```
GET /api/conversations/stats
Returns: { success, stats }
```

### Service Mode
```
GET  /api/service/status
POST /api/service/mode      Body: { mode: "cloud" | "local" | "hybrid" }   (409 if that mode cannot work)
```

## Configuration

Environment variables (`.env`):

```bash
# Server
PORT=3000
HOST=127.0.0.1          # loopback only (default). Set 0.0.0.0 to expose it on your network - there is no login.
NODE_ENV=development

# OpenAI
OPENAI_API_KEY=your_key_here
WHISPER_MODEL=whisper-1
TTS_MODEL=tts-1
TTS_VOICE=alloy

# Web Search + Weather (real API integrations)
TAVILY_API_KEY=your_tavily_key
OPENWEATHER_API_KEY=your_openweathermap_key
DEFAULT_WEATHER_LOCATION=Houston,TX,US

# Audio
MAX_AUDIO_SIZE_MB=25
AUDIO_TEMP_DIR=./data/audio-cache
CLEANUP_INTERVAL_MS=3600000

# Rate limit (per client, on /api/command, /api/transcribe, /api/synthesize)
RATE_LIMIT_WINDOW_MS=60000
RATE_LIMIT_MAX_REQUESTS=60

# CORS - the page and API share an origin, so this is OFF unless you list origins
# (comma-separated; "*" allows any website to call your assistant - only do that on purpose)
ALLOWED_ORIGINS=

# Local tools
FFMPEG_PATH=ffmpeg      # converts recordings for Whisper
WHISPER_CONCURRENCY=2   # transcriptions run at once; more wait their turn
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
- **Input Format**: whatever the browser's MediaRecorder produces (WebM, or MP4 on Safari); ffmpeg converts it
- **Sample Rate**: 16kHz mono (optimized for speech)
- **Transcription**: OpenAI Whisper API, or local whisper.cpp
- **Silence**: a recording whose loudest sample is below -50 dB is "no speech" and never reaches Whisper
- **Output Format**: MP3 (OpenAI TTS) or WAV (local engines)

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

### "I didn't catch any speech"
- The recording was silent or only noise. Check the microphone input level, and hold the button while speaking.

### "ffmpeg is not installed" / "That recording could not be read as audio"
- Install ffmpeg (`brew install ffmpeg`) or set `FFMPEG_PATH`. The second message means the upload was not valid audio.

### Local mode won't switch / "Local mode needs ..."
- Open the settings panel's Service Status: local mode needs both Local Whisper and Local TTS to be available (model file present, `espeak` installed).

### Timers
- Timers are sounded by the open page. If you close the tab they do not ring; reopening it rings any that ran out meanwhile.

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

### Phase 3 Complete ✅
- [x] Context tracking with configurable window size
- [x] Multi-turn dialogue with conversation history
- [x] History persistence to disk (JSON files)
- [x] Session management and auto-creation
- [x] Conversation CRUD API endpoints
- [x] Automatic cleanup of old conversations
- [x] In-memory caching for active conversations

### Phase 4 Complete ✅
- [x] Real-time audio visualization with Web Audio API
- [x] Frequency-based visualizer bars
- [x] Keyboard shortcuts (Spacebar, Ctrl+H)
- [x] Conversation manager UI component
- [x] Conversation browsing and switching
- [x] Conversation statistics display
- [x] Delete and load conversation actions

### Phase 5 Complete ✅
- [x] Whisper.cpp integration
- [x] Local TTS engines (espeak, piper, festival)
- [x] ServiceManager for cloud/local/hybrid switching
- [x] Runtime mode toggle API
- [x] Service status display

### Phase 6 Complete ✅
- [x] Voice activation detection (VAD) using Web Audio API
- [x] Hands-free mode toggle
- [x] Adjustable sensitivity slider
- [x] Real-time volume visualization in hands-free mode
- [x] Automatic recording start/stop based on speech detection
- [x] Visual feedback for hands-free mode active state

## Testing

```bash
npm test        # Node's built-in test runner, no extra dependencies (~7 seconds)
```

The tests cover the command matcher, the arithmetic and duration parsers, conversation storage (including path-traversal attempts), every HTTP endpoint and status code, the ffmpeg/Whisper/espeak/festival wrappers (against fake executables, so failure paths are tested deterministically), the OpenAI tool-calling loop (SDK faked), and the page itself (the real `public/app.js` runs in a Node `vm` with a fake DOM, microphone and `fetch`: the press/release race, the Space key, timers, settings). They were checked by mutation: about 70 deliberate breakages of the source, each of which must make a test fail.

Not covered by automated tests: real OpenAI calls (they need a key), real microphone capture and the browser's autoplay rules, and hands-free voice detection (needs live audio).

## Security Notes

- API keys are server-side only (never exposed to client)
- The server listens on **127.0.0.1** by default and CORS is closed by default; there is no authentication, so only change `HOST`/`ALLOWED_ORIGINS` if you mean to
- Conversation ids are validated as ids before they are used as file names
- In `local` mode nothing leaves your machine, even with an OpenAI key set
- External programs (ffmpeg, whisper, espeak) are run with an argument list, never through a shell; text for espeak follows `--`; text for festival is escaped before it goes into a Scheme string
- Audio file size limits enforced; temporary files are uniquely named and removed
- Rate limiting on the endpoints that call paid services (see Configuration)
- Unexpected errors are logged in full and reported to the client generically (no paths or stack details)

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

**Project 8** of AI Experiments Hub | OpenAI APIs or fully local (whisper.cpp, espeak, Ollama)
