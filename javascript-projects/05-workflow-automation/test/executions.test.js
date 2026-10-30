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
