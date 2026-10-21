const fs = require('fs').promises;
const path = require('path');
const PythonBridge = require('./PythonBridge');
const ExecutionManager = require('./ExecutionManager');

const PROJECT_ROOT = path.join(__dirname, '..');

/**
 * Core workflow execution engine
 */
class WorkflowEngine {
  constructor(workflowsDir, options = {}) {
    // Relative paths resolve against the project root, not the process cwd
    this.workflowsDir = path.resolve(PROJECT_ROOT, workflowsDir || process.env.WORKFLOWS_DIR || './workflows');
    this.pythonBridge = new PythonBridge(
      options.pythonPath || process.env.PYTHON_PATH || 'python3',
      options.pythonTimeout || parseInt(process.env.PYTHON_TIMEOUT) || 300000
    );
    this.executionManager = new ExecutionManager(
      path.resolve(PROJECT_ROOT, options.executionsDir || process.env.EXECUTIONS_DIR || './data/executions')
    );
  }

  /**
   * Load workflow definition from file
   * @param {String} workflowId - Workflow ID
   * @returns {Promise<Object>} Workflow definition
   */
  async loadWorkflow(workflowId) {
    if (typeof workflowId !== 'string' || !/^[\w-]+(\/[\w-]+)*$/.test(workflowId)) {
      throw new Error(`Workflow not found: ${workflowId}`);
    }

    // Direct path (e.g. "examples/file-processor"), kept inside the workflows dir
    const root = path.resolve(this.workflowsDir);
    const workflowPath = path.resolve(root, `${workflowId}.json`);
    if (workflowPath.startsWith(root + path.sep)) {
      try {
        return JSON.parse(await fs.readFile(workflowPath, 'utf-8'));
      } catch (error) {
        // fall through to lookup by the "id" field
      }
    }

    // The list endpoint advertises each workflow's own "id", which can differ
    // from its file path when it lives in a sub-folder
    const found = (await this._readAllWorkflows()).find(w => w.id === workflowId);
    if (found) {
      return found;
    }
    throw new Error(`Workflow not found: ${workflowId}`);
  }

  /**
   * Execute a workflow
   * @param {String} workflowId - Workflow ID
   * @param {Object} inputData - Input data for workflow
   * @param {Object} options - Execution options
   * @returns {Promise<Object>} Execution result
   */
  async executeWorkflow(workflowId, inputData = {}, options = {}) {
    const { execution, run } = await this.startExecution(workflowId, inputData, options);
    await run();
    return await this.executionManager.loadExecution(execution.execution_id);
  }

  /**
   * Validate the workflow and create its execution record, without running it.
   * Lets callers (the API) get the real execution ID and report "not found"
   * before anything runs.
   * @returns {Promise<{execution: Object, run: Function}>} run() performs the execution
   */
  async startExecution(workflowId, inputData = {}, options = {}) {
    const workflow = await this.loadWorkflow(workflowId);

    const execution = await this.executionManager.createExecution(
      workflowId,
      options.triggerType || 'manual',
      inputData
    );

    return {
      execution,
      run: () => this._runExecution(workflow, execution, inputData, options)
    };
  }

  async _runExecution(workflow, execution, inputData, options) {
    await this.executionManager.appendLog(
      execution.execution_id,
      'info',
      `Starting workflow: ${workflow.name}`
    );

    try {
      // Update status to running
      await this.executionManager.updateExecutionStatus(execution.execution_id, 'running');

      // Execute workflow steps
      const context = { ...inputData };
      const stepResults = [];

      for (const step of workflow.steps) {
        const stepResult = await this.executeStep(
          execution.execution_id,
          step,
          context,
          options
        );

        stepResults.push(stepResult);

        // Store step output in context
        if (step.output && stepResult.success) {
          context[step.output] = stepResult.result;
        }

        // Stop on failure unless configured to continue
        if (!stepResult.success && !options.continueOnError) {
          break;
        }
      }

      // Determine final status
      const allSucceeded = stepResults.every(r => r.success);
      const finalStatus = allSucceeded ? 'completed' : 'failed';

      // Update execution with final result
      await this.executionManager.updateExecutionStatus(
        execution.execution_id,
        finalStatus,
        {
          steps: stepResults,
          outputs: context
        }
      );

      await this.executionManager.updateOutputs(execution.execution_id, context);

      await this.executionManager.appendLog(
        execution.execution_id,
        'info',
        `Workflow ${finalStatus}: ${workflow.name}`
      );

      return finalStatus;

    } catch (error) {
      // Mark execution as failed
      await this.executionManager.updateExecutionStatus(
        execution.execution_id,
        'failed',
        { error: error.message }
      );

      await this.executionManager.appendLog(
        execution.execution_id,
        'error',
        `Workflow failed: ${error.message}`
      );

      throw error;
    }
  }

