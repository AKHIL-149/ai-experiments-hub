const { test } = require('node:test');
const assert = require('node:assert/strict');

const { Scheduler, ScheduleValidationError, describeFailure } = require('../src/Scheduler');

const quietLog = { info() {}, warn() {}, error() {} };

function deferred() {
  let resolve;
  const promise = new Promise(r => { resolve = r; });
  return { promise, resolve };
}

function setup(options = {}) {
  let current = options.start || new Date(2026, 9, 30, 9, 0, 0);   // Fri 30 Oct 2026 09:00 local
  const clock = {
    now: () => new Date(current),
    set: (date) => { current = date; },
    advanceMinutes: (n) => { current = new Date(current.getTime() + n * 60000); },
  };
  const store = {
    schedules: options.initial || [], saves: 0, failSave: false,
    async load() { return { schedules: structuredClone(this.schedules), warnings: [] }; },
    async save(list) {
      if (this.failSave) throw new Error('disk full');
      this.schedules = structuredClone(list);
      this.saves += 1;
    },
  };
  const starts = [];
  const start = async (workflowId, inputData, runOptions) => {
    if (options.startError) throw options.startError;
    if (options.slowStart) await options.slowStart.promise;
    const done = deferred();
    const run = { workflowId, inputData, options: runOptions, executionId: `exec-${starts.length + 1}`, finish: done.resolve };
    starts.push(run);
    return { executionId: run.executionId, done: done.promise };
  };
  const checkWorkflow = async (workflowId, inputData) => (options.problems ? options.problems(workflowId, inputData) : []);
  const scheduler = new Scheduler({
    store, start, checkWorkflow, now: clock.now, tickMs: 1000, maxSchedules: 3,
    lateToleranceMs: 120000, log: quietLog, pauseAfterFailures: options.pauseAfterFailures ?? 0,
  });
  return { scheduler, store, starts, clock };
}

const valid = (extra = {}) => ({ name: 'Check prices', workflow_id: 'price-alert', cron: '*/5 * * * *', input_data: { a: 1 }, ...extra });
const flush = () => new Promise(r => setImmediate(r));
const withTimeZone = async (zone, fn) => {
  const before = process.env.TZ;
  process.env.TZ = zone;
  try { return await fn(); } finally { if (before === undefined) delete process.env.TZ; else process.env.TZ = before; }
};

// ------------------------------------------------------------------ creating

test('create stores the schedule, works out its next run and saves it', async () => {
  const { scheduler, store } = setup();
  await scheduler.init();
  const view = await scheduler.create(valid());
  assert.match(view.id, /^sch-[0-9a-f]{8}$/);
  assert.equal(view.enabled, true);
  assert.equal(view.next_run, new Date(2026, 9, 30, 9, 5).toISOString());
  assert.equal(view.description, 'Every 5 minutes');
  assert.equal(view.run_count, 0);
  assert.equal(store.schedules.length, 1);
  assert.equal(store.schedules[0].id, view.id);
});

test('a disabled schedule has no next run', async () => {
  const { scheduler } = setup();
  await scheduler.init();
  const view = await scheduler.create(valid({ enabled: false }));
  assert.equal(view.next_run, null);
});

const badInputs = [
  ['an empty name', { name: '  ' }, /name is required/i],
  ['a name over 80 characters', { name: 'x'.repeat(81) }, /name.*80/i],
  ['a bad workflow id', { workflow_id: '../etc' }, /workflow/i],
  ['a missing workflow id', { workflow_id: undefined }, /workflow/i],
  ['an invalid cron', { cron: '99 * * * *' }, /minute field must be between 0 and 59/],
  ['six cron fields', { cron: '* * * * * *' }, /5 fields/],
  ['input_data that is a list', { input_data: [1] }, /input_data must be an object/i],
  ['input_data that is text', { input_data: 'x' }, /input_data must be an object/i],
  ['huge input_data', { input_data: { big: 'x'.repeat(25000) } }, /too large/i],
  ['a bad model name', { model: 'bad name; x' }, /model must be/i],
  ['a non-boolean enabled', { enabled: 'yes' }, /enabled must be/i],
];
for (const [label, patch, message] of badInputs) {
  test(`create rejects ${label}`, async () => {
    const { scheduler, store } = setup();
    await scheduler.init();
    await assert.rejects(scheduler.create(valid(patch)), (error) =>
      error instanceof ScheduleValidationError && error.details.some(d => message.test(d)), label);
    assert.equal(store.schedules.length, 0);
  });
}

