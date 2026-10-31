const { replaceNumberWords } = require('./SpokenNumbers');

/**
 * Spoken durations for timers: "5 minutes", "1 hour 30 minutes", "1.5 hours", "an hour",
 * "half an hour", "two and a half minutes", "90 seconds". A bare number means minutes.
 */

const MAX_SECONDS = 24 * 60 * 60;

const UNIT_SECONDS = [
  [/^(?:hours?|hrs?|h)$/, 3600],
  [/^(?:minutes?|mins?|m)$/, 60],
  [/^(?:seconds?|secs?|s)$/, 1]
];

function secondsPerUnit(unit) {
  for (const [pattern, seconds] of UNIT_SECONDS) {
    if (pattern.test(unit)) return seconds;
  }
  return null;
}

/**
 * @param {string} text - the spoken duration, e.g. "1 hour 30 minutes"
 * @returns {{ok: true, seconds: number} | {ok: false, reason: 'unparseable' | 'too-long' | 'zero'}}
 */
function parseDuration(text) {
  let s = ` ${String(text).toLowerCase().replace(/[,.](?!\d)/g, ' ')} `;
  s = replaceNumberWords(s.trim());
  s = ` ${s} `
    .replace(/\bhalf an? hour\b/g, ' 30 minutes ')
    .replace(/\bhalf an? minute\b/g, ' 30 seconds ')
    .replace(/\b(?:a )?quarter (?:of an? )?hour\b/g, ' 15 minutes ')
    .replace(/\b(\d+) and a half\b/g, ' $1.5 ')
    .replace(/\ban? hour and a half\b/g, ' 1.5 hours ')
    .replace(/\b(?:an|a|one more)\s+(?=hours?\b|hrs?\b|minutes?\b|mins?\b|seconds?\b|secs?\b)/g, ' 1 ');

  let total = 0;
  let matched = false;
  const pattern = /(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b/g;
  let match;
  while ((match = pattern.exec(s)) !== null) {
    total += parseFloat(match[1]) * secondsPerUnit(match[2]);
    matched = true;
  }

  if (!matched) {
    // A bare number: assume minutes ("timer for 10")
    const bare = s.match(/(\d+(?:\.\d+)?)/);
    if (!bare) return { ok: false, reason: 'unparseable' };
    total = parseFloat(bare[1]) * 60;
  }

  const seconds = Math.round(total);
  if (!Number.isFinite(seconds)) return { ok: false, reason: 'unparseable' };
  if (seconds < 1) return { ok: false, reason: 'zero' };
  if (seconds > MAX_SECONDS) return { ok: false, reason: 'too-long' };
  return { ok: true, seconds };
}

/**
 * Seconds as words: 5400 -> "1 hour and 30 minutes"
 */
function formatDuration(totalSeconds) {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  const parts = [];
  if (hours > 0) parts.push(`${hours} hour${hours !== 1 ? 's' : ''}`);
  if (minutes > 0) parts.push(`${minutes} minute${minutes !== 1 ? 's' : ''}`);
  if (seconds > 0) parts.push(`${seconds} second${seconds !== 1 ? 's' : ''}`);

  if (parts.length <= 1) return parts[0] || '0 seconds';
  return `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`;
}

module.exports = { parseDuration, formatDuration, MAX_SECONDS };
