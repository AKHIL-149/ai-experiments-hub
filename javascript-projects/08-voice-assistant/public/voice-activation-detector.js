/**
 * Voice Activation Detector (VAD) - Phase 6
 * Detects voice activity using Web Audio API for hands-free mode
 */
class VoiceActivationDetector {
  constructor(options = {}) {
    this.sensitivity = options.sensitivity || 0.3; // 0.0 to 1.0
    this.minSpeechDuration = options.minSpeechDuration || 300; // ms
    this.silenceDuration = options.silenceDuration || 1000; // ms before stopping
    this.fftSize = 2048;

    // State
    this.isActive = false;
    this.isListening = false;
    this.isSpeaking = false;
    this.audioContext = null;
    this.analyser = null;
    this.microphone = null;
    this.dataArray = null;

    // Timing
    this.speechStartTime = null;
    this.lastSpeechTime = null;
    this.checkInterval = null;

    // Callbacks
    this.onSpeechStart = options.onSpeechStart || (() => {});
    this.onSpeechEnd = options.onSpeechEnd || (() => {});
    this.onVolumeChange = options.onVolumeChange || (() => {});
  }

  /**
   * Initialize Web Audio API for VAD
   * @param {MediaStream} stream - Microphone stream
   */
  async initialize(stream) {
    try {
      this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
      this.analyser = this.audioContext.createAnalyser();
      this.analyser.fftSize = this.fftSize;

      this.microphone = this.audioContext.createMediaStreamSource(stream);
      this.microphone.connect(this.analyser);

      this.dataArray = new Uint8Array(this.analyser.frequencyBinCount);

      console.log('✓ VAD initialized');
      return true;
    } catch (error) {
      console.error('VAD initialization failed:', error);
      return false;
    }
  }

  /**
   * Start voice activity detection
   */
  start() {
    if (!this.analyser || this.isActive) {
      return;
    }

    this.isActive = true;
    this.isListening = true;
    this.isSpeaking = false;

    // Check audio levels periodically
    this.checkInterval = setInterval(() => {
      this.checkAudioLevel();
    }, 100); // Check every 100ms

    console.log('✓ VAD started');
  }

  /**
   * Stop voice activity detection
   */
  stop() {
    this.isActive = false;
    this.isListening = false;
    this.isSpeaking = false;

    if (this.checkInterval) {
      clearInterval(this.checkInterval);
      this.checkInterval = null;
    }

    console.log('✓ VAD stopped');
  }

  /**
   * Check current audio level and detect speech
   */
  checkAudioLevel() {
    if (!this.analyser || !this.isActive) {
      return;
    }

    this.analyser.getByteFrequencyData(this.dataArray);

    // Calculate RMS (Root Mean Square) for better voice detection
    const rms = this.calculateRMS(this.dataArray);
    const normalizedVolume = rms / 255; // Normalize to 0-1

    // Notify volume change (for visualization)
    this.onVolumeChange(normalizedVolume);

    // Detect speech based on threshold
    const threshold = this.sensitivity;
    const isSpeechDetected = normalizedVolume > threshold;

    const now = Date.now();

    if (isSpeechDetected) {
      this.lastSpeechTime = now;

      if (!this.isSpeaking) {
        // Speech just started
        if (!this.speechStartTime) {
          this.speechStartTime = now;
        } else if (now - this.speechStartTime >= this.minSpeechDuration) {
          // Speech has been sustained long enough
          this.isSpeaking = true;
          console.log('🎤 Speech detected');
          this.onSpeechStart();
        }
      }
    } else {
      // No speech detected
      this.speechStartTime = null;

      if (this.isSpeaking && this.lastSpeechTime) {
        // Check if silence has been sustained long enough
        if (now - this.lastSpeechTime >= this.silenceDuration) {
          this.isSpeaking = false;
          console.log('🔇 Speech ended');
          this.onSpeechEnd();
        }
      }
    }
  }

  /**
   * Calculate RMS (Root Mean Square) of audio data
   * @param {Uint8Array} dataArray - Frequency data
   * @returns {number} RMS value
   */
  calculateRMS(dataArray) {
    let sum = 0;
    for (let i = 0; i < dataArray.length; i++) {
      sum += dataArray[i] * dataArray[i];
    }
    return Math.sqrt(sum / dataArray.length);
  }

  /**
   * Calculate average volume from frequency data
   * @param {Uint8Array} dataArray - Frequency data
   * @returns {number} Average volume (0-255)
   */
  calculateAverageVolume(dataArray) {
    let sum = 0;
    for (let i = 0; i < dataArray.length; i++) {
      sum += dataArray[i];
    }
    return sum / dataArray.length;
  }

  /**
   * Set sensitivity threshold
   * @param {number} sensitivity - Value between 0.0 and 1.0
   */
  setSensitivity(sensitivity) {
    this.sensitivity = Math.max(0.0, Math.min(1.0, sensitivity));
    console.log(`✓ VAD sensitivity set to ${(this.sensitivity * 100).toFixed(0)}%`);
  }

  /**
   * Set minimum speech duration
   * @param {number} duration - Duration in milliseconds
   */
  setMinSpeechDuration(duration) {
    this.minSpeechDuration = Math.max(100, duration);
  }

  /**
   * Set silence duration before stopping
   * @param {number} duration - Duration in milliseconds
   */
  setSilenceDuration(duration) {
    this.silenceDuration = Math.max(500, duration);
  }

  /**
   * Get current state
   * @returns {Object}
   */
  getState() {
    return {
      isActive: this.isActive,
      isListening: this.isListening,
      isSpeaking: this.isSpeaking,
      sensitivity: this.sensitivity,
      minSpeechDuration: this.minSpeechDuration,
      silenceDuration: this.silenceDuration
    };
  }

  /**
   * Cleanup resources
   */
  destroy() {
    this.stop();

    if (this.microphone) {
      this.microphone.disconnect();
      this.microphone = null;
    }

    if (this.analyser) {
      this.analyser.disconnect();
      this.analyser = null;
    }

    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }

    console.log('✓ VAD destroyed');
  }
}

// Export for use in app.js
window.VoiceActivationDetector = VoiceActivationDetector;