test('create reports every problem at once', async () => {
  const { scheduler } = setup();
  await scheduler.init();
  await assert.rejects(scheduler.create({ name: '', workflow_id: '', cron: 'nope' }), (error) => error.details.length >= 3);
});

test('create asks the workflow check about the inputs and passes its problems on', async () => {
  const { scheduler } = setup({ problems: (wf, input) => (input.a ? [] : ['Missing input: a']) });
  await scheduler.init();
  await assert.rejects(scheduler.create(valid({ input_data: {} })), (error) => error.details.includes('Missing input: a'));
  await scheduler.create(valid());
});

test('there is a limit on how many schedules exist', async () => {
  const { scheduler } = setup();
  await scheduler.init();
  for (let i = 0; i < 3; i++) await scheduler.create(valid({ name: `s${i}` }));
  await assert.rejects(scheduler.create(valid()), (error) => /at most 3 schedules/i.test(error.details[0]));
});

test('parallel creates cannot exceed the limit', async () => {
  const { scheduler } = setup();
  await scheduler.init();
  const results = await Promise.allSettled(Array.from({ length: 6 }, (_, i) => scheduler.create(valid({ name: `p${i}` }))));
  assert.equal(results.filter(r => r.status === 'fulfilled').length, 3);
  assert.equal(scheduler.list().length, 3);
});

test('a failed save rolls the change back', async () => {
  const { scheduler, store } = setup();
  await scheduler.init();
  store.failSave = true;
  await assert.rejects(scheduler.create(valid()), /disk full/);
  assert.equal(scheduler.list().length, 0);
});

// ------------------------------------------------------------------ firing

test('a due schedule is started once, with the right inputs and trigger, and moves to its next time', async () => {
  const { scheduler, starts, clock } = setup();
  await scheduler.init();
  const { id } = await scheduler.create(valid({ model: 'qwen3:8b' }));
  clock.set(new Date(2026, 9, 30, 9, 5, 4));
  await scheduler.tick();

  assert.equal(starts.length, 1);
  assert.deepEqual(starts[0].inputData, { a: 1 });
  assert.equal(starts[0].workflowId, 'price-alert');
  assert.deepEqual(starts[0].options, { model: 'qwen3:8b', triggerType: 'schedule', scheduleId: id });
  const view = scheduler.get(id);
  assert.equal(view.last_status, 'running');
  assert.equal(view.last_execution_id, 'exec-1');
  assert.equal(view.run_count, 1);
  assert.equal(view.next_run, new Date(2026, 9, 30, 9, 10).toISOString());

  await scheduler.tick();                           // same moment again: nothing more is due
  assert.equal(starts.length, 1);
});

test('nothing starts before the time', async () => {
  const { scheduler, starts, clock } = setup();
  await scheduler.init();
  await scheduler.create(valid());
  clock.set(new Date(2026, 9, 30, 9, 4, 59));
  await scheduler.tick();
  assert.equal(starts.length, 0);
});

test('a disabled schedule never starts; enabling it does not run it at once', async () => {
  const { scheduler, starts, clock } = setup();
  await scheduler.init();
  const { id } = await scheduler.create(valid({ enabled: false }));
  clock.advanceMinutes(30);
  await scheduler.tick();
  assert.equal(starts.length, 0);

  const enabled = await scheduler.update(id, { enabled: true });
  assert.equal(enabled.next_run, new Date(2026, 9, 30, 9, 35).toISOString());   // next slot after "now", no catch-up
  await scheduler.tick();
  assert.equal(starts.length, 0);

  await scheduler.update(id, { enabled: false });
  assert.equal(scheduler.get(id).next_run, null);
});

