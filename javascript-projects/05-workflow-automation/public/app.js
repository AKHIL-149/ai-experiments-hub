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
    if (step.run_if?.variable) scan(`{{${step.run_if.variable}}}`);
    if (step.output) produced.add(step.output);
  }
  return inputs;
}

const SCHEDULE_PRESETS = [
  { label: 'Every 5 minutes', cron: '*/5 * * * *' },
  { label: 'Every 15 minutes', cron: '*/15 * * * *' },
  { label: 'Every 30 minutes', cron: '*/30 * * * *' },
  { label: 'Every hour', cron: '0 * * * *' },
  { label: 'Weekdays every 30 minutes, 09:00 to 16:30', cron: '*/30 9-16 * * 1-5' },
  { label: 'Weekdays at 09:30', cron: '30 9 * * 1-5' },
  { label: 'Every day at 09:00', cron: '0 9 * * *' },
  { label: 'Custom…', cron: null }
];

function formatWhen(iso) {
  if (!iso) return '-';
  return new Date(iso).toLocaleString([], { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

// "in 3 min", "2 h 5 min ago": relative to `now` (the server's clock, so a wrong browser clock does not matter)
function relativeTime(iso, now = Date.now()) {
  const diff = new Date(iso).getTime() - now;
  const minutes = Math.round(Math.abs(diff) / 60000);
  let text;
  if (Math.abs(diff) < 45000) text = 'a moment';
  else if (minutes < 60) text = `${minutes} min`;
  else if (minutes < 1440) text = minutes % 60 ? `${Math.floor(minutes / 60)} h ${minutes % 60} min` : `${minutes / 60} h`;
  else text = `${Math.round(minutes / 1440)} day${Math.round(minutes / 1440) === 1 ? '' : 's'}`;
  return diff >= 0 ? `in ${text}` : `${text} ago`;
}

class WorkflowApp {
  constructor() {
    this.workflows = [];
    this.executions = [];
    this.tools = [];
    this.models = [];
    this.defaultModel = '';
    this.schedules = [];
    this.scheduleTimer = null;
    this.scheduleClockOffset = 0;
    this.editingScheduleId = null;
    this.autoScheduleInputs = '';
    this.openRuns = new Set();
    this.previewSeq = 0;
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
    await Promise.all([this.loadWorkflows(), this.loadExecutions(), this.loadTools(), this.loadModels()]);
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
    document.getElementById('modelSelect').addEventListener('change', (e) => this.rememberModel(e.target.value));
    document.getElementById('refreshModelsBtn').addEventListener('click', () => this.loadModels());
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

    // Schedules
    document.getElementById('newScheduleBtn').addEventListener('click', () => this.openScheduleForm());
    document.getElementById('scheduleFromQuickBtn').addEventListener('click', () => this.scheduleFromQuickExecute());
    document.getElementById('cancelScheduleBtn').addEventListener('click', () => this.closeScheduleForm());
    document.getElementById('saveScheduleBtn').addEventListener('click', () => this.saveSchedule());
    document.getElementById('scheduleWorkflow').addEventListener('change', (e) => this.prefillScheduleInputs(e.target.value));
    document.getElementById('schedulePreset').addEventListener('change', () => this.onPresetChange());
    document.getElementById('scheduleCron').addEventListener('input', () => this.refreshSchedulePreview());
    document.getElementById('schedulesList').addEventListener('click', (e) => this.onScheduleClick(e));
    document.getElementById('schedulesList').addEventListener('change', (e) => {
      if (e.target.dataset.action === 'toggle') this.toggleSchedule(e.target.closest('.schedule-card').dataset.id, e.target.checked);
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
    if (tabName === 'schedules') {
      this.loadSchedules();
      this.startScheduleRefresh();
    } else {
      this.stopScheduleRefresh();
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

    const scheduleSelect = document.getElementById('scheduleWorkflow');
    const scheduleSelected = scheduleSelect.value;
    scheduleSelect.innerHTML = '<option value="">Select a workflow...</option>' + options;
    scheduleSelect.value = scheduleSelected;

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

  // Models installed in Ollama. The choice is remembered in this browser only.
  async loadModels() {
    const hint = document.getElementById('modelHint');
    try {
      const response = await fetch('/api/models');
      const data = await response.json();
      this.models = data.models || [];
      this.defaultModel = data.default || '';
      hint.textContent = response.ok ? '' : data.error;
    } catch (error) {
      this.models = [];
      hint.textContent = 'Could not load the model list.';
    }
    this.renderModelSelect();
  }

  savedModel() {
    try {
      return localStorage.getItem('workflowModel') || '';
    } catch (error) {
      return '';
    }
  }

  rememberModel(model) {
    try {
      if (model) localStorage.setItem('workflowModel', model);
      else localStorage.removeItem('workflowModel');
    } catch (error) {
      // private window or blocked storage: the choice just lasts for this page
    }
  }

  renderModelSelect() {
    const select = document.getElementById('modelSelect');
    const wanted = select.value || this.savedModel();
    const gb = (bytes) => (bytes ? ` · ${(bytes / 1e9).toFixed(1)} GB` : '');

    select.innerHTML = `<option value="">Default${this.defaultModel ? ` (${esc(this.defaultModel)})` : ''}</option>` +
      this.models.map(m => `<option value="${esc(m.name)}">${esc(m.name)}${m.parameterSize ? ` · ${esc(m.parameterSize)}` : ''}${gb(m.sizeBytes)}</option>`).join('');

    // a remembered model that is no longer installed falls back to the default
    select.value = this.models.some(m => m.name === wanted) ? wanted : '';

    const scheduleModel = document.getElementById('scheduleModel');
    const keep = scheduleModel.value;
    scheduleModel.innerHTML = select.innerHTML;
    scheduleModel.value = this.models.some(m => m.name === keep) ? keep : '';
  }

  selectedModel() {
    return document.getElementById('modelSelect').value;
  }

  async executeWorkflowById(workflowId, inputData = {}) {
    this.showExecuteMessage('Starting execution...', 'loading');

    try {
      const response = await fetch(`/api/workflows/${encodeURIComponent(workflowId)}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ inputData, options: this.selectedModel() ? { model: this.selectedModel() } : {} })
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
            ${exec.model ? `<span class="model-chip">${esc(exec.model)}</span>` : ''}
            ${String(exec.trigger_type || '').startsWith('schedule') ? '<span class="model-chip">⏰ scheduled</span>' : ''}
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
            <tr><td>Model</td><td>${esc(execution.model || 'default')}</td></tr>
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
      const badge = step.skipped
        ? '<span class="badge badge-info" title="Its condition was not met">skipped</span>'
        : step.success
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
            ${step.truncated ? '<span class="badge badge-warn" title="The model hit its token limit. Raise max_tokens in this step.">output cut off</span>' : ''}
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

    // csv_operations: say what happened, then show the data (a table when it is one)
    if (['filter', 'label', 'to_markdown', 'count'].includes(result.operation) && typeof result.content === 'string') {
      const summary = {
        filter: `Kept ${result.rows} of ${result.total} rows`,
        label: `Labelled ${result.rows} rows${result.unlabelled ? ` (${result.unlabelled} outside every range)` : ''}`,
        to_markdown: `Built a table of ${result.rows} rows`,
        count: `Counted ${result.rows} rows`
      }[result.operation];
      let data = '';
      if (result.operation === 'to_markdown') {
        data = textBlock(result.content);
      } else if (result.operation !== 'count') {
        data = `<details class="raw-data"><summary>Show the CSV</summary>
          <pre class="output-text mono">${esc(result.content)}</pre></details>`;
      }
      const repaired = result.repaired_rows
        ? ` <strong>${result.repaired_rows} row(s) had extra commas; the extra text was joined onto the last column.</strong>`
        : '';
      return `<p class="note">${esc(summary)}${repaired}</p>${data}`;
    }

    // market_data / portfolio_operations: a one-line summary, anything worth flagging, then the table
    if (typeof result.summary === 'string' && typeof result.content === 'string') {
      const body = typeof result.markdown === 'string'
        ? textBlock(`${result.totals_text ? `${result.totals_text}\n\n` : ''}${result.markdown}`)
        : `<details class="raw-data"><summary>Show the data</summary>
            <pre class="output-text mono">${esc(result.content)}</pre></details>`;
      const flag = result.notes && !/^All /.test(result.notes) ? `<p class="note"><strong>${esc(result.notes)}</strong></p>` : '';
      const source = result.source ? ` <span class="model-chip">${esc(result.source)}</span>` : '';
      return `<p class="note">${esc(result.summary)}${source}</p>${flag}${body}`;
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
      maxTokens: '',
      tool: this.tools[0]?.name || '',
      params: {},
      runIf: { variable: '', operator: '>', value: '' },
      ifSkipped: '',
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
      } else if (field.startsWith('runIf.')) {
        step.runIf[field.slice(6)] = e.target.value;
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
        // a value outside the list (typically a template such as {{source}}) must stay visible and selected
        const options = value !== '' && !schema.enum.includes(value) ? [...schema.enum, value] : schema.enum;
        control = `<select class="input-sm" data-field="param:${esc(name)}">
          <option value="">(choose)</option>
          ${options.map(o => `<option value="${esc(o)}"${o === value ? ' selected' : ''}>${esc(o)}${schema.enum.includes(o) ? '' : ' (from a variable)'}</option>`).join('')}
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
        </label>
        <div class="step-field">
          <label>Longest reply, in tokens (optional; default 4096). A reply that hits it is flagged as cut off</label>
          <input class="input-sm" data-field="maxTokens" inputmode="numeric" placeholder="e.g. 1500" value="${esc(step.maxTokens)}" />
        </div>`;
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
        <details class="step-field condition"${step.runIf.variable ? ' open' : ''}>
          <summary>Only run this step when… (optional)</summary>
          <div class="step-row three">
            <div><label>Result to check</label>
              <input class="input-sm" data-field="runIf.variable" placeholder="e.g. unhappy.rows" value="${esc(step.runIf.variable)}" /></div>
            <div><label>Is</label>
              <select class="input-sm" data-field="runIf.operator">
                ${['==', '!=', '>', '>=', '<', '<='].map(o => `<option value="${o}"${o === step.runIf.operator ? ' selected' : ''}>${esc(o)}</option>`).join('')}
              </select></div>
            <div><label>Value</label>
              <input class="input-sm" data-field="runIf.value" placeholder="e.g. 0" value="${esc(step.runIf.value)}" /></div>
          </div>
          <label>If the step is skipped, its result is</label>
          <input class="input-sm" data-field="ifSkipped" placeholder="e.g. No unhappy customers this period." value="${esc(step.ifSkipped)}" />
        </details>
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
        const limit = String(s.maxTokens).trim();
        if (limit !== '') {
          task.max_tokens = Number.isFinite(Number(limit)) ? Number(limit) : limit; // the server explains a bad value
        } else {
          delete task.max_tokens;
        }
        step.task = task;
      }
      if (s.runIf.variable.trim()) {
        const raw = String(s.runIf.value).trim();
        step.run_if = {
          variable: s.runIf.variable.trim(),
          operator: s.runIf.operator,
          value: raw !== '' && Number.isFinite(Number(raw)) ? Number(raw) : s.runIf.value
        };
        if (s.ifSkipped) step.if_skipped = s.ifSkipped;
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

    const { id, type, output, task, tool, parameters, run_if, if_skipped, ...extra } = def;
    step.extra = extra;
    if (run_if) {
      step.runIf = { variable: run_if.variable || '', operator: run_if.operator || '>', value: run_if.value ?? '' };
      step.ifSkipped = if_skipped || '';
    }

    if (def.type === 'tool') {
      step.tool = tool || '';
      step.params = { ...(parameters || {}) };
    } else {
      const { instruction, use_tools, max_tokens, ...extraTask } = task || {};
      step.instruction = instruction || '';
      step.use_tools = use_tools !== false;
      step.maxTokens = max_tokens ?? '';
      step.extraTask = extraTask;
    }
    return step;
  }

  // ------------------------------------------------------------ schedules

  startScheduleRefresh() {
    this.stopScheduleRefresh();
    this.scheduleTimer = setInterval(() => this.loadSchedules(), 5000);
  }

  stopScheduleRefresh() {
    if (this.scheduleTimer) {
      clearInterval(this.scheduleTimer);
      this.scheduleTimer = null;
    }
  }

  async loadSchedules() {
    try {
      const response = await fetch('/api/schedules');
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      this.schedules = data.schedules;
      this.scheduleClockOffset = Date.parse(data.now) - Date.now();
      document.getElementById('scheduleTz').textContent = `Times use the server's time zone (${data.timezone})`;
      this.renderSchedules();
    } catch (error) {
      document.getElementById('schedulesList').innerHTML =
        `<div class="error">Failed to load schedules: ${esc(error.message)}</div>`;
    }
  }

  scheduleStatusBadge(s) {
    if (s.running) return '<span class="badge badge-info">running</span>';
    if (!s.last_status) return '<span class="badge">not run yet</span>';
    const kind = { completed: 'success', failed: 'error', error: 'error', skipped: 'warn', missed: 'warn' }[s.last_status] || 'info';
    return `<span class="badge badge-${kind}">${esc(s.last_status)}</span>`;
  }

  renderSchedules() {
    const container = document.getElementById('schedulesList');
    if (this.schedules.length === 0) {
      container.innerHTML = '<div class="empty-state">No schedules yet. Click "+ New Schedule", or use "Schedule this…" on the Dashboard.</div>';
      return;
    }

    const now = Date.now() + this.scheduleClockOffset;
    container.innerHTML = this.schedules.map((s) => {
      const next = !s.enabled ? 'Paused'
        : s.next_run ? `${esc(formatWhen(s.next_run))} <span class="hint">(${esc(relativeTime(s.next_run, now))})</span>`
        : '<span class="warning-text">none: check the schedule</span>';
      const last = s.last_run_at
        ? `${esc(formatWhen(s.last_run_at))} <span class="hint">(${esc(relativeTime(s.last_run_at, now))})</span>`
        : 'never';
      const problem = ['skipped', 'missed', 'error', 'failed'].includes(s.last_status) && s.last_message
        ? `<div class="warning-text">${esc(s.last_message)}</div>` : '';
      const streak = s.consecutive_failures > 0
        ? ` · <span class="warning-text">${s.consecutive_failures} failed in a row</span>` : '';

      return `
        <div class="schedule-card${s.enabled ? '' : ' off'}" data-id="${esc(s.id)}">
          <div class="schedule-top">
            <h3>${esc(s.name)}</h3>
            <span class="model-chip">${esc(s.workflow_id)}</span>
            ${this.scheduleStatusBadge(s)}
            <span class="spacer"></span>
            <label class="step-check" style="margin:0"><input type="checkbox" data-action="toggle"${s.enabled ? ' checked' : ''} /> Enabled</label>
          </div>
          <dl class="schedule-meta">
            <dt>Schedule</dt><dd>${esc(s.description)} <code>${esc(s.cron)}</code></dd>
            <dt>Next run</dt><dd>${next}</dd>
            <dt>Last run</dt><dd>${last}${problem}</dd>
            <dt>Runs</dt><dd>${s.run_count} started${streak}${s.model ? ` · model ${esc(s.model)}` : ''}</dd>
          </dl>
          <div class="schedule-actions">
            <button class="btn-sm" data-action="run">Run now</button>
            <button class="btn-sm" data-action="edit">Edit</button>
            <button class="btn-sm" data-action="runs">${this.openRuns.has(s.id) ? 'Hide runs' : 'Show runs'}</button>
            <button class="btn-sm btn-danger" data-action="delete">Delete</button>
          </div>
          <div class="schedule-runs${this.openRuns.has(s.id) ? '' : ' hidden'}" data-runs></div>
        </div>`;
    }).join('');

    this.openRuns.forEach(id => this.loadScheduleRuns(id));
  }

  onScheduleClick(e) {
    const open = e.target.closest('[data-open-run]');
    if (open) return this.monitorExecution(open.dataset.openRun);

    const button = e.target.closest('[data-action]');
    if (!button || button.dataset.action === 'toggle') return;
    const id = button.closest('.schedule-card').dataset.id;
    const action = button.dataset.action;

    if (action === 'run') this.runScheduleNow(id, button);
    else if (action === 'edit') this.openScheduleForm(this.schedules.find(s => s.id === id));
    else if (action === 'runs') this.toggleScheduleRuns(id);
    else if (action === 'delete') this.deleteSchedule(id);
  }

  async scheduleRequest(method, url, body) {
    const response = await fetch(url, {
      method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body)
    });
    const data = response.status === 204 ? null : await response.json();
    if (!response.ok) {
      const error = new Error(data.details ? data.details.join('; ') : data.error);
      error.details = data.details;
      throw error;
    }
    return data;
  }

  async toggleSchedule(id, enabled) {
    try {
      await this.scheduleRequest('PATCH', `/api/schedules/${encodeURIComponent(id)}`, { enabled });
    } catch (error) {
      alert(`Could not change the schedule: ${error.message}`);
    }
    this.loadSchedules();
  }

  async runScheduleNow(id, button) {
    button.disabled = true;
    try {
      await this.scheduleRequest('POST', `/api/schedules/${encodeURIComponent(id)}/run`);
      this.openRuns.add(id);
    } catch (error) {
      alert(`Could not run it: ${error.message}`);
    } finally {
      button.disabled = false;
    }
    this.loadSchedules();
  }

  async deleteSchedule(id) {
    const schedule = this.schedules.find(s => s.id === id);
    if (!confirm(`Delete the schedule "${schedule?.name || id}"? Its past runs stay in History.`)) return;
    try {
      await this.scheduleRequest('DELETE', `/api/schedules/${encodeURIComponent(id)}`);
      this.openRuns.delete(id);
    } catch (error) {
      alert(`Could not delete it: ${error.message}`);
    }
    this.loadSchedules();
  }

  toggleScheduleRuns(id) {
    if (this.openRuns.has(id)) this.openRuns.delete(id);
    else this.openRuns.add(id);
    this.renderSchedules();
  }

  async loadScheduleRuns(id) {
    const card = document.querySelector(`.schedule-card[data-id="${CSS.escape(id)}"] [data-runs]`);
    if (!card) return;
    try {
      const response = await fetch(`/api/schedules/${encodeURIComponent(id)}/runs?limit=8`);
      const runs = await response.json();
      if (!response.ok) throw new Error(runs.error);
      const now = Date.now() + this.scheduleClockOffset;
      card.innerHTML = runs.length === 0 ? '<span class="hint">No runs yet.</span>' : runs.map(run => `
        <div class="schedule-run">
          <span class="badge badge-${statusClass(run.status)}">${esc(run.status)}</span>
          <span>${esc(formatWhen(run.started_at))} <span class="hint">(${esc(relativeTime(run.started_at, now))})</span></span>
          <span class="hint">${run.trigger_type === 'schedule-manual' ? 'run now' : 'scheduled'}${formatDuration(run.duration_ms) ? ` · ${formatDuration(run.duration_ms)}` : ''}</span>
          <a data-open-run="${esc(run.execution_id)}">Open results</a>
        </div>`).join('');
    } catch (error) {
      card.innerHTML = `<span class="warning-text">Could not load runs: ${esc(error.message)}</span>`;
    }
  }

  // ---- the form

  scheduleFormFields() {
    return {
      name: document.getElementById('scheduleName'),
      workflow: document.getElementById('scheduleWorkflow'),
      inputs: document.getElementById('scheduleInputs'),
      model: document.getElementById('scheduleModel'),
      preset: document.getElementById('schedulePreset'),
      cron: document.getElementById('scheduleCron'),
      enabled: document.getElementById('scheduleEnabled')
    };
  }

  openScheduleForm(schedule = null, prefill = {}) {
    const f = this.scheduleFormFields();
    this.editingScheduleId = schedule ? schedule.id : null;
    document.getElementById('scheduleFormTitle').textContent = schedule ? 'Edit schedule' : 'New schedule';
    document.getElementById('scheduleFormMessage').className = 'editor-message hidden';

    f.preset.innerHTML = SCHEDULE_PRESETS.map((p, i) => `<option value="${i}">${esc(p.label)}</option>`).join('');
    f.name.value = schedule?.name || prefill.name || '';
    f.workflow.value = schedule?.workflow_id || prefill.workflow_id || '';
    f.model.value = schedule ? (schedule.model || '') : (prefill.model || '');
    f.enabled.checked = schedule ? schedule.enabled : true;

    const cron = schedule?.cron || '*/30 * * * *';
    const presetIndex = SCHEDULE_PRESETS.findIndex(p => p.cron === cron);
    f.preset.value = String(presetIndex >= 0 ? presetIndex : SCHEDULE_PRESETS.length - 1);
    f.cron.value = presetIndex >= 0 ? '' : cron;
    f.cron.classList.toggle('hidden', presetIndex >= 0);

    const inputs = schedule ? schedule.input_data : prefill.input_data;
    this.autoScheduleInputs = '';
    if (inputs && Object.keys(inputs).length > 0) {
      f.inputs.value = JSON.stringify(inputs, null, 2);
    } else {
      f.inputs.value = '';
      this.prefillScheduleInputs(f.workflow.value);
    }

    document.getElementById('scheduleForm').classList.remove('hidden');
    document.getElementById('scheduleForm').scrollIntoView({ behavior: 'smooth', block: 'start' });
    f.name.focus();
    this.refreshSchedulePreview();
  }

  closeScheduleForm() {
    document.getElementById('scheduleForm').classList.add('hidden');
    this.editingScheduleId = null;
  }

  prefillScheduleInputs(workflowId) {
    const f = this.scheduleFormFields();
    const hint = document.getElementById('scheduleInputHint');
    const workflow = this.workflows.find(w => w.id === workflowId);
    if (!workflow) {
      hint.textContent = '';
      return;
    }
    const inputs = workflow.inputs || [];
    const template = inputs.length ? JSON.stringify(Object.fromEntries(inputs.map(name => [name, ''])), null, 2) : '';
    if (!f.inputs.value.trim() || f.inputs.value === this.autoScheduleInputs) {
      f.inputs.value = template;
      this.autoScheduleInputs = template;
    }
    hint.textContent = inputs.length ? `This workflow needs: ${inputs.join(', ')}. Every one must have a value.` : 'This workflow needs no inputs.';
  }

  onPresetChange() {
    const f = this.scheduleFormFields();
    const preset = SCHEDULE_PRESETS[Number(f.preset.value)];
    f.cron.classList.toggle('hidden', preset.cron !== null);
    if (preset.cron === null) f.cron.focus();
    this.refreshSchedulePreview();
  }

  currentCron() {
    const f = this.scheduleFormFields();
    const preset = SCHEDULE_PRESETS[Number(f.preset.value)];
    return preset && preset.cron !== null ? preset.cron : f.cron.value.trim();
  }

  // Shows what the chosen schedule means and when it will next run (asks the server, which owns the rules)
  refreshSchedulePreview() {
    clearTimeout(this.previewTimer);
    this.previewTimer = setTimeout(async () => {
      const box = document.getElementById('schedulePreview');
      const cron = this.currentCron();
      const seq = ++this.previewSeq;
      if (!cron) {
        box.innerHTML = '<span class="hint">Enter a schedule: minute hour day-of-month month day-of-week</span>';
        return;
      }
      try {
        const response = await fetch('/api/schedules/preview', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cron })
        });
        const data = await response.json();
        if (seq !== this.previewSeq) return; // a newer edit is already being checked
        box.innerHTML = data.valid
          ? `<strong>${esc(data.description)}</strong><ul>${data.next.slice(0, 3).map(n => `<li>${esc(formatWhen(n))}</li>`).join('')}</ul>`
          : `<span class="bad">${esc(data.error)}</span>`;
      } catch (error) {
        if (seq === this.previewSeq) box.innerHTML = '<span class="bad">Could not check the schedule</span>';
      }
    }, 250);
  }

  showScheduleFormMessage(html) {
    const box = document.getElementById('scheduleFormMessage');
    box.className = 'editor-message bad';
    box.innerHTML = html;
  }

  async saveSchedule() {
    const f = this.scheduleFormFields();
    let inputData = {};
    if (f.inputs.value.trim()) {
      try {
        inputData = JSON.parse(f.inputs.value);
      } catch (error) {
        return this.showScheduleFormMessage(`Inputs are not valid JSON: ${esc(error.message)}`);
      }
    }

    const body = {
      name: f.name.value, workflow_id: f.workflow.value, cron: this.currentCron(),
      input_data: inputData, model: f.model.value || null, enabled: f.enabled.checked
    };
    try {
      if (this.editingScheduleId) {
        await this.scheduleRequest('PATCH', `/api/schedules/${encodeURIComponent(this.editingScheduleId)}`, body);
      } else {
        await this.scheduleRequest('POST', '/api/schedules', body);
      }
      this.closeScheduleForm();
      this.loadSchedules();
    } catch (error) {
      this.showScheduleFormMessage(error.details
        ? `<strong>Not saved. Please fix:</strong><ul>${error.details.map(d => `<li>${esc(d)}</li>`).join('')}</ul>`
        : esc(error.message));
    }
  }

  // Dashboard "Schedule this…": start a schedule from the workflow, inputs and model chosen there
  scheduleFromQuickExecute() {
    const workflowId = document.getElementById('workflowSelect').value;
    if (!workflowId) {
      return this.showExecuteMessage('Select a workflow first, then choose "Schedule this…".', 'error');
    }
    let inputData = {};
    const text = document.getElementById('inputDataJson').value;
    if (text.trim()) {
      try {
        inputData = JSON.parse(text);
      } catch (error) {
        return this.showExecuteMessage(`Input data is not valid JSON: ${esc(error.message)}`, 'error');
      }
    }
    const workflow = this.workflows.find(w => w.id === workflowId);
    this.switchTab('schedules');
    this.openScheduleForm(null, {
      name: workflow ? workflow.name : '', workflow_id: workflowId, input_data: inputData, model: this.selectedModel()
    });
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

    document.getElementById('monitorModelValue').textContent = execution.model || 'default';
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
