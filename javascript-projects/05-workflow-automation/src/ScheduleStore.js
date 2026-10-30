const fs = require('fs').promises;
const path = require('path');

const ID_PATTERN = /^[\w-]+$/;

/**
 * Keeps the schedules in one JSON file. Writes are atomic (temp file, then rename) and
 * queued, so a crash or a concurrent save can never leave a half-written file, and a file
 * that cannot be read is moved aside instead of being overwritten.
 */
class ScheduleStore {
  constructor(filePath) {
    this.filePath = filePath;
    this.queue = Promise.resolve();
    this.counter = 0;
  }

  /** @returns {Promise<{schedules: Object[], warnings: string[]}>} */
  async load() {
    let raw;
    try {
      raw = await fs.readFile(this.filePath, 'utf-8');
    } catch (error) {
      if (error.code === 'ENOENT') {
        return { schedules: [], warnings: [] };
      }
      throw error;
    }

    let data;
    try {
      data = JSON.parse(raw);
    } catch (error) {
      const aside = `${this.filePath}.corrupt-${new Date().toISOString().replace(/[:.]/g, '-')}`;
      await fs.rename(this.filePath, aside);
      return {
        schedules: [],
        warnings: [`${path.basename(this.filePath)} is not valid JSON (${error.message}); kept as ${path.basename(aside)} and started with no schedules`]
      };
    }

    if (!data || typeof data !== 'object' || !Array.isArray(data.schedules)) {
      return { schedules: [], warnings: [`${path.basename(this.filePath)} has an unexpected format and was ignored`] };
    }

    const warnings = [];
    const seen = new Set();
    const schedules = [];
    data.schedules.forEach((entry, index) => {
      if (!entry || typeof entry !== 'object' || typeof entry.id !== 'string' || !ID_PATTERN.test(entry.id)) {
        warnings.push(`Skipped schedule #${index + 1}: it has no usable id`);
      } else if (seen.has(entry.id)) {
        warnings.push(`Skipped a duplicate of schedule ${entry.id}`);
      } else {
        seen.add(entry.id);
        schedules.push(entry);
      }
    });
    return { schedules, warnings };
  }

  /** Replace the stored list. Saves run one at a time, in the order they were requested. */
  save(schedules) {
    const run = () => this._write(schedules);
    const result = this.queue.then(run, run);
    this.queue = result.catch(() => {}); // a failed save must not block the ones after it
    return result;
  }

  async _write(schedules) {
    await fs.mkdir(path.dirname(this.filePath), { recursive: true });
    this.counter += 1;
    const temp = `${this.filePath}.${process.pid}.${this.counter}.tmp`;
    try {
      await fs.writeFile(temp, JSON.stringify({ version: 1, schedules }, null, 2) + '\n', 'utf-8');
      await fs.rename(temp, this.filePath);
    } catch (error) {
      await fs.rm(temp, { force: true });
      throw error;
    }
  }
}

module.exports = ScheduleStore;
