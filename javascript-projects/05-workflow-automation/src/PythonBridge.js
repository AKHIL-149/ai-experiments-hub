const { spawn } = require('child_process');
const path = require('path');

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
      const pythonProcess = spawn(this.pythonPath, args);

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

        if (code === 0) {
          try {
            const result = JSON.parse(stdoutData);
            resolve(result);
          } catch (e) {
            reject(new Error(`Failed to parse Python output: ${e.message}\n${stdoutData}`));
          }
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
   * Test Python environment health
   * @returns {Promise<Boolean>} True if Python environment is working
   */
  async healthCheck() {
    try {
      const testTask = {
        instruction: "Test health check - respond with 'OK'",
        context: {}
      };

      const result = await this.executeAgent(testTask, {
        backend: 'ollama',
        timeout: 30000
      });

      return result.success === true;
    } catch (error) {
      console.error('Python health check failed:', error.message);
      return false;
    }
  }
}

module.exports = PythonBridge;
