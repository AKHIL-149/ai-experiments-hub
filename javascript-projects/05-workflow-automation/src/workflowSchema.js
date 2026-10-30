/**
 * Shape rules for workflow definitions, shared by the save endpoint and the engine.
 */

const NAME_PATTERN = /^[\w-]+$/;
const STEP_TYPES = ['agent', 'tool'];
const MAX_STEPS = 50;
const TEMPLATE_PATTERN = /\{\{([\w]+(?:\.[\w]+)*)\}\}/g;

/** Names of the {{variables}} used inside any string of a value (the part before the first dot). */
function templateRoots(value, found = new Set()) {
  if (typeof value === 'string') {
    for (const match of value.matchAll(TEMPLATE_PATTERN)) {
      found.add(match[1].split('.')[0]);
    }
  } else if (Array.isArray(value)) {
    value.forEach(item => templateRoots(item, found));
  } else if (value && typeof value === 'object') {
    Object.values(value).forEach(item => templateRoots(item, found));
  }
  return found;
}

function stepPayload(step) {
  return step.type === 'tool' ? step.parameters : step.task;
}

const CONDITION_OPERATORS = ['==', '!=', '>', '>=', '<', '<='];

/** Every {{variable}} a step needs: its template variables, the one its run_if tests and any in if_skipped. */
function stepVariables(step) {
  const found = new Set();
  const variable = step && step.run_if && step.run_if.variable;
  if (typeof variable === 'string' && /^\w+(\.\w+)*$/.test(variable)) {
    found.add(variable.split('.')[0]);
  }
  templateRoots(stepPayload(step || {}), found);
  if (step && step.run_if && typeof step.if_skipped === 'string') {
    templateRoots(step.if_skipped, found);
  }
  return found;
}

/** Variables a caller must supply: used by a step but not produced by an earlier step. */
function requiredInputs(workflow) {
  const produced = new Set();
  const inputs = [];
  for (const step of workflow.steps || []) {
    for (const name of stepVariables(step)) {
      if (!produced.has(name) && !inputs.includes(name)) {
        inputs.push(name);
      }
    }
    if (step && typeof step.output === 'string' && step.output) {
      produced.add(step.output);
    }
  }
  return inputs;
}

function validateCondition(step, name) {
  const errors = [];
  if (step.if_skipped !== undefined && typeof step.if_skipped !== 'string') {
    errors.push(`${name}: if_skipped must be text`);
  }
  if (step.run_if === undefined) {
    if (step.if_skipped !== undefined) {
      errors.push(`${name}: if_skipped only applies to a step that has run_if`);
    }
    return errors;
  }

  const cond = step.run_if;
  if (!cond || typeof cond !== 'object' || Array.isArray(cond)) {
    return [...errors, `${name}: run_if must be an object with variable, operator and value`];
  }
  if (typeof cond.variable !== 'string' || !/^\w+(\.\w+)*$/.test(cond.variable)) {
    errors.push(`${name}: run_if variable must be a name such as table.rows`);
  }
  if (!CONDITION_OPERATORS.includes(cond.operator)) {
    errors.push(`${name}: run_if operator must be one of ${CONDITION_OPERATORS.join(' ')}`);
  }
  if (!['string', 'number', 'boolean'].includes(typeof cond.value)) {
    errors.push(`${name}: run_if needs a value to compare with`);
  }
  return errors;
}

/** Returns a list of human-readable problems; empty means the workflow is valid. */
function validateWorkflow(workflow) {
  const errors = [];

  if (!workflow || typeof workflow !== 'object' || Array.isArray(workflow)) {
    return ['Workflow must be a JSON object'];
  }

  if (typeof workflow.id !== 'string' || !NAME_PATTERN.test(workflow.id) || workflow.id.length > 64) {
    errors.push('Workflow ID is required: letters, numbers, "-" and "_" only (max 64 characters)');
  }
  if (typeof workflow.name !== 'string' || !workflow.name.trim()) {
    errors.push('Workflow name is required');
  }
  if (workflow.description !== undefined && typeof workflow.description !== 'string') {
    errors.push('Description must be text');
  }

  if (!Array.isArray(workflow.steps) || workflow.steps.length === 0) {
    errors.push('Add at least one step');
    return errors;
  }
  if (workflow.steps.length > MAX_STEPS) {
    errors.push(`A workflow can have at most ${MAX_STEPS} steps`);
    return errors;
  }

  const seen = new Set();
  const produced = new Set();
  const laterOutputs = new Map(); // output name -> step id that creates it
  for (const step of workflow.steps) {
    if (step && typeof step.output === 'string' && step.output && !laterOutputs.has(step.output)) {
      laterOutputs.set(step.output, step.id);
    }
  }

  workflow.steps.forEach((step, index) => {
    const label = `Step ${index + 1}`;

    if (!step || typeof step !== 'object' || Array.isArray(step)) {
      errors.push(`${label} must be an object`);
      return;
    }

    if (typeof step.id !== 'string' || !NAME_PATTERN.test(step.id)) {
      errors.push(`${label}: ID is required (letters, numbers, "-" and "_" only)`);
    } else if (seen.has(step.id)) {
      errors.push(`${label}: ID "${step.id}" is used by another step`);
    } else {
      seen.add(step.id);
    }
    const name = typeof step.id === 'string' && step.id ? `Step "${step.id}"` : label;

    if (!STEP_TYPES.includes(step.type)) {
      errors.push(`${name}: type must be one of ${STEP_TYPES.join(', ')}`);
      return;
    }

    if (step.output !== undefined && step.output !== '' &&
        (typeof step.output !== 'string' || !/^\w+$/.test(step.output))) {
      errors.push(`${name}: output name may only contain letters, numbers and "_"`);
    }

    if (step.type === 'agent') {
      const task = step.task;
      if (!task || typeof task !== 'object' || typeof task.instruction !== 'string' || !task.instruction.trim()) {
        errors.push(`${name}: instruction is required`);
      } else {
        if (task.use_tools !== undefined && typeof task.use_tools !== 'boolean') {
          errors.push(`${name}: use_tools must be true or false`);
        }
        if (task.max_tokens !== undefined &&
            (!Number.isInteger(task.max_tokens) || task.max_tokens < 1 || task.max_tokens > 32768)) {
          errors.push(`${name}: max_tokens must be a whole number between 1 and 32768`);
        }
      }
    } else {
      if (typeof step.tool !== 'string' || !step.tool.trim()) {
        errors.push(`${name}: choose a tool`);
      }
      if (step.parameters !== undefined &&
          (!step.parameters || typeof step.parameters !== 'object' || Array.isArray(step.parameters))) {
        errors.push(`${name}: parameters must be an object`);
      }
    }

    errors.push(...validateCondition(step, name));

    // A variable that only a later step creates would never be filled in
    for (const variable of stepVariables(step)) {
      if (!produced.has(variable) && laterOutputs.has(variable) && laterOutputs.get(variable) !== step.id) {
        errors.push(
          `${name}: uses {{${variable}}}, which step "${laterOutputs.get(variable)}" only produces later. ` +
          'Move that step above this one.'
        );
      }
    }

    if (typeof step.output === 'string' && step.output) {
      produced.add(step.output);
    }
  });

  return errors;
}

class WorkflowValidationError extends Error {
  constructor(errors) {
    super(errors.join('; '));
    this.errors = errors;
  }
}

module.exports = {
  validateWorkflow, requiredInputs, templateRoots, CONDITION_OPERATORS, WorkflowValidationError
};
