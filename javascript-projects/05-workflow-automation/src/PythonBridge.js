const { spawn } = require('child_process');
const path = require('path');

const PROJECT_ROOT = path.join(__dirname, '..');

/**
 * Bridge for executing Python agents and handling IPC
 */
class PythonBridge {
  constructor(pythonPath = 'python3', timeout = 300000) {
    this.pythonPath = pythonPath;
    this.timeout = timeout;
  }

  /**
   * Execute Python agent with task data
   * @param {Object} taskData - Task definition
   * @param {Object} options - Execution options
   * @returns {Promise<Object>} Agent execution result
   */
  async executeAgent(taskData, options = {}) {
    const {
      backend = 'ollama',
      model = null,
      timeout = this.timeout
    } = options;

    const agentPath = path.join(__dirname, '../python/agent.py');
    const taskJson = JSON.stringify(taskData);

    const args = [
      agentPath,
      '--task-type', 'workflow',
      '--input', taskJson,
      '--backend', backend
    ];

    if (model) {
      args.push('--model', model);
    }

    return new Promise((resolve, reject) => {
      const pythonProcess = spawn(this.pythonPath, args, { cwd: PROJECT_ROOT });

      let stdoutData = '';
      let stderrData = '';
      let timeoutId = null;

      // Set timeout
      if (timeout) {
        timeoutId = setTimeout(() => {
          pythonProcess.kill();
          reject(new Error(`Python process timeout after ${timeout}ms`));
        }, timeout);
      }

      // Collect stdout (JSON result)
      pythonProcess.stdout.on('data', (data) => {
        stdoutData += data.toString();
      });

      // Collect stderr (logs and errors)
      pythonProcess.stderr.on('data', (data) => {
        stderrData += data.toString();
        // Log stderr in real-time for debugging
        if (options.logStderr) {
          console.error('[Python Agent]', data.toString().trim());
        }
      });

      // Handle process completion
      pythonProcess.on('close', (code) => {
        if (timeoutId) {
          clearTimeout(timeoutId);
        }

        // The agent prints a JSON result to stdout even when the task fails
        // (exit code 1), so prefer its structured error over raw stderr logs
        let parsed = null;
        try {
          parsed = JSON.parse(stdoutData);
        } catch (e) {
          // handled below
        }

        if (parsed) {
          resolve(parsed);
        } else if (code === 0) {
          reject(new Error(`Failed to parse Python output: invalid JSON\n${stdoutData}`));
        } else {
          reject(new Error(`Python process failed (exit code ${code}):\n${stderrData}`));
        }
      });

      // Handle process errors
      pythonProcess.on('error', (error) => {
        if (timeoutId) {
          clearTimeout(timeoutId);
        }
        reject(new Error(`Failed to spawn Python process: ${error.message}`));
      });
    });
  }

  /**
   * Run one tool directly, without an LLM
   * @param {String} tool - Registered tool name
   * @param {Object} params - Tool parameters
   * @returns {Promise<Object>} {success, result, error}
   */
  executeTool(tool, params, timeout = 60000) {
    const scriptPath = path.join(__dirname, '../python/run_tool.py');

    return new Promise((resolve, reject) => {
      const proc = spawn(
        this.pythonPath,
        [scriptPath, '--tool', tool, '--params', JSON.stringify(params)],
        { cwd: PROJECT_ROOT }
      );

      let stdout = '';
      let stderr = '';
      const timeoutId = setTimeout(() => {
        proc.kill();
        reject(new Error(`Tool ${tool} timed out after ${timeout}ms`));
      }, timeout);

      proc.stdout.on('data', (d) => { stdout += d.toString(); });
      proc.stderr.on('data', (d) => { stderr += d.toString(); });
      proc.on('close', () => {
        clearTimeout(timeoutId);
        try {
          resolve(JSON.parse(stdout));
        } catch (e) {
          reject(new Error(`Tool ${tool} produced no result:\n${stderr || stdout}`));
        }
      });
      proc.on('error', (error) => {
        clearTimeout(timeoutId);
        reject(new Error(`Failed to spawn Python process: ${error.message}`));
      });
    });
  }

  /**
   * Describe the registered tools (name, description, parameter schema) for the editor
   * @returns {Promise<Array>} Tool descriptions
   */
  listTools(timeout = 15000) {
    const scriptPath = path.join(__dirname, '../python/run_tool.py');

    return new Promise((resolve, reject) => {
      const proc = spawn(this.pythonPath, [scriptPath, '--list'], { cwd: PROJECT_ROOT });
      let stdout = '';
      let stderr = '';
      const timeoutId = setTimeout(() => {
        proc.kill();
        reject(new Error('Listing tools timed out'));
      }, timeout);

      proc.stdout.on('data', (d) => { stdout += d.toString(); });
      proc.stderr.on('data', (d) => { stderr += d.toString(); });
      proc.on('close', () => {
        clearTimeout(timeoutId);
        try {
          resolve(JSON.parse(stdout).tools);
        } catch (e) {
          reject(new Error(`Could not list tools:\n${stderr || stdout}`));
        }
      });
      proc.on('error', (error) => {
        clearTimeout(timeoutId);
        reject(new Error(`Failed to spawn Python process: ${error.message}`));
      });
    });
  }

  /**
   * Test Python environment health: the interpreter starts and the agent's
   * imports resolve. Deliberately does not call an LLM, so it is fast and can
   * be polled without loading the model.
   * @returns {Promise<Boolean>} True if Python environment is working
   */
  async healthCheck() {
    return new Promise((resolve) => {
      const proc = spawn(this.pythonPath, ['-c', 'import requests, dotenv']);
      const timeoutId = setTimeout(() => {
        proc.kill();
        resolve(false);
      }, 10000);

      proc.on('close', (code) => {
        clearTimeout(timeoutId);
        resolve(code === 0);
      });
      proc.on('error', (error) => {
        clearTimeout(timeoutId);
        console.error('Python health check failed:', error.message);
        resolve(false);
      });
    });
  }
}

module.exports = PythonBridge;