test('a finished run updates the status, the run counters and the failure streak', async () => {
  const { scheduler, starts, clock } = setup();
  await scheduler.init();
  const { id } = await scheduler.create(valid({ cron: '* * * * *' }));
  const fire = async (status) => {
    clock.advanceMinutes(1);
    await scheduler.tick();
    starts.at(-1).finish(status);
    await flush();
  };
  await fire('failed');
  assert.equal(scheduler.get(id).last_status, 'failed');
  assert.equal(scheduler.get(id).consecutive_failures, 1);
  await fire('failed');
  assert.equal(scheduler.get(id).consecutive_failures, 2);
  await fire('completed');
  assert.equal(scheduler.get(id).last_status, 'completed');
  assert.equal(scheduler.get(id).consecutive_failures, 0);
  assert.equal(scheduler.get(id).run_count, 3);
  assert.equal(scheduler.get(id).running, false);
});

test('a run still going when the next one is due makes the schedule skip, and says why', async () => {
  const { scheduler, starts, clock } = setup();
  await scheduler.init();
  const { id } = await scheduler.create(valid({ cron: '* * * * *' }));
  clock.advanceMinutes(1);
  await scheduler.tick();                           // run 1 starts and stays running
  clock.advanceMinutes(1);
  await scheduler.tick();                           // due again: skipped
  assert.equal(starts.length, 1);
  assert.match(scheduler.get(id).last_message, /previous run is still in progress/i);
  assert.equal(scheduler.get(id).running, true);
  assert.equal(scheduler.get(id).next_run, new Date(2026, 9, 30, 9, 3).toISOString());

  starts[0].finish('completed');
  await flush();
  clock.advanceMinutes(1);
  await scheduler.tick();                           // free again
  assert.equal(starts.length, 2);
});

test('when the server is at its limit the run is skipped (not failed) with the reason', async () => {
  const busy = Object.assign(new Error('Too many running executions (limit 5)'), { code: 'BUSY' });
  const { scheduler, clock } = setup({ startError: busy });
  await scheduler.init();
  const { id } = await scheduler.create(valid({ cron: '* * * * *' }));
  clock.advanceMinutes(1);
  await scheduler.tick();
  const view = scheduler.get(id);
  assert.equal(view.last_status, 'skipped');
  assert.match(view.last_message, /too many running executions/i);
  assert.equal(view.consecutive_failures, 0);
  assert.equal(view.run_count, 0);
  assert.equal(view.next_run, new Date(2026, 9, 30, 9, 2).toISOString());
});

test('a run that cannot even start is an error and counts towards the failure streak', async () => {
  const { scheduler, clock } = setup({ startError: new Error('Workflow not found: price-alert') });
  await scheduler.init();
  const { id } = await scheduler.create(valid({ cron: '* * * * *' }));
  clock.advanceMinutes(1);
  await scheduler.tick();
  const view = scheduler.get(id);
  assert.equal(view.last_status, 'error');
  assert.match(view.last_message, /Workflow not found/);
  assert.equal(view.consecutive_failures, 1);
});

test('a run that is far too late (computer asleep, long pause) is skipped, not run as a stale check', async () => {
  const { scheduler, starts, clock } = setup();
  await scheduler.init();
  const { id } = await scheduler.create(valid({ cron: '0 10 * * *' }));      // due 10:00
  clock.set(new Date(2026, 9, 30, 14, 30));                                   // woke up at 14:30
  await scheduler.tick();
  assert.equal(starts.length, 0);
  const view = scheduler.get(id);
  assert.equal(view.last_status, 'missed');
  assert.match(view.last_message, /missed the run due at/i);
  assert.equal(view.next_run, new Date(2026, 9, 31, 10, 0).toISOString());
});

test('a run only slightly late still happens', async () => {
  const { scheduler, starts, clock } = setup();
  await scheduler.init();
  await scheduler.create(valid({ cron: '0 10 * * *' }));
  clock.set(new Date(2026, 9, 30, 10, 1, 30));                                // 90 s late, within tolerance
  await scheduler.tick();
  assert.equal(starts.length, 1);
});

test('two ticks at once start a due schedule only once', async () => {
  const gate = deferred();
  const { scheduler, starts, clock } = setup({ slowStart: gate });
  await scheduler.init();
  await scheduler.create(valid({ cron: '* * * * *' }));
  clock.advanceMinutes(1);
  const first = scheduler.tick();
  const second = scheduler.tick();
  gate.resolve();
  await Promise.all([first, second]);
  assert.equal(starts.length, 1);
});

