const axios = require('axios');

/**
 * F1 Service - Wrapper for the free Jolpica-F1 API (Ergast's successor)
 * No API key required.
 */
class F1Service {
  constructor() {
    this.baseURL = 'https://api.jolpi.ca/ergast/f1';
  }

  /**
   * Get the next upcoming F1 race
   * @returns {Promise<Object|null>} - { raceName, circuit, date, dateFormatted } or null if no upcoming race
   */
  async getNextRace() {
    const response = await axios.get(`${this.baseURL}/current/next.json`, { timeout: 8000 });
    const races = response.data?.MRData?.RaceTable?.Races || [];
    if (races.length === 0) return null;

    const race = races[0];
    const raceDate = new Date(`${race.date}T${race.time || '00:00:00Z'}`);

    return {
      raceName: race.raceName,
      circuit: race.Circuit?.circuitName,
      date: race.date,
      dateFormatted: raceDate.toLocaleDateString('en-US', {
        weekday: 'long', month: 'long', day: 'numeric', year: 'numeric'
      })
    };
  }
}

module.exports = F1Service;
