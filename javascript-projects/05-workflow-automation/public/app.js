class WorkflowApp {
  constructor() {
    this.workflows = [];
    this.executions = [];
    this.currentWorkflow = null;
    this.monitorEventSource = null;

    this.init();
  }

  async init() {
    this.setupEventListeners();
    await this.checkHealth();
    await this.loadWorkflows();
    await this.loadExecutions();

    // Refresh health every 30 seconds
    setInterval(() => this.checkHealth(), 30000);
  }

  setupEventListeners() {
    // Tab navigation
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', (e) => this.switchTab(e.target.dataset.tab));
    });

    // Dashboard
    document.getElementById('executeBtn').addEventListener('click', () => this.executeWorkflow());

    // History
    document.getElementById('refreshHistoryBtn').addEventListener('click', () => this.loadExecutions());
    document.getElementById('statusFilter').addEventListener('change', () => this.loadExecutions());
    document.querySelector('.modal-close')?.addEventListener('click', () => this.closeModal());

    // Editor
    document.getElementById('newWorkflowBtn').addEventListener('click', () => this.newWorkflow());
    document.getElementById('saveWorkflowBtn').addEventListener('click', () => this.saveWorkflow());
    document.getElementById('loadWorkflowBtn').addEventListener('click', () => this.loadWorkflowToEditor());
    document.getElementById('addStepBtn').addEventListener('click', () => this.addStep());

    // Update JSON preview when properties change
    ['workflowId', 'workflowName', 'workflowDesc'].forEach(id => {
      document.getElementById(id)?.addEventListener('input', () => this.updateJsonPreview());
    });

    // Monitor
    document.getElementById('startMonitorBtn').addEventListener('click', () => this.startMonitoring());
    document.getElementById('stopMonitorBtn').addEventListener('click', () => this.stopMonitoring());
  }

  switchTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === tabName);
    });

    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => {
      content.classList.toggle('active', content.id === tabName);
    });

    // Load data for specific tabs
    if (tabName === 'history') {
      this.loadExecutions();
    }
  }

  async checkHealth() {
    try {
      const response = await fetch('/api/health');
      const data = await response.json();

      const indicator = document.getElementById('healthIndicator');
      const text = document.getElementById('healthText');

      if (data.python === 'healthy') {
        indicator.className = 'status-indicator status-ok';
        text.textContent = 'System Healthy';
      } else {
        indicator.className = 'status-indicator status-error';
        text.textContent = 'Python Agent Unhealthy';
      }
    } catch (error) {
      const indicator = document.getElementById('healthIndicator');
      const text = document.getElementById('healthText');
      indicator.className = 'status-indicator status-error';
      text.textContent = 'Server Offline';
    }
  }

  async loadWorkflows() {
    try {
      const response = await fetch('/api/workflows');
      this.workflows = await response.json();

      this.renderWorkflows();
      this.updateWorkflowSelect();
    } catch (error) {
      console.error('Failed to load workflows:', error);
      document.getElementById('workflowsList').innerHTML =
        `<div class="error">Failed to load workflows: ${error.message}</div>`;
    }
  }

  renderWorkflows() {
    const container = document.getElementById('workflowsList');

    if (this.workflows.length === 0) {
      container.innerHTML = '<div class="empty-state">No workflows found</div>';
      return;
    }

    container.innerHTML = this.workflows.map(workflow => `
      <div class="workflow-card">
        <h3>${workflow.name}</h3>
        <p>${workflow.description || 'No description'}</p>
        <div class="workflow-meta">
          <span class="badge">${workflow.steps} steps</span>
          <button class="btn-sm" onclick="app.executeWorkflowById('${workflow.id}')">Execute</button>
        </div>
      </div>
    `).join('');
  }

  updateWorkflowSelect() {
    const select = document.getElementById('workflowSelect');
    select.innerHTML = '<option value="">Select a workflow...</option>' +
      this.workflows.map(w => `<option value="${w.id}">${w.name}</option>`).join('');
  }

  async executeWorkflow() {
    const workflowId = document.getElementById('workflowSelect').value;
    const inputDataText = document.getElementById('inputDataJson').value;

    if (!workflowId) {
      alert('Please select a workflow');
      return;
    }

    let inputData = {};
    if (inputDataText.trim()) {
      try {
        inputData = JSON.parse(inputDataText);
      } catch (error) {
        alert('Invalid JSON in input data');
        return;
      }
    }

    await this.executeWorkflowById(workflowId, inputData);
  }

  async executeWorkflowById(workflowId, inputData = {}) {
    const resultBox = document.getElementById('executeResult');
    resultBox.className = 'result-box';
    resultBox.innerHTML = '<div class="loading">Starting execution...</div>';

    try {
      const response = await fetch(`/api/workflows/${workflowId}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ inputData })
      });

      const data = await response.json();

      if (response.ok) {
        resultBox.innerHTML = `
          <div class="success">
            <strong>Execution Started!</strong><br>
            Execution ID: <code>${data.execution_id}</code><br>
            <button class="btn-sm" onclick="app.monitorExecution('${data.execution_id}')">Monitor</button>
          </div>
        `;

        // Refresh executions list
        setTimeout(() => this.loadExecutions(), 1000);
      } else {
        throw new Error(data.error);
      }
    } catch (error) {
      resultBox.innerHTML = `<div class="error">Execution failed: ${error.message}</div>`;
    }
  }

  async loadExecutions() {
    try {
      const statusFilter = document.getElementById('statusFilter').value;
      const url = statusFilter
        ? `/api/executions?status=${statusFilter}`
        : '/api/executions';

      const response = await fetch(url);
      this.executions = await response.json();

      this.renderExecutions();
    } catch (error) {
      console.error('Failed to load executions:', error);
      document.getElementById('executionsList').innerHTML =
        `<div class="error">Failed to load executions: ${error.message}</div>`;
    }
  }

  renderExecutions() {
    const container = document.getElementById('executionsList');

    if (this.executions.length === 0) {
      container.innerHTML = '<div class="empty-state">No executions found</div>';
      return;
    }

    container.innerHTML = this.executions.map(exec => {
      const startTime = new Date(exec.started_at).toLocaleString();
      const duration = exec.duration_ms ? `${(exec.duration_ms / 1000).toFixed(1)}s` : '-';
      const statusClass = exec.status === 'completed' ? 'success' :
                         exec.status === 'failed' ? 'error' : 'info';

      return `
        <div class="execution-item" onclick="app.showExecutionDetails('${exec.execution_id}')">
          <div class="execution-header">
            <strong>${exec.workflow_id}</strong>
            <span class="badge badge-${statusClass}">${exec.status}</span>
          </div>
          <div class="execution-meta">
            <span>📅 ${startTime}</span>
            <span>⏱️ ${duration}</span>
            <span>✓ ${exec.steps_completed} steps</span>
          </div>
          <div class="execution-id">${exec.execution_id}</div>
        </div>
      `;
    }).join('');
  }

  async showExecutionDetails(executionId) {
    try {
      const response = await fetch(`/api/executions/${executionId}`);
      const execution = await response.json();

      const modal = document.getElementById('executionModal');
      const details = document.getElementById('executionDetails');

      const duration = execution.duration_ms ? `${(execution.duration_ms / 1000).toFixed(1)}s` : 'In progress';

      details.innerHTML = `
        <div class="detail-section">
          <h4>Overview</h4>
          <table class="detail-table">
            <tr><td>Execution ID</td><td><code>${execution.execution_id}</code></td></tr>
            <tr><td>Workflow</td><td>${execution.workflow_id}</td></tr>
            <tr><td>Status</td><td><span class="badge badge-${execution.status}">${execution.status}</span></td></tr>
            <tr><td>Started</td><td>${new Date(execution.started_at).toLocaleString()}</td></tr>
            <tr><td>Duration</td><td>${duration}</td></tr>
            <tr><td>Steps Completed</td><td>${execution.steps_completed}</td></tr>
            <tr><td>Steps Failed</td><td>${execution.steps_failed}</td></tr>
          </table>
        </div>

        <div class="detail-section">
          <h4>Execution Logs</h4>
          <div class="logs-content">
            ${execution.logs.map(log => {
              const time = new Date(log.timestamp).toLocaleTimeString();
              const levelClass = log.level === 'error' ? 'error' : log.level === 'warn' ? 'warn' : 'info';
              return `<div class="log-entry log-${levelClass}">[${time}] [${log.level}] ${log.message}</div>`;
            }).join('')}
          </div>
        </div>

        ${execution.outputs && Object.keys(execution.outputs).length > 0 ? `
        <div class="detail-section">
          <h4>Outputs</h4>
          <pre class="code-block">${JSON.stringify(execution.outputs, null, 2)}</pre>
        </div>
        ` : ''}

        <div class="modal-footer">
          <button class="btn" onclick="app.monitorExecution('${executionId}')">Monitor Live</button>
        </div>
      `;

      modal.classList.remove('hidden');
    } catch (error) {
      alert('Failed to load execution details: ' + error.message);
    }
  }

  closeModal() {
    document.getElementById('executionModal').classList.add('hidden');
  }

  // Workflow Editor
  newWorkflow() {
    document.getElementById('workflowId').value = '';
    document.getElementById('workflowName').value = '';
    document.getElementById('workflowDesc').value = '';
    document.getElementById('stepsList').innerHTML = '<div class="empty-state">No steps yet. Click "Add Step" to begin.</div>';
    this.currentWorkflow = { steps: [] };
    this.updateJsonPreview();
  }

  addStep() {
    const stepId = `step_${Date.now()}`;
    const stepsContainer = document.getElementById('stepsList');

    if (stepsContainer.querySelector('.empty-state')) {
      stepsContainer.innerHTML = '';
    }

    const stepHtml = `
      <div class="step-card" data-step-id="${stepId}">
        <div class="step-header">
          <input class="input-sm step-id" placeholder="Step ID" value="${stepId}" />
          <button class="btn-sm btn-danger" onclick="app.removeStep('${stepId}')">Remove</button>
        </div>
        <input class="input step-type" placeholder="Type (e.g., agent)" value="agent" />
        <textarea class="input textarea step-instruction" placeholder="Task instruction"></textarea>
        <input class="input-sm step-output" placeholder="Output variable name (optional)" />
      </div>
    `;

    stepsContainer.insertAdjacentHTML('beforeend', stepHtml);

    // Add event listeners for JSON preview update
    stepsContainer.querySelectorAll(`[data-step-id="${stepId}"] input, [data-step-id="${stepId}"] textarea`).forEach(el => {
      el.addEventListener('input', () => this.updateJsonPreview());
    });

    this.updateJsonPreview();
  }

  removeStep(stepId) {
    document.querySelector(`[data-step-id="${stepId}"]`)?.remove();

    const stepsContainer = document.getElementById('stepsList');
    if (stepsContainer.children.length === 0) {
      stepsContainer.innerHTML = '<div class="empty-state">No steps yet. Click "Add Step" to begin.</div>';
    }

    this.updateJsonPreview();
  }

  updateJsonPreview() {
    const workflow = {
      id: document.getElementById('workflowId').value || 'workflow-id',
      name: document.getElementById('workflowName').value || 'Workflow Name',
      description: document.getElementById('workflowDesc').value || '',
      steps: []
    };

    document.querySelectorAll('.step-card').forEach(card => {
      const stepId = card.querySelector('.step-id').value;
      const stepType = card.querySelector('.step-type').value || 'agent';
      const instruction = card.querySelector('.step-instruction').value;
      const output = card.querySelector('.step-output').value;

      const step = {
        id: stepId,
        type: stepType,
        task: {
          instruction: instruction
        }
      };

      if (output) {
        step.output = output;
      }

      workflow.steps.push(step);
    });

    document.getElementById('jsonPreview').textContent = JSON.stringify(workflow, null, 2);
  }

  async saveWorkflow() {
    const workflowJson = document.getElementById('jsonPreview').textContent;

    try {
      const workflow = JSON.parse(workflowJson);

      // Save to file (in real implementation, this would be a POST to /api/workflows)
      const blob = new Blob([JSON.stringify(workflow, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${workflow.id}.json`;
      a.click();
      URL.revokeObjectURL(url);

      alert(`Workflow saved! Place the file in the workflows/ directory and refresh.`);
    } catch (error) {
      alert('Invalid workflow JSON: ' + error.message);
    }
  }

  async loadWorkflowToEditor() {
    const workflowId = prompt('Enter workflow ID to load:');
    if (!workflowId) return;

    try {
      const response = await fetch(`/api/workflows/${workflowId}`);
      const workflow = await response.json();

      document.getElementById('workflowId').value = workflow.id;
      document.getElementById('workflowName').value = workflow.name;
      document.getElementById('workflowDesc').value = workflow.description || '';

      // Clear existing steps
      document.getElementById('stepsList').innerHTML = '';

      // Add workflow steps
      workflow.steps.forEach(step => {
        this.addStep();
        const lastStep = document.querySelector('.step-card:last-child');
        lastStep.querySelector('.step-id').value = step.id;
        lastStep.querySelector('.step-type').value = step.type;
        lastStep.querySelector('.step-instruction').value = step.task.instruction || '';
        lastStep.querySelector('.step-output').value = step.output || '';
      });

      this.updateJsonPreview();
    } catch (error) {
      alert('Failed to load workflow: ' + error.message);
    }
  }

  // Live Monitor
  monitorExecution(executionId) {
    this.switchTab('monitor');
    document.getElementById('monitorExecutionId').value = executionId;
    this.startMonitoring();
  }

  startMonitoring() {
    const executionId = document.getElementById('monitorExecutionId').value;
    if (!executionId) {
      alert('Please enter an execution ID');
      return;
    }

    // Stop existing monitoring
    this.stopMonitoring();

    // Show monitor UI
    document.getElementById('monitorStatus').classList.remove('hidden');
    document.getElementById('monitorLogs').classList.remove('hidden');
    document.getElementById('logsContent').innerHTML = '';
    document.getElementById('startMonitorBtn').disabled = true;
    document.getElementById('stopMonitorBtn').disabled = false;

    // Start SSE connection
    this.monitorEventSource = new EventSource(`/api/executions/${executionId}/stream`);

    this.monitorEventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'update') {
        this.updateMonitorDisplay(data.execution);
      } else if (data.type === 'done') {
        this.stopMonitoring();
        alert('Execution completed!');
      } else if (data.type === 'error') {
        this.stopMonitoring();
        alert('Monitoring error: ' + data.error);
      }
    };

    this.monitorEventSource.onerror = () => {
      this.stopMonitoring();
      alert('Lost connection to server');
    };
  }

  updateMonitorDisplay(execution) {
    // Update status
    const statusBadge = document.getElementById('monitorStatusValue');
    statusBadge.textContent = execution.status;
    statusBadge.className = `badge badge-${execution.status === 'completed' ? 'success' : execution.status === 'failed' ? 'error' : 'info'}`;

    // Update steps
    document.getElementById('monitorStepsValue').textContent =
      `${execution.steps_completed} completed, ${execution.steps_failed} failed`;

    // Update duration
    if (execution.duration_ms) {
      document.getElementById('monitorDurationValue').textContent =
        `${(execution.duration_ms / 1000).toFixed(1)}s`;
    } else {
      const startTime = new Date(execution.started_at);
      const duration = Date.now() - startTime;
      document.getElementById('monitorDurationValue').textContent =
        `${(duration / 1000).toFixed(1)}s`;
    }

    // Update logs
    const logsContainer = document.getElementById('logsContent');
    logsContainer.innerHTML = execution.logs.map(log => {
      const time = new Date(log.timestamp).toLocaleTimeString();
      const levelClass = log.level === 'error' ? 'error' : log.level === 'warn' ? 'warn' : 'info';
      return `<div class="log-entry log-${levelClass}">[${time}] [${log.level}] ${log.message}</div>`;
    }).join('');

    // Auto-scroll logs
    logsContainer.scrollTop = logsContainer.scrollHeight;
  }

  stopMonitoring() {
    if (this.monitorEventSource) {
      this.monitorEventSource.close();
      this.monitorEventSource = null;
    }
    document.getElementById('startMonitorBtn').disabled = false;
    document.getElementById('stopMonitorBtn').disabled = true;
  }
}

// Initialize app
const app = new WorkflowApp();