test('after daylight saving repeats an hour a clock time is not run twice', async () => {
  await withTimeZone('America/New_York', async () => {
    const { scheduler, starts, clock } = setup({ start: new Date(2026, 10, 1, 0, 0) });
    await scheduler.init();
    const { id } = await scheduler.create(valid({ cron: '30 1 * * *' }));
    clock.set(new Date(scheduler.get(id).next_run));
    await scheduler.tick();
    assert.equal(starts.length, 1);
    assert.equal(scheduler.get(id).next_run, new Date(2026, 10, 2, 1, 30).toISOString());   // not the repeated 01:30
  });
});

// ------------------------------------------------------------------ run now

test('run now starts immediately as a manual run, even when disabled, and keeps the schedule', async () => {
  const { scheduler, starts } = setup();
  await scheduler.init();
  const { id, next_run } = await scheduler.create(valid({ enabled: false }));
  const view = await scheduler.runNow(id);
  assert.equal(starts.length, 1);
  assert.equal(starts[0].options.triggerType, 'schedule-manual');
  assert.equal(starts[0].options.scheduleId, id);
  assert.equal(view.last_status, 'running');
  assert.equal(view.next_run, next_run);
});

test('run now refuses while the schedule is already running; unknown ids are not found', async () => {
  const { scheduler } = setup();
  await scheduler.init();
  const { id } = await scheduler.create(valid());
  await scheduler.runNow(id);
  await assert.rejects(scheduler.runNow(id), (error) => error.status === 409 && /already running/i.test(error.message));
  await assert.rejects(scheduler.runNow('sch-nope'), (error) => error.status === 404);
});

test('run now reports a busy server instead of hiding it', async () => {
  const busy = Object.assign(new Error('Too many running executions (limit 5)'), { code: 'BUSY' });
  const { scheduler } = setup({ startError: busy });
  await scheduler.init();
  const { id } = await scheduler.create(valid());
  await assert.rejects(scheduler.runNow(id), (error) => error.status === 429);
});

// ------------------------------------------------------------------ update / remove

test('update changes only what is given, and a new cron moves the next run', async () => {
  const { scheduler } = setup();
  await scheduler.init();
  const { id } = await scheduler.create(valid());
  const renamed = await scheduler.update(id, { name: 'Renamed' });
  assert.equal(renamed.name, 'Renamed');
  assert.equal(renamed.cron, '*/5 * * * *');
  const moved = await scheduler.update(id, { cron: '0 10 * * *' });
  assert.equal(moved.next_run, new Date(2026, 9, 30, 10, 0).toISOString());
  assert.equal(moved.description, 'Every day at 10:00');
});

test('an invalid update is rejected and changes nothing', async () => {
  const { scheduler, store } = setup();
  await scheduler.init();
  const { id } = await scheduler.create(valid());
  await assert.rejects(scheduler.update(id, { cron: 'bad', name: 'Changed' }), ScheduleValidationError);
  assert.equal(scheduler.get(id).name, 'Check prices');
  assert.equal(store.schedules[0].name, 'Check prices');
  await assert.rejects(scheduler.update('sch-nope', { name: 'x' }), (error) => error.status === 404);
});

test('changing the workflow or inputs runs the workflow check again', async () => {
  const { scheduler } = setup({ problems: (wf, input) => (input.ok ? [] : ['Missing input: ok']) });
  await scheduler.init();
  const { id } = await scheduler.create(valid({ input_data: { ok: 1 } }));
  await assert.rejects(scheduler.update(id, { input_data: {} }), (error) => error.details.includes('Missing input: ok'));
  await scheduler.update(id, { input_data: { ok: 2 } });
});

