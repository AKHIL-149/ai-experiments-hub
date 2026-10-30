const { test } = require('node:test');
const assert = require('node:assert/strict');
const express = require('express');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');

const { Scheduler } = require('../src/Scheduler');
const { registerScheduleRoutes, makeWorkflowChecker } = require('../src/scheduleRoutes');
const WorkflowEngine = require('../src/WorkflowEngine');
const ExecutionManager = require('../src/ExecutionManager');

const quietLog = { info() {}, warn() {}, error() {} };

async function withServer(fn, { problems = [], clock = new Date(2026, 9, 30, 9, 0, 0), runs } = {}) {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'wf-routes-'));
  const store = { schedules: [], async load() { return { schedules: [], warnings: [] }; }, async save(list) { this.schedules = structuredClone(list); } };
  const executionManager = new ExecutionManager(path.join(dir, 'exec'));
  const started = [];
  const scheduler = new Scheduler({
    store, now: () => new Date(clock), log: quietLog, maxSchedules: 3,
    checkWorkflow: async () => problems,
    start: async (workflowId, inputData, options) => {
      const execution = await executionManager.createExecution(workflowId, options.triggerType, inputData, { scheduleId: options.scheduleId });
      started.push({ workflowId, options });
      return { executionId: execution.execution_id, done: new Promise(() => {}) };
    },
  });
  await scheduler.init();
  const app = express();
  app.use(express.json());
  registerScheduleRoutes(app, { scheduler, executionManager });
  const server = await new Promise(resolve => { const s = app.listen(0, '127.0.0.1', () => resolve(s)); });
  const base = `http://127.0.0.1:${server.address().port}`;
  const call = async (method, url, payload) => {
    const response = await fetch(base + url, {
      method, headers: { 'Content-Type': 'application/json' }, body: payload === undefined ? undefined : JSON.stringify(payload),
    });
    const text = await response.text();
    return { status: response.status, body: text ? JSON.parse(text) : null };
  };
  try {
    await fn({ call, scheduler, started, executionManager });
  } finally {
    await new Promise(resolve => server.close(resolve));
    await fs.rm(dir, { recursive: true, force: true });
  }
}

const body = (extra = {}) => ({ name: 'Check prices', workflow_id: 'price-alert', cron: '*/5 * * * *', input_data: { a: 1 }, ...extra });

test('create, list, read, update and delete a schedule over HTTP', async () => {
  await withServer(async ({ call }) => {
    const created = await call('POST', '/api/schedules', body());
    assert.equal(created.status, 201);
    assert.match(created.body.id, /^sch-[0-9a-f]{8}$/);
    assert.equal(created.body.description, 'Every 5 minutes');

    const list = await call('GET', '/api/schedules');
    assert.equal(list.status, 200);
    assert.equal(list.body.schedules.length, 1);
    assert.ok(list.body.timezone && list.body.now);

    assert.equal((await call('GET', `/api/schedules/${created.body.id}`)).body.name, 'Check prices');

    const patched = await call('PATCH', `/api/schedules/${created.body.id}`, { name: 'Renamed', enabled: false });
    assert.equal(patched.status, 200);
    assert.deepEqual([patched.body.name, patched.body.enabled, patched.body.next_run], ['Renamed', false, null]);

    assert.equal((await call('DELETE', `/api/schedules/${created.body.id}`)).status, 204);
    assert.equal((await call('GET', `/api/schedules/${created.body.id}`)).status, 404);
    assert.equal((await call('GET', '/api/schedules')).body.schedules.length, 0);
  });
});

test('invalid schedules get a 400 that lists every problem', async () => {
  await withServer(async ({ call }) => {
    const bad = await call('POST', '/api/schedules', { name: '', workflow_id: 'w', cron: '61 * * * *' });
    assert.equal(bad.status, 400);
    assert.equal(bad.body.error, 'Schedule is not valid');
    assert.ok(bad.body.details.some(d => /Name is required/.test(d)));
    assert.ok(bad.body.details.some(d => /minute field must be between 0 and 59/.test(d)));
  });
});

test('problems with the workflow or its inputs are reported when saving', async () => {
  await withServer(async ({ call }) => {
    const bad = await call('POST', '/api/schedules', body());
    assert.equal(bad.status, 400);
    assert.deepEqual(bad.body.details, ['Missing input: threshold_pct']);
  }, { problems: ['Missing input: threshold_pct'] });
});

test('the limit on the number of schedules is a 400', async () => {
  await withServer(async ({ call }) => {
    for (let i = 0; i < 3; i++) assert.equal((await call('POST', '/api/schedules', body())).status, 201);
    const over = await call('POST', '/api/schedules', body());
    assert.equal(over.status, 400);
    assert.match(over.body.details[0], /at most 3 schedules/);
  });
});

test('unknown schedules are 404 on every route', async () => {
  await withServer(async ({ call }) => {
    for (const [method, url, payload] of [['GET', '/api/schedules/sch-00000000'], ['PATCH', '/api/schedules/sch-00000000', { name: 'x' }],
      ['DELETE', '/api/schedules/sch-00000000'], ['POST', '/api/schedules/sch-00000000/run'], ['GET', '/api/schedules/sch-00000000/runs']]) {
      const r = await call(method, url, payload);
      assert.equal(r.status, 404, `${method} ${url}`);
      assert.match(r.body.error, /Schedule not found/);
    }
  });
});

