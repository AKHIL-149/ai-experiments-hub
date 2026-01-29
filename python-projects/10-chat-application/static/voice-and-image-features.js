/**
 * Voice Input and Image Generation Features
 * Real-time microphone input and image generation support
 */

// Voice Input Manager
class VoiceInputManager {
    constructor() {
        this.recognition = null;
        this.isRecording = false;
        this.setupVoiceRecognition();
        this.setupUI();
    }

    setupVoiceRecognition() {
        // Check for Web Speech API support
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

        if (SpeechRecognition) {
            this.recognition = new SpeechRecognition();
            this.recognition.continuous = false;
            this.recognition.interimResults = true;
            this.recognition.lang = 'en-US';

            this.recognition.onstart = () => {
                this.isRecording = true;
                this.updateMicButton(true);
                console.log('Voice recognition started');
            };

            this.recognition.onresult = (event) => {
                let interimTranscript = '';
                let finalTranscript = '';

                for (let i = event.resultIndex; i < event.results.length; i++) {
                    const transcript = event.results[i][0].transcript;
                    if (event.results[i].isFinal) {
                        finalTranscript += transcript;
                    } else {
                        interimTranscript += transcript;
                    }
                }

                // Update input with transcript
                const userInput = document.getElementById('user-input');
                if (finalTranscript) {
                    userInput.value = finalTranscript;
                } else if (interimTranscript) {
                    // Show interim results in placeholder
                    userInput.placeholder = `Listening: "${interimTranscript}"...`;
                }
            };

            this.recognition.onend = () => {
                this.isRecording = false;
                this.updateMicButton(false);
                document.getElementById('user-input').placeholder = 'Type your message...';
                console.log('Voice recognition ended');
            };

            this.recognition.onerror = (event) => {
                console.error('Speech recognition error:', event.error);
                this.isRecording = false;
                this.updateMicButton(false);

                if (event.error === 'not-allowed') {
                    alert('Microphone access denied. Please allow microphone access in your browser settings.');
                }
            };
        } else {
            console.warn('Web Speech API not supported in this browser');
        }
    }

    setupUI() {
        // Wait for chat view to be ready and visible
        const checkAndSetup = () => {
            const inputContainer = document.querySelector('.chat-input-container');
            const chatView = document.getElementById('chat-view');

            // Check if chat view is visible (user logged in)
            if (!inputContainer || !chatView || chatView.style.display === 'none') {
                setTimeout(checkAndSetup, 500);
                return;
            }

            // Check if button already exists
            if (document.getElementById('mic-button')) {
                return;
            }

            // Create microphone button
            const micButton = document.createElement('button');
            micButton.id = 'mic-button';
            micButton.className = 'btn-mic';
            micButton.innerHTML = '🎤';
            micButton.title = 'Voice input (click to speak)';

            // Insert before send button
            const sendButton = document.getElementById('send-button');
            inputContainer.insertBefore(micButton, sendButton);

            // Add click handler
            micButton.addEventListener('click', () => {
                this.toggleRecording();
            });

            console.log('Voice input UI initialized');
        };

        checkAndSetup();
    }

    toggleRecording() {
        if (!this.recognition) {
            alert('Voice recognition not supported in this browser. Please use Chrome, Edge, or Safari.');
            return;
        }

        if (this.isRecording) {
            this.recognition.stop();
        } else {
            try {
                this.recognition.start();
            } catch (error) {
                console.error('Failed to start recognition:', error);
            }
        }
    }

    updateMicButton(isRecording) {
        const micButton = document.getElementById('mic-button');
        if (micButton) {
            if (isRecording) {
                micButton.classList.add('recording');
                micButton.innerHTML = '⏹️';
                micButton.title = 'Stop recording';
            } else {
                micButton.classList.remove('recording');
                micButton.innerHTML = '🎤';
                micButton.title = 'Voice input (click to speak)';
            }
        }
    }
}

// Image Generation Manager
class ImageGenerationManager {
    constructor() {
        this.setupUI();
        this.checkImageCapabilities();
    }

    async checkImageCapabilities() {
        // Check if backend supports image generation
        try {
            const response = await fetch('/api/health', { credentials: 'include' });
            if (response.ok) {
                const data = await response.json();
                console.log('Image generation capabilities:', data.image_generation || 'Not available');
            }
        } catch (error) {
            console.error('Error checking image capabilities:', error);
        }
    }

    setupUI() {
        // Wait for chat view to be ready and visible
        const checkAndSetup = () => {
            const inputContainer = document.querySelector('.chat-input-container');
            const chatView = document.getElementById('chat-view');

            // Check if chat view is visible (user logged in)
            if (!inputContainer || !chatView || chatView.style.display === 'none') {
                setTimeout(checkAndSetup, 500);
                return;
            }

            // Check if button already exists
            if (document.getElementById('image-button')) {
                return;
            }

            // Create image generation button
            const imageButton = document.createElement('button');
            imageButton.id = 'image-button';
            imageButton.className = 'btn-image';
            imageButton.innerHTML = '🎨';
            imageButton.title = 'Generate image (type /image <prompt>)';

            // Insert before send button
            const sendButton = document.getElementById('send-button');
            inputContainer.insertBefore(imageButton, sendButton);

            // Add click handler
            imageButton.addEventListener('click', () => {
                this.showImagePrompt();
            });

            console.log('Image generation UI initialized');
        };

        checkAndSetup();
    }

