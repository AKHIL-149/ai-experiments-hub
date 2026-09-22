const axios = require('axios');

/**
 * Weather Service - two backends, no configuration required to have at
 * least basic current-weather capability:
 *
 * - OpenWeatherMap (preferred, needs OPENWEATHER_API_KEY): richer data,
 *   generous free tier.
 * - wttr.in (fallback, free, no signup, no key): a real weather service
 *   built specifically for programmatic/CLI use - confirmed live it
 *   returns real current conditions for a plain city name with no
 *   configuration at all.
 */
class WeatherService {
  constructor(options = {}) {
    this.apiKey = options.apiKey || null;
    this.defaultLocation = options.defaultLocation || null;
    this.openWeatherURL = 'https://api.openweathermap.org/data/2.5/weather';
    this.mode = this.apiKey ? 'openweathermap' : 'wttr.in';
  }

  /**
   * Whether a weather lookup can be attempted at all. Always true -
   * wttr.in needs no configuration, OpenWeatherMap is used instead when
   * a key is set.
   * @returns {boolean}
   */
  available() {
    return true;
  }

  /**
   * Get current weather for a location
   * @param {string} location - City name, e.g. "Austin,TX,US" (falls back to defaultLocation if omitted)
   * @returns {Promise<Object>} - { location, description, tempF, feelsLikeF, humidity }
   */
  async getCurrentWeather(location) {
    const query = location || this.defaultLocation;
    if (!query) {
      throw new Error('No location provided and no DEFAULT_WEATHER_LOCATION configured.');
    }

    return this.apiKey
      ? this._getFromOpenWeather(query)
      : this._getFromWttr(query);
  }

  async _getFromOpenWeather(query) {
    const response = await axios.get(this.openWeatherURL, {
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

  async _getFromWttr(query) {
    const response = await axios.get(`https://wttr.in/${encodeURIComponent(query)}`, {
      params: { format: 'j1' },
      timeout: 8000
    });

    const data = response.data;
    const current = data.current_condition?.[0];
    if (!current) {
      throw new Error('wttr.in returned no current conditions');
    }

    // wttr.in's nearest_area resolves to the closest weather station,
    // which can be an obscure neighborhood name rather than the city
    // that was actually asked about (e.g. "Chicago" -> "Mccormickville")
    // - use what was actually queried for display instead. Add spaces
    // after commas since DEFAULT_WEATHER_LOCATION-style values
    // ("Houston,TX,US") are typed compactly for the env file.
    return {
      location: query.replace(/,\s*/g, ', '),
      description: (current.weatherDesc?.[0]?.value || 'unknown conditions').trim().toLowerCase(),
      tempF: parseInt(current.temp_F, 10),
      feelsLikeF: parseInt(current.FeelsLikeF, 10),
      humidity: parseInt(current.humidity, 10)
    };
  }

  /**
   * Get service information
   * @returns {Object}
   */
  getInfo() {
    return {
      available: this.available(),
      mode: this.mode,
      defaultLocation: this.defaultLocation
    };
  }
}

module.exports = WeatherService;