test('ids that could be a path are just not found', async () => {
  await withServer(async ({ call }) => {
    assert.equal((await call('GET', '/api/schedules/..%2F..%2Fetc')).status, 404);
    assert.equal((await call('GET', '/api/schedules/a.b')).status, 404);
  });
});

test('a request body that is not an object is a 400, not a crash', async () => {
  await withServer(async ({ call }) => {
    for (const [method, url] of [['POST', '/api/schedules'], ['POST', '/api/schedules/preview']]) {
      const r = await call(method, url, [1, 2]);
      assert.equal(r.status, 400, `${method} ${url}`);
      assert.match(r.body.error, /JSON object/);
    }
    const { body: created } = await call('POST', '/api/schedules', body());
    assert.equal((await call('PATCH', `/api/schedules/${created.id}`, ['x'])).status, 400);
  });
});

test('preview explains a cron expression and lists the next five runs without saving anything', async () => {
  await withServer(async ({ call }) => {
    const ok = await call('POST', '/api/schedules/preview', { cron: '30 9 * * 1-5' });
    assert.equal(ok.status, 200);
    assert.equal(ok.body.valid, true);
    assert.equal(ok.body.description, 'Weekdays at 09:30');
    assert.equal(ok.body.next.length, 5);
    assert.equal(ok.body.next[0], new Date(2026, 9, 30, 9, 30).toISOString());         // Fri, clock is 09:00
    assert.equal(ok.body.next[1], new Date(2026, 10, 2, 9, 30).toISOString());         // then Monday
    assert.equal((await call('GET', '/api/schedules')).body.schedules.length, 0);

    const bad = await call('POST', '/api/schedules/preview', { cron: '* * *' });
    assert.equal(bad.status, 200);
    assert.deepEqual([bad.body.valid, bad.body.next], [false, []]);
    assert.match(bad.body.error, /5 fields/);
  });
});

test('run now starts a manual run and records it on the schedule', async () => {
  await withServer(async ({ call, started }) => {
    const { body: created } = await call('POST', '/api/schedules', body());
    const run = await call('POST', `/api/schedules/${created.id}/run`);
    assert.equal(run.status, 202);
    assert.equal(run.body.last_status, 'running');
    assert.equal(run.body.running, true);
    assert.equal(started[0].options.triggerType, 'schedule-manual');
    const again = await call('POST', `/api/schedules/${created.id}/run`);
    assert.equal(again.status, 409);
    assert.match(again.body.error, /already running/);
  });
});

test('the runs of one schedule are listed, newest first, and no others', async () => {
  await withServer(async ({ call, scheduler, executionManager }) => {
    const a = (await call('POST', '/api/schedules', body({ name: 'A' }))).body;
    const b = (await call('POST', '/api/schedules', body({ name: 'B' }))).body;
    await executionManager.createExecution('w', 'schedule', {}, { scheduleId: a.id });
    await new Promise(r => setTimeout(r, 5));
    const latest = await executionManager.createExecution('w', 'schedule-manual', {}, { scheduleId: a.id });
    await executionManager.createExecution('w', 'schedule', {}, { scheduleId: b.id });
    await executionManager.createExecution('w', 'api', {});

    const runs = await call('GET', `/api/schedules/${a.id}/runs`);
    assert.equal(runs.status, 200);
    assert.equal(runs.body.length, 2);
    assert.equal(runs.body[0].execution_id, latest.execution_id);
    assert.deepEqual(Object.keys(runs.body[0]).sort(), ['execution_id', 'started_at', 'status', 'steps_completed', 'steps_failed', 'trigger_type']);  // no duration yet: not finished
    assert.equal(runs.body[0].trigger_type, 'schedule-manual');
    assert.equal((await call('GET', `/api/schedules/${a.id}/runs?limit=1`)).body.length, 1);
    assert.equal((await call('GET', `/api/schedules/${a.id}/runs?limit=abc`)).body.length, 2);
    assert.equal(scheduler.list().length, 2);
  });
});

// ------------------------------------------------------------------ the workflow check used by the server

async function withEngine(fn) {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'wf-check-'));
  try {
    const engine = new WorkflowEngine(path.join(dir, 'workflows'), { executionsDir: path.join(dir, 'exec') });
    await engine.saveWorkflow({
      id: 'w', name: 'W',
      steps: [{ id: 'a', type: 'agent', task: { instruction: 'Hello {{name}} from {{city}}', use_tools: false } }],
    });
    await fn(makeWorkflowChecker(engine));
  } finally {
    await fs.rm(dir, { recursive: true, force: true });
  }
}

test('the workflow check passes when the workflow exists and every input has a value', async () => {
  await withEngine(async (check) => {
    assert.deepEqual(await check('w', { name: 'Ann', city: 'Oslo' }), []);
    assert.deepEqual(await check('w', { name: 0, city: false }), []);           // 0 and false are real values
  });
});

test('the workflow check names every missing or blank input, and unknown workflows', async () => {
  await withEngine(async (check) => {
    assert.deepEqual(await check('w', { name: 'Ann' }), ['Missing input: city']);
    assert.deepEqual(await check('w', { name: '  ', city: '' }), ['Missing inputs: name, city']);
    assert.deepEqual(await check('w', { name: null, city: 'x' }), ['Missing input: name']);
    assert.deepEqual(await check('nope', {}), ['Workflow not found: nope']);
  });
});
