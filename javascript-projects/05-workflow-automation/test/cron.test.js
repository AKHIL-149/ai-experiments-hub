const { test } = require('node:test');
const assert = require('node:assert/strict');

const { parseCron, nextRun, nextRuns, describeCron, localMinuteKey, CronError } = require('../src/cron');

// Dates are built from local parts so the expectations do not depend on the machine's time zone
const at = (y, mo, d, h = 0, mi = 0) => new Date(y, mo - 1, d, h, mi, 0, 0);
const key = (date) => localMinuteKey(date);
const withTimeZone = (zone, fn) => {
  const before = process.env.TZ;
  process.env.TZ = zone;
  try { return fn(); } finally { if (before === undefined) delete process.env.TZ; else process.env.TZ = before; }
};

// ---------------------------------------------------------------- parsing

test('parses wildcards, lists, ranges and steps in every field', () => {
  const c = parseCron('*/15 9-17 1,15 jan-mar mon-fri');
  assert.deepEqual([...c.minute], [0, 15, 30, 45]);
  assert.deepEqual([...c.hour], [9, 10, 11, 12, 13, 14, 15, 16, 17]);
  assert.deepEqual([...c.dom], [1, 15]);
  assert.deepEqual([...c.month], [1, 2, 3]);
  assert.deepEqual([...c.dow], [1, 2, 3, 4, 5]);
});

test('the largest useful step in each field is accepted', () => {
  assert.deepEqual([...parseCron('*/59 * * * *').minute], [0, 59]);
  assert.deepEqual([...parseCron('* */23 * * *').hour], [0, 23]);
  assert.deepEqual([...parseCron('0-10/10 * * * *').minute], [0, 10]);
  assert.deepEqual([...parseCron('* * * * */6').dow], [0, 6]);
  assert.deepEqual([...parseCron('50/9 * * * *').minute], [50, 59]);
});

test('step forms: a-b/n and a/n (from a to the end)', () => {
  assert.deepEqual([...parseCron('10-30/10 * * * *').minute], [10, 20, 30]);
  assert.deepEqual([...parseCron('45/5 * * * *').minute], [45, 50, 55]);
  assert.deepEqual([...parseCron('0 */6 * * *').hour], [0, 6, 12, 18]);
});

test('day names and numbers, with 7 meaning Sunday', () => {
  assert.deepEqual([...parseCron('0 0 * * sun').dow], [0]);
  assert.deepEqual([...parseCron('0 0 * * 7').dow], [0]);
  assert.deepEqual([...parseCron('0 0 * * 0,6').dow].sort(), [0, 6]);
  assert.deepEqual([...parseCron('0 0 * * 6-7').dow].sort(), [0, 6]);   // Saturday and Sunday
});

test('extra spaces are fine and fields are case-insensitive', () => {
  assert.deepEqual([...parseCron('  5   4  *  *  MON ').dow], [1]);
});

const invalid = [
  ['', /5 fields/], ['* * * *', /5 fields.*\(got 4\)$/], ['* * * * * *', /\(got 6\)\. Seconds are not supported/], ['0 0 * * sat-sun', /ends before it starts/], ['0 0 0 * * *', /5 fields/],
  ['60 * * * *', /minute.*0.*59/], ['-1 * * * *', /minute/], ['* 24 * * *', /hour.*0.*23/],
  ['* * 0 * *', /day of month.*1.*31/], ['* * 32 * *', /day of month/], ['* * * 13 *', /month.*1.*12/],
  ['* * * 0 *', /month/], ['* * * * 8', /day of week.*0.*7/], ['*/0 * * * *', /step/], ['*/-5 * * * *', /minute/],
  ['5-1 * * * *', /range.*5-1/], ['a * * * *', /minute/], ['1,,2 * * * *', /minute/], ['1- * * * *', /minute/],
  ['*/90 * * * *', /step of 90, which is larger than the minute field/], ['*/60 * * * *', /step of 60, which is larger/], ['0 */24 * * *', /step of 24, which is larger than the hour field/],
  ['0-10/20 * * * *', /step of 20, which is larger than the range 0-10/], ['* * */32 * *', /step of 32/], ['* * * */12 *', /step of 12/], ['* * * * */7', /step of 7/],
  ['@hourly', /5 fields/], ['* * * foo *', /month/], ['*/2/3 * * * *', /minute/], ['1.5 * * * *', /minute/],
];
for (const [expr, message] of invalid) {
  test(`rejects ${JSON.stringify(expr)}`, () => {
    assert.throws(() => parseCron(expr), (error) => error instanceof CronError && message.test(error.message), expr);
  });
}

test('rejects non-strings', () => {
  for (const bad of [null, undefined, 5, {}, []]) assert.throws(() => parseCron(bad), CronError);
});

// ---------------------------------------------------------------- next run

test('the next run is strictly after the given time', () => {
  assert.equal(nextRun('*/5 * * * *', at(2026, 10, 30, 9, 5)).getTime(), at(2026, 10, 30, 9, 10).getTime());
  assert.equal(nextRun('*/5 * * * *', at(2026, 10, 30, 9, 4)).getTime(), at(2026, 10, 30, 9, 5).getTime());
  const withSeconds = new Date(2026, 9, 30, 9, 5, 42, 500);
  assert.equal(nextRun('* * * * *', withSeconds).getTime(), at(2026, 10, 30, 9, 6).getTime());
});

test('daily, weekday and monthly schedules', () => {
  assert.equal(nextRun('30 9 * * *', at(2026, 10, 30, 9, 30)).getTime(), at(2026, 10, 31, 9, 30).getTime());
  // Fri 30 Oct 2026 16:00 -> next weekday 09:30 is Mon 2 Nov
  assert.equal(nextRun('30 9 * * 1-5', at(2026, 10, 30, 16)).getTime(), at(2026, 11, 2, 9, 30).getTime());
  assert.equal(nextRun('0 8 15 * *', at(2026, 10, 30)).getTime(), at(2026, 11, 15, 8).getTime());
});

