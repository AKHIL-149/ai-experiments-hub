const axios = require('axios');

/**
 * Weather Service - Wrapper for OpenWeatherMap's free Current Weather API
 */
class WeatherService {
  constructor(options = {}) {
    this.apiKey = options.apiKey || null;
    this.defaultLocation = options.defaultLocation || null;
    this.baseURL = 'https://api.openweathermap.org/data/2.5/weather';
  }

  /**
   * Check if the service has what it needs to make requests
   * @returns {boolean}
   */
  available() {
    return !!this.apiKey;
  }

  /**
   * Get current weather for a location
   * @param {string} location - City name, e.g. "Austin,TX,US" (falls back to defaultLocation if omitted)
   * @returns {Promise<Object>} - { location, description, tempF, feelsLikeF, humidity }
   */
  async getCurrentWeather(location) {
    if (!this.available()) {
      throw new Error('Weather service not configured. Set OPENWEATHER_API_KEY.');
    }

    const query = location || this.defaultLocation;
    if (!query) {
      throw new Error('No location provided and no DEFAULT_WEATHER_LOCATION configured.');
    }

    const response = await axios.get(this.baseURL, {
      params: {
        q: query,
        appid: this.apiKey,
        units: 'imperial'
      },
      timeout: 8000
    });

    const data = response.data;
    return {
      location: `${data.name}${data.sys?.country ? ', ' + data.sys.country : ''}`,
      description: data.weather?.[0]?.description || 'unknown conditions',
      tempF: Math.round(data.main.temp),
      feelsLikeF: Math.round(data.main.feels_like),
      humidity: data.main.humidity
    };
  }

  /**
   * Get service information
   * @returns {Object}
   */
  getInfo() {
    return {
      available: this.available(),
      defaultLocation: this.defaultLocation
    };
  }
}

module.exports = WeatherService;
