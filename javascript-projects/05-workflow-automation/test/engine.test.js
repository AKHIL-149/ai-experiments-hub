const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');

const WorkflowEngine = require('../src/WorkflowEngine');

async function withEngine(bridge, fn) {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'wf-engine-'));
  try {
    const engine = new WorkflowEngine(path.join(dir, 'workflows'), { executionsDir: path.join(dir, 'exec') });
    Object.assign(engine.pythonBridge, bridge);
    await fn(engine);
  } finally {
    await fs.rm(dir, { recursive: true, force: true });
  }
}

const agent = (id, instruction, extra = {}) => ({ id, type: 'agent', task: { instruction, use_tools: false }, ...extra });

test('resolveTemplateVariables reports empty and missing variables separately', () => {
  const engine = new WorkflowEngine(os.tmpdir());
  const missing = new Set();
  const empty = new Set();
  const out = engine.resolveTemplateVariables(
    { a: '{{full}} {{blank}} {{nope}} {{obj.text}} {{obj.none}}' },
    { full: 'x', blank: '  ', obj: { text: 'ok', none: '' } },
    missing, empty
  );
  assert.deepEqual([...missing], ['nope']);
  assert.deepEqual([...empty].sort(), ['blank', 'obj.none']);
  assert.equal(out.a, 'x    {{nope}} ok ');
});

test('non-string values (numbers, objects) are never treated as empty', () => {
  const engine = new WorkflowEngine(os.tmpdir());
  const empty = new Set();
  engine.resolveTemplateVariables({ a: '{{n}} {{o}} {{z}}' }, { n: 0, o: {}, z: false }, new Set(), empty);
  assert.equal(empty.size, 0);
});

test('assertNoEmptyVariables names every empty variable', () => {
  const engine = new WorkflowEngine(os.tmpdir());
  assert.doesNotThrow(() => engine.assertNoEmptyVariables(new Set()));
  assert.throws(() => engine.assertNoEmptyVariables(new Set(['a', 'b.c'])), /\{\{a\}\}, \{\{b\.c\}\} are empty/);
});

async function runWorkflow(engine, steps, input = {}) {
  await engine.saveWorkflow({ id: 'w', name: 'W', steps });
  const execution = await engine.executeWorkflow('w', input);
  return execution;
}

test('a cut-off model reply is flagged on the step and logged as a warning', async () => {
  const bridge = {
    executeAgent: async () => ({ success: true, result: 'half a tab', truncated: true, max_tokens: 1000 })
  };
  await withEngine(bridge, async (engine) => {
    const execution = await runWorkflow(engine, [agent('long', 'Write a table')]);
    assert.equal(execution.status, 'completed');
    const [step] = execution.result.steps;
    assert.equal(step.truncated, true);
    const warning = execution.logs.find(l => l.level === 'warn');
    assert.ok(warning, 'expected a warn log');
    assert.match(warning.message, /cut off at 1000 tokens.*max_tokens/);
  });
});

test('a complete reply carries no truncation flag or warning', async () => {
  const bridge = { executeAgent: async () => ({ success: true, result: 'done', truncated: false, max_tokens: 4096 }) };
  await withEngine(bridge, async (engine) => {
    const execution = await runWorkflow(engine, [agent('a', 'Say hi')]);
    assert.equal('truncated' in execution.result.steps[0], false);
    assert.equal(execution.logs.some(l => l.level === 'warn'), false);
  });
});

test('an empty earlier result fails the next step and the model is never called for it', async () => {
  const prompts = [];
  const bridge = {
    executeTool: async () => ({ success: true, result: { content: '' } }),
    executeAgent: async (task) => { prompts.push(task.instruction); return { success: true, result: 'invented rows' }; }
  };
  await withEngine(bridge, async (engine) => {
    const execution = await runWorkflow(engine, [
      { id: 'read', type: 'tool', tool: 'file_operations', parameters: { operation: 'read', path: 'x.csv' }, output: 'data' },
      agent('classify', 'Classify {{data.content}}')
    ]);
    assert.equal(execution.status, 'failed');
    const failed = execution.result.steps.find(s => !s.success);
    assert.equal(failed.step_id, 'classify');
    assert.match(failed.error, /\{\{data\.content\}\} are empty/);
    assert.deepEqual(prompts, []);
  });
});

