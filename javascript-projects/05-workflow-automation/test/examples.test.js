const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const { validateWorkflow, requiredInputs } = require('../src/workflowSchema');

const DIR = path.join(__dirname, '..', 'workflows', 'examples');
const examples = fs.readdirSync(DIR).filter(f => f.endsWith('.json')).map(f => ({
  file: f, workflow: JSON.parse(fs.readFileSync(path.join(DIR, f), 'utf-8'))
}));

test('there are example workflows to check', () => {
  assert.ok(examples.length >= 6, `found ${examples.length}`);
});

for (const { file, workflow } of examples) {
  test(`${file} is a valid workflow whose id matches its file name`, () => {
    assert.deepEqual(validateWorkflow(workflow), []);
    assert.equal(workflow.id, file.replace(/\.json$/, ''));
  });
}

const inputsOf = (id) => requiredInputs(examples.find(e => e.workflow.id === id).workflow);

test('the finance workflows ask for the inputs the docs promise', () => {
  assert.deepEqual(inputsOf('stock-ticker-update'), ['symbols', 'source', 'report_path']);
  assert.deepEqual(inputsOf('create-random-portfolio'), ['count', 'seed', 'source', 'portfolio_path']);
  assert.deepEqual(inputsOf('portfolio-tracker'), ['portfolio_path', 'source', 'history_path', 'report_path']);
  assert.deepEqual(inputsOf('price-alert'), ['portfolio_path', 'source', 'threshold_pct', 'log_path', 'alert_path']);
});

test('finance reports carry the not-advice notice and AI steps are told not to advise or predict', () => {
  for (const id of ['stock-ticker-update', 'portfolio-tracker', 'price-alert']) {
    const { steps } = examples.find(e => e.workflow.id === id).workflow;
    const save = steps.find(s => s.id === 'save_report' || s.id === 'write_alert');
    assert.match(save.parameters.content, /not investment advice/i, id);
    for (const ai of steps.filter(s => s.type === 'agent')) {
      assert.match(ai.task.instruction, /do not predict, give opinions or give advice/i, `${id}/${ai.id}`);
      assert.equal(ai.task.use_tools, false);
    }
  }
});

test('the tracker gives the model only facts the tools already worked out', () => {
  const { steps } = examples.find(e => e.workflow.id === 'portfolio-tracker').workflow;
  const ai = steps.find(s => s.id === 'describe_portfolio');
  assert.match(ai.task.instruction, /\{\{valued\.totals_text\}\}/);
  assert.match(ai.task.instruction, /\{\{trend\.summary\}\}/);
  assert.match(ai.task.instruction, /do not work anything out yourself/i);
});

test('the price alert is fully deterministic: no model text, and the alert is only written when a position qualified', () => {
  const { steps } = examples.find(e => e.workflow.id === 'price-alert').workflow;
  // a model sentence once contradicted the numbers above it ("Eight positions moved" for 1 of 8)
  assert.deepEqual(steps.filter(s => s.type === 'agent'), []);
  const write = steps.find(s => s.id === 'write_alert');
  assert.deepEqual(write.run_if, { variable: 'moves.count', operator: '>', value: 0 });
  // when nothing qualifies the line shown is the tool's own sentence (it names the largest move)
  assert.equal(write.if_skipped, '{{moves.summary}}');
  // the check itself and its log run every time
  for (const id of ['check_moves', 'log_check']) assert.equal(steps.find(s => s.id === id).run_if, undefined, id);
});
