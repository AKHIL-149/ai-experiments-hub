const fs = require('fs').promises;
const path = require('path');
const PythonBridge = require('./PythonBridge');
const ExecutionManager = require('./ExecutionManager');

/**
 * Core workflow execution engine
 */
class WorkflowEngine {
  constructor(workflowsDir = './workflows', options = {}) {
    this.workflowsDir = workflowsDir;
    this.pythonBridge = new PythonBridge(
      options.pythonPath || process.env.PYTHON_PATH || 'python3',
      options.pythonTimeout || parseInt(process.env.PYTHON_TIMEOUT) || 300000
    );
    this.executionManager = new ExecutionManager(
      options.executionsDir || process.env.EXECUTIONS_DIR || './data/executions'
    );
  }

  /**
   * Load workflow definition from file
   * @param {String} workflowId - Workflow ID
   * @returns {Promise<Object>} Workflow definition
   */
  async loadWorkflow(workflowId) {
    const workflowPath = path.join(this.workflowsDir, `${workflowId}.json`);

    try {
      const data = await fs.readFile(workflowPath, 'utf-8');
      return JSON.parse(data);
    } catch (error) {
      throw new Error(`Workflow not found: ${workflowId}`);
    }
  }

  /**
   * Execute a workflow
   * @param {String} workflowId - Workflow ID
   * @param {Object} inputData - Input data for workflow
   * @param {Object} options - Execution options
   * @returns {Promise<Object>} Execution result
   */
  async executeWorkflow(workflowId, inputData = {}, options = {}) {
    // Load workflow definition
    const workflow = await this.loadWorkflow(workflowId);

    // Create execution record
    const execution = await this.executionManager.createExecution(
      workflowId,
      options.triggerType || 'manual',
      inputData
    );

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

      return await this.executionManager.loadExecution(execution.execution_id);

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

      if (step.type === 'agent') {
        // Execute agent step via Python
        result = await this.executeAgentStep(step, context, options);
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
        result: result
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
   * Execute an agent step using Python bridge
   * @param {Object} step - Step definition
   * @param {Object} context - Execution context
   * @param {Object} options - Execution options
   * @returns {Promise<Object>} Agent result
   */
  async executeAgentStep(step, context, options = {}) {
    // Resolve template variables in task (e.g., {{variable}})
    const task = this.resolveTemplateVariables(step.task, context);

    // Execute via Python bridge
    const agentResult = await this.pythonBridge.executeAgent(task, {
      backend: options.backend || 'ollama',
      model: options.model,
      logStderr: true
    });

    if (!agentResult.success) {
      throw new Error(agentResult.error || 'Agent execution failed');
    }

    return agentResult.result;
  }

  /**
   * Resolve template variables like {{variable}} in an object
   * @param {Object} obj - Object with potential template variables
   * @param {Object} context - Context with variable values
   * @returns {Object} Object with resolved variables
   */
  resolveTemplateVariables(obj, context) {
    const resolved = {};

    for (const [key, value] of Object.entries(obj)) {
      if (typeof value === 'string') {
        // Replace {{variable}} with context value
        resolved[key] = value.replace(/\{\{(\w+)\}\}/g, (match, varName) => {
          if (varName in context) {
            const ctxValue = context[varName];
            return typeof ctxValue === 'string' ? ctxValue : JSON.stringify(ctxValue);
          }
          return match;
        });
      } else if (typeof value === 'object' && value !== null) {
        resolved[key] = this.resolveTemplateVariables(value, context);
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
    try {
      await fs.mkdir(this.workflowsDir, { recursive: true });
      const files = await fs.readdir(this.workflowsDir, { recursive: true });

      const workflows = [];
      for (const file of files) {
        if (!file.endsWith('.json')) continue;

        const filePath = path.join(this.workflowsDir, file);
        const data = await fs.readFile(filePath, 'utf-8');
        const workflow = JSON.parse(data);

        workflows.push({
          id: workflow.id,
          name: workflow.name,
          description: workflow.description,
          steps: workflow.steps.length
        });
      }

      return workflows;
    } catch (error) {
      return [];
    }
  }
}

module.exports = WorkflowEngine;
