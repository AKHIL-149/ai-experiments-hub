const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');

const WorkflowEngine = require('../src/WorkflowEngine');
const { validateWorkflow, requiredInputs, WorkflowValidationError } = require('../src/workflowSchema');

const toolStep = (id, extra = {}) => ({
  id, type: 'tool', tool: 'file_operations',
  parameters: { operation: 'read', path: '{{src}}' }, ...extra
});
const agentStep = (id, instruction, extra = {}) => ({
  id, type: 'agent', task: { instruction, use_tools: false }, ...extra
});
const workflow = (steps, extra = {}) => ({ id: 'demo', name: 'Demo', steps, ...extra });

test('a well-formed workflow has no problems', () => {
  const wf = workflow([
    toolStep('read', { output: 'notes' }),
    agentStep('sum', 'Summarise {{notes.content}}', { output: 'summary' })
  ]);
  assert.deepEqual(validateWorkflow(wf), []);
});

test('rejects bad ids so a workflow cannot be written outside the workflows folder', () => {
  for (const id of ['../evil', 'a/b', 'has space', '', undefined, 'x'.repeat(65)]) {
    const errors = validateWorkflow(workflow([toolStep('a')], { id }));
    assert.ok(errors.some(e => /Workflow ID/.test(e)), `id ${JSON.stringify(id)} should be rejected`);
  }
});

test('requires a name and at least one step', () => {
  assert.ok(validateWorkflow(workflow([toolStep('a')], { name: '  ' })).some(e => /name/i.test(e)));
  assert.ok(validateWorkflow(workflow([])).some(e => /at least one step/.test(e)));
  assert.ok(validateWorkflow(null)[0]);
  assert.ok(validateWorkflow([])[0]);
});

test('checks each step: unique ids, known type, required fields', () => {
  const errors = validateWorkflow(workflow([
    toolStep('a'),
    toolStep('a'),                                   // duplicate id
    { id: 'b', type: 'webhook' },                    // unknown type
    { id: 'c', type: 'agent', task: { instruction: '  ' } },
    { id: 'd', type: 'tool' },                       // no tool
    agentStep('e', 'ok', { output: 'bad name!' })    // output not a plain name
  ]));
  assert.ok(errors.some(e => /used by another step/.test(e)));
  assert.ok(errors.some(e => /type must be one of/.test(e)));
  assert.ok(errors.some(e => /"c".*instruction is required/.test(e)));
  assert.ok(errors.some(e => /"d".*choose a tool/.test(e)));
  assert.ok(errors.some(e => /"e".*output name/.test(e)));
});

test('use_tools must be a boolean', () => {
  const wf = workflow([{ id: 'a', type: 'agent', task: { instruction: 'x', use_tools: 'no' } }]);
  assert.ok(validateWorkflow(wf).some(e => /use_tools/.test(e)));
});

test('flags a variable that only a later step produces', () => {
  const errors = validateWorkflow(workflow([
    agentStep('use_it', 'Summarise {{notes}}'),
    toolStep('make_it', { output: 'notes' })
  ]));
  assert.equal(errors.length, 1);
  assert.match(errors[0], /\{\{notes\}\}.*"make_it".*later/);
});

test('a step may use its own earlier output name as an input when no later step makes it', () => {
  assert.deepEqual(validateWorkflow(workflow([agentStep('a', 'Hello {{name}}')])), []);
});

test('requiredInputs lists variables not produced by earlier steps, in order, without duplicates', () => {
  const wf = workflow([
    toolStep('read', { output: 'notes' }),
    agentStep('sum', '{{notes.content}} for {{audience}} / {{audience}}', { output: 'summary' }),
    toolStep('save', { parameters: { operation: 'write', path: '{{out}}', content: '{{summary}}' } })
  ]);
  assert.deepEqual(requiredInputs(wf), ['src', 'audience', 'out']);
});

async function withEngine(fn) {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'wf-test-'));
  try {
    await fn(new WorkflowEngine(path.join(dir, 'workflows'), { executionsDir: path.join(dir, 'exec') }), dir);
  } finally {
    await fs.rm(dir, { recursive: true, force: true });
  }
}

test('saveWorkflow stores a valid workflow, which then appears in the list with its inputs', async () => {
  await withEngine(async (engine, dir) => {
    const wf = workflow([toolStep('read', { output: 'notes' })], { description: '  hi  ' });
    assert.deepEqual(await engine.saveWorkflow(wf), { id: 'demo', created: true });

    const onDisk = JSON.parse(await fs.readFile(path.join(dir, 'workflows', 'demo.json'), 'utf-8'));
    assert.equal(onDisk.description, 'hi');
    assert.equal((await engine.loadWorkflow('demo')).name, 'Demo');

    const [listed] = await engine.listWorkflows();
    assert.deepEqual(listed, { id: 'demo', name: 'Demo', description: 'hi', steps: 1, inputs: ['src'] });
  });
});

