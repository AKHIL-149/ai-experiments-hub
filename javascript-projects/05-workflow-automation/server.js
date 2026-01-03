const express = require('express');
const cors = require('cors');
const path = require('path');
require('dotenv').config();

const WorkflowEngine = require('./src/WorkflowEngine');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.static('public'));

// Initialize workflow engine
const workflowEngine = new WorkflowEngine();

// Store active executions for SSE
const activeExecutions = new Map();

// API Routes

// Health check
app.get('/api/health', async (req, res) => {
  try {
    const pythonHealthy = await workflowEngine.pythonBridge.healthCheck();
    res.json({
      status: 'ok',
      python: pythonHealthy ? 'healthy' : 'unhealthy',
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

// Execute workflow
app.post('/api/workflows/:id/execute', async (req, res) => {
  try {
    const { inputData = {}, options = {} } = req.body;

    // Start execution asynchronously
    const executionPromise = workflowEngine.executeWorkflow(
      req.params.id,
      inputData,
      { ...options, triggerType: 'api' }
    );

    // Get the execution ID immediately
    const execution = await workflowEngine.executionManager.listExecutions();
    const latestExecution = execution[0];

    // Store promise for SSE streaming
    activeExecutions.set(latestExecution.execution_id, executionPromise);

    // Return execution ID immediately
    res.json({
      execution_id: latestExecution.execution_id,
      status: 'started'
    });

    // Clean up after execution completes
    executionPromise.finally(() => {
      activeExecutions.delete(latestExecution.execution_id);
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

// Start server
app.listen(PORT, () => {
  console.log(`\n🤖 AI Workflow Automation Server`);
  console.log(`📡 Server: http://localhost:${PORT}`);
  console.log(`🐍 Python: ${process.env.PYTHON_PATH || 'python3'}`);
  console.log(`🦙 Ollama: ${process.env.OLLAMA_API_URL || 'http://localhost:11434'}`);
  console.log(`\nPress Ctrl+C to stop\n`);
});
