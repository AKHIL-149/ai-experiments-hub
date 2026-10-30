const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');

const { validateModelName, listGenerationModels } = require('../src/ollamaModels');
const WorkflowEngine = require('../src/WorkflowEngine');

test('model names: accepts real Ollama names, treats empty as the default', () => {
  for (const ok of ['llama3.2', 'llama3.2:3b', 'qwen3:14b', 'hf.co/user/model:Q4_K_M', 'mistral-nemo:12b-instruct']) {
    assert.equal(validateModelName(ok), ok);
  }
  for (const none of [undefined, null, '']) assert.equal(validateModelName(none), null);
});

test('model names: rejects anything that is not a plain name, with status 400', () => {
  for (const bad of ['a b', '-rf', '../x', 'x;y', 'x\ny', '$(id)', 'a'.repeat(101), 5, {}, ['llama3.2'], true]) {
    assert.throws(() => validateModelName(bad), (error) => error.status === 400 && /model must be/.test(error.message), JSON.stringify(bad));
  }
});

test('the model list leaves out embedding models, keeps vision/code ones, and is sorted', () => {
  const tags = {
    models: [
      { name: 'qwen3:8b', size: 5, details: { family: 'qwen3', parameter_size: '8.2B' } },
      { name: 'nomic-embed-text:latest', size: 1, details: { family: 'nomic-bert' } },
      { name: 'all-minilm', size: 1, details: { family: 'bert' } },
      { name: 'some-embedding-model', size: 1, details: { family: 'llama' } },
      { name: 'llava:latest', size: 4, details: { family: 'llama', parameter_size: '7B' } },
      { name: 'llama3.2:3b', size: 2, details: { family: 'llama', parameter_size: '3.2B' } },
      { broken: true },
      null
    ]
  };
  assert.deepEqual(listGenerationModels(tags).map(m => m.name), ['llama3.2:3b', 'llava:latest', 'qwen3:8b']);
  assert.deepEqual(listGenerationModels(tags)[0], { name: 'llama3.2:3b', parameterSize: '3.2B', sizeBytes: 2 });
});

test('the model list copes with missing or odd responses', () => {
  assert.deepEqual(listGenerationModels({}), []);
  assert.deepEqual(listGenerationModels(null), []);
  assert.deepEqual(listGenerationModels({ models: [{ name: 'x' }] }), [{ name: 'x', parameterSize: null, sizeBytes: null }]);
});

async function withEngine(bridge, fn) {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'wf-models-'));
  try {
    const engine = new WorkflowEngine(path.join(dir, 'workflows'), { executionsDir: path.join(dir, 'exec') });
    Object.assign(engine.pythonBridge, bridge);
    await engine.saveWorkflow({
      id: 'w', name: 'W',
      steps: [{ id: 'a', type: 'agent', task: { instruction: 'hi', use_tools: false }, output: 'out' }]
    });
    await fn(engine);
  } finally {
    await fs.rm(dir, { recursive: true, force: true });
  }
}

test('the chosen model reaches the agent for every AI step and is recorded on the execution', async () => {
  const seen = [];
  const bridge = { executeAgent: async (task, options) => { seen.push(options.model); return { success: true, result: 'ok' }; } };
  await withEngine(bridge, async (engine) => {
    const execution = await engine.executeWorkflow('w', {}, { model: 'qwen3:14b' });
    assert.deepEqual(seen, ['qwen3:14b']);
    assert.equal(execution.model, 'qwen3:14b');
  });
});

test('no model chosen: the agent gets none (the server default applies) and the record says so', async () => {
  const seen = [];
  const bridge = { executeAgent: async (task, options) => { seen.push(options.model); return { success: true, result: 'ok' }; } };
  await withEngine(bridge, async (engine) => {
    for (const none of [undefined, '', null]) {
      const execution = await engine.executeWorkflow('w', {}, { model: none });
      assert.equal(execution.model, null);
    }
    assert.deepEqual(seen, [null, null, null]);
  });
});

test('a bad model name is refused before an execution record is created', async () => {
  await withEngine({ executeAgent: async () => ({ success: true, result: 'x' }) }, async (engine) => {
    await assert.rejects(engine.startExecution('w', {}, { model: 'bad name; rm' }), (error) => error.status === 400);
    assert.deepEqual(await engine.executionManager.listExecutions(), []);
  });
});

test('the schedule that started a run is recorded on its execution record', async () => {
  const bridge = { executeAgent: async () => ({ success: true, result: 'ok' }) };
  await withEngine(bridge, async (engine) => {
    const scheduled = await engine.executeWorkflow('w', {}, { triggerType: 'schedule', scheduleId: 'sch-1a2b' });
    assert.equal(scheduled.trigger_type, 'schedule');
    assert.equal(scheduled.schedule_id, 'sch-1a2b');
    assert.equal((await engine.executeWorkflow('w', {}, {})).schedule_id, null);
  });
});
