# Voice Assistant - Local Testing Guide

## 🚀 Quick Start

### 1. Configure Environment

Your `.env` file needs an OpenAI API key:

```bash
# Edit .env file
OPENAI_API_KEY=sk-your-actual-api-key-here
```

Get your API key from: https://platform.openai.com/api-keys

### 2. Install Dependencies (if needed)

```bash
cd javascript-projects/08-voice-assistant
npm install
```

### 3. Start the Server

```bash
npm start
# or for development with auto-reload:
npm run dev
```

You should see:
```
✓ Services initialized
✓ Service mode: cloud
✓ Loaded 8 voice commands
✓ Conversation manager ready

Server running on http://localhost:3000
```

### 4. Open in Browser

Navigate to: **http://localhost:3000**

---

## 🧪 Testing Checklist

### Phase 1: Basic Voice Recording (Cloud Mode)

**Test 1: Push-to-Talk Recording**
- ✅ Click and hold the "Push to Talk" button
- ✅ Speak: "Hello, how are you?"
- ✅ Release the button
- ✅ Verify transcription appears
- ✅ Verify audio response plays

**Test 2: Keyboard Shortcut**
- ✅ Press and hold **Spacebar**
- ✅ Speak: "What time is it?"
- ✅ Release Spacebar
- ✅ Verify recording stops and processes

**Test 3: Microphone Permission**
- ✅ First use should prompt for microphone access
- ✅ Grant permission
- ✅ Verify recording works

---

### Phase 2: Voice Commands

Test these built-in commands:

**Utility Commands:**
- ✅ "What time is it?" → Returns current time
- ✅ "What's the date today?" → Returns current date
- ✅ "Calculate 25 times 4" → Returns 100
- ✅ "Set a timer for 2 minutes" → Starts timer

**Information:**
- ✅ "What's the weather?" → Weather placeholder response

**Entertainment:**
- ✅ "Tell me a joke" → Returns random joke

**System:**
- ✅ "Help" or "What can you do?" → Lists available commands
- ✅ "Hello" or "Good morning" → Greeting response

**AI Fallback:**
- ✅ "Explain quantum computing" → Should use conversational AI (not recognized as command)

---

### Phase 3: Conversation Memory

**Test 1: Multi-turn Conversation**
- ✅ Say: "My name is John"
- ✅ Then say: "What's my name?"
- ✅ Assistant should remember: "Your name is John"

**Test 2: Context Window**
- ✅ Have a 5+ message conversation
- ✅ Verify context is maintained
- ✅ Check conversation persists after page reload

**Test 3: Conversation Management**
- ✅ Click the 💬 button (or press **Ctrl+H**)
- ✅ View conversation list
- ✅ Create new conversation
- ✅ Switch between conversations
- ✅ Delete a conversation
- ✅ View conversation statistics

---

### Phase 4: Enhanced UX

**Test 1: Audio Visualization**
- ✅ Start recording
- ✅ Verify visualizer bars animate with your voice
- ✅ Check different volume levels show different heights

**Test 2: Keyboard Shortcuts**
- ✅ **Spacebar** → Push-to-talk (hold and release)
- ✅ **Ctrl+H** (or **Cmd+H** on Mac) → Open conversation manager

**Test 3: Settings Panel**
- ✅ Click ⚙️ icon
- ✅ Change TTS voice (try different voices)
- ✅ Adjust playback speed (0.75x - 1.5x)
- ✅ Test each voice responds differently

---

### Phase 5: Local Models (Optional)

**Prerequisites:**
- Whisper.cpp installed
- espeak/piper/festival installed

**Test 1: Service Mode Switching**
- ✅ Open Settings → Service Mode
- ✅ Try switching modes (requires local models):
  - **Cloud** (default) - Uses OpenAI APIs
  - **Local** - Uses local Whisper + TTS
  - **Hybrid** - Local with cloud fallback

**Test 2: Service Status**
- ✅ Check service status indicators:
  - Cloud: ✓ Available / ✗ Unavailable
  - Local Whisper: Status
  - Local TTS: Status

---

### Phase 6: Hands-free Mode

**Test 1: Enable Hands-free**
- ✅ Open Settings
- ✅ Check "Hands-free Mode"
- ✅ Allow microphone access
- ✅ Verify button changes to purple gradient
- ✅ Verify button text changes to "Speak Anytime"

**Test 2: Voice Activation Detection**
- ✅ Just start speaking naturally
- ✅ Recording should start automatically
- ✅ Stop speaking for 1 second
- ✅ Recording should stop and process

**Test 3: Sensitivity Adjustment**
- ✅ Test default sensitivity (30%)
- ✅ Lower sensitivity (20%) → More sensitive
  - Should trigger on quieter sounds
