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
    this.recheckMs = options.recheckMs ?? 30000; // how often to look again while offline
    this.isOnline = null; // unknown until the first check resolves
    this.lastCheck = 0;
    this.checking = false;
    this.checkPromise = this.check();
  }

  async check() {
    this.checking = true;
    try {
      await axios.head(this.checkURL, { timeout: this.timeoutMs });
      if (this.isOnline !== true) {
        console.log('✓ Internet connectivity confirmed');
      }
      this.isOnline = true;
    } catch (error) {
      if (this.isOnline !== false) {
        console.warn('⚠️  No internet connectivity detected - cloud/search/weather calls will be skipped');
      }
      this.isOnline = false;
    }
    this.lastCheck = Date.now();
    this.checking = false;
    return this.isOnline;
  }

  /**
   * While offline, look again in the background every so often - otherwise a server that
   * started without a network would skip the cloud until it was restarted.
   */
  recheckIfStale() {
    if (this.isOnline === false && !this.checking && Date.now() - this.lastCheck >= this.recheckMs) {
      this.checkPromise = this.check();
    }
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