test('an empty value also stops a tool step', async () => {
  let toolCalls = 0;
  const bridge = { executeTool: async () => { toolCalls += 1; return { success: true, result: {} }; } };
  await withEngine(bridge, async (engine) => {
    const execution = await runWorkflow(engine, [
      { id: 'w', type: 'tool', tool: 'file_operations', parameters: { operation: 'write', path: 'o.md', content: '{{body}}' } }
    ], { body: '' });
    assert.equal(execution.status, 'failed');
    assert.equal(toolCalls, 0);
  });
});

// ----------------------------------------------------------------- run_if / if_skipped

test('evaluateCondition compares numbers as numbers, including numeric strings', () => {
  const engine = new WorkflowEngine(os.tmpdir());
  const ctx = { rows: 10, text: '9', obj: { n: 0 } };
  const check = (variable, operator, value) => engine.evaluateCondition({ variable, operator, value }, ctx).passed;
  assert.equal(check('rows', '>', 9), true);
  assert.equal(check('rows', '>', '9'), true);   // "10" > "9" as numbers, not as text
  assert.equal(check('text', '<', 10), true);
  assert.equal(check('obj.n', '==', 0), true);
  assert.equal(check('obj.n', '!=', 0), false);
  assert.equal(check('rows', '>=', 10), true);
  assert.equal(check('rows', '<=', 9), false);
});

test('evaluateCondition compares text with == and != ignoring case and spaces', () => {
  const engine = new WorkflowEngine(os.tmpdir());
  const run = (operator, value) => engine.evaluateCondition({ variable: 'mode', operator, value }, { mode: ' Fast ' }).passed;
  assert.equal(run('==', 'fast'), true);
  assert.equal(run('!=', 'slow'), true);
  assert.equal(run('==', 'slow'), false);
});

test('evaluateCondition refuses nonsense instead of guessing', () => {
  const engine = new WorkflowEngine(os.tmpdir());
  assert.throws(() => engine.evaluateCondition({ variable: 'x', operator: '>', value: 1 }, { x: 'abc' }), /both must be numbers/);
  assert.throws(() => engine.evaluateCondition({ variable: 'nope.rows', operator: '>', value: 1 }, {}), /\{\{nope\.rows\}\} is not available/);
  assert.throws(() => engine.evaluateCondition({ variable: 'a.b', operator: '>', value: 1 }, { a: 5 }), /not available/);
  // a plain missing name must not quietly compare "undefined" as text
  assert.throws(() => engine.evaluateCondition({ variable: 'ghost', operator: '==', value: 'undefined' }, {}), /\{\{ghost\}\} is not available/);
});

const countingBridge = () => {
  const bridge = { calls: [] };
  bridge.executeAgent = async (task) => { bridge.calls.push(task.instruction); return { success: true, result: 'ai wrote this' }; };
  bridge.executeTool = async () => ({ success: true, result: { content: 'a,b\n', rows: 0 } });
  return bridge;
};

const gated = (value) => [
  { id: 'count', type: 'tool', tool: 'csv_operations', parameters: { operation: 'count', content: 'x' }, output: 'data' },
  agent('draft', 'Write about {{data.content}}', {
    run_if: { variable: 'data.rows', operator: '>', value }, if_skipped: 'Nothing to draft.', output: 'draft'
  }),
  { id: 'save', type: 'tool', tool: 'file_operations', parameters: { operation: 'write', path: 'o.md', content: '{{draft}}' } }
];

