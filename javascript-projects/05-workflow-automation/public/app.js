// Escape text before it goes into innerHTML: workflow names and LLM output are untrusted
function esc(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// Text shown as formatted markdown, with a button to flip to the raw text
function textBlock(text, asMarkdown = true) {
  if (!asMarkdown) {
    return `<pre class="output-text">${esc(text)}</pre>`;
  }
  return `
    <div class="text-block">
      <div class="md-view">${renderMarkdown(text)}</div>
      <pre class="output-text hidden">${esc(text)}</pre>
      <button class="btn-sm raw-toggle">Show raw text</button>
    </div>`;
}

function statusClass(status) {
  return status === 'completed' ? 'success' : status === 'failed' ? 'error' : 'info';
}

function formatDuration(ms) {
  return ms ? `${(ms / 1000).toFixed(1)}s` : null;
}

// Variables a run must be given: used by a step but not produced by an earlier step
function detectInputs(workflow) {
  const produced = new Set();
  const inputs = [];
  const scan = (value) => {
    if (typeof value === 'string') {
      for (const m of value.matchAll(/\{\{(\w+)(?:\.\w+)*\}\}/g)) {
        if (!produced.has(m[1]) && !inputs.includes(m[1])) inputs.push(m[1]);
      }
    } else if (value && typeof value === 'object') {
      Object.values(value).forEach(scan);
    }
  };
  for (const step of workflow.steps || []) {
    scan(step.type === 'tool' ? step.parameters : step.task);
    if (step.output) produced.add(step.output);
  }
  return inputs;
}

class WorkflowApp {
  constructor() {
    this.workflows = [];
    this.executions = [];
    this.tools = [];
    this.monitorEventSource = null;
    this.monitorRenderedKey = null;

    // Editor state: steps are kept as data and re-rendered, so loading and saving
    // never depend on what happens to be in the DOM
    this.editor = { steps: [], loadedId: null };
    this.stepCounter = 0;
    this.autoInputs = '';

    this.init();
  }

  async init() {
    this.setupEventListeners();
    await this.checkHealth();
    await Promise.all([this.loadWorkflows(), this.loadExecutions(), this.loadTools()]);
    this.renderSteps();
    this.updateJsonPreview();

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
    document.getElementById('workflowSelect').addEventListener('change', (e) => this.prefillInputs(e.target.value));
    document.getElementById('workflowsList').addEventListener('click', (e) => {
      const button = e.target.closest('[data-run]');
      if (button) this.runFromCard(button.dataset.run);
    });

    // History
    document.getElementById('refreshHistoryBtn').addEventListener('click', () => this.loadExecutions());
    document.getElementById('statusFilter').addEventListener('change', () => this.loadExecutions());
    document.getElementById('executionsList').addEventListener('click', (e) => {
      const item = e.target.closest('[data-execution]');
      if (item) this.showExecutionDetails(item.dataset.execution);
    });
    document.querySelector('.modal-close')?.addEventListener('click', () => this.closeModal());
    document.getElementById('executionModal').addEventListener('click', (e) => {
      if (e.target.id === 'executionModal') this.closeModal();
    });

    // Result viewers (modal and monitor) share these buttons
    document.addEventListener('click', (e) => {
      const artifact = e.target.closest('.view-artifact');
      if (artifact) this.toggleArtifact(artifact);
      const raw = e.target.closest('.raw-toggle');
      if (raw) {
        const block = raw.closest('.text-block');
        const showing = block.querySelector('.md-view').classList.toggle('hidden');
        block.querySelector('pre').classList.toggle('hidden', !showing);
        raw.textContent = showing ? 'Show formatted' : 'Show raw text';
      }
      const monitor = e.target.closest('[data-monitor]');
      if (monitor) this.monitorExecution(monitor.dataset.monitor);
    });

    // Editor
    document.getElementById('newWorkflowBtn').addEventListener('click', () => this.newWorkflow());
    document.getElementById('saveWorkflowBtn').addEventListener('click', () => this.saveWorkflow());
    document.getElementById('saveRunBtn').addEventListener('click', () => this.saveWorkflow({ run: true }));
    document.getElementById('loadWorkflowBtn').addEventListener('click', () => this.loadWorkflowToEditor());
    document.getElementById('addStepBtn').addEventListener('click', () => this.addStep());
    this.setupStepListeners();

    ['workflowId', 'workflowName', 'workflowDesc'].forEach(id => {
      document.getElementById(id)?.addEventListener('input', () => this.updateJsonPreview());
    });

    // Monitor
    document.getElementById('startMonitorBtn').addEventListener('click', () => this.startMonitoring());
    document.getElementById('stopMonitorBtn').addEventListener('click', () => this.stopMonitoring());
  }

  switchTab(tabName) {
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === tabName);
    });
    document.querySelectorAll('.tab-content').forEach(content => {
      content.classList.toggle('active', content.id === tabName);
    });

    if (tabName === 'history') {
      this.loadExecutions();
    }
  }

  async checkHealth() {
    const indicator = document.getElementById('healthIndicator');
    const text = document.getElementById('healthText');
    try {
      const response = await fetch('/api/health');
      const data = await response.json();

      if (data.python !== 'healthy') {
        indicator.className = 'status-indicator status-error';
        text.textContent = 'Python Agent Unhealthy';
      } else if (data.ollama === 'unreachable') {
        indicator.className = 'status-indicator status-error';
        text.textContent = 'Ollama not reachable (AI steps will fail)';
      } else {
        indicator.className = 'status-indicator status-ok';
        text.textContent = 'System Healthy';
      }
    } catch (error) {
      indicator.className = 'status-indicator status-error';
      text.textContent = 'Server Offline';
    }
  }

  // ------------------------------------------------------------ dashboard

  async loadWorkflows() {
    try {
      const response = await fetch('/api/workflows');
      this.workflows = await response.json();

      this.renderWorkflows();
      this.updateWorkflowSelects();
    } catch (error) {
      console.error('Failed to load workflows:', error);
      document.getElementById('workflowsList').innerHTML =
        `<div class="error">Failed to load workflows: ${esc(error.message)}</div>`;
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
        <h3>${esc(workflow.name)}</h3>
        <p>${esc(workflow.description || 'No description')}</p>
        <div class="workflow-meta">
          <span class="badge">${workflow.steps} steps</span>
          <button class="btn-sm" data-run="${esc(workflow.id)}">${workflow.inputs?.length ? 'Set inputs &amp; run' : 'Execute'}</button>
        </div>
      </div>
    `).join('');
  }

  updateWorkflowSelects() {
    const options = this.workflows.map(w => `<option value="${esc(w.id)}">${esc(w.name)}</option>`).join('');

    const select = document.getElementById('workflowSelect');
    const selected = select.value;
    select.innerHTML = '<option value="">Select a workflow...</option>' + options;
    select.value = selected;

    const loadSelect = document.getElementById('loadWorkflowSelect');
    const loadSelected = loadSelect.value;
    loadSelect.innerHTML = '<option value="">Load a saved workflow...</option>' + options;
    loadSelect.value = loadSelected;
  }

  // Fill the input box with the values the chosen workflow needs
  prefillInputs(workflowId) {
    const box = document.getElementById('inputDataJson');
    const hint = document.getElementById('inputHint');
    const workflow = this.workflows.find(w => w.id === workflowId);

    if (!workflow) {
      hint.classList.add('hidden');
      return;
    }

    const inputs = workflow.inputs || [];
    const template = inputs.length
      ? JSON.stringify(Object.fromEntries(inputs.map(name => [name, ''])), null, 2)
      : '';

    // Never overwrite something the user typed
    if (!box.value.trim() || box.value === this.autoInputs) {
      box.value = template;
      this.autoInputs = template;
    }

    hint.textContent = inputs.length
      ? `This workflow needs: ${inputs.join(', ')}. Fill in the values, then execute.`
      : 'This workflow needs no inputs.';
    hint.classList.remove('hidden');
  }

  // Cards run straight away unless the workflow needs inputs
  runFromCard(workflowId) {
    const workflow = this.workflows.find(w => w.id === workflowId);
    if (workflow?.inputs?.length) {
      this.goToRun(workflowId);
    } else {
      this.executeWorkflowById(workflowId);
    }
  }

  goToRun(workflowId) {
    this.switchTab('dashboard');
    document.getElementById('workflowSelect').value = workflowId;
    this.prefillInputs(workflowId);
    document.getElementById('executeResult').className = 'result-box hidden';
    document.getElementById('inputDataJson').scrollIntoView({ behavior: 'smooth', block: 'center' });
    document.getElementById('inputDataJson').focus();
  }

  showExecuteMessage(html, kind) {
    const resultBox = document.getElementById('executeResult');
    resultBox.className = 'result-box';
    resultBox.innerHTML = `<div class="${kind}">${html}</div>`;
  }

  async executeWorkflow() {
    const workflowId = document.getElementById('workflowSelect').value;
    const inputDataText = document.getElementById('inputDataJson').value;

    if (!workflowId) {
      this.showExecuteMessage('Please select a workflow first.', 'error');
      return;
    }

    let inputData = {};
    if (inputDataText.trim()) {
      try {
        inputData = JSON.parse(inputDataText);
      } catch (error) {
        this.showExecuteMessage(`Input data is not valid JSON: ${esc(error.message)}`, 'error');
        return;
      }
      if (!inputData || typeof inputData !== 'object' || Array.isArray(inputData)) {
        this.showExecuteMessage('Input data must be a JSON object, like {"name": "value"}.', 'error');
        return;
      }
    }

    const workflow = this.workflows.find(w => w.id === workflowId);
    const empty = (workflow?.inputs || []).filter(name => inputData[name] === undefined || inputData[name] === '');
    if (empty.length > 0) {
      this.showExecuteMessage(`Fill in a value for: ${esc(empty.join(', '))}`, 'error');
      return;
    }

    await this.executeWorkflowById(workflowId, inputData);
  }

  async executeWorkflowById(workflowId, inputData = {}) {
    this.showExecuteMessage('Starting execution...', 'loading');

    try {
      const response = await fetch(`/api/workflows/${encodeURIComponent(workflowId)}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ inputData })
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error);
      }

      // Follow the run live: logs while it works, results when it finishes
      this.monitorExecution(data.execution_id);
      setTimeout(() => this.loadExecutions(), 1000);
    } catch (error) {
      this.showExecuteMessage(`Execution failed: ${esc(error.message)}`, 'error');
    }
  }

  // ------------------------------------------------------------ history

  async loadExecutions() {
    try {
      const statusFilter = document.getElementById('statusFilter').value;
      const url = statusFilter
        ? `/api/executions?status=${encodeURIComponent(statusFilter)}`
        : '/api/executions';

      const response = await fetch(url);
      this.executions = await response.json();

      this.renderExecutions();
    } catch (error) {
      console.error('Failed to load executions:', error);
      document.getElementById('executionsList').innerHTML =
        `<div class="error">Failed to load executions: ${esc(error.message)}</div>`;
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
      const duration = formatDuration(exec.duration_ms) || '-';

      return `
        <div class="execution-item" data-execution="${esc(exec.execution_id)}">
          <div class="execution-header">
            <strong>${esc(exec.workflow_id)}</strong>
            <span class="badge badge-${statusClass(exec.status)}">${esc(exec.status)}</span>
          </div>
          <div class="execution-meta">
            <span>📅 ${esc(startTime)}</span>
            <span>⏱️ ${esc(duration)}</span>
            <span>✓ ${exec.steps_completed} steps</span>
          </div>
          <div class="execution-id">${esc(exec.execution_id)}</div>
        </div>
      `;
    }).join('');
  }

  renderLogs(logs) {
    return (logs || []).map(log => {
      const time = new Date(log.timestamp).toLocaleTimeString();
      const levelClass = log.level === 'error' ? 'error' : log.level === 'warn' ? 'warn' : 'info';
      return `<div class="log-entry log-${levelClass}">[${esc(time)}] [${esc(log.level)}] ${esc(log.message)}</div>`;
    }).join('');
  }

  async showExecutionDetails(executionId) {
    try {
      const response = await fetch(`/api/executions/${encodeURIComponent(executionId)}`);
      if (!response.ok) throw new Error('Execution not found');
      const execution = await response.json();

      const modal = document.getElementById('executionModal');
      const details = document.getElementById('executionDetails');
      const duration = formatDuration(execution.duration_ms) || 'In progress';

      details.innerHTML = `
        <div class="detail-section">
          <h4>Overview</h4>
          <table class="detail-table">
            <tr><td>Execution ID</td><td><code>${esc(execution.execution_id)}</code></td></tr>
            <tr><td>Workflow</td><td>${esc(execution.workflow_id)}</td></tr>
            <tr><td>Status</td><td><span class="badge badge-${statusClass(execution.status)}">${esc(execution.status)}</span></td></tr>
            <tr><td>Started</td><td>${esc(new Date(execution.started_at).toLocaleString())}</td></tr>
            <tr><td>Duration</td><td>${esc(duration)}</td></tr>
            <tr><td>Steps Completed</td><td>${execution.steps_completed}</td></tr>
            <tr><td>Steps Failed</td><td>${execution.steps_failed}</td></tr>
          </table>
        </div>

        <div class="detail-section">
          <h4>Inputs</h4>
          <pre class="output-text mono">${esc(JSON.stringify(execution.input_data || {}, null, 2))}</pre>
        </div>

        <div class="detail-section">
          <h4>Results</h4>
          ${this.renderResults(execution) || '<p class="hint">No results recorded.</p>'}
        </div>

        <div class="detail-section">
          <h4>Execution Logs</h4>
          <div class="logs-content">${this.renderLogs(execution.logs)}</div>
        </div>

        <div class="modal-footer">
          <button class="btn" data-monitor="${esc(executionId)}">Open in Monitor</button>
        </div>
      `;

      modal.classList.remove('hidden');
      this.autoOpenArtifacts(details);
    } catch (error) {
      alert('Failed to load execution details: ' + error.message);
    }
  }

  closeModal() {
    document.getElementById('executionModal').classList.add('hidden');
  }

  // ------------------------------------------------------------ results

  // What each step produced, in the order it ran. Shared by the history modal and the monitor.
  renderResults(execution) {
    const steps = execution.result?.steps;
    if (!Array.isArray(steps)) {
      if (execution.result?.error) {
        return `<div class="result-error">${esc(execution.result.error)}</div>`;
      }
      return execution.status === 'running' || execution.status === 'pending'
        ? '<p class="hint">Results appear here when the run finishes.</p>'
        : '';
    }

    return steps.map((step, index) => {
      const isLast = index === steps.length - 1;
      const badge = step.success
        ? '<span class="badge badge-success">done</span>'
        : '<span class="badge badge-error">failed</span>';
      const kind = step.type === 'tool'
        ? `tool${step.tool ? `: ${esc(step.tool)}` : ''}`
        : step.type === 'agent' ? 'AI step' : esc(step.type || 'step');
      const variable = step.output ? `<span class="step-var">saved as <code>{{${esc(step.output)}}}</code></span>` : '';

      return `
        <div class="result-step${isLast && step.success ? ' final-output' : ''}">
          <div class="result-step-header">
            <span class="step-name">${index + 1}. ${esc(step.step_id)}</span>
            ${badge}
            <span class="hint" style="margin:0">${kind}</span>
            ${variable}
          </div>
          <div class="result-step-body">
            ${this.renderStepResult(step, isLast)}
          </div>
        </div>
      `;
    }).join('');
  }

  renderStepResult(step, isLast) {
    if (!step.success) {
      return `<div class="result-error">${esc(step.error || 'Step failed')}</div>`;
    }

    const result = step.result;
    if (typeof result === 'string') {
      return textBlock(result);
    }
    if (!result || typeof result !== 'object') {
      return `<pre class="output-text mono">${esc(JSON.stringify(result, null, 2))}</pre>`;
    }

    const file = result.path ? String(result.path).split('/').pop() : '';
    if (result.operation === 'read' && typeof result.content === 'string') {
      return `
        <p class="note">Read ${result.size ?? result.content.length} characters from <code>${esc(file)}</code></p>
        <details class="raw-data"><summary>Show file content</summary>
          <pre class="output-text mono">${esc(result.content)}</pre>
        </details>`;
    }

    if (result.operation === 'write' || result.operation === 'append') {
      const verb = result.operation === 'write' ? 'Wrote' : 'Appended';
      const size = result.size ?? result.appended_size ?? '';
      // Only files under data/artifacts can be viewed in the browser
      const artifact = String(result.path || '').match(/data\/artifacts\/.+$/);
      return `
        <p class="note">${verb} ${size} characters to <code>${esc(result.path)}</code></p>
        ${artifact ? `
          <button class="btn-sm view-artifact" data-path="${esc(artifact[0])}"${isLast ? ' data-auto="1"' : ''}>View saved file</button>
          <div class="hidden"></div>` : ''}`;
    }

    if (result.operation === 'transform') {
      return `<p class="note">Converted ${result.records ?? '?'} records (${esc(result.format)}) into <code>${esc(result.target)}</code></p>`;
    }

    return `<pre class="output-text mono">${esc(JSON.stringify(result, null, 2))}</pre>`;
  }

  async toggleArtifact(button) {
    const view = button.nextElementSibling;
    if (!view) return;

    if (!view.classList.contains('hidden')) {
      view.classList.add('hidden');
      button.textContent = 'View saved file';
      return;
    }

    button.disabled = true;
    try {
      const response = await fetch(`/api/artifacts?path=${encodeURIComponent(button.dataset.path)}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      view.innerHTML = textBlock(data.content, /\.(md|markdown)$/i.test(data.path));
      view.classList.remove('hidden');
      button.textContent = 'Hide saved file';
    } catch (error) {
      view.textContent = `Could not load file: ${error.message}`;
      view.classList.remove('hidden');
    } finally {
      button.disabled = false;
    }
  }

  // The last step's saved file is the workflow's deliverable: show it without a click
  autoOpenArtifacts(container) {
    container.querySelectorAll('.view-artifact[data-auto]').forEach(button => this.toggleArtifact(button));
  }

  // ------------------------------------------------------------ editor

  async loadTools() {
    try {
      const response = await fetch('/api/tools');
      if (!response.ok) throw new Error((await response.json()).error);
      this.tools = await response.json();
    } catch (error) {
      console.error('Failed to load tools:', error);
      this.tools = [];
    }
  }

  showEditorMessage(html, kind) {
    const box = document.getElementById('editorMessage');
    box.className = `editor-message ${kind}`;
    box.innerHTML = html;
  }

  clearEditorMessage() {
    document.getElementById('editorMessage').className = 'editor-message hidden';
  }

  toolByName(name) {
    return this.tools.find(t => t.name === name);
  }

  makeStep(type = 'agent') {
    this.stepCounter += 1;
    const used = new Set(this.editor.steps.map(s => s.id));
    let n = this.editor.steps.length + 1;
    while (used.has(`step_${n}`)) n += 1;

    return {
      uid: `s${this.stepCounter}`,
      id: `step_${n}`,
      type,
      output: '',
      instruction: '',
      use_tools: false,
      tool: this.tools[0]?.name || '',
      params: {},
      extraTask: {},
      extra: {}
    };
  }

  newWorkflow() {
    document.getElementById('workflowId').value = '';
    document.getElementById('workflowName').value = '';
    document.getElementById('workflowDesc').value = '';
    this.editor = { steps: [], loadedId: null };
    document.getElementById('loadWorkflowSelect').value = '';
    this.clearEditorMessage();
    this.renderSteps();
    this.updateJsonPreview();
  }

  addStep() {
    this.editor.steps.push(this.makeStep());
    this.renderSteps();
    this.updateJsonPreview();
    document.querySelector('.step-card:last-child .step-id')?.focus();
  }

  findStep(uid) {
    return this.editor.steps.find(s => s.uid === uid);
  }

  setupStepListeners() {
    const list = document.getElementById('stepsList');

    list.addEventListener('input', (e) => {
      const field = e.target.dataset.field;
      const card = e.target.closest('.step-card');
      const step = card && this.findStep(card.dataset.uid);
      if (!field || !step) return;

      if (field === 'use_tools') {
        step.use_tools = e.target.checked;
      } else if (field.startsWith('param:')) {
        const name = field.slice(6);
        const schema = this.toolByName(step.tool)?.parameters?.properties?.[name];
        if (e.target.value === '') {
          delete step.params[name];
        } else if ((schema?.type === 'integer' || schema?.type === 'number') && Number.isFinite(Number(e.target.value))) {
          step.params[name] = Number(e.target.value);
        } else {
          step.params[name] = e.target.value;
        }
      } else if (field === 'type' || field === 'tool') {
        return; // handled on change: these rebuild the card
      } else {
        step[field] = e.target.value;
      }
      this.updateJsonPreview();
    });

    list.addEventListener('change', (e) => {
      const field = e.target.dataset.field;
      const card = e.target.closest('.step-card');
      const step = card && this.findStep(card.dataset.uid);
      if (!step) return;

      if (field === 'type') {
        step.type = e.target.value;
      } else if (field === 'tool') {
        step.tool = e.target.value;
        step.params = {}; // parameters belong to one tool's schema
      } else {
        return;
      }
      this.renderSteps();
      this.updateJsonPreview();
    });

    list.addEventListener('click', (e) => {
      const button = e.target.closest('[data-action]');
      const card = e.target.closest('.step-card');
      if (!button || !card) return;

      const steps = this.editor.steps;
      const index = steps.findIndex(s => s.uid === card.dataset.uid);
      if (button.dataset.action === 'remove') {
        steps.splice(index, 1);
      } else if (button.dataset.action === 'up' && index > 0) {
        [steps[index - 1], steps[index]] = [steps[index], steps[index - 1]];
      } else if (button.dataset.action === 'down' && index < steps.length - 1) {
        [steps[index + 1], steps[index]] = [steps[index], steps[index + 1]];
      }
      this.renderSteps();
      this.updateJsonPreview();
    });
  }

  renderToolParams(step) {
    const tool = this.toolByName(step.tool);
    const properties = tool?.parameters?.properties;
    if (!properties) {
      return step.tool
        ? '<p class="hint">This tool is not available on the server, so its parameters cannot be edited here.</p>'
        : '';
    }
    const required = tool.parameters.required || [];

    return Object.entries(properties).map(([name, schema]) => {
      const value = step.params[name] ?? '';
      const label = `${esc(name)}${required.includes(name) ? ' *' : ''} <span style="color:#999">${esc(schema.description || '')}</span>`;
      let control;
      if (schema.enum) {
        control = `<select class="input-sm" data-field="param:${esc(name)}">
          <option value="">(choose)</option>
          ${schema.enum.map(o => `<option value="${esc(o)}"${o === value ? ' selected' : ''}>${esc(o)}</option>`).join('')}
        </select>`;
      } else if (['content', 'body', 'text', 'prompt'].includes(name)) {
        control = `<textarea class="input textarea" data-field="param:${esc(name)}">${esc(value)}</textarea>`;
      } else {
        control = `<input class="input-sm" data-field="param:${esc(name)}" value="${esc(value)}" />`;
      }
      return `<div class="step-field"><label>${label}</label>${control}</div>`;
    }).join('');
  }

  renderStep(step, index, total) {
    const typeOptions = ['agent', 'tool'];
    if (!typeOptions.includes(step.type)) typeOptions.push(step.type);

    let body;
    if (step.type === 'tool') {
      const names = this.tools.map(t => t.name);
      if (step.tool && !names.includes(step.tool)) names.push(step.tool);
      body = `
        <div class="step-field">
          <label>Tool</label>
          <select class="input-sm" data-field="tool">
            ${names.map(n => `<option value="${esc(n)}"${n === step.tool ? ' selected' : ''}>${esc(n)}</option>`).join('')}
          </select>
        </div>
        ${this.renderToolParams(step)}`;
    } else {
      body = `
        <div class="step-field">
          <label>Instruction for the AI</label>
          <textarea class="input textarea step-instruction" data-field="instruction"
            placeholder="What should the AI do? Use {{name}} to include data.">${esc(step.instruction)}</textarea>
        </div>
        <label class="step-check">
          <input type="checkbox" data-field="use_tools"${step.use_tools ? ' checked' : ''} />
          Let the AI decide to call tools on its own (slower; leave off for plain writing or analysis)
        </label>`;
    }

    return `
      <div class="step-card" data-uid="${esc(step.uid)}">
        <div class="step-header">
          <span class="step-number">${index + 1}</span>
          <input class="input-sm step-id" data-field="id" placeholder="Step ID" value="${esc(step.id)}" />
          <select class="input-sm" data-field="type" aria-label="Step type">
            ${typeOptions.map(t => `<option value="${esc(t)}"${t === step.type ? ' selected' : ''}>${t === 'agent' ? 'AI step' : t === 'tool' ? 'Tool step' : esc(t)}</option>`).join('')}
          </select>
          <div class="step-tools">
            <button class="btn-sm" data-action="up" title="Move up"${index === 0 ? ' disabled' : ''}>↑</button>
            <button class="btn-sm" data-action="down" title="Move down"${index === total - 1 ? ' disabled' : ''}>↓</button>
            <button class="btn-sm btn-danger" data-action="remove">Remove</button>
          </div>
        </div>
        ${body}
        <div class="step-field">
          <label>Save result as (optional): later steps can use it as {{name}}</label>
          <input class="input-sm" data-field="output" placeholder="e.g. notes" value="${esc(step.output)}" />
        </div>
      </div>`;
  }

  renderSteps() {
    const container = document.getElementById('stepsList');
    const steps = this.editor.steps;

    container.innerHTML = steps.length
      ? steps.map((step, i) => this.renderStep(step, i, steps.length)).join('')
      : '<div class="empty-state">No steps yet. Click "Add Step" to begin.</div>';
  }

  // The workflow definition exactly as it will be saved
  buildWorkflow() {
    const steps = this.editor.steps.map(s => {
      const step = { id: s.id, type: s.type };

      if (s.type === 'tool') {
        step.tool = s.tool;
        step.parameters = { ...s.params };
      } else if (s.type === 'agent') {
        const task = { ...s.extraTask, instruction: s.instruction };
        if (s.use_tools) {
          delete task.use_tools; // tools are on unless the step turns them off
        } else {
          task.use_tools = false;
        }
        step.task = task;
      }
      if (s.output) step.output = s.output;
      return { ...s.extra, ...step };
    });

    return {
      id: document.getElementById('workflowId').value.trim(),
      name: document.getElementById('workflowName').value.trim(),
      description: document.getElementById('workflowDesc').value.trim(),
      steps
    };
  }

  updateJsonPreview() {
    const workflow = this.buildWorkflow();
    document.getElementById('jsonPreview').textContent = JSON.stringify(workflow, null, 2);

    const inputs = detectInputs(workflow);
    document.getElementById('inputsHint').textContent = inputs.length
      ? `Inputs you will provide when running: ${inputs.join(', ')}`
      : 'This workflow needs no inputs.';
  }

  // Returns the saved ID, or null when the save did not happen
  async saveWorkflow({ run = false } = {}) {
    const workflow = this.buildWorkflow();
    this.clearEditorMessage();

    const send = async (overwrite) => {
      const response = await fetch('/api/workflows', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ workflow, overwrite })
      });
      return { response, data: await response.json() };
    };

    try {
      // Saving the workflow you loaded replaces it; anything else must not clobber an existing one silently
      let { response, data } = await send(this.editor.loadedId === workflow.id);

      if (response.status === 409) {
        if (!confirm(`A workflow with ID "${workflow.id}" already exists. Replace it?`)) {
          return null;
        }
        ({ response, data } = await send(true));
      }

      if (response.status === 400 && data.details) {
        this.showEditorMessage(
          `<strong>Not saved. Please fix:</strong><ul>${data.details.map(d => `<li>${esc(d)}</li>`).join('')}</ul>`,
          'bad'
        );
        return null;
      }
      if (!response.ok) {
        throw new Error(data.error || 'Save failed');
      }

      this.editor.loadedId = workflow.id;
      await this.loadWorkflows();
      document.getElementById('loadWorkflowSelect').value = workflow.id;

      if (run) {
        this.goToRun(workflow.id);
      } else {
        this.showEditorMessage(
          `Saved <code>workflows/${esc(workflow.id)}.json</code>. It is now on the Dashboard; pick it under "Load a saved workflow" to edit it later.`,
          'ok'
        );
      }
      return workflow.id;
    } catch (error) {
      this.showEditorMessage(`Could not save: ${esc(error.message)}`, 'bad');
      return null;
    }
  }

  async loadWorkflowToEditor() {
    const workflowId = document.getElementById('loadWorkflowSelect').value;
    if (!workflowId) {
      this.showEditorMessage('Choose a workflow in the list first.', 'bad');
      return;
    }

    try {
      const response = await fetch(`/api/workflows/${encodeURIComponent(workflowId)}`);
      if (!response.ok) throw new Error('Workflow not found');
      const workflow = await response.json();

      document.getElementById('workflowId').value = workflow.id;
      document.getElementById('workflowName').value = workflow.name || '';
      document.getElementById('workflowDesc').value = workflow.description || '';

      this.editor = { loadedId: workflow.id, steps: (workflow.steps || []).map(s => this.stepFromDefinition(s)) };
      this.renderSteps();
      this.updateJsonPreview();
      this.showEditorMessage(
        `Loaded <strong>${esc(workflow.name)}</strong>. Edit it and Save, or use Save &amp; Run.`,
        'ok'
      );
    } catch (error) {
      this.showEditorMessage(`Failed to load workflow: ${esc(error.message)}`, 'bad');
    }
  }

  // Definition -> editor model. Fields the editor has no control for are carried along untouched.
  stepFromDefinition(def) {
    const step = this.makeStep(def.type);
    step.id = def.id || step.id;
    step.output = def.output || '';

    const { id, type, output, task, tool, parameters, ...extra } = def;
    step.extra = extra;

    if (def.type === 'tool') {
      step.tool = tool || '';
      step.params = { ...(parameters || {}) };
    } else {
      const { instruction, use_tools, ...extraTask } = task || {};
      step.instruction = instruction || '';
      step.use_tools = use_tools !== false;
      step.extraTask = extraTask;
    }
    return step;
  }

  // ------------------------------------------------------------ live monitor

  monitorExecution(executionId) {
    this.switchTab('monitor');
    document.getElementById('monitorExecutionId').value = executionId;
    this.startMonitoring();
  }

  startMonitoring() {
    const executionId = document.getElementById('monitorExecutionId').value.trim();
    if (!executionId) {
      alert('Please enter an execution ID');
      return;
    }

    this.stopMonitoring();

    document.getElementById('monitorStatus').classList.remove('hidden');
    document.getElementById('monitorLogs').classList.remove('hidden');
    document.getElementById('logsContent').innerHTML = '';
    document.getElementById('monitorResults').classList.add('hidden');
    document.getElementById('monitorResults').innerHTML = '';
    this.monitorRenderedKey = null;
    document.getElementById('startMonitorBtn').disabled = true;
    document.getElementById('stopMonitorBtn').disabled = false;

    this.monitorEventSource = new EventSource(`/api/executions/${encodeURIComponent(executionId)}/stream`);

    this.monitorEventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'update') {
        this.updateMonitorDisplay(data.execution);
      } else if (data.type === 'done') {
        this.stopMonitoring();
        this.loadExecutions();
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
    const statusBadge = document.getElementById('monitorStatusValue');
    statusBadge.textContent = execution.status;
    statusBadge.className = `badge badge-${statusClass(execution.status)}`;

    document.getElementById('monitorStepsValue').textContent =
      `${execution.steps_completed} completed, ${execution.steps_failed} failed`;

    document.getElementById('monitorDurationValue').textContent = execution.duration_ms
      ? formatDuration(execution.duration_ms)
      : `${((Date.now() - new Date(execution.started_at)) / 1000).toFixed(1)}s`;

    const logsContainer = document.getElementById('logsContent');
    logsContainer.innerHTML = this.renderLogs(execution.logs);
    logsContainer.scrollTop = logsContainer.scrollHeight;

    // Results exist once the run has finished; render them once
    const finished = execution.status === 'completed' || execution.status === 'failed';
    const key = `${execution.execution_id}:${execution.status}`;
    if (finished && this.monitorRenderedKey !== key) {
      this.monitorRenderedKey = key;
      const results = document.getElementById('monitorResults');
      results.innerHTML = `<h3>Results</h3>${this.renderResults(execution)}`;
      results.classList.remove('hidden');
      this.autoOpenArtifacts(results);
    }
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
