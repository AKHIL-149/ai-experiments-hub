/**
 * Voice Assistant - Frontend Application
 * Handles audio recording, transcription, and playback
 */

class VoiceAssistant {
    constructor() {
        // DOM elements
        this.recordBtn = document.getElementById('recordBtn');
        this.statusIndicator = document.getElementById('statusIndicator');
        this.statusText = this.statusIndicator.querySelector('.status-text');
        this.conversationBox = document.getElementById('conversationBox');
        this.audioVisualizer = document.getElementById('audioVisualizer');
        this.loadingOverlay = document.getElementById('loadingOverlay');
        this.loadingText = document.getElementById('loadingText');
        this.settingsBtn = document.getElementById('settingsBtn');
        this.settingsPanel = document.getElementById('settingsPanel');
        this.closeSettingsBtn = document.getElementById('closeSettingsBtn');
        this.voiceSelect = document.getElementById('voiceSelect');
        this.speedSelect = document.getElementById('speedSelect');
        this.serviceModeSelect = document.getElementById('serviceModeSelect');
        this.handsfreeToggle = document.getElementById('handsfreeToggle');
        this.sensitivitySlider = document.getElementById('sensitivitySlider');
        this.sensitivityValue = document.getElementById('sensitivityValue');

        // State
        this.isRecording = false;
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.audioStream = null;
        this.conversationId = null;
        this.wantRecording = false;   // the user is holding the button / key (may precede the mic being ready)
        this.isProcessing = false;    // transcribing, thinking or speaking
        this.isPlaying = false;
        this.timers = [];             // running timers: { id, endTime, label, handle }

        // Phase 4: Audio visualization
        this.audioContext = null;
        this.analyser = null;
        this.visualizerAnimationId = null;

        // Phase 4: Conversation manager
        this.conversationManager = null;

        // Phase 6: Voice Activation Detection
        this.vad = null;
        this.isHandsfreeMode = false;
        this.vadStream = null;

        // Settings
        this.settings = {
            voice: 'alloy',
            speed: 1.0,
            handsfree: false,
            vadSensitivity: 0.3
        };

        this.init();
    }

    /**
     * Initialize the application
     */
    async init() {
        // Check browser compatibility
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            this.showError('Your browser does not support audio recording. Please use a modern browser.');
            return;
        }

        // Set up event listeners
        this.setupEventListeners();

        // Phase 4: Initialize conversation manager UI
        if (window.ConversationManagerUI) {
            this.conversationManager = new ConversationManagerUI();
            this.setupConversationManagerListeners();
        }

        // Check server health
        await this.checkHealth();

        // Load saved settings. The conversation itself is created on the first message,
        // so just opening the page does not leave an empty conversation behind.
        await this.loadVoices();
        this.loadSettings();
        this.restoreTimers();

