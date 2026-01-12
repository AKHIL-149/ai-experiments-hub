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

        // State
        this.isRecording = false;
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.audioStream = null;
        this.conversationId = null;

        // Phase 4: Audio visualization
        this.audioContext = null;
        this.analyser = null;
        this.visualizerAnimationId = null;

        // Phase 4: Conversation manager
        this.conversationManager = null;

        // Settings
        this.settings = {
            voice: 'alloy',
            speed: 1.0
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

        // Create conversation session
        await this.createConversation();

        // Load saved settings
        this.loadSettings();

        // Clear placeholder
        this.clearPlaceholder();
    }

    /**
     * Set up event listeners
     */
    setupEventListeners() {
        // Recording button (mousedown/mouseup for push-to-talk)
        this.recordBtn.addEventListener('mousedown', () => this.startRecording());
        this.recordBtn.addEventListener('mouseup', () => this.stopRecording());
        this.recordBtn.addEventListener('mouseleave', () => {
            if (this.isRecording) this.stopRecording();
        });

        // Touch support for mobile
        this.recordBtn.addEventListener('touchstart', (e) => {
            e.preventDefault();
            this.startRecording();
        });
        this.recordBtn.addEventListener('touchend', (e) => {
            e.preventDefault();
            this.stopRecording();
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
        // Spacebar for push-to-talk (when not in input field)
        if (e.code === 'Space' && !e.repeat && document.activeElement.tagName !== 'INPUT') {
            e.preventDefault();
            if (!this.isRecording && !this.loadingOverlay.classList.contains('hidden')) {
                return; // Don't start recording while processing
            }
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
        if (e.code === 'Space' && this.isRecording) {
            e.preventDefault();
            this.stopRecording();
        }
    }

    /**
     * Check server health
     */
    async checkHealth() {
        try {
            const response = await fetch('/api/health');
            const data = await response.json();

            if (data.status === 'ok' && data.openai === 'connected') {
                this.updateStatus('Ready', 'ready');
            } else {
                this.updateStatus('Server issue', 'error');
            }
        } catch (error) {
            console.error('Health check failed:', error);
            this.updateStatus('Disconnected', 'error');
        }
    }

    /**
     * Start recording audio
     */
    async startRecording() {
        if (this.isRecording) return;

        try {
            // Request microphone access
            this.audioStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    sampleRate: 16000
                }
            });

            // Create media recorder
            this.mediaRecorder = new MediaRecorder(this.audioStream, {
                mimeType: 'audio/webm'
            });

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

            // Start recording
            this.mediaRecorder.start();
            this.isRecording = true;

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
        }
    }

    /**
     * Stop recording audio
     */
    stopRecording() {
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
        const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
        console.log(`Audio recorded: ${(audioBlob.size / 1024).toFixed(2)} KB`);

        // Show loading
        this.showLoading('Transcribing audio...');

        try {
            // Step 1: Transcribe audio
            const transcript = await this.transcribeAudio(audioBlob);

            if (!transcript || transcript.trim().length === 0) {
                throw new Error('No speech detected');
            }

            // Add user message to conversation
            this.addMessage('user', transcript);

            // Step 2: Get response
            this.showLoading('Generating response...');
            const response = await this.getResponse(transcript);

            // Add assistant message to conversation
            this.addMessage('assistant', response.response);

            // Step 3: Play audio response
            this.showLoading('Generating voice...');
            await this.playAudioResponse(response.audio);

            // Done
            this.hideLoading();
            this.updateStatus('Ready', 'ready');

        } catch (error) {
            console.error('Processing error:', error);
            this.hideLoading();
            this.updateStatus('Error', 'error');
            this.showError(error.message);
            setTimeout(() => this.updateStatus('Ready', 'ready'), 3000);
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
            const error = await response.json();
            throw new Error(error.error || 'Transcription failed');
        }

        const data = await response.json();
        return data.transcript;
    }

    /**
     * Create conversation session
     */
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
        const response = await fetch('/api/command', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                transcript: transcript,
                conversationId: this.conversationId
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to get response');
        }

        return await response.json();
    }

    /**
     * Play audio response
     */
    async playAudioResponse(base64Audio) {
        return new Promise((resolve, reject) => {
            try {
                // Convert base64 to blob
                const binaryString = atob(base64Audio);
                const bytes = new Uint8Array(binaryString.length);
                for (let i = 0; i < binaryString.length; i++) {
                    bytes[i] = binaryString.charCodeAt(i);
                }
                const audioBlob = new Blob([bytes], { type: 'audio/mpeg' });

                // Create audio element
                const audio = new Audio();
                audio.src = URL.createObjectURL(audioBlob);

                audio.onended = () => {
                    URL.revokeObjectURL(audio.src);
                    resolve();
                };

                audio.onerror = (error) => {
                    URL.revokeObjectURL(audio.src);
                    reject(new Error('Audio playback failed'));
                };

                // Play audio
                audio.play().catch(reject);

            } catch (error) {
                reject(error);
            }
        });
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
        const saved = localStorage.getItem('voiceAssistantSettings');
        if (saved) {
            try {
                this.settings = JSON.parse(saved);
                this.voiceSelect.value = this.settings.voice;
                this.speedSelect.value = this.settings.speed;
            } catch (error) {
                console.error('Failed to load settings:', error);
            }
        }
    }

    /**
     * Save settings to localStorage
     */
    saveSettings() {
        localStorage.setItem('voiceAssistantSettings', JSON.stringify(this.settings));
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.voiceAssistant = new VoiceAssistant();
});