test('a schedule can still be paused, renamed or deleted after its workflow has been removed', async () => {
  let workflowExists = true;
  const { scheduler } = setup({ problems: () => (workflowExists ? [] : ['Workflow not found: price-alert']) });
  await scheduler.init();
  const { id } = await scheduler.create(valid());
  workflowExists = false;
  assert.equal((await scheduler.update(id, { enabled: false })).enabled, false);
  assert.equal((await scheduler.update(id, { name: 'Old alert' })).name, 'Old alert');
  assert.equal((await scheduler.update(id, { cron: '0 8 * * *' })).cron, '0 8 * * *');
  // but pointing it at a workflow that does not exist is refused
  await assert.rejects(scheduler.update(id, { workflow_id: 'gone' }), (error) => error.details.includes('Workflow not found: price-alert'));
  await scheduler.remove(id);
});

test('remove deletes the schedule and saves; unknown ids are not found', async () => {
  const { scheduler, store } = setup();
  await scheduler.init();
  const { id } = await scheduler.create(valid());
  await scheduler.remove(id);
  assert.equal(scheduler.list().length, 0);
  assert.equal(store.schedules.length, 0);
  await assert.rejects(scheduler.remove(id), (error) => error.status === 404);
});

test('removing a schedule while its run is going does not break when the run finishes', async () => {
  const { scheduler, starts } = setup();
  await scheduler.init();
  const { id } = await scheduler.create(valid());
  await scheduler.runNow(id);
  await scheduler.remove(id);
  starts[0].finish('completed');
  await flush();
  assert.equal(scheduler.list().length, 0);
});

// ------------------------------------------------------------------ restarts

test('after a restart the schedules come back with their history', async () => {
  const first = setup();
  await first.scheduler.init();
  const { id } = await first.scheduler.create(valid({ cron: '* * * * *' }));
  first.clock.advanceMinutes(1);
  await first.scheduler.tick();
  first.starts[0].finish('completed');
  await flush();

  const second = setup({ initial: first.store.schedules, start: first.clock.now() });
  await second.scheduler.init();
  const view = second.scheduler.get(id);
  assert.equal(view.name, 'Check prices');
  assert.equal(view.last_status, 'completed');
  assert.equal(view.run_count, 1);
});

test('a run that was in progress when the server stopped is shown as interrupted, not running forever', async () => {
  const first = setup();
  await first.scheduler.init();
  const { id } = await first.scheduler.create(valid());
  await first.scheduler.runNow(id);                      // never finishes: the server "dies"
  const second = setup({ initial: first.store.schedules });
  await second.scheduler.init();
  const view = second.scheduler.get(id);
  assert.equal(view.last_status, 'failed');
  assert.match(view.last_message, /interrupted/i);
  assert.equal(view.running, false);
  assert.equal(view.consecutive_failures, 1);
});

test('runs missed while the server was off are skipped, noted, and not made up', async () => {
  const first = setup();
  await first.scheduler.init();
  const { id } = await first.scheduler.create(valid({ cron: '0 10 * * *' }));
  assert.equal(first.store.schedules[0].next_run, new Date(2026, 9, 30, 10, 0).toISOString());

  const second = setup({ initial: first.store.schedules, start: new Date(2026, 9, 31, 8, 0) });   // back next morning
  await second.scheduler.init();
  await second.scheduler.tick();
  assert.equal(second.starts.length, 0);
  const view = second.scheduler.get(id);
  assert.equal(view.last_status, 'missed');
  assert.match(view.last_message, /server was not running/i);
  assert.equal(view.next_run, new Date(2026, 9, 31, 10, 0).toISOString());
});

test('a run due a moment before the restart still happens', async () => {
  const first = setup();
  await first.scheduler.init();
  await first.scheduler.create(valid({ cron: '0 10 * * *' }));
  const second = setup({ initial: first.store.schedules, start: new Date(2026, 9, 30, 10, 0, 40) });
  await second.scheduler.init();
  await second.scheduler.tick();
  assert.equal(second.starts.length, 1);
});

test('init gives enabled schedules without a stored time a next run, and disabled ones none', async () => {
  const stored = [
    { id: 'sch-a', name: 'A', workflow_id: 'w', cron: '30 9 * * *', input_data: {}, enabled: true },
    { id: 'sch-b', name: 'B', workflow_id: 'w', cron: '30 9 * * *', input_data: {}, enabled: false, next_run: '2026-10-30T14:00:00.000Z' },
  ];
  const { scheduler } = setup({ initial: stored });
  await scheduler.init();
  assert.equal(scheduler.get('sch-a').next_run, new Date(2026, 9, 30, 9, 30).toISOString());
  assert.equal(scheduler.get('sch-b').next_run, null);
});