test('a step whose condition fails is skipped without calling the model, and its output is if_skipped', async () => {
  const bridge = countingBridge();
  let written;
  bridge.executeTool = async (tool, params) => {
    if (tool === 'file_operations') { written = params.content; return { success: true, result: {} }; }
    return { success: true, result: { content: 'a,b\n', rows: 0 } };
  };
  await withEngine(bridge, async (engine) => {
    const execution = await runWorkflow(engine, gated(0));
    assert.equal(execution.status, 'completed');
    assert.deepEqual(bridge.calls, []);
    const skipped = execution.result.steps.find(s => s.step_id === 'draft');
    assert.equal(skipped.skipped, true);
    assert.equal(skipped.result, 'Nothing to draft.');
    assert.equal(written, 'Nothing to draft.');
    assert.equal(execution.steps_completed, 3);
    assert.ok(execution.logs.some(l => /Skipped step: draft.*data\.rows > 0.*is 0/.test(l.message)));
  });
});

test('a step whose condition holds runs normally', async () => {
  const bridge = countingBridge();
  bridge.executeTool = async () => ({ success: true, result: { content: 'a,b\n1,2\n', rows: 1 } });
  await withEngine(bridge, async (engine) => {
    const execution = await runWorkflow(engine, gated(0));
    assert.equal(execution.status, 'completed');
    assert.equal(bridge.calls.length, 1);
    const ran = execution.result.steps.find(s => s.step_id === 'draft');
    assert.equal(ran.skipped, undefined);
    assert.equal(ran.result, 'ai wrote this');
  });
});

test('a run_if on a variable that does not exist fails that step clearly', async () => {
  await withEngine(countingBridge(), async (engine) => {
    const execution = await runWorkflow(engine, [
      agent('a', 'hi', { run_if: { variable: 'ghost.rows', operator: '>', value: 0 } })
    ]);
    assert.equal(execution.status, 'failed');
    assert.match(execution.result.steps[0].error, /\{\{ghost\.rows\}\} is not available/);
  });
});

test('a skipped step with no if_skipped leaves an empty output, which stops the step that needs it', async () => {
  const bridge = countingBridge();
  await withEngine(bridge, async (engine) => {
    const steps = gated(5);
    delete steps[1].if_skipped;
    const execution = await runWorkflow(engine, steps);
    assert.equal(execution.status, 'failed');
    assert.match(execution.result.steps.at(-1).error, /\{\{draft\}\} are empty/);
  });
});

// ----------------------------------------------------------------- if_skipped templates

test('if_skipped can use {{variables}} from inputs and earlier results', async () => {
  const bridge = countingBridge();
  bridge.executeTool = async () => ({ success: true, result: { content: 'x', rows: 0, count: 0 } });
  await withEngine(bridge, async (engine) => {
    const execution = await runWorkflow(engine, [
      { id: 'check', type: 'tool', tool: 'csv_operations', parameters: { operation: 'count', content: 'x' }, output: 'moves' },
      agent('note', 'Describe it', {
        run_if: { variable: 'moves.count', operator: '>', value: 0 },
        if_skipped: 'No alert: nothing moved {{threshold}}% or more ({{moves.count}} found).', output: 'note'
      })
    ], { threshold: 3 });
    assert.equal(execution.status, 'completed');
    assert.equal(execution.result.steps[1].result, 'No alert: nothing moved 3% or more (0 found).');
    assert.deepEqual(bridge.calls, []);
  });
});

test('an if_skipped variable that does not exist fails the step with a clear message', async () => {
  await withEngine(countingBridge(), async (engine) => {
    const execution = await runWorkflow(engine, [
      agent('a', 'hi', { run_if: { variable: 'flag', operator: '==', value: 'yes' }, if_skipped: 'Skipped for {{ghost}}' })
    ], { flag: 'no' });
    assert.equal(execution.status, 'failed');
    assert.match(execution.result.steps[0].error, /if_skipped.*\{\{ghost\}\}/);
  });
});

test('literal if_skipped text without variables is unchanged', async () => {
  await withEngine(countingBridge(), async (engine) => {
    const execution = await runWorkflow(engine, [
      agent('a', 'hi', { run_if: { variable: 'n', operator: '>', value: 1 }, if_skipped: 'Nothing to do. 100% fine {not a var}' })
    ], { n: 0 });
    assert.equal(execution.result.steps[0].result, 'Nothing to do. 100% fine {not a var}');
  });
});
