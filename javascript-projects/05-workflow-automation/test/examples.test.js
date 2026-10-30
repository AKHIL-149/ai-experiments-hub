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
});

test('finance reports carry the not-advice notice and AI steps are told not to advise or predict', () => {
  for (const id of ['stock-ticker-update', 'portfolio-tracker']) {
    const { steps } = examples.find(e => e.workflow.id === id).workflow;
    const save = steps.find(s => s.id === 'save_report');
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
