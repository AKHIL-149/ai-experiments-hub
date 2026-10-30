const fs = require('fs').promises;
const path = require('path');

/**
 * Manages workflow execution persistence and logging
 */
class ExecutionManager {
  constructor(executionsDir = './data/executions') {
    this.executionsDir = executionsDir;
  }

  /**
   * Generate unique execution ID
   * @returns {String} Execution ID
   */
  generateExecutionId() {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const random = Math.random().toString(36).substring(2, 8);
    return `exec-${timestamp}-${random}`;
  }

  /**
   * Create new execution record
   * @param {String} workflowId - Workflow identifier
   * @param {String} triggerType - How workflow was triggered
   * @param {Object} inputData - Input data for workflow
   * @param {Object} options - Run options (model)
   * @returns {Promise<Object>} Created execution record
   */
  async createExecution(workflowId, triggerType, inputData = {}, options = {}) {
    const executionId = this.generateExecutionId();

    const execution = {
      execution_id: executionId,
      workflow_id: workflowId,
      status: 'pending',
      trigger_type: triggerType,
      started_at: new Date().toISOString(),
      input_data: inputData,
      model: options.model || null, // null: the server's default model
      steps_completed: 0,
      steps_failed: 0,
      logs: [],
      outputs: {},
      artifacts: []
    };

    await this._saveExecution(execution);
    return execution;
  }

  /**
   * Update execution status
   * @param {String} executionId - Execution ID
   * @param {String} status - New status (running, completed, failed)
   * @param {Object} result - Execution result (optional)
   * @returns {Promise<Object>} Updated execution
   */
  async updateExecutionStatus(executionId, status, result = null) {
    const execution = await this.loadExecution(executionId);

    execution.status = status;

    if (status === 'completed' || status === 'failed') {
      execution.completed_at = new Date().toISOString();
      const startTime = new Date(execution.started_at);
      const endTime = new Date(execution.completed_at);
      execution.duration_ms = endTime - startTime;
    }

    if (result) {
      execution.result = result;
    }

    await this._saveExecution(execution);
    return execution;
  }

  /**
   * Append log entry to execution
   * @param {String} executionId - Execution ID
   * @param {String} level - Log level (info, warn, error)
   * @param {String} message - Log message
   * @param {Object} metadata - Additional metadata
   * @returns {Promise<void>}
   */
  async appendLog(executionId, level, message, metadata = {}) {
    const execution = await this.loadExecution(executionId);

    execution.logs.push({
      timestamp: new Date().toISOString(),
      level,
      message,
      ...metadata
    });

    await this._saveExecution(execution);
  }

  /**
   * Update execution outputs
   * @param {String} executionId - Execution ID
   * @param {Object} outputs - Step outputs
   * @returns {Promise<void>}
   */
  async updateOutputs(executionId, outputs) {
    const execution = await this.loadExecution(executionId);
    execution.outputs = { ...execution.outputs, ...outputs };
    await this._saveExecution(execution);
  }

  /**
   * Increment step counters
   * @param {String} executionId - Execution ID
   * @param {Boolean} success - Whether step succeeded
   * @returns {Promise<void>}
   */
  async incrementStepCounter(executionId, success = true) {
    const execution = await this.loadExecution(executionId);

    if (success) {
      execution.steps_completed++;
    } else {
      execution.steps_failed++;
    }

    await this._saveExecution(execution);
  }

  /**
   * Load execution record
   * @param {String} executionId - Execution ID
   * @returns {Promise<Object>} Execution record
   */
  async loadExecution(executionId) {
    if (typeof executionId !== 'string' || !/^exec-[\w-]+$/.test(executionId)) {
      throw new Error(`Execution not found: ${executionId}`);
    }

    const filePath = path.join(this.executionsDir, `${executionId}.json`);

    try {
      const data = await fs.readFile(filePath, 'utf-8');
      return JSON.parse(data);
    } catch (error) {
      throw new Error(`Execution not found: ${executionId}`);
    }
  }

  /**
   * List all executions
   * @param {Object} filters - Optional filters
   * @returns {Promise<Array>} List of executions
   */
  async listExecutions(filters = {}) {
    try {
      await fs.mkdir(this.executionsDir, { recursive: true });
      const files = await fs.readdir(this.executionsDir);

      const executions = [];
      for (const file of files) {
        if (!file.endsWith('.json')) continue;

        // One unreadable record must not hide every other execution
        let execution;
        try {
          execution = JSON.parse(await fs.readFile(path.join(this.executionsDir, file), 'utf-8'));
        } catch (error) {
          console.warn(`Skipping unreadable execution record ${file}: ${error.message}`);
          continue;
        }

        // Apply filters
        if (filters.workflow_id && execution.workflow_id !== filters.workflow_id) {
          continue;
        }
        if (filters.status && execution.status !== filters.status) {
          continue;
        }

        executions.push(execution);
      }

      // Sort by start time descending
      executions.sort((a, b) =>
        new Date(b.started_at) - new Date(a.started_at)
      );

      return executions;
    } catch (error) {
      return [];
    }
  }

  /**
   * Save execution to file
   * @param {Object} execution - Execution record
   * @returns {Promise<void>}
   * @private
   */
  async _saveExecution(execution) {
    await fs.mkdir(this.executionsDir, { recursive: true });

    const filePath = path.join(this.executionsDir, `${execution.execution_id}.json`);
    // Write a temp file and rename it into place: a reader (the history list, the live monitor)
    // sees the old or the new record, never a half-written one
    this.writeCounter = (this.writeCounter || 0) + 1;
    const temp = `${filePath}.${process.pid}.${this.writeCounter}.tmp`;
    await fs.writeFile(temp, JSON.stringify(execution, null, 2), 'utf-8');
    await fs.rename(temp, filePath);
  }
}

module.exports = ExecutionManager;