  /**
   * Execute a single workflow step
   * @param {String} executionId - Execution ID
   * @param {Object} step - Step definition
   * @param {Object} context - Execution context
   * @param {Object} options - Execution options
   * @returns {Promise<Object>} Step result
   */
  async executeStep(executionId, step, context, options = {}) {
    await this.executionManager.appendLog(
      executionId,
      'info',
      `Executing step: ${step.id}`,
      { step_type: step.type }
    );

    try {
      let result;
      let details = null;

      if (step.type === 'agent') {
        // Execute agent step via Python
        const agentResult = await this.executeAgentStep(step, context, options);
        result = agentResult.result;
        details = {
          tools_used: agentResult.tools_used || [],
          tool_results: agentResult.tool_results || []
        };
      } else if (step.type === 'tool') {
        // Deterministic tool call: no LLM planning, parameters come from the step
        result = await this.executeToolStep(step, context);
        details = { tools_used: [step.tool] };
      } else {
        throw new Error(`Unsupported step type: ${step.type}`);
      }

      await this.executionManager.incrementStepCounter(executionId, true);

      await this.executionManager.appendLog(
        executionId,
        'info',
        `Step completed: ${step.id}`
      );

      return {
        step_id: step.id,
        success: true,
        result: result,
        ...(details && { details })
      };

    } catch (error) {
      await this.executionManager.incrementStepCounter(executionId, false);

      await this.executionManager.appendLog(
        executionId,
        'error',
        `Step failed: ${step.id} - ${error.message}`
      );

      return {
        step_id: step.id,
        success: false,
        error: error.message
      };
    }
  }

  /**
   * Execute a tool step: run a registered tool directly with templated parameters
   * @returns {Promise<Object>} The tool's result object
   */
  async executeToolStep(step, context) {
    if (!step.tool) {
      throw new Error(`Tool step "${step.id}" is missing "tool"`);
    }

    const missing = new Set();
    const params = this.resolveTemplateVariables(step.parameters || {}, context, missing);
    if (missing.size > 0) {
      throw new Error(`Unresolved template variable(s): ${[...missing].join(', ')}`);
    }

    const response = await this.pythonBridge.executeTool(step.tool, params);
    if (!response.success) {
      throw new Error(response.error || `Tool ${step.tool} failed`);
    }
    return response.result;
  }

  /**
   * Execute an agent step using Python bridge
   * @param {Object} step - Step definition
   * @param {Object} context - Execution context
   * @param {Object} options - Execution options
   * @returns {Promise<Object>} Agent result
   */
  async executeAgentStep(step, context, options = {}) {
    // Resolve template variables in task (e.g., {{variable}})
    const missing = new Set();
    const task = this.resolveTemplateVariables(step.task, context, missing);
    if (missing.size > 0) {
      // Sending a literal "{{name}}" to the model would silently produce nonsense
      throw new Error(
        `Unresolved template variable(s): ${[...missing].join(', ')} ` +
        `(not an input or the "output" of an earlier step)`
      );
    }

    // Execute via Python bridge
    const agentResult = await this.pythonBridge.executeAgent(task, {
      backend: options.backend || 'ollama',
      model: options.model,
      logStderr: true
    });

    if (!agentResult.success) {
      throw new Error(agentResult.error || 'Agent execution failed');
    }

    return agentResult;
  }

  /**
   * Resolve template variables like {{variable}} in an object
   * @param {Object} obj - Object with potential template variables
   * @param {Object} context - Context with variable values
   * @returns {Object} Object with resolved variables
   */
  resolveTemplateVariables(obj, context, missing = new Set()) {
    const resolved = {};

    for (const [key, value] of Object.entries(obj)) {
      if (typeof value === 'string') {
        // Replace {{variable}} with context value
        // {{name}} or a path into an object output, e.g. {{notes.content}}
        resolved[key] = value.replace(/\{\{([\w]+(?:\.[\w]+)*)\}\}/g, (match, varName) => {
          let ctxValue = context;
          for (const part of varName.split('.')) {
            if (ctxValue === null || typeof ctxValue !== 'object' || !(part in ctxValue)) {
              missing.add(varName);
              return match;
            }
            ctxValue = ctxValue[part];
          }
          return typeof ctxValue === 'string' ? ctxValue : JSON.stringify(ctxValue);
        });
      } else if (typeof value === 'object' && value !== null) {
        resolved[key] = this.resolveTemplateVariables(value, context, missing);
      } else {
        resolved[key] = value;
      }
    }

    return resolved;
  }

  /**
   * List all available workflows
   * @returns {Promise<Array>} List of workflow summaries
   */
  async listWorkflows() {
    const workflows = await this._readAllWorkflows();
    return workflows.map(workflow => ({
      id: workflow.id,
      name: workflow.name,
      description: workflow.description,
      steps: Array.isArray(workflow.steps) ? workflow.steps.length : 0
    }));
  }

  /**
   * Read every workflow definition under the workflows dir. A malformed file
   * is skipped with a warning instead of hiding every other workflow.
   */
  async _readAllWorkflows() {
    let files;
    try {
      await fs.mkdir(this.workflowsDir, { recursive: true });
      files = await fs.readdir(this.workflowsDir, { recursive: true });
    } catch (error) {
      return [];
    }

    const workflows = [];
    for (const file of files) {
      if (!file.endsWith('.json')) continue;

      try {
        const data = await fs.readFile(path.join(this.workflowsDir, file), 'utf-8');
        const workflow = JSON.parse(data);
        if (workflow && workflow.id && Array.isArray(workflow.steps)) {
          workflows.push(workflow);
        } else {
          console.warn(`Skipping ${file}: missing "id" or "steps"`);
        }
      } catch (error) {
        console.warn(`Skipping ${file}: ${error.message}`);
      }
    }
    return workflows;
  }
}

module.exports = WorkflowEngine;
