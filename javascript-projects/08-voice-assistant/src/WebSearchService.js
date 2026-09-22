const axios = require('axios');

/**
 * Web Search Service - two backends, no configuration required to have
 * at least basic search capability:
 *
 * - Tavily (preferred, needs TAVILY_API_KEY): purpose-built for feeding
 *   LLM tools, returns short clean content snippets from real web pages.
 * - DuckDuckGo Instant Answer API (fallback, free, no signup, no key):
 *   a legitimate public API, not scraping - but much narrower coverage.
 *   It answers direct factual/infobox-style queries well ("capital of
 *   Japan", "population of Canada") and often returns nothing for
 *   general queries (news, schedules, "latest X") that Tavily handles
 *   fine. Optional upgrade path: add a Tavily key for real search.
 */
class WebSearchService {
  constructor(options = {}) {
    this.apiKey = options.apiKey || null;
    this.tavilyURL = 'https://api.tavily.com/search';
    this.duckduckgoURL = 'https://api.duckduckgo.com/';
    this.mode = this.apiKey ? 'tavily' : 'duckduckgo';
  }

  /**
   * Whether search can be attempted at all. Always true - DuckDuckGo
   * needs no configuration, Tavily is used instead when a key is set.
   * @returns {boolean}
   */
  available() {
    return true;
  }

  /**
   * Search the web
   * @param {string} query - Search query
   * @param {number} maxResults - Max results to return
   * @returns {Promise<Array>} - [{ title, url, content }]
   */
  async search(query, maxResults = 3) {
    return this.apiKey
      ? this._searchTavily(query, maxResults)
      : this._searchDuckDuckGo(query, maxResults);
  }

  async _searchTavily(query, maxResults) {
    const response = await axios.post(this.tavilyURL, {
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

  async _searchDuckDuckGo(query, maxResults) {
    const response = await axios.get(this.duckduckgoURL, {
      params: { q: query, format: 'json', no_html: 1, skip_disambig: 1 },
      timeout: 8000
    });

    const data = response.data || {};
    const results = [];

    if (data.AbstractText) {
      results.push({
        title: data.Heading || query,
        url: data.AbstractURL || '',
        content: data.AbstractText
      });
    }

    for (const topic of (data.RelatedTopics || [])) {
      if (results.length >= maxResults) break;
      if (topic.Text) {
        results.push({
          title: topic.Text.split(' - ')[0],
          url: topic.FirstURL || '',
          content: topic.Text
        });
      }
    }

    return results.slice(0, maxResults);
  }

  /**
   * Get service information
   * @returns {Object}
   */
  getInfo() {
    return {
      available: this.available(),
      mode: this.mode
    };
  }
}

module.exports = WebSearchService;
