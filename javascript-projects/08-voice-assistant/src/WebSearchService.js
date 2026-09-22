const axios = require('axios');

/**
 * Web Search Service - Wrapper for Tavily's search API
 * Purpose-built for feeding LLM tools: returns short, clean content
 * snippets instead of raw HTML.
 */
class WebSearchService {
  constructor(options = {}) {
    this.apiKey = options.apiKey || null;
    this.baseURL = 'https://api.tavily.com/search';
  }

  /**
   * Check if the service has what it needs to make requests
   * @returns {boolean}
   */
  available() {
    return !!this.apiKey;
  }

  /**
   * Search the web
   * @param {string} query - Search query
   * @param {number} maxResults - Max results to return
   * @returns {Promise<Array>} - [{ title, url, content }]
   */
  async search(query, maxResults = 3) {
    if (!this.available()) {
      throw new Error('Web search not configured. Set TAVILY_API_KEY.');
    }

    const response = await axios.post(this.baseURL, {
      api_key: this.apiKey,
      query: query,
      max_results: maxResults
    }, { timeout: 10000 });

    const results = response.data.results || [];
    return results.map(r => ({
      title: r.title,
      url: r.url,
      content: r.content
    }));
  }

  /**
   * Get service information
   * @returns {Object}
   */
  getInfo() {
    return {
      available: this.available()
    };
  }
}

module.exports = WebSearchService;