test('rolls over month and year boundaries', () => {
  assert.equal(nextRun('0 0 1 1 *', at(2026, 6, 1)).getTime(), at(2027, 1, 1).getTime());
  assert.equal(nextRun('59 23 31 12 *', at(2026, 12, 31, 23, 59)).getTime(), at(2027, 12, 31, 23, 59).getTime());
});

test('a day that does not exist in a month is skipped; leap days wait for a leap year', () => {
  assert.equal(nextRun('0 0 31 * *', at(2026, 4, 1)).getTime(), at(2026, 5, 31).getTime());   // April has 30 days
  assert.equal(nextRun('0 0 29 2 *', at(2026, 3, 1)).getTime(), at(2028, 2, 29).getTime());
  assert.equal(nextRun('0 0 30 2 *', at(2026, 1, 1)), null);                                    // never happens
});

test('day of month and day of week together mean "either", like standard cron', () => {
  // the 13th OR any Friday: after Thu 29 Oct the next match is Fri 30 Oct
  assert.equal(nextRun('0 0 13 * 5', at(2026, 10, 29, 12)).getTime(), at(2026, 10, 30).getTime());
  // only day-of-week restricted ('*' for day of month): AND, so just Fridays
  assert.equal(nextRun('0 0 * * 5', at(2026, 10, 31)).getTime(), at(2026, 11, 6).getTime());
  // a step on the star still counts as a star
  assert.equal(nextRun('0 0 */2 * 1', at(2026, 10, 1)).getTime(), at(2026, 10, 5).getTime());   // odd days AND Monday: Oct 5
});

test('nextRuns lists several in order', () => {
  const runs = nextRuns('0 */6 * * *', at(2026, 10, 30, 1), 4).map(d => d.getTime());
  assert.deepEqual(runs, [at(2026, 10, 30, 6), at(2026, 10, 30, 12), at(2026, 10, 30, 18), at(2026, 10, 31)].map(d => d.getTime()));
});

test('skipping a local minute (used after a run, for repeated clock times)', () => {
  const after = at(2026, 10, 30, 9, 29);
  const first = nextRun('30 9 * * *', after);
  assert.equal(nextRun('30 9 * * *', after, { skipLocalMinute: key(first) }).getTime(), at(2026, 10, 31, 9, 30).getTime());
});

test('daylight saving: a time that does not exist is skipped that day', () => {
  withTimeZone('America/New_York', () => {
    // 2026-03-08 02:30 does not exist (clocks jump 02:00 -> 03:00)
    const next = nextRun('30 2 * * *', new Date(2026, 2, 8, 0, 0));
    assert.equal(next.getTime(), new Date(2026, 2, 9, 2, 30).getTime());
  });
});

test('daylight saving: a repeated hour fires once when the last run is passed in', () => {
  withTimeZone('America/New_York', () => {
    // 2026-11-01 01:30 happens twice (EDT then EST)
    const first = nextRun('30 1 * * *', new Date(2026, 10, 1, 0, 0));
    assert.equal(first.getHours(), 1);
    const second = nextRun('30 1 * * *', first, { skipLocalMinute: key(first) });
    assert.equal(second.getTime(), new Date(2026, 10, 2, 1, 30).getTime());
    // without the guard the repeated 01:30 would run again an hour later
    assert.equal(nextRun('30 1 * * *', first).getTime() - first.getTime(), 3600 * 1000);
  });
});

test('works in a zone ahead of UTC too', () => {
  withTimeZone('Asia/Kolkata', () => {
    assert.equal(nextRun('0 9 * * *', new Date(2026, 9, 30, 9, 0)).getTime(), new Date(2026, 9, 31, 9, 0).getTime());
  });
});

test('a search for an impossible schedule returns null quickly', () => {
  const started = Date.now();
  assert.equal(nextRun('0 0 31 2 *', at(2026, 1, 1)), null);
  assert.ok(Date.now() - started < 500, 'search should jump over months, not step minute by minute');
});

// ---------------------------------------------------------------- description

test('describeCron names the common schedules and falls back to the expression', () => {
  const cases = {
    '* * * * *': 'Every minute',
    '*/5 * * * *': 'Every 5 minutes',
    '0 * * * *': 'Every hour',
    '15 * * * *': 'Every hour at :15',
    '0 */4 * * *': 'Every 4 hours',
    '30 9 * * *': 'Every day at 09:30',
    '30 9 * * 1-5': 'Weekdays at 09:30',
    '0 18 * * 5': 'Every Friday at 18:00',
    '0 8 15 * *': 'Day 15 of every month at 08:00',
    '5 4 * * 0,6': 'Custom schedule (5 4 * * 0,6)',
    '*/10 9-16 * * 1-5': 'Custom schedule (*/10 9-16 * * 1-5)',
    // steps that do not divide the hour or day evenly are not "every N": the gap at the end is shorter
    '*/7 * * * *': 'Custom schedule (*/7 * * * *)',
    '*/25 * * * *': 'Custom schedule (*/25 * * * *)',
    '0 */5 * * *': 'Custom schedule (0 */5 * * *)',
    '*/20 * * * *': 'Every 20 minutes',
    '0 */8 * * *': 'Every 8 hours',
  };
  for (const [expr, text] of Object.entries(cases)) assert.equal(describeCron(expr), text, expr);
});

test('localMinuteKey is a sortable local date and time', () => {
  assert.equal(localMinuteKey(new Date(2026, 0, 5, 7, 3, 59)), '2026-01-05 07:03');
});