        // Clear placeholder
        this.clearPlaceholder();
    }

    /**
     * Set up event listeners
     */
    setupEventListeners() {
        // Recording button (mousedown/mouseup for push-to-talk)
        // Phase 6: Disable push-to-talk when in hands-free mode
        this.recordBtn.addEventListener('mousedown', () => {
            if (!this.isHandsfreeMode) this.startRecording();
        });
        // Releasing always counts, even if the microphone is still being opened
        this.recordBtn.addEventListener('mouseup', () => {
            if (!this.isHandsfreeMode) this.stopRecording();
        });
        this.recordBtn.addEventListener('mouseleave', () => {
            if (!this.isHandsfreeMode) this.stopRecording();
        });

        // Touch support for mobile
        this.recordBtn.addEventListener('touchstart', (e) => {
            e.preventDefault();
            if (!this.isHandsfreeMode) this.startRecording();
        });
        this.recordBtn.addEventListener('touchend', (e) => {
            e.preventDefault();
            if (!this.isHandsfreeMode) this.stopRecording();
        });

        // Phase 4: Conversations button
        const conversationsBtn = document.getElementById('conversationsBtn');
        if (conversationsBtn) {
            conversationsBtn.addEventListener('click', () => {
                if (this.conversationManager) {
                    this.conversationManager.toggle();
                }
            });
        }

        // Settings
        this.settingsBtn.addEventListener('click', () => this.openSettings());
        this.closeSettingsBtn.addEventListener('click', () => this.closeSettings());
        this.voiceSelect.addEventListener('change', (e) => {
            this.settings.voice = e.target.value;
            this.saveSettings();
        });
        this.speedSelect.addEventListener('change', (e) => {
            this.settings.speed = parseFloat(e.target.value);
            this.saveSettings();
        });

        // Phase 5: Service mode
        if (this.serviceModeSelect) {
            this.serviceModeSelect.addEventListener('change', (e) => {
                this.changeServiceMode(e.target.value);
            });
        }

        // Phase 6: Hands-free mode
        if (this.handsfreeToggle) {
            this.handsfreeToggle.addEventListener('change', (e) => {
                this.toggleHandsfreeMode(e.target.checked);
            });
        }

        // Phase 6: VAD sensitivity
        if (this.sensitivitySlider) {
            this.sensitivitySlider.addEventListener('input', (e) => {
                const sensitivity = parseFloat(e.target.value);
                this.settings.vadSensitivity = sensitivity;
                this.sensitivityValue.textContent = `${Math.round(sensitivity * 100)}%`;
                if (this.vad) {
                    this.vad.setSensitivity(sensitivity);
                }
                this.saveSettings();
            });
        }

        // Phase 4: Keyboard shortcuts
        document.addEventListener('keydown', (e) => this.handleKeyDown(e));
        document.addEventListener('keyup', (e) => this.handleKeyUp(e));
    }

    /**
     * Phase 4: Set up conversation manager listeners
     */
    setupConversationManagerListeners() {
        // Listen for conversation events
        window.addEventListener('conversationCreated', (e) => {
            this.conversationId = e.detail.conversationId;
            this.conversationBox.innerHTML = '';
            this.addMessage('assistant', 'New conversation started. How can I help you?');
        });

        window.addEventListener('conversationLoaded', (e) => {
            this.conversationId = e.detail.conversationId;
            this.conversationBox.innerHTML = '';

            // Display loaded messages
            e.detail.messages.forEach(msg => {
                this.addMessage(msg.role, msg.content);
            });
        });
    }

    /**
     * Phase 4: Handle keyboard shortcuts
     */
    handleKeyDown(e) {
        // Spacebar for push-to-talk - but not while a control has focus (Space operates
        // buttons, checkboxes and dropdowns) and not in hands-free mode
        if (e.code === 'Space' && !e.repeat && !this.isHandsfreeMode && !this.spaceBelongsToFocusedControl()) {
            e.preventDefault();
            if (this.isProcessing) {
                return; // Don't start recording while processing
            }
            this.keyHeld = true;
            this.startRecording();
        }

        // Ctrl/Cmd + H for conversation history
        if ((e.ctrlKey || e.metaKey) && e.key === 'h') {
            e.preventDefault();
            if (this.conversationManager) {
                this.conversationManager.toggle();
            }
        }
    }

    /**
     * Phase 4: Handle keyboard release
     */
    handleKeyUp(e) {
        // Phase 6: Don't stop recording on spacebar if in hands-free mode
        if (e.code === 'Space' && this.keyHeld && !this.isHandsfreeMode) {
            e.preventDefault();
            this.keyHeld = false;
            this.stopRecording();
        }
    }

    /**
     * Whether the focused element uses the Space key itself
     */
    spaceBelongsToFocusedControl() {
        const el = document.activeElement;
        if (!el || el === document.body) return false;
        return ['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON', 'A', 'SUMMARY'].includes(el.tagName) || el.isContentEditable;
    }

    /**
     * Check server health
     */
    async checkHealth() {
        try {
            const response = await fetch('/api/health');
            const data = await response.json();

            if (data.status === 'ok') {
                this.updateStatus('Ready', 'ready');
                // Phase 5: Update service status UI
                this.updateServiceStatus(data.services);
            } else {
                this.updateStatus('Server issue', 'error');
            }
        } catch (error) {
            console.error('Health check failed:', error);
            this.updateStatus('Disconnected', 'error');
        }
    }

    /**
     * Phase 5: Update service status display
     */
    updateServiceStatus(services) {
        if (!services) return;

        // Update cloud status
        const cloudBadge = document.getElementById('cloudStatus');
        if (cloudBadge) {
            if (services.cloud && services.cloud.available) {
                cloudBadge.textContent = '✓ Available';
                cloudBadge.className = 'status-badge status-ok';
            } else {
                cloudBadge.textContent = '✗ Unavailable';
                cloudBadge.className = 'status-badge status-error';
            }
        }

        // Update local Whisper status
        const whisperBadge = document.getElementById('localWhisperStatus');
        if (whisperBadge) {
            if (services.local && services.local.whisper && services.local.whisper.available) {
                whisperBadge.textContent = '✓ Available';
                whisperBadge.className = 'status-badge status-ok';
            } else {
                whisperBadge.textContent = '✗ Unavailable';
                whisperBadge.className = 'status-badge status-error';
            }
        }

        // Update local TTS status
        const ttsBadge = document.getElementById('localTTSStatus');
        if (ttsBadge) {
            if (services.local && services.local.tts && services.local.tts.available) {
                ttsBadge.textContent = '✓ Available';
                ttsBadge.className = 'status-badge status-ok';
            } else {
                ttsBadge.textContent = '✗ Unavailable';
                ttsBadge.className = 'status-badge status-error';
            }
        }

        // Update service mode selector
        if (this.serviceModeSelect && services.mode) {
            this.serviceModeSelect.value = services.mode;
        }
    }

    /**
     * Phase 5: Change service mode
     */
    async changeServiceMode(mode) {
        try {
            const response = await fetch('/api/service/mode', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ mode })
            });

            if (response.ok) {
                const data = await response.json();
                console.log(`✓ Service mode changed to: ${data.mode}`);
                this.updateServiceStatus(data.status);
                this.updateStatus(`Mode: ${mode}`, 'ready');
                setTimeout(() => this.updateStatus('Ready', 'ready'), 2000);
                await this.loadVoices(); // the voices on offer depend on the mode
            } else {
                throw new Error(await this.readError(response, 'Failed to change service mode'));
            }
        } catch (error) {
            console.error('Error changing service mode:', error);
            this.showError(error.message);
            await this.checkHealth(); // puts the selector back on the mode that is really active
        }
    }

    /**
     * Phase 6: Toggle hands-free mode
     */
    async toggleHandsfreeMode(enabled) {
        this.isHandsfreeMode = enabled;
        this.settings.handsfree = enabled;
        this.saveSettings();

        if (enabled) {
            try {
                // Request microphone access for VAD
                this.vadStream = await navigator.mediaDevices.getUserMedia({
                    audio: {
                        echoCancellation: true,
                        noiseSuppression: true,
                        sampleRate: 16000
                    }
                });

                // Initialize VAD
                if (!this.vad) {
                    this.vad = new VoiceActivationDetector({
                        sensitivity: this.settings.vadSensitivity,
                        minSpeechDuration: 300,
                        silenceDuration: 1000,
                        onSpeechStart: () => this.handleVADSpeechStart(),
                        onSpeechEnd: () => this.handleVADSpeechEnd(),
                        onVolumeChange: (volume) => this.handleVADVolumeChange(volume)
                    });
                }

                const initialized = await this.vad.initialize(this.vadStream);
                if (!initialized) {
                    throw new Error('Could not start listening for speech');
                }
                this.vad.start();

                // Update UI
                this.updateStatus('Hands-free active', 'ready');
                this.recordBtn.querySelector('.btn-text').textContent = 'Speak Anytime';
                this.recordBtn.classList.add('handsfree-mode');
                this.audioVisualizer.classList.add('active');

                console.log('✓ Hands-free mode enabled');
            } catch (error) {
                console.error('Failed to enable hands-free mode:', error);
                this.showError('Failed to enable hands-free mode: ' + error.message);
                this.handsfreeToggle.checked = false;
                this.isHandsfreeMode = false;
                this.settings.handsfree = false;
                this.saveSettings();
                if (this.vadStream) {
                    this.vadStream.getTracks().forEach(track => track.stop());
                    this.vadStream = null;
                }
            }
        } else {
            // Disable hands-free mode
            if (this.vad) {
                this.vad.stop();
            }

            if (this.vadStream) {
                this.vadStream.getTracks().forEach(track => track.stop());
                this.vadStream = null;
            }

            // Update UI
            this.updateStatus('Ready', 'ready');
            this.recordBtn.querySelector('.btn-text').textContent = 'Push to Talk';
            this.recordBtn.classList.remove('handsfree-mode');
            this.audioVisualizer.classList.remove('active');

            console.log('✓ Hands-free mode disabled');
        }
    }

    /**
     * Phase 6: Handle VAD speech start
     */
    handleVADSpeechStart() {
        // Ignore "speech" while the assistant is working or talking - its own voice coming
        // out of the speakers would otherwise be picked up and answered, forever
        if (this.isProcessing || this.isPlaying) return;
        console.log('VAD: Speech detected, starting recording');
        this.wantRecording = true;
        this.startRecording();
    }

    /**
     * Phase 6: Handle VAD speech end
     */
    handleVADSpeechEnd() {
        console.log('VAD: Speech ended, stopping recording');
        this.stopRecording();
    }

    /**
     * Phase 6: Handle VAD volume change (for visualization)
     */
    handleVADVolumeChange(volume) {
        if (!this.isHandsfreeMode || !this.audioVisualizer) return;

        // Update visualizer to show VAD volume
        const bars = this.audioVisualizer.querySelectorAll('.visualizer-bar');
        bars.forEach((bar, index) => {
            const multiplier = (index + 1) * 0.8;
            const height = Math.min(volume * multiplier * 100, 100);
            bar.style.height = `${height}%`;
        });
    }

    /**
     * Start recording audio
     */
    async startRecording() {
        this.wantRecording = true;
        if (this.isRecording || this.isStarting) return;
        this.isStarting = true;

        try {
            // Request microphone access
            this.audioStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    sampleRate: 16000
                }
            });

            // Create media recorder (Safari records mp4, not webm - use what the browser supports;
            // the server's ffmpeg reads either)
            const mimeType = ['audio/webm', 'audio/mp4', 'audio/ogg'].find(type => MediaRecorder.isTypeSupported(type));
            this.mediaRecorder = new MediaRecorder(this.audioStream, mimeType ? { mimeType } : undefined);
            this.recordingMimeType = this.mediaRecorder.mimeType || mimeType || 'audio/webm';

            this.audioChunks = [];

            // Collect audio data
            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                }
            };

            // Handle stop event
            this.mediaRecorder.onstop = () => {
                this.processRecording();
            };

            // Phase 4: Setup real-time audio visualization
            this.setupAudioVisualization(this.audioStream);

            // The button/key may already have been released while the microphone was being
            // opened - then there is nothing to record, and the microphone must not stay on
            if (!this.wantRecording) {
                this.stopAudioVisualization();
                this.audioStream.getTracks().forEach(track => track.stop());
                this.audioStream = null;
                this.mediaRecorder = null;
                return;
            }

            // Start recording
            this.mediaRecorder.start();
            this.isRecording = true;
            this.recordingStartTime = Date.now();

            // Update UI
            this.updateStatus('Listening...', 'recording');
            this.recordBtn.classList.add('recording');
            this.audioVisualizer.classList.add('active');

        } catch (error) {
            console.error('Failed to start recording:', error);
            if (error.name === 'NotAllowedError') {
                this.showError('Microphone access denied. Please allow microphone access in your browser settings.');
            } else {
                this.showError('Failed to access microphone: ' + error.message);
            }
        } finally {
            this.isStarting = false;
        }
    }

    /**
     * Stop recording audio
     */
    stopRecording() {
        this.wantRecording = false;
        if (!this.isRecording || !this.mediaRecorder) return;

        this.mediaRecorder.stop();
        this.isRecording = false;

        // Phase 4: Stop audio visualization
        this.stopAudioVisualization();

        // Stop audio stream
        if (this.audioStream) {
            this.audioStream.getTracks().forEach(track => track.stop());
            this.audioStream = null;
        }

        // Update UI
        this.recordBtn.classList.remove('recording');
        this.audioVisualizer.classList.remove('active');
    }

    /**
     * Phase 4: Setup real-time audio visualization
     */
    setupAudioVisualization(stream) {
        try {
            // Create audio context
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();

            // Create analyser node
            this.analyser = this.audioContext.createAnalyser();
            this.analyser.fftSize = 256;
            this.analyser.smoothingTimeConstant = 0.8;

            // Connect stream to analyser
            const source = this.audioContext.createMediaStreamSource(stream);
            source.connect(this.analyser);

            // Start visualization loop
            this.animateVisualizer();
        } catch (error) {
            console.error('Failed to setup audio visualization:', error);
        }
    }

    /**
     * Phase 4: Animate audio visualizer with real frequency data
     */
    animateVisualizer() {
        if (!this.isRecording || !this.analyser) return;

        const bufferLength = this.analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);
        this.analyser.getByteFrequencyData(dataArray);

        // Get visualizer bars
        const bars = this.audioVisualizer.querySelectorAll('.visualizer-bar');

        // Calculate average amplitude for each bar
        const barCount = bars.length;
        const samplesPerBar = Math.floor(bufferLength / barCount);

        for (let i = 0; i < barCount; i++) {
            let sum = 0;
            for (let j = 0; j < samplesPerBar; j++) {
                sum += dataArray[i * samplesPerBar + j];
            }
            const average = sum / samplesPerBar;

            // Map amplitude (0-255) to height (10-30px)
            const height = Math.max(10, Math.min(30, (average / 255) * 30));
            bars[i].style.height = `${height}px`;
        }

        // Continue animation
        this.visualizerAnimationId = requestAnimationFrame(() => this.animateVisualizer());
    }

    /**
     * Phase 4: Stop audio visualization
     */
    stopAudioVisualization() {
        if (this.visualizerAnimationId) {
            cancelAnimationFrame(this.visualizerAnimationId);
            this.visualizerAnimationId = null;
        }

        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }

        this.analyser = null;

        // Reset visualizer bars
        const bars = this.audioVisualizer.querySelectorAll('.visualizer-bar');
        bars.forEach(bar => {
            bar.style.height = '10px';
        });
    }

    /**
     * Process recorded audio
     */
    async processRecording() {
        if (this.audioChunks.length === 0) {
            this.updateStatus('No audio recorded', 'error');
            setTimeout(() => this.updateStatus('Ready', 'ready'), 2000);
            return;
        }

        // Create audio blob
        const audioBlob = new Blob(this.audioChunks, { type: this.recordingMimeType || 'audio/webm' });
        const recordingDuration = this.recordingStartTime ? Date.now() - this.recordingStartTime : null;
        console.log(`Audio recorded: ${(audioBlob.size / 1024).toFixed(2)} KB, ${recordingDuration}ms`);

        // A press-and-release shorter than this produces a WebM with no
        // real audio content (just container header) - ffmpeg can't
        // decode it, so catch it here with a friendly message instead of
        // sending it to the server.
        const MIN_RECORDING_DURATION_MS = 300;
        const MIN_RECORDING_SIZE_BYTES = 1024;
        if ((recordingDuration !== null && recordingDuration < MIN_RECORDING_DURATION_MS) ||
            audioBlob.size < MIN_RECORDING_SIZE_BYTES) {
            this.updateStatus('Recording too short', 'error');
            this.showError('Recording too short - hold the button and speak before releasing.');
            setTimeout(() => this.updateStatus('Ready', 'ready'), 2000);
            return;
        }

        // Show loading
        this.isProcessing = true;
        this.showLoading('Transcribing audio...');

        try {
            // Step 1: Transcribe audio
            const transcript = await this.transcribeAudio(audioBlob);

            if (!transcript || transcript.trim().length === 0) {
                this.hideLoading();
                this.updateStatus('No speech detected', 'error');
                this.showError("I didn't catch any speech. Try again a little closer to the microphone.");
                setTimeout(() => this.updateStatus('Ready', 'ready'), 2500);
                return;
            }

            // Add user message to conversation
            this.addMessage('user', transcript);

            // Step 2: Get response
            this.showLoading('Generating response...');
            const response = await this.getResponse(transcript);

            // Add assistant message to conversation
            this.addMessage('assistant', response.response);

            // A timer was set: this page will sound the alarm
            if (response.timer) {
                this.startTimer(response.timer);
            }

            // Step 3: Play audio response (text-only if the server could not make the voice)
            if (response.audio) {
                this.showLoading('Generating voice...');
                await this.playAudioResponse(response.audio, response.audioFormat);
            } else if (response.audioError) {
                this.addMessage('assistant', `(${response.audioError})`);
            }

            // Done
            this.hideLoading();
            this.updateStatus('Ready', 'ready');

        } catch (error) {
            console.error('Processing error:', error);
            this.hideLoading();
            this.updateStatus('Error', 'error');
            this.showError(error.message);
            setTimeout(() => this.updateStatus('Ready', 'ready'), 3000);
        } finally {
            this.isProcessing = false;
        }
    }

    /**
     * Transcribe audio to text
     */
    async transcribeAudio(audioBlob) {
        const formData = new FormData();
        formData.append('audio', audioBlob, 'recording.webm');

        const response = await fetch('/api/transcribe', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error(await this.readError(response, 'Transcription failed'));
        }

        const data = await response.json();
        return data.transcript;
    }

    /**
     * Create conversation session
     */
    async ensureConversation() {
        if (!this.conversationId) {
            await this.createConversation();
        }
    }

    async createConversation() {
        try {
            const response = await fetch('/api/conversations', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    userId: 'default'
                })
            });

            if (response.ok) {
                const data = await response.json();
                this.conversationId = data.conversationId;
                console.log('✓ Created conversation:', this.conversationId);

                // Phase 4: Notify conversation manager
                if (this.conversationManager) {
                    this.conversationManager.setCurrentConversation(this.conversationId);
                }
            }
        } catch (error) {
            console.error('Failed to create conversation:', error);
        }
    }

    /**
     * Get response from assistant
     */
    async getResponse(transcript) {
        await this.ensureConversation();

        const response = await fetch('/api/command', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                transcript: transcript,
                conversationId: this.conversationId || undefined,
                voice: this.settings.voice,
                speed: this.settings.speed
            })
        });

        if (!response.ok) {
            throw new Error(await this.readError(response, 'Failed to get response'));
        }

        return await response.json();
    }

    /**
     * Play audio response
     */
    async playAudioResponse(base64Audio, format = 'mp3') {
        const mimeTypes = { mp3: 'audio/mpeg', wav: 'audio/wav' };

        return new Promise((resolve, reject) => {
            try {
                // Convert base64 to blob
                const binaryString = atob(base64Audio);
                const bytes = new Uint8Array(binaryString.length);
                for (let i = 0; i < binaryString.length; i++) {
                    bytes[i] = binaryString.charCodeAt(i);
                }
                const audioBlob = new Blob([bytes], { type: mimeTypes[format] || 'audio/mpeg' });

                // Create audio element
                const audio = new Audio();
                audio.src = URL.createObjectURL(audioBlob);
                this.isPlaying = true;

                audio.onended = () => {
                    this.isPlaying = false;
                    URL.revokeObjectURL(audio.src);
                    resolve();
                };

                audio.onerror = (error) => {
                    this.isPlaying = false;
                    URL.revokeObjectURL(audio.src);
                    reject(new Error('Audio playback failed'));
                };

                // Play audio
                audio.play().catch((error) => {
                    this.isPlaying = false;
                    reject(error.name === 'NotAllowedError'
                        ? new Error('The browser blocked audio playback. Click the page once and try again.')
                        : error);
                });

            } catch (error) {
                this.isPlaying = false;
                reject(error);
            }
        });
    }

    /**
     * The message from a failed API response, whatever shape the body has
     */
    async readError(response, fallback) {
        try {
            const body = await response.json();
            return body.error || fallback;
        } catch (error) {
            return fallback;
        }
    }

    /**
     * Fill the voice list from the server - which voices exist depends on the service mode
     */
    async loadVoices() {
        try {
            const response = await fetch('/api/voices');
            const { voices } = await response.json();
            if (!Array.isArray(voices) || voices.length === 0) return;

            const previous = this.voiceSelect.value;
            this.voiceSelect.innerHTML = '';
            voices.forEach(voice => {
                const option = document.createElement('option');
                option.value = voice;
                option.textContent = voice.charAt(0).toUpperCase() + voice.slice(1);
                this.voiceSelect.appendChild(option);
            });

            const preferred = [this.settings.voice, previous].find(v => voices.includes(v)) || voices[0];
            this.voiceSelect.value = preferred;
            this.settings.voice = preferred;
        } catch (error) {
            console.error('Failed to load voices:', error);
        }
    }

    // ---------------------------------------------------------------- timers

    /**
     * Run a timer set by voice. It is kept in localStorage so it survives a reload.
     */
    startTimer(timer, { announce = true } = {}) {
        if (this.timers.some(t => t.id === timer.id)) return;

        const entry = { id: timer.id, endTime: timer.endTime, label: timer.label || null, handle: null };
        entry.handle = setTimeout(() => this.timerFinished(entry), Math.max(0, timer.endTime - Date.now()));
        this.timers.push(entry);
        this.saveTimers();
    }

    async timerFinished(entry) {
        this.timers = this.timers.filter(t => t.id !== entry.id);
        this.saveTimers();

        const text = entry.label ? `Time to ${entry.label}!` : "Time's up! Your timer has finished.";
        this.addMessage('assistant', `⏰ ${text}`);
        this.beep();

        // Say it out loud too (best effort)
        try {
            const response = await fetch('/api/synthesize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text, speed: this.settings.speed })
            });
            if (response.ok) {
                const blob = await response.blob();
                const audio = new Audio(URL.createObjectURL(blob));
                audio.onended = () => URL.revokeObjectURL(audio.src);
                await audio.play();
            }
        } catch (error) {
            console.error('Could not speak the timer alert:', error);
        }
    }

    /**
     * A short beep, so the alarm is heard even when speech is unavailable
     */
    beep() {
        try {
            const context = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = context.createOscillator();
            const gain = context.createGain();
            oscillator.frequency.value = 880;
            gain.gain.value = 0.15;
            oscillator.connect(gain);
            gain.connect(context.destination);
            oscillator.start();
            oscillator.stop(context.currentTime + 0.4);
            oscillator.onended = () => context.close();
        } catch (error) {
            console.error('Could not play the timer beep:', error);
        }
    }

    saveTimers() {
        try {
            localStorage.setItem('voiceAssistantTimers',
                JSON.stringify(this.timers.map(({ id, endTime, label }) => ({ id, endTime, label }))));
        } catch (error) {
            console.error('Failed to save timers:', error);
        }
    }

    /**
     * Pick up timers that were running when the page was closed or reloaded
     */
    restoreTimers() {
        try {
            const saved = JSON.parse(localStorage.getItem('voiceAssistantTimers') || '[]');
            if (!Array.isArray(saved)) return;
            saved.forEach(timer => {
                if (timer && typeof timer.id === 'string' && Number.isFinite(timer.endTime)) {
                    this.startTimer(timer);
                }
            });
        } catch (error) {
            console.error('Failed to restore timers:', error);
        }
    }

    /**
     * Add message to conversation
     */
    addMessage(role, content) {
        // Remove placeholder if exists
        this.clearPlaceholder();

        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;

        const roleDiv = document.createElement('div');
        roleDiv.className = 'message-role';
        roleDiv.textContent = role === 'user' ? 'You' : 'Assistant';

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.textContent = content;

        messageDiv.appendChild(roleDiv);
        messageDiv.appendChild(contentDiv);

        this.conversationBox.appendChild(messageDiv);

        // Scroll to bottom
        this.conversationBox.scrollTop = this.conversationBox.scrollHeight;
    }

    /**
     * Clear placeholder message
     */
    clearPlaceholder() {
        const placeholder = this.conversationBox.querySelector('.message-placeholder');
        if (placeholder) {
            placeholder.remove();
        }
    }

    /**
     * Update status indicator
     */
    updateStatus(text, state) {
        this.statusText.textContent = text;
        this.statusIndicator.className = 'status-indicator';
        if (state) {
            this.statusIndicator.classList.add(state);
        }
    }

    /**
     * Show loading overlay
     */
    showLoading(text) {
        this.loadingText.textContent = text;
        this.loadingOverlay.classList.remove('hidden');
    }

    /**
     * Hide loading overlay
     */
    hideLoading() {
        this.loadingOverlay.classList.add('hidden');
    }

    /**
     * Show error message
     */
    showError(message) {
        this.addMessage('assistant', `Error: ${message}`);
    }

    /**
     * Open settings panel
     */
    openSettings() {
        this.settingsPanel.classList.remove('hidden');
    }

    /**
     * Close settings panel
     */
    closeSettings() {
        this.settingsPanel.classList.add('hidden');
    }

    /**
     * Load settings from localStorage
     */
    loadSettings() {
        let saved = null;
        try {
            saved = localStorage.getItem('voiceAssistantSettings');
        } catch (error) {
            console.error('Failed to read settings:', error);
        }
        if (saved) {
            try {
                this.settings = { ...this.settings, ...JSON.parse(saved) };
                if ([...this.voiceSelect.options].some(o => o.value === this.settings.voice)) {
                    this.voiceSelect.value = this.settings.voice;
                } else {
                    this.settings.voice = this.voiceSelect.value;
                }
                this.speedSelect.value = this.settings.speed;

                // Hands-free needs the microphone, which the browser only grants on request
                // (and a prompt on page load would be unwelcome) - so it always starts off.
                this.settings.handsfree = false;
                if (this.handsfreeToggle) {
                    this.handsfreeToggle.checked = false;
                }
                if (this.sensitivitySlider && this.settings.vadSensitivity !== undefined) {
                    this.sensitivitySlider.value = this.settings.vadSensitivity;
                    this.sensitivityValue.textContent = `${Math.round(this.settings.vadSensitivity * 100)}%`;
                }
            } catch (error) {
                console.error('Failed to load settings:', error);
            }
        }
    }

    /**
     * Save settings to localStorage
     */
    saveSettings() {
        try {
            localStorage.setItem('voiceAssistantSettings', JSON.stringify(this.settings));
        } catch (error) {
            console.error('Failed to save settings:', error);
        }
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.voiceAssistant = new VoiceAssistant();
});
