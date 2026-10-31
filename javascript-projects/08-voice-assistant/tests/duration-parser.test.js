const test = require('node:test');
const assert = require('node:assert/strict');
const { parseDuration, formatDuration, MAX_SECONDS } = require('../src/DurationParser');

const seconds = (text) => {
  const result = parseDuration(text);
  assert.ok(result.ok, `${text}: expected a duration, got ${result.reason}`);
  return result.seconds;
};

test('plain units', () => {
  assert.equal(seconds('5 minutes'), 300);
  assert.equal(seconds('2 mins'), 120);
  assert.equal(seconds('30 sec'), 30);
  assert.equal(seconds('90 seconds'), 90);
  assert.equal(seconds('2 hours'), 7200);
  assert.equal(seconds('1 hr'), 3600);
});

test('several units add up', () => {
  assert.equal(seconds('1 hour 30 minutes'), 5400);
  assert.equal(seconds('1 hour 30 minutes 15 seconds'), 5415);
  assert.equal(seconds('one hour and thirty minutes'), 5400);
});

test('decimals are fractions of the unit, not a different number', () => {
  assert.equal(seconds('1.5 hours'), 5400);       // used to be read as 5 hours
  assert.equal(seconds('2.5 minutes'), 150);
  assert.equal(seconds('0.5 hours'), 1800);
});

test('number words and "a / an"', () => {
  assert.equal(seconds('five minutes'), 300);
  assert.equal(seconds('an hour'), 3600);
  assert.equal(seconds('a minute'), 60);
  assert.equal(seconds('twenty seconds'), 20);
});

test('halves and quarters', () => {
  assert.equal(seconds('half an hour'), 1800);
  assert.equal(seconds('half a minute'), 30);
  assert.equal(seconds('a quarter of an hour'), 900);
  assert.equal(seconds('two and a half minutes'), 150);
  assert.equal(seconds('an hour and a half'), 5400);
});

test('a bare number means minutes', () => {
  assert.equal(seconds('10'), 600);
});

test('text after the duration is ignored', () => {
  assert.equal(seconds('5 minutes to call mom'), 300);
});

test('zero, absurd and unusable durations are refused', () => {
  assert.deepEqual(parseDuration('0 minutes'), { ok: false, reason: 'zero' });
  assert.deepEqual(parseDuration('99999999 hours'), { ok: false, reason: 'too-long' });
  assert.deepEqual(parseDuration('25 hours'), { ok: false, reason: 'too-long' });
  assert.deepEqual(parseDuration('for the pasta'), { ok: false, reason: 'unparseable' });
  assert.deepEqual(parseDuration(''), { ok: false, reason: 'unparseable' });
  assert.equal(seconds('24 hours'), MAX_SECONDS);
});

test('formatDuration words', () => {
  assert.equal(formatDuration(1), '1 second');
  assert.equal(formatDuration(60), '1 minute');
  assert.equal(formatDuration(300), '5 minutes');
  assert.equal(formatDuration(3600), '1 hour');
  assert.equal(formatDuration(5400), '1 hour and 30 minutes');
  assert.equal(formatDuration(5415), '1 hour, 30 minutes and 15 seconds');
  assert.equal(formatDuration(90), '1 minute and 30 seconds');
});