test('a stored schedule with an invalid cron is kept but never runs, and is flagged', async () => {
  const stored = [{ id: 'sch-x', name: 'X', workflow_id: 'w', cron: 'garbage', input_data: {}, enabled: true }];
  const { scheduler, starts, clock } = setup({ initial: stored });
  await scheduler.init();
  clock.advanceMinutes(5);
  await scheduler.tick();
  assert.equal(starts.length, 0);
  const view = scheduler.get('sch-x');
  assert.equal(view.next_run, null);
  assert.match(view.last_message, /schedule is not valid/i);
});

// ------------------------------------------------------------------ timer

test('the timer starts and stops cleanly and does not keep the process alive', async () => {
  const { scheduler } = setup();
  await scheduler.init();
  try {
    scheduler.startTimer();
    assert.ok(scheduler.timer);
    assert.equal(scheduler.timer.hasRef(), false);
    const first = scheduler.timer;
    scheduler.startTimer();                     // calling it twice does not create a second timer
    assert.equal(scheduler.timer, first);
  } finally {
    scheduler.stopTimer();                      // a failing assertion must not leave a timer running
  }
  assert.equal(scheduler.timer, null);
});

test('list returns the schedules newest first with their view fields', async () => {
  const { scheduler, clock } = setup();
  await scheduler.init();
  await scheduler.create(valid({ name: 'first' }));
  clock.advanceMinutes(1);
  await scheduler.create(valid({ name: 'second' }));
  assert.deepEqual(scheduler.list().map(s => s.name), ['second', 'first']);
  for (const key of ['id', 'name', 'workflow_id', 'cron', 'description', 'input_data', 'model', 'enabled', 'next_run',
    'last_run_at', 'last_status', 'last_message', 'last_execution_id', 'run_count', 'consecutive_failures', 'running']) {
    assert.ok(key in scheduler.list()[0], key);
  }
});


// ------------------------------------------------------------------ why a run failed, and pausing a broken schedule

test('a finished run can report why it failed, and that reason is shown on the schedule', async () => {
  const { scheduler, starts, clock } = setup();
  await scheduler.init();
  const { id } = await scheduler.create(valid({ cron: '* * * * *' }));
  clock.advanceMinutes(1);
  await scheduler.tick();
  starts[0].finish({ status: 'failed', message: 'Step "read_portfolio" failed: File not found: data/x.csv' });
  await flush();
  const view = scheduler.get(id);
  assert.equal(view.last_status, 'failed');
  assert.equal(view.last_message, 'Step "read_portfolio" failed: File not found: data/x.csv');
  assert.equal(view.consecutive_failures, 1);

  clock.advanceMinutes(1);
  await scheduler.tick();
  starts[1].finish({ status: 'completed', message: '' });
  await flush();
  assert.equal(scheduler.get(id).last_status, 'completed');
  assert.equal(scheduler.get(id).last_message, '', 'a success clears the old reason');
});

test('after too many failures in a row the schedule pauses itself and says so', async () => {
  const { scheduler, starts, clock } = setup({ pauseAfterFailures: 3 });
  await scheduler.init();
  const { id } = await scheduler.create(valid({ cron: '* * * * *' }));
  for (let i = 0; i < 3; i++) {
    clock.advanceMinutes(1);
    await scheduler.tick();
    starts[i].finish({ status: 'failed', message: 'File not found' });
    await flush();
  }
  const view = scheduler.get(id);
  assert.equal(view.enabled, false);
  assert.equal(view.next_run, null);
  assert.equal(view.consecutive_failures, 3);
  assert.match(view.last_message, /File not found/);
  assert.match(view.last_message, /Paused automatically after 3 failed runs in a row/);

  clock.advanceMinutes(5);
  await scheduler.tick();
  assert.equal(starts.length, 3, 'a paused schedule no longer runs');
});