- ✅ Raise sensitivity (60%) → Less sensitive
  - Should ignore background noise better

**Test 4: Visual Feedback**
- ✅ Verify visualizer shows real-time voice activity
- ✅ Check purple pulsing animation when active
- ✅ Verify smooth transitions between speaking/silence

**Test 5: Mode Switching**
- ✅ Disable hands-free mode
- ✅ Verify button returns to normal (blue)
- ✅ Verify button text returns to "Push to Talk"
- ✅ Verify push-to-talk works again

---

## 🐛 Common Issues & Solutions

### Issue 1: "Microphone access denied"
**Solution:**
- Chrome: chrome://settings/content/microphone
- Firefox: about:preferences#privacy → Permissions
- Grant permission and reload page

### Issue 2: "Server not responding"
**Solution:**
```bash
# Check if server is running
lsof -i :3000

# Restart server
npm start
```

### Issue 3: "OpenAI API error"
**Solution:**
- Verify API key in `.env` is correct
- Check API key has sufficient credits
- Ensure you have access to Whisper and TTS models

### Issue 4: Hands-free mode triggers on background noise
**Solution:**
- Increase sensitivity slider (40-70%)
- Move to quieter environment
- Use push-to-talk mode instead

### Issue 5: Hands-free mode not detecting speech
**Solution:**
- Lower sensitivity slider (10-30%)
- Speak louder or closer to microphone
- Check microphone input levels in system settings

### Issue 6: Recording stops too early in hands-free mode
**Solution:**
- Speak continuously without long pauses
- System waits 1 second of silence before stopping
- Use push-to-talk for better control

---

## 📊 Performance Testing

### Test API Response Times

Open browser console (F12) and run:

```javascript
// Test transcription speed
const start = Date.now();
// Record 5 seconds of audio
// Check console: "Processing time: XXXms"
```

**Expected response times:**
- Transcription: 1-3 seconds
- TTS generation: 1-2 seconds
- Total round-trip: 2-5 seconds

### Test Conversation Persistence

1. Have a conversation with 10+ messages
2. Close browser tab
3. Reopen http://localhost:3000
4. Click 💬 → Load conversation
5. Verify all messages are preserved

---

## 🔒 Security Testing

### Test 1: API Key Protection
- ✅ Open browser DevTools → Network tab
- ✅ Record audio and send request
- ✅ Verify API key is NOT visible in requests
- ✅ Check API key stays server-side only

### Test 2: CORS Configuration
- ✅ Verify only allowed origins can access API
- ✅ Test from different port (should be blocked)

### Test 3: Rate Limiting
- ✅ Send 60+ requests in 1 minute
- ✅ Verify rate limiting kicks in
- ✅ Check appropriate error message

---

## 📈 Load Testing

### Test Concurrent Conversations

```bash
# Install artillery (if needed)
npm install -g artillery

# Create test script: load-test.yml
artillery run load-test.yml
```

**Expected capacity:**
- Handle 10+ concurrent users
- No memory leaks over 1 hour
- Temp files cleaned up automatically

---

## ✅ Production Readiness Checklist

Before deploying:

- [ ] Environment variables configured
- [ ] HTTPS enabled (required for production microphone access)
- [ ] API rate limiting configured
- [ ] Error logging set up
- [ ] Conversation cleanup scheduled
- [ ] Audio cache cleanup scheduled
- [ ] CORS properly configured for production domain
- [ ] Security headers added
- [ ] Dependencies updated (npm audit)
- [ ] Browser compatibility tested

---

## 🎯 Feature Coverage

- ✅ **Phase 1**: Voice recording, STT, TTS
- ✅ **Phase 2**: 8 voice commands
- ✅ **Phase 3**: Conversation memory
- ✅ **Phase 4**: Audio visualization, keyboard shortcuts
- ✅ **Phase 5**: Local models (optional)
- ✅ **Phase 6**: Hands-free mode with VAD

**Total Features Implemented: 6/6 phases (100%)**

---

## 🆘 Getting Help

If you encounter issues:

1. Check browser console (F12) for errors
2. Check server logs in terminal
3. Review `.env` configuration
4. Verify microphone permissions
5. Test with different browsers
6. Check OpenAI API status

---

## 🎉 Happy Testing!

This project includes:
- **2 recording modes**: Push-to-talk + Hands-free
- **3 service modes**: Cloud, Local, Hybrid
- **8 voice commands** + AI fallback
- **Full conversation management**
- **Real-time audio visualization**
- **Persistent conversation history**

Enjoy testing your AI voice assistant! 🎤✨
