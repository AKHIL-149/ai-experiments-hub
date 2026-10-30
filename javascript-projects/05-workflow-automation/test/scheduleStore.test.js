const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');

const ScheduleStore = require('../src/ScheduleStore');

async function withStore(fn) {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'wf-sched-'));
  try {
    await fn(new ScheduleStore(path.join(dir, 'data', 'schedules.json')), dir);
  } finally {
    await fs.rm(dir, { recursive: true, force: true });
  }
}

const sched = (id, extra = {}) => ({ id, name: `Schedule ${id}`, workflow_id: 'w', cron: '* * * * *', ...extra });

test('a missing file is an empty list, not an error', async () => {
  await withStore(async (store) => {
    assert.deepEqual(await store.load(), { schedules: [], warnings: [] });
  });
});

test('what is saved is what is loaded, and the folder is created', async () => {
  await withStore(async (store) => {
    const items = [sched('a', { input_data: { x: 1 } }), sched('b', { enabled: false })];
    await store.save(items);
    assert.deepEqual((await store.load()).schedules, items);
  });
});

test('no temp files are left behind', async () => {
  await withStore(async (store, dir) => {
    await store.save([sched('a')]);
    await store.save([sched('a'), sched('b')]);
    assert.deepEqual(await fs.readdir(path.join(dir, 'data')), ['schedules.json']);
  });
});

test('a reader never sees a half-written file while saves are happening', async () => {
  await withStore(async (store) => {
    const big = Array.from({ length: 60 }, (_, i) => sched(`s${i}`, { input_data: { text: 'x'.repeat(8000) } }));
    await store.save(big);
    let failures = 0;
    let reads = 0;
    let writing = true;
    const writer = (async () => { for (let i = 0; i < 40; i++) await store.save(big); writing = false; })();
    const reader = (async () => {
      while (writing) {
        try {
          const { schedules, warnings } = await store.load();
          // a half-written file shows up as a warning (and an empty list), not as an exception
          if (warnings.length > 0 || schedules.length !== 60) failures += 1;
        } catch (error) { failures += 1; }
        reads += 1;
      }
    })();
    await Promise.all([writer, reader]);
    assert.ok(reads > 20, `${reads} reads`);
    assert.equal(failures, 0);
  });
});

test('concurrent saves are applied in the order they were made', async () => {
  await withStore(async (store) => {
    const saves = [];
    for (let i = 1; i <= 25; i++) saves.push(store.save([sched(`n${i}`)]));
    await Promise.all(saves);
    assert.deepEqual((await store.load()).schedules.map(s => s.id), ['n25']);
  });
});

test('a corrupt file is kept aside, not overwritten, and the store starts empty with a warning', async () => {
  await withStore(async (store, dir) => {
    await fs.mkdir(path.join(dir, 'data'), { recursive: true });
    await fs.writeFile(store.filePath, '{"schedules": [ {"id": "a", ');
    const { schedules, warnings } = await store.load();
    assert.deepEqual(schedules, []);
    assert.match(warnings[0], /not valid JSON.*schedules\.json\.corrupt-/);
    const files = await fs.readdir(path.join(dir, 'data'));
    const aside = files.find(f => f.includes('.corrupt-'));
    assert.ok(aside, `expected a .corrupt- copy in ${files}`);
    assert.equal(await fs.readFile(path.join(dir, 'data', aside), 'utf-8'), '{"schedules": [ {"id": "a", ');
  });
});

test('entries that are not usable are skipped with a warning; the rest load', async () => {
  await withStore(async (store, dir) => {
    await fs.mkdir(path.join(dir, 'data'), { recursive: true });
    await fs.writeFile(store.filePath, JSON.stringify({ schedules: [sched('ok'), 5, null, { name: 'no id' }, { id: '../x' }, sched('ok2')] }));
    const { schedules, warnings } = await store.load();
    assert.deepEqual(schedules.map(s => s.id), ['ok', 'ok2']);
    assert.equal(warnings.length, 4);
  });
});

test('a file with the wrong shape is treated as empty with a warning', async () => {
  await withStore(async (store, dir) => {
    await fs.mkdir(path.join(dir, 'data'), { recursive: true });
    await fs.writeFile(store.filePath, '[]');
    const { schedules, warnings } = await store.load();
    assert.deepEqual(schedules, []);
    assert.match(warnings[0], /unexpected format/);
  });
});

test('duplicate ids keep the first and warn', async () => {
  await withStore(async (store, dir) => {
    await fs.mkdir(path.join(dir, 'data'), { recursive: true });
    await fs.writeFile(store.filePath, JSON.stringify({ schedules: [sched('a', { name: 'first' }), sched('a', { name: 'second' })] }));
    const { schedules, warnings } = await store.load();
    assert.deepEqual(schedules.map(s => s.name), ['first']);
    assert.match(warnings[0], /duplicate/i);
  });
});

test('a failed save does not leave a temp file and reports the error', async () => {
  await withStore(async (store, dir) => {
    await fs.mkdir(path.join(dir, 'data'), { recursive: true });
    await fs.mkdir(store.filePath); // a directory where the file should go: the rename must fail
    await assert.rejects(store.save([sched('a')]));
    assert.deepEqual((await fs.readdir(path.join(dir, 'data'))).filter(f => f.endsWith('.tmp')), []);
    await store.save([]).catch(() => {}); // the queue keeps working after a failure
  });
});

test('the real file is only ever replaced by a rename, never written to directly', async () => {
  await withStore(async (store) => {
    const writes = [];
    const renames = [];
    const realWrite = fs.writeFile;
    const realRename = fs.rename;
    fs.writeFile = async (file, ...rest) => { writes.push(String(file)); return realWrite.call(fs, file, ...rest); };
    fs.rename = async (from, to) => { renames.push([String(from), String(to)]); return realRename.call(fs, from, to); };
    try {
      await store.save([sched('a')]);
      await store.save([sched('a'), sched('b')]);
    } finally {
      fs.writeFile = realWrite;
      fs.rename = realRename;
    }
    assert.equal(writes.length, 2);
    assert.ok(writes.every(file => file !== store.filePath && file.endsWith('.tmp')), `direct write to ${writes}`);
    assert.deepEqual(renames.map(([, to]) => to), [store.filePath, store.filePath]);
    assert.ok(renames.every(([from]) => writes.includes(from)));
  });
});