test('saveWorkflow refuses invalid workflows and writes nothing', async () => {
  await withEngine(async (engine, dir) => {
    await assert.rejects(engine.saveWorkflow(workflow([], { id: '../x' })), WorkflowValidationError);
    const files = await fs.readdir(path.join(dir, 'workflows')).catch(() => []);
    assert.deepEqual(files, []);
  });
});

test('saveWorkflow will not replace an existing workflow unless told to', async () => {
  await withEngine(async (engine) => {
    await engine.saveWorkflow(workflow([toolStep('a')]));

    await assert.rejects(
      engine.saveWorkflow(workflow([toolStep('a'), toolStep('b')])),
      (error) => error.status === 409
    );
    assert.equal((await engine.loadWorkflow('demo')).steps.length, 1);

    assert.deepEqual(await engine.saveWorkflow(workflow([toolStep('a'), toolStep('b')]), { overwrite: true }),
      { id: 'demo', created: false });
    assert.equal((await engine.loadWorkflow('demo')).steps.length, 2);
  });
});

test('overwriting replaces the file that already holds the id, even in a sub-folder', async () => {
  await withEngine(async (engine, dir) => {
    const nested = path.join(dir, 'workflows', 'examples');
    await fs.mkdir(nested, { recursive: true });
    await fs.writeFile(path.join(nested, 'old.json'), JSON.stringify(workflow([toolStep('a')])));

    await engine.saveWorkflow(workflow([toolStep('a'), toolStep('b')]), { overwrite: true });

    assert.deepEqual((await fs.readdir(path.join(dir, 'workflows'))).sort(), ['examples']);
    assert.equal(JSON.parse(await fs.readFile(path.join(nested, 'old.json'), 'utf-8')).steps.length, 2);
    assert.equal((await engine.listWorkflows()).length, 1);
  });
});

test('run_if and if_skipped are validated', () => {
  const step = (extra) => agentStep('a', 'x', extra);
  const ok = { run_if: { variable: 'data.rows', operator: '>', value: 0 }, if_skipped: 'none' };
  assert.deepEqual(validateWorkflow(workflow([toolStep('data', { output: 'data' }), step(ok)])), []);

  const problems = (extra) => validateWorkflow(workflow([toolStep('data', { output: 'data' }), step(extra)]));
  assert.ok(problems({ run_if: 'rows > 0' }).some(e => /run_if must be an object/.test(e)));
  assert.ok(problems({ run_if: { variable: 'a b', operator: '>', value: 1 } }).some(e => /variable/.test(e)));
  assert.ok(problems({ run_if: { variable: 'data.rows', operator: 'contains', value: 1 } }).some(e => /operator/.test(e)));
  assert.ok(problems({ run_if: { variable: 'data.rows', operator: '>' } }).some(e => /value/.test(e)));
  assert.ok(problems({ run_if: ok.run_if, if_skipped: 5 }).some(e => /if_skipped must be text/.test(e)));
  assert.ok(problems({ if_skipped: 'x' }).some(e => /only applies to a step that has run_if/.test(e)));
});

test('a run_if variable counts as an input unless an earlier step makes it, and must not come from a later step', () => {
  const gate = { run_if: { variable: 'flag', operator: '==', value: 'yes' } };
  assert.deepEqual(requiredInputs(workflow([agentStep('a', 'hi', gate)])), ['flag']);
  assert.deepEqual(requiredInputs(workflow([toolStep('t', { output: 'flag' }), agentStep('a', 'hi', gate)])), ['src']);

  const errors = validateWorkflow(workflow([agentStep('a', 'hi', gate), toolStep('t', { output: 'flag' })]));
  assert.ok(errors.some(e => /\{\{flag\}\}.*later/.test(e)));
});

test('max_tokens must be a whole number from 1 to 32768', () => {
  const withLimit = (max_tokens) => validateWorkflow(workflow([
    { id: 'a', type: 'agent', task: { instruction: 'x', max_tokens } }
  ]));
  for (const ok of [1, 1500, 32768]) assert.deepEqual(withLimit(ok), []);
  for (const bad of [0, -1, 32769, 1.5, '1500', null, true]) {
    assert.ok(withLimit(bad).some(e => /max_tokens must be a whole number/.test(e)), `${bad} should be rejected`);
  }
});