test('failures below the limit, or interrupted by a success, do not pause it', async () => {
  const { scheduler, starts, clock } = setup({ pauseAfterFailures: 3 });
  await scheduler.init();
  const { id } = await scheduler.create(valid({ cron: '* * * * *' }));
  const run = async (status) => { clock.advanceMinutes(1); await scheduler.tick(); starts.at(-1).finish(status); await flush(); };
  await run('failed'); await run('failed'); await run('completed'); await run('failed'); await run('failed');
  assert.equal(scheduler.get(id).enabled, true);
  assert.equal(scheduler.get(id).consecutive_failures, 2);
});

test('runs that cannot even start count towards pausing too', async () => {
  const { scheduler, clock } = setup({ pauseAfterFailures: 2, startError: new Error('Workflow not found: price-alert') });
  await scheduler.init();
  const { id } = await scheduler.create(valid({ cron: '* * * * *' }));
  for (let i = 0; i < 2; i++) { clock.advanceMinutes(1); await scheduler.tick(); }
  const view = scheduler.get(id);
  assert.equal(view.enabled, false);
  assert.match(view.last_message, /Workflow not found: price-alert/);
  assert.match(view.last_message, /Paused automatically after 2 failed runs in a row/);
});

test('skipped runs (busy server, overlap) never count as failures', async () => {
  const busy = Object.assign(new Error('Too many running executions (limit 5)'), { code: 'BUSY' });
  const { scheduler, clock } = setup({ pauseAfterFailures: 2, startError: busy });
  await scheduler.init();
  const { id } = await scheduler.create(valid({ cron: '* * * * *' }));
  for (let i = 0; i < 5; i++) { clock.advanceMinutes(1); await scheduler.tick(); }
  assert.equal(scheduler.get(id).enabled, true);
  assert.equal(scheduler.get(id).consecutive_failures, 0);
});

test('a limit of 0 turns automatic pausing off', async () => {
  const { scheduler, starts, clock } = setup({ pauseAfterFailures: 0 });
  await scheduler.init();
  const { id } = await scheduler.create(valid({ cron: '* * * * *' }));
  for (let i = 0; i < 12; i++) {
    clock.advanceMinutes(1);
    await scheduler.tick();
    starts[i].finish('failed');
    await flush();
  }
  assert.equal(scheduler.get(id).enabled, true);
  assert.equal(scheduler.get(id).consecutive_failures, 12);
});

test('turning a paused schedule back on starts a fresh failure count', async () => {
  const { scheduler, starts, clock } = setup({ pauseAfterFailures: 2 });
  await scheduler.init();
  const { id } = await scheduler.create(valid({ cron: '* * * * *' }));
  for (let i = 0; i < 2; i++) { clock.advanceMinutes(1); await scheduler.tick(); starts[i].finish('failed'); await flush(); }
  assert.equal(scheduler.get(id).enabled, false);

  const back = await scheduler.update(id, { enabled: true });
  assert.equal(back.enabled, true);
  assert.equal(back.consecutive_failures, 0);
  assert.equal(back.last_message, '');
  clock.advanceMinutes(1);
  await scheduler.tick();
  starts[2].finish('failed');
  await flush();
  assert.equal(scheduler.get(id).enabled, true, 'one new failure must not pause it again straight away');
});


test('describeFailure names the step that failed and why', () => {
  const execution = { result: { steps: [
    { step_id: 'read', success: true },
    { step_id: 'value', success: false, error: 'File not found: data/x.csv' },
    { step_id: 'save', success: false, error: 'later problem' },
  ] } };
  assert.equal(describeFailure(execution), 'Step "value" failed: File not found: data/x.csv');
});

test('describeFailure falls back to the run-level error, then to nothing', () => {
  assert.equal(describeFailure({ result: { error: 'Interrupted: the server stopped' } }), 'Interrupted: the server stopped');
  assert.equal(describeFailure({ result: { steps: [{ step_id: 'a', success: true }] } }), '');
  assert.equal(describeFailure({}), '');
});

test('describeFailure keeps long errors short', () => {
  const text = describeFailure({ result: { steps: [{ step_id: 'a', success: false, error: 'x'.repeat(1000) }] } });
  assert.ok(text.length <= 300 && text.endsWith('...'), `${text.length} chars`);
});
