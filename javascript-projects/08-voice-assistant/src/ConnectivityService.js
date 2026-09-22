const axios = require('axios');

/**
 * Connectivity Service - lightweight internet-reachability check.
 * No API key, no signup - just confirms outbound network access is
 * actually available before attempting real API calls that would
 * otherwise time out and fail. Runs the check in the background at
 * startup (same fire-and-forget pattern as LocalWhisperService/
 * LocalLLMService's own availability checks) rather than blocking boot.
 */
class ConnectivityService {
  constructor(options = {}) {
    this.checkURL = options.checkURL || 'https://www.google.com';
    this.timeoutMs = options.timeoutMs || 3000;
    this.isOnline = null; // unknown until the first check resolves
    this.checkPromise = this.check();
  }

  async check() {
    try {
      await axios.head(this.checkURL, { timeout: this.timeoutMs });
      this.isOnline = true;
      console.log('✓ Internet connectivity confirmed');
    } catch (error) {
      this.isOnline = false;
      console.warn('⚠️  No internet connectivity detected - cloud/search/weather calls will be skipped');
    }
    return this.isOnline;
  }

  /**
   * Wait for the initial check to resolve, then return current status.
   */
  async ready() {
    await this.checkPromise;
    return this.isOnline;
  }

  /**
   * Best-known status right now. Treats "not yet checked" (isOnline ===
   * null, only possible in the first ~seconds after startup) as
   * available, so a fast first request isn't blocked by a check still
   * in flight - the real network call it then attempts will fail on its
   * own if we're actually offline, same as before this existed.
   * @returns {boolean}
   */
  available() {
    return this.isOnline !== false;
  }

  getInfo() {
    return { online: this.isOnline };
  }
}

module.exports = ConnectivityService;
