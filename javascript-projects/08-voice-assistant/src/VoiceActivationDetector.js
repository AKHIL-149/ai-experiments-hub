const EventEmitter = require('events');

/**
 * Voice Activation Detector - Detects speech in audio stream
 * Uses amplitude-based detection for voice activity
 */
class VoiceActivationDetector extends EventEmitter {
  constructor(options = {}) {
    super();

    // Configuration
    this.threshold = options.threshold || 0.02; // Amplitude threshold (0-1)
    this.silenceDelay = options.silenceDelay || 1500; // ms of silence before stopping
    this.minSpeechDuration = options.minSpeechDuration || 500; // Min speech duration
    this.smoothingFactor = options.smoothingFactor || 0.8; // Smoothing for audio level

    // State
    this.isActive = false;
    this.isSpeaking = false;
    this.speechStartTime = null;
    this.lastSpeechTime = null;
    this.silenceTimer = null;
    this.smoothedLevel = 0;

    // Audio context
    this.audioContext = null;
    this.analyser = null;
    this.dataArray = null;
    this.animationFrameId = null;
  }

  /**
   * Start monitoring audio stream
   * @param {MediaStream} stream - Audio input stream
   */
  start(stream) {
    if (this.isActive) {
      console.warn('Voice activation already active');
      return;
    }

    try {
      // Create audio context
      this.audioContext = new (window.AudioContext || window.webkitAudioContext)();

      // Create analyser node
      this.analyser = this.audioContext.createAnalyser();
      this.analyser.fftSize = 2048;
      this.analyser.smoothingTimeConstant = 0.8;

      // Connect stream to analyser
      const source = this.audioContext.createMediaStreamSource(stream);
      source.connect(this.analyser);

      // Create data array for frequency data
      const bufferLength = this.analyser.frequencyBinCount;
      this.dataArray = new Uint8Array(bufferLength);

      this.isActive = true;
      this.startAnalysis();

      this.emit('started');
      console.log('Voice activation started');

    } catch (error) {
      console.error('Failed to start voice activation:', error);
      this.emit('error', error);
    }
  }

  /**
   * Stop monitoring audio
   */
  stop() {
    if (!this.isActive) return;

    this.isActive = false;

    // Cancel animation frame
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
      this.animationFrameId = null;
    }

    // Clear silence timer
    if (this.silenceTimer) {
      clearTimeout(this.silenceTimer);
      this.silenceTimer = null;
    }

    // Close audio context
    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }

    this.analyser = null;
    this.dataArray = null;
    this.isSpeaking = false;
    this.speechStartTime = null;
    this.lastSpeechTime = null;

    this.emit('stopped');
    console.log('Voice activation stopped');
  }

  /**
   * Start analyzing audio levels
   */
  startAnalysis() {
    const analyze = () => {
      if (!this.isActive) return;

      // Get audio level
      this.analyser.getByteTimeDomainData(this.dataArray);

      // Calculate RMS (root mean square) level
      const rms = this.calculateRMS(this.dataArray);

      // Smooth the level
      this.smoothedLevel = (this.smoothingFactor * this.smoothedLevel) +
                          ((1 - this.smoothingFactor) * rms);

      // Emit audio level for visualization
      this.emit('audioLevel', this.smoothedLevel);

      // Check if speaking
      const now = Date.now();

      if (this.smoothedLevel > this.threshold) {
        // Speech detected
        this.lastSpeechTime = now;

        if (!this.isSpeaking) {
          // Start of speech
          this.speechStartTime = now;
          this.isSpeaking = true;
          this.emit('speechStart');
          console.log('Speech detected');
        }

        // Clear silence timer
        if (this.silenceTimer) {
          clearTimeout(this.silenceTimer);
          this.silenceTimer = null;
        }

      } else if (this.isSpeaking) {
        // Currently speaking but level dropped

        if (!this.silenceTimer) {
          // Start silence timer
          this.silenceTimer = setTimeout(() => {
            if (this.isSpeaking) {
              const speechDuration = now - this.speechStartTime;

              // Only emit speechEnd if speech was long enough
              if (speechDuration >= this.minSpeechDuration) {
                this.emit('speechEnd', { duration: speechDuration });
                console.log(`Speech ended (${speechDuration}ms)`);
              }

              this.isSpeaking = false;
              this.speechStartTime = null;
              this.silenceTimer = null;
            }
          }, this.silenceDelay);
        }
      }

      // Continue analysis
      this.animationFrameId = requestAnimationFrame(analyze);
    };

    analyze();
  }

  /**
   * Calculate RMS level from audio data
   * @param {Uint8Array} dataArray - Time domain data
   * @returns {number} - RMS level (0-1)
   */
  calculateRMS(dataArray) {
    let sum = 0;

    for (let i = 0; i < dataArray.length; i++) {
      // Convert to -1 to 1 range
      const normalized = (dataArray[i] - 128) / 128;
      sum += normalized * normalized;
    }

    const rms = Math.sqrt(sum / dataArray.length);
    return rms;
  }

  /**
   * Get frequency data for visualization
   * @returns {Uint8Array|null} - Frequency data array
   */
  getFrequencyData() {
    if (!this.analyser) return null;

    const freqData = new Uint8Array(this.analyser.frequencyBinCount);
    this.analyser.getByteFrequencyData(freqData);
    return freqData;
  }

  /**
   * Get time domain data for waveform visualization
   * @returns {Uint8Array|null} - Time domain data array
   */
  getTimeDomainData() {
    if (!this.analyser) return null;

    const timeData = new Uint8Array(this.analyser.frequencyBinCount);
    this.analyser.getByteTimeDomainData(timeData);
    return timeData;
  }

  /**
   * Update detection threshold
   * @param {number} threshold - New threshold (0-1)
   */
  setThreshold(threshold) {
    this.threshold = Math.max(0, Math.min(1, threshold));
    console.log(`VAD threshold set to ${this.threshold}`);
  }

  /**
   * Update silence delay
   * @param {number} delay - Delay in milliseconds
   */
  setSilenceDelay(delay) {
    this.silenceDelay = Math.max(100, delay);
    console.log(`Silence delay set to ${this.silenceDelay}ms`);
  }

  /**
   * Get current audio level
   * @returns {number} - Current smoothed level (0-1)
   */
  getCurrentLevel() {
    return this.smoothedLevel;
  }

  /**
   * Check if currently speaking
   * @returns {boolean}
   */
  isSpeakingNow() {
    return this.isSpeaking;
  }

  /**
   * Get speech duration if currently speaking
   * @returns {number|null} - Duration in ms or null
   */
  getSpeechDuration() {
    if (!this.isSpeaking || !this.speechStartTime) return null;
    return Date.now() - this.speechStartTime;
  }
}

// Browser-compatible export for frontend use
if (typeof module !== 'undefined' && module.exports) {
  module.exports = VoiceActivationDetector;
}
