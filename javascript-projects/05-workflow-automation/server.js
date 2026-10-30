const express = require('express');
const cors = require('cors');
const path = require('path');
const fs = require('fs').promises;
require('dotenv').config();

const WorkflowEngine = require('./src/WorkflowEngine');
const { WorkflowValidationError } = require('./src/workflowSchema');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
// Local tool that can run workflows and write files: only same-origin pages may call it
app.use(cors({ origin: process.env.CORS_ORIGIN || false }));
app.use(express.json({ limit: '1mb' }));
app.use(express.static(path.join(__dirname, 'public')));

// Workflows may only show files they saved under this folder
const ARTIFACTS_DIR = path.join(__dirname, 'data', 'artifacts');
const MAX_VIEW_BYTES = 1024 * 1024;

// Initialize workflow engine
const workflowEngine = new WorkflowEngine();

// Store active executions for SSE
const activeExecutions = new Map();

// API Routes

// Health check
app.get('/api/health', async (req, res) => {
  try {
    const ollamaUrl = process.env.OLLAMA_API_URL || 'http://localhost:11434';
    const [pythonHealthy, ollamaHealthy] = await Promise.all([
      workflowEngine.pythonBridge.healthCheck(),
      fetch(`${ollamaUrl}/api/tags`, { signal: AbortSignal.timeout(3000) })
        .then(r => r.ok)
        .catch(() => false)
    ]);
    res.json({
      status: 'ok',
      python: pythonHealthy ? 'healthy' : 'unhealthy',
      ollama: ollamaHealthy ? 'reachable' : 'unreachable',
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    res.status(500).json({
      status: 'error',
      error: error.message
    });
  }
});

// List workflows
app.get('/api/workflows', async (req, res) => {
  try {
    const workflows = await workflowEngine.listWorkflows();
    res.json(workflows);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Get workflow details
app.get('/api/workflows/:id', async (req, res) => {
  try {
    const workflow = await workflowEngine.loadWorkflow(req.params.id);
    res.json(workflow);
  } catch (error) {
    res.status(404).json({ error: 'Workflow not found' });
  }
});

// Save a workflow created in the editor (body: { workflow, overwrite })
app.post('/api/workflows', async (req, res) => {
  try {
    const { workflow, overwrite = false } = req.body || {};
    const saved = await workflowEngine.saveWorkflow(workflow, { overwrite: overwrite === true });
    res.status(saved.created ? 201 : 200).json(saved);
  } catch (error) {
    if (error instanceof WorkflowValidationError) {
      return res.status(400).json({ error: 'Workflow is not valid', details: error.errors });
    }
    res.status(error.status || 500).json({ error: error.message });
  }
});

// Tools a step can call, with their parameter schemas (lets the editor build the form)
let toolsCache = null;
app.get('/api/tools', async (req, res) => {
  try {
    if (!toolsCache) {
      toolsCache = await workflowEngine.pythonBridge.listTools();
    }
    res.json(toolsCache);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Read a file a workflow saved, so results can be viewed in the UI
app.get('/api/artifacts', async (req, res) => {
  try {
    const requested = typeof req.query.path === 'string' ? req.query.path : '';
    if (!requested) {
      return res.status(400).json({ error: 'path is required' });
    }

    // realpath, so a symlink cannot lead out of the artifacts folder
    await fs.mkdir(ARTIFACTS_DIR, { recursive: true });
    const root = await fs.realpath(ARTIFACTS_DIR);
    let resolved;
    try {
      resolved = await fs.realpath(path.resolve(__dirname, requested));
    } catch (error) {
      return res.status(404).json({ error: 'File not found' });
    }
    if (!resolved.startsWith(root + path.sep)) {
      return res.status(403).json({ error: 'Only files under data/artifacts can be viewed' });
    }

    const stat = await fs.stat(resolved);
    if (!stat.isFile()) {
      return res.status(404).json({ error: 'File not found' });
    }
    if (stat.size > MAX_VIEW_BYTES) {
      return res.status(413).json({ error: 'File is larger than 1 MB' });
    }
    res.json({
      path: path.relative(__dirname, resolved),
      size: stat.size,
      content: await fs.readFile(resolved, 'utf-8')
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Execute workflow
app.post('/api/workflows/:id/execute', async (req, res) => {
  try {
    const { inputData = {}, options = {} } = req.body;

    const maxConcurrent = parseInt(process.env.MAX_CONCURRENT_EXECUTIONS) || 5;
    if (activeExecutions.size >= maxConcurrent) {
      return res.status(429).json({
        error: `Too many running executions (limit ${maxConcurrent})`
      });
    }

    // Validates the workflow and creates the execution record up front, so the
    // response carries the real execution ID and unknown workflows get a 404
    let started;
    try {
      started = await workflowEngine.startExecution(
        req.params.id,
        inputData,
        { ...options, triggerType: 'api' }
      );
    } catch (error) {
      if (error.message.startsWith('Workflow not found')) {
        return res.status(404).json({ error: error.message });
      }
      throw error;
    }

    const executionId = started.execution.execution_id;

    // Run in the background. Failures are already recorded on the execution;
    // the catch keeps a rejected promise from crashing the server.
    const executionPromise = started.run().catch((error) => {
      console.error(`Execution ${executionId} failed:`, error.message);
    });
    activeExecutions.set(executionId, executionPromise);
    executionPromise.finally(() => activeExecutions.delete(executionId));

    res.json({
      execution_id: executionId,
      status: 'started'
    });

  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// List executions
app.get('/api/executions', async (req, res) => {
  try {
    const { workflow_id, status, limit = 50 } = req.query;

    const filters = {};
    if (workflow_id) filters.workflow_id = workflow_id;
    if (status) filters.status = status;

    const executions = await workflowEngine.executionManager.listExecutions(filters);

    // Limit results
    const limitedExecutions = executions.slice(0, parseInt(limit));

    res.json(limitedExecutions);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Get execution details
app.get('/api/executions/:id', async (req, res) => {
  try {
    const execution = await workflowEngine.executionManager.loadExecution(req.params.id);
    res.json(execution);
  } catch (error) {
    res.status(404).json({ error: 'Execution not found' });
  }
});

// Stream execution logs (Server-Sent Events)
app.get('/api/executions/:id/stream', async (req, res) => {
  const executionId = req.params.id;

  // Set up SSE
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');

  // Send initial connection message
  res.write(`data: ${JSON.stringify({ type: 'connected', execution_id: executionId })}\n\n`);

  // Poll for execution updates
  const pollInterval = setInterval(async () => {
    try {
      const execution = await workflowEngine.executionManager.loadExecution(executionId);

      // Send execution update
      res.write(`data: ${JSON.stringify({
        type: 'update',
        execution
      })}\n\n`);

      // Stop polling if execution is complete
      if (execution.status === 'completed' || execution.status === 'failed') {
        clearInterval(pollInterval);
        res.write(`data: ${JSON.stringify({ type: 'done' })}\n\n`);
        res.end();
      }
    } catch (error) {
      clearInterval(pollInterval);
      res.write(`data: ${JSON.stringify({ type: 'error', error: error.message })}\n\n`);
      res.end();
    }
  }, 1000); // Poll every second

  // Clean up on client disconnect
  req.on('close', () => {
    clearInterval(pollInterval);
  });
});

// Serve index.html for root
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// JSON errors only (bad JSON bodies, oversized requests): no HTML pages or stack traces
app.use((error, req, res, next) => {
  if (error.type === 'entity.parse.failed') {
    return res.status(400).json({ error: 'Request body is not valid JSON' });
  }
  if (error.type === 'entity.too.large') {
    return res.status(413).json({ error: 'Request too large (limit 1 MB)' });
  }
  console.error('Request error:', error.message);
  res.status(error.status || 500).json({ error: error.message });
});

// Start server
// Loopback only unless HOST says otherwise
const HOST = process.env.HOST || '127.0.0.1';
app.listen(PORT, HOST, () => {
  console.log(`\n🤖 AI Workflow Automation Server`);
  console.log(`📡 Server: http://localhost:${PORT}`);
  console.log(`🐍 Python: ${process.env.PYTHON_PATH || 'python3'}`);
  console.log(`🦙 Ollama: ${process.env.OLLAMA_API_URL || 'http://localhost:11434'}`);
  console.log(`\nPress Ctrl+C to stop\n`);
});