    showImagePrompt() {
        const userInput = document.getElementById('user-input');
        const currentValue = userInput.value.trim();

        if (!currentValue.startsWith('/image ')) {
            userInput.value = '/image ';
            userInput.focus();
            userInput.setSelectionRange(7, 7); // Position cursor after /image
        }
    }

    async generateImage(prompt) {
        console.log('Generating image for prompt:', prompt);

        // Show loading message
        if (window.chatApp && window.chatApp.chatView) {
            window.chatApp.chatView.addMessage('assistant', '🎨 Generating image...', false);
        }

        try {
            // Send image generation request
            const response = await fetch('/api/generate-image', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({
                    prompt: prompt,
                    provider: 'stable-diffusion' // or 'dall-e', 'midjourney', etc.
                })
            });

            if (response.ok) {
                const data = await response.json();
                this.displayGeneratedImage(data.image_url, prompt);
            } else {
                const error = await response.json();
                this.showImageError(error.detail || 'Image generation failed');
            }
        } catch (error) {
            console.error('Image generation error:', error);
            this.showImageError('Image generation service not available. This feature requires local Stable Diffusion setup.');
        }
    }

    displayGeneratedImage(imageUrl, prompt) {
        if (!window.chatApp || !window.chatApp.chatView) return;

        const container = document.getElementById('message-container');
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant-message';

        messageDiv.innerHTML = `
            <div class="message-role">Assistant</div>
            <div class="message-content">
                <p><strong>Generated image:</strong> ${this.escapeHtml(prompt)}</p>
                <img src="${imageUrl}" alt="${this.escapeHtml(prompt)}" class="generated-image">
            </div>
        `;

        container.appendChild(messageDiv);
        container.scrollTop = container.scrollHeight;
    }

    showImageError(errorMessage) {
        if (!window.chatApp || !window.chatApp.chatView) return;

        const container = document.getElementById('message-container');
        // Remove loading message
        const messages = container.querySelectorAll('.message');
        const lastMessage = messages[messages.length - 1];
        if (lastMessage && lastMessage.textContent.includes('Generating image')) {
            lastMessage.remove();
        }

        // Show error
        window.chatApp.chatView.addMessage('assistant',
            `⚠️ ${errorMessage}\n\n**To enable image generation:**\n` +
            `1. Install Stable Diffusion WebUI or ComfyUI\n` +
            `2. Configure the API endpoint in .env\n` +
            `3. Or use cloud providers (DALL-E, Midjourney)`,
            false
        );
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Message Interceptor for /image commands
class MessageInterceptor {
    constructor() {
        this.imageManager = null;
        this.setupInterceptor();
    }

    setupInterceptor() {
        setTimeout(() => {
            if (window.chatApp && window.chatApp.chatView) {
                const chatView = window.chatApp.chatView;
                const originalSendMessage = chatView.sendMessage.bind(chatView);

                chatView.sendMessage = () => {
                    const input = document.getElementById('user-input');
                    const content = input.value.trim();

                    // Check for /image command
                    if (content.startsWith('/image ')) {
                        const prompt = content.substring(7).trim();
                        if (prompt && this.imageManager) {
                            input.value = '';
                            this.imageManager.generateImage(prompt);
                            return; // Don't send to LLM
                        }
                    }

                    // Otherwise, use original sendMessage
                    originalSendMessage();
                };

                console.log('Message interceptor initialized');
            }
        }, 400);
    }

    setImageManager(imageManager) {
        this.imageManager = imageManager;
    }
}

// Initialize features when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => {
        // Initialize voice input
        const voiceManager = new VoiceInputManager();
        window.voiceManager = voiceManager;

        // Initialize image generation
        const imageManager = new ImageGenerationManager();
        window.imageManager = imageManager;

        // Initialize message interceptor
        const interceptor = new MessageInterceptor();
        interceptor.setImageManager(imageManager);

        console.log('Voice and image features loaded');
    }, 500);
});

// Add CSS for new features (wrapped in IIFE to avoid variable conflicts)
(function() {
    const style = document.createElement('style');
    style.textContent = `
        /* Microphone button */
        .btn-mic {
            padding: 12px 16px;
            background: #4caf50;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 20px;
            cursor: pointer;
            transition: all 0.3s;
            margin-right: 10px;
        }

        .btn-mic:hover {
            background: #45a049;
            transform: translateY(-2px);
        }

        .btn-mic.recording {
            background: #f44336;
            animation: pulse-mic 1.5s infinite;
        }

        @keyframes pulse-mic {
            0%, 100% {
                box-shadow: 0 0 0 0 rgba(244, 67, 54, 0.7);
            }
            50% {
                box-shadow: 0 0 0 10px rgba(244, 67, 54, 0);
            }
        }

        /* Image button */
        .btn-image {
            padding: 12px 16px;
            background: #9c27b0;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 20px;
            cursor: pointer;
            transition: all 0.3s;
            margin-right: 10px;
        }

        .btn-image:hover {
            background: #7b1fa2;
            transform: translateY(-2px);
        }

        /* Generated images */
        .generated-image {
            max-width: 100%;
            max-height: 512px;
            border-radius: 8px;
            margin-top: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
            cursor: pointer;
        }

        .generated-image:hover {
            transform: scale(1.02);
            transition: transform 0.3s;
        }

        /* Update input container flex */
        .chat-input-container {
            display: flex;
            align-items: flex-start;
        }

        #user-input {
            flex: 1;
        }
    `;
    document.head.appendChild(style);
})();
