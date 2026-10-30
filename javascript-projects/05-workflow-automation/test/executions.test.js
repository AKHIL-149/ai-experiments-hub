const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');

const ExecutionManager = require('../src/ExecutionManager');

async function withManager(fn) {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'wf-exec-'));
  try {
    await fn(new ExecutionManager(dir), dir);
  } finally {
    await fs.rm(dir, { recursive: true, force: true });
  }
}

test('a record being rewritten can always be read (never half-written)', async () => {
  await withManager(async (manager) => {
    // a large record makes a non-atomic write easy to catch mid-way
    const { execution_id: id } = await manager.createExecution('w', 'api', { big: 'x'.repeat(300000) });

    let failures = 0;
    let reads = 0;
    let writing = true;
    const writer = (async () => {
      for (let i = 0; i < 150; i++) await manager.appendLog(id, 'info', `m${i}`);
      writing = false;
    })();
    const reader = (async () => {
      while (writing) {
        try { await manager.loadExecution(id); } catch (error) { failures += 1; }
        reads += 1;
      }
    })();
    await Promise.all([writer, reader]);

    assert.ok(reads > 50, `only ${reads} reads happened`);
    assert.equal(failures, 0);
    assert.equal((await manager.loadExecution(id)).logs.length, 150);
  });
});

test('no temp files are left behind', async () => {
  await withManager(async (manager, dir) => {
    const { execution_id: id } = await manager.createExecution('w', 'api', {});
    await manager.appendLog(id, 'info', 'x');
    await manager.updateExecutionStatus(id, 'completed');
    assert.deepEqual(await fs.readdir(dir), [`${id}.json`]);
  });
});

test('one corrupt record does not empty the history', async () => {
  await withManager(async (manager, dir) => {
    const a = await manager.createExecution('w', 'api', {});
    await fs.writeFile(path.join(dir, 'exec-broken.json'), '{"half": ');
    const b = await manager.createExecution('w', 'api', {});

    const listed = (await manager.listExecutions()).map(e => e.execution_id).sort();
    assert.deepEqual(listed, [a.execution_id, b.execution_id].sort());
  });
});

test('temp files from a crashed write are not listed as executions', async () => {
  await withManager(async (manager, dir) => {
    const { execution_id: id } = await manager.createExecution('w', 'api', {});
    await fs.writeFile(path.join(dir, `${id}.json.123.1.tmp`), '{"execution_id": "ghost"}');
    assert.deepEqual((await manager.listExecutions()).map(e => e.execution_id), [id]);
  });
});

// ------------------------------------------------------------------ schedules and interrupted runs

test('a run started by a schedule records which schedule and why', async () => {
  await withManager(async (manager) => {
    const exec = await manager.createExecution('w', 'schedule', {}, { scheduleId: 'sch-abc123' });
    const loaded = await manager.loadExecution(exec.execution_id);
    assert.equal(loaded.trigger_type, 'schedule');
    assert.equal(loaded.schedule_id, 'sch-abc123');
    const plain = await manager.createExecution('w', 'api', {});
    assert.equal((await manager.loadExecution(plain.execution_id)).schedule_id, null);
  });
});

test('executions can be listed for one schedule', async () => {
  await withManager(async (manager) => {
    const a1 = await manager.createExecution('w', 'schedule', {}, { scheduleId: 'sch-a' });
    await manager.createExecution('w', 'schedule', {}, { scheduleId: 'sch-b' });
    const a2 = await manager.createExecution('w', 'schedule', {}, { scheduleId: 'sch-a' });
    await manager.createExecution('w', 'api', {});
    const ids = (await manager.listExecutions({ schedule_id: 'sch-a' })).map(e => e.execution_id).sort();
    assert.deepEqual(ids, [a1.execution_id, a2.execution_id].sort());
  });
});

test('runs a restart left "running" or "pending" are marked failed as interrupted; finished runs are untouched', async () => {
  await withManager(async (manager) => {
    const running = await manager.createExecution('w', 'api', {});
    await manager.updateExecutionStatus(running.execution_id, 'running');
    const pending = await manager.createExecution('w', 'api', {});
    const done = await manager.createExecution('w', 'api', {});
    await manager.updateExecutionStatus(done.execution_id, 'completed');
    const failed = await manager.createExecution('w', 'api', {});
    await manager.updateExecutionStatus(failed.execution_id, 'failed', { error: 'original reason' });

    assert.equal(await manager.markInterrupted(), 2);

    for (const id of [running.execution_id, pending.execution_id]) {
      const rec = await manager.loadExecution(id);
      assert.equal(rec.status, 'failed');
      assert.match(rec.result.error, /interrupted.*server stopped/i);
      assert.ok(rec.completed_at && rec.duration_ms >= 0);
      assert.equal(rec.logs.at(-1).level, 'error');
    }
    assert.equal((await manager.loadExecution(done.execution_id)).status, 'completed');
    const keep = await manager.loadExecution(failed.execution_id);
    assert.equal(keep.status, 'failed');
    assert.equal(keep.result.error, 'original reason');
    assert.equal(await manager.markInterrupted(), 0, 'running it again changes nothing');
  });
});

test('only runs that started before the cutoff are treated as interrupted', async () => {
  await withManager(async (manager) => {
    const old = await manager.createExecution('w', 'api', {});
    await new Promise(r => setTimeout(r, 15));
    const cutoff = new Date().toISOString();
    await new Promise(r => setTimeout(r, 15));
    const fresh = await manager.createExecution('w', 'api', {});
    assert.equal(await manager.markInterrupted(cutoff), 1);
    assert.equal((await manager.loadExecution(old.execution_id)).status, 'failed');
    assert.equal((await manager.loadExecution(fresh.execution_id)).status, 'pending');
  });
});
