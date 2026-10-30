/**
 * Five-field cron schedules ("minute hour day-of-month month day-of-week") in the server's
 * local time zone. Supports *, lists (1,15), ranges (9-17), steps (*\/5, 10-30/10, 45/5) and
 * month / weekday names. No seconds field: the finest schedule is one minute.
 */

class CronError extends Error {}

const FIELDS = [
  { name: 'minute', min: 0, max: 59 },
  { name: 'hour', min: 0, max: 23 },
  { name: 'day of month', min: 1, max: 31 },
  { name: 'month', min: 1, max: 12, names: ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'], nameBase: 1 },
  { name: 'day of week', min: 0, max: 7, names: ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'], nameBase: 0 },
];

const DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const HORIZON_YEARS = 8; // long enough for a leap day

function parseNumber(token, field) {
  const lower = token.toLowerCase();
  if (field.names && field.names.includes(lower)) {
    return field.names.indexOf(lower) + field.nameBase;
  }
  if (!/^\d+$/.test(token)) {
    throw new CronError(`The ${field.name} field has "${token}", which is not a number${field.names ? ' or name' : ''}`);
  }
  const value = Number(token);
  if (value < field.min || value > field.max) {
    throw new CronError(`The ${field.name} field must be between ${field.min} and ${field.max} (got ${value})`);
  }
  return value;
}

function parseField(text, field) {
  const values = new Set();
  for (const part of text.split(',')) {
    const [range, step, extra] = part.split('/');
    if (extra !== undefined || part === '') {
      throw new CronError(`The ${field.name} field has "${part}", which is not valid`);
    }

    let stepSize = 1;
    if (step !== undefined) {
      if (!/^\d+$/.test(step) || Number(step) < 1) {
        throw new CronError(`The ${field.name} field has a step of "${step}": a step must be a whole number of 1 or more`);
      }
      stepSize = Number(step);
    }

    let from;
    let to;
    const last = field.name === 'day of week' ? 6 : field.max;
    if (range === '*') {
      [from, to] = [field.min, field.name === 'day of week' ? 6 : field.max];
    } else if (range.includes('-')) {
      const [a, b, more] = range.split('-');
      if (more !== undefined || a === '' || b === undefined || b === '') {
        throw new CronError(`The ${field.name} field has "${range}", which is not a valid range`);
      }
      from = parseNumber(a, field);
      to = parseNumber(b, field);
      if (from > to) {
        throw new CronError(`The ${field.name} field has the range ${range}, which ends before it starts`);
      }
    } else {
      from = parseNumber(range, field);
      to = step !== undefined ? (field.name === 'day of week' ? 6 : field.max) : from; // "45/5" means 45 to the end
    }

    // A step bigger than the span only ever matches the first value (*/90 minutes is hourly, not "every 90 minutes")
    if (step !== undefined && stepSize > to - from) {
      throw new CronError(
        `The ${field.name} field has a step of ${stepSize}, which is larger than ${range === '*' || !range.includes('-') ? `the ${field.name} field (${from}-${to})` : `the range ${range}`}: it would only match ${from}`
      );
    }

    for (let v = from; v <= to; v += stepSize) {
      values.add(field.name === 'day of week' && v === 7 ? 0 : v);
    }
  }
  return values;
}

/** Validate and expand an expression. Throws CronError with a readable message. */
function parseCron(expression) {
  if (typeof expression !== 'string') {
    throw new CronError('A schedule needs 5 fields: minute hour day-of-month month day-of-week');
  }
  const parts = expression.trim().split(/\s+/).filter(Boolean);
  if (parts.length !== 5) {
    throw new CronError(
      `A schedule needs 5 fields: minute hour day-of-month month day-of-week (got ${parts.length})` +
      (parts.length === 6 ? '. Seconds are not supported' : '')
    );
  }
  const [minute, hour, dom, month, dow] = FIELDS.map((field, i) => parseField(parts[i], field));
  return {
    minute, hour, dom, month, dow,
    // like standard cron, day-of-month and day-of-week are "either" when both are restricted
    domRestricted: !parts[2].startsWith('*'),
    dowRestricted: !parts[4].startsWith('*'),
  };
}

function dayMatches(cron, date) {
  const dom = cron.dom.has(date.getDate());
  const dow = cron.dow.has(date.getDay());
  return cron.domRestricted && cron.dowRestricted ? dom || dow : dom && dow;
}

/** "2026-10-30 09:05": the local clock minute, used to avoid running a repeated minute twice. */
function localMinuteKey(date) {
  const p = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())} ${p(date.getHours())}:${p(date.getMinutes())}`;
}

/**
 * First matching minute strictly after `after`, or null if there is none within eight years.
 * `skipLocalMinute` skips a clock time that was already run: when daylight saving repeats an hour,
 * the same local time would otherwise match twice.
 */
function nextRun(expression, after, { skipLocalMinute } = {}) {
  const cron = typeof expression === 'string' ? parseCron(expression) : expression;
  const start = new Date(after.getTime());
  start.setSeconds(0, 0);
  let t = new Date(start.getTime() + 60000);
  const horizon = start.getTime() + HORIZON_YEARS * 366 * 86400000;

  while (t.getTime() < horizon) {
    // jump over whole months, days and hours that cannot match instead of stepping minute by minute
    if (!cron.month.has(t.getMonth() + 1)) {
      t = new Date(t.getFullYear(), t.getMonth() + 1, 1, 0, 0);
    } else if (!dayMatches(cron, t)) {
      t = new Date(t.getFullYear(), t.getMonth(), t.getDate() + 1, 0, 0);
    } else if (!cron.hour.has(t.getHours())) {
      t = new Date(t.getFullYear(), t.getMonth(), t.getDate(), t.getHours() + 1, 0);
    } else if (!cron.minute.has(t.getMinutes()) || (skipLocalMinute && localMinuteKey(t) === skipLocalMinute)) {
      t = new Date(t.getTime() + 60000);
    } else {
      return t;
    }
  }
  return null;
}

function nextRuns(expression, after, count) {
  const cron = typeof expression === 'string' ? parseCron(expression) : expression;
  const runs = [];
  let cursor = after;
  while (runs.length < count) {
    const next = nextRun(cron, cursor);
    if (!next) break;
    runs.push(next);
    cursor = next;
  }
  return runs;
}

/** A short plain-English name for the common schedules; anything else is shown as written. */
function describeCron(expression) {
  const parts = String(expression).trim().split(/\s+/);
  if (parts.length !== 5) return `Custom schedule (${expression})`;
  const [mi, h, dom, mo, dow] = parts;
  const num = (s) => /^\d+$/.test(s);
  const clock = () => `${h.padStart(2, '0')}:${mi.padStart(2, '0')}`;
  const custom = `Custom schedule (${expression})`;

  if (mo !== '*') return custom;
  if (h === '*' && dom === '*' && dow === '*') {
    if (mi === '*') return 'Every minute';
    if (/^\*\/\d+$/.test(mi)) return 60 % Number(mi.slice(2)) === 0 ? `Every ${mi.slice(2)} minutes` : custom;
    if (mi === '0') return 'Every hour';
    if (num(mi)) return `Every hour at :${mi.padStart(2, '0')}`;
  }
  if (mi === '0' && /^\*\/\d+$/.test(h) && dom === '*' && dow === '*') {
    return 24 % Number(h.slice(2)) === 0 ? `Every ${h.slice(2)} hours` : custom;
  }
  if (num(mi) && num(h)) {
    if (dom === '*' && dow === '*') return `Every day at ${clock()}`;
    if (dom === '*' && dow === '1-5') return `Weekdays at ${clock()}`;
    if (dom === '*' && num(dow)) return `Every ${DAY_NAMES[Number(dow) % 7]} at ${clock()}`;
    if (num(dom) && dow === '*') return `Day ${dom} of every month at ${clock()}`;
  }
  return custom;
}

module.exports = { parseCron, nextRun, nextRuns, describeCron, localMinuteKey, CronError };
