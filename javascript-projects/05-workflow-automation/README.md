# AI Workflow Automation

Autonomous agent system for executing workflows with AI reasoning and tool execution. Hybrid Node.js + Python architecture supporting CLI execution, REST API, cron scheduling, and event-driven triggers.

## Features

- **Autonomous AI Agents**: LLM-powered agents that reason about tasks and select appropriate tools
- **Hybrid Architecture**: Node.js orchestration + Python agent logic
- **Extensible Tool System**: Plugin-based tools (web scraping, file ops, API calls, data analysis)
- **Workflow Definitions**: JSON-based workflow configuration
- **Execution History**: File-based persistence of all executions and logs
- **Multiple Triggers**: Manual, API, cron schedules, event-driven (future)
- **Template Variables**: Dynamic workflows with {{variable}} substitution

## Architecture

```
Node.js Layer (Orchestration)
├── WorkflowEngine    - Executes workflow steps
├── PythonBridge      - Spawns Python processes, handles IPC
├── ExecutionManager  - Tracks execution state and logs
└── TaskScheduler     - Cron scheduling (Phase 4)

Python Layer (AI Agent)
├── agent.py          - Main agent with reasoning loop
├── llm_client.py     - LLM abstraction (Ollama/Anthropic/OpenAI)
├── tool_registry.py  - Dynamic tool discovery
└── tools/            - Extensible tool modules
    ├── file_ops.py   - File read/write/transform
    ├── web_scraper.py    (Phase 2)
    ├── api_client.py     (Phase 2)
    └── data_analyzer.py  (Phase 2)
```

## Setup

### Prerequisites

- Python 3.8+
- Node.js 18+
- Ollama (or Anthropic/OpenAI API keys)

### Installation

1. **Install Python dependencies:**
```bash
cd javascript-projects/05-workflow-automation
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. **Install Node.js dependencies:**
```bash
npm install
```

3. **Configure environment:**
```bash
cp .env.example .env
# Edit .env with your settings
```

4. **Ensure Ollama is running:**
```bash
ollama pull llama3.2
```

## Usage

### Web Interface (Recommended)

Start the web server:

```bash
npm start
```

Then open http://localhost:3000 in your browser.

The web interface provides:
- **Dashboard**: View and execute workflows with one click
- **Execution History**: Browse all past executions with detailed logs
- **Workflow Editor**: Visual workflow creation with JSON preview
- **Live Monitor**: Real-time execution monitoring with streaming logs

### Testing the System (CLI)

Run the test script to verify everything works:

```bash
node test.js
```

This will:
1. Check Python environment health
2. List available workflows
3. Execute the example file-processor workflow
4. Display execution logs and results

### Direct Python Agent Testing

Test the Python agent directly:

```bash
cd python
python agent.py --input '{"instruction": "Create a file at data/artifacts/test.txt with content Hello World"}'
```

### Creating Workflows

Create a workflow JSON file in `workflows/`:

```json
{
  "id": "my-workflow",
  "name": "My Custom Workflow",
  "description": "Description of what this workflow does",
  "steps": [
    {
      "id": "step1",
      "type": "agent",
      "task": {
        "instruction": "Describe what the agent should do"
      },
      "output": "step1_result"
    },
    {
      "id": "step2",
      "type": "agent",
      "task": {
        "instruction": "Use previous result: {{step1_result}}"
      }
    }
  ]
}
```

### Executing Workflows Programmatically

```javascript
const WorkflowEngine = require('./src/WorkflowEngine');

const engine = new WorkflowEngine();

// Execute a workflow
const execution = await engine.executeWorkflow('my-workflow', {
  input_param: 'value'
});

console.log(execution.status); // 'completed' or 'failed'
console.log(execution.outputs); // Step outputs
```

## Workflow Definition Format

### Basic Structure

```json
{
  "id": "workflow-id",
  "name": "Workflow Name",
  "description": "What this workflow does",
  "steps": []
}
```

### Step Types

#### Agent Step

Executes AI agent with tool access:

```json
{
  "id": "unique_step_id",
  "type": "agent",
  "task": {
    "instruction": "Clear instruction for the AI agent",
    "optional_context": "Additional context or parameters"
  },
  "output": "variable_name"
}
```

### Template Variables

Use `{{variable}}` to reference previous step outputs:

```json
{
  "id": "process_data",
  "type": "agent",
  "task": {
    "instruction": "Analyze this data: {{previous_step_output}}"
  }
}
```

## Available Tools (Phase 1)

### FileOpsTool

Read, write, transform files:

```javascript
// Read file
{
  "operation": "read",
  "path": "data/file.txt"
}

// Write file
{
  "operation": "write",
  "path": "data/output.txt",
  "content": "File content"
}

// Transform format
{
  "operation": "transform",
  "path": "data/input.csv",
  "target_format": "json"
}
```

## Example Workflows

### File Processing

```json
{
  "id": "file-processor",
  "name": "Process and Transform Files",
  "steps": [
    {
      "id": "read",
      "type": "agent",
      "task": {
        "instruction": "Read the file at data/input.txt"
      },
      "output": "content"
    },
    {
      "id": "analyze",
      "type": "agent",
      "task": {
        "instruction": "Count words in this text: {{content}}"
      },
      "output": "analysis"
    }
  ]
}
```

## Project Structure

```
05-workflow-automation/
├── .env.example
├── README.md
├── package.json
├── requirements.txt
├── test.js                    # Test script
├── server.js                  # REST API server (Phase 3)
├── workflows/
│   └── examples/
│       └── file-processor.json
├── data/
│   ├── executions/            # Execution history
│   └── artifacts/             # Generated files
├── src/                       # Node.js orchestration
│   ├── WorkflowEngine.js
│   ├── PythonBridge.js
│   ├── ExecutionManager.js
│   ├── TaskScheduler.js       (Phase 4)
│   └── routes.js              (Phase 3)
└── python/                    # Python agent layer
    ├── agent.py
    ├── llm_client.py
    ├── tool_registry.py
    └── tools/
        ├── base_tool.py
        ├── file_ops.py
        ├── web_scraper.py     (Phase 2)
        ├── api_client.py      (Phase 2)
        └── data_analyzer.py   (Phase 2)
```

## Development

### Adding New Tools

1. Create a new file in `python/tools/`:

```python
from tools.base_tool import BaseTool

class MyTool(BaseTool):
    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "What this tool does"

    def get_parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "param1": {"type": "string"}
            },
            "required": ["param1"]
        }

    def execute(self, **kwargs) -> dict:
        # Tool logic here
        return {"success": True, "result": "..."}
```

2. The tool will be auto-discovered on next agent execution

### Testing Python Agent

```bash
cd python
python agent.py --input '{"instruction": "your task here"}' --backend ollama
```

### Debugging

Enable stderr logging:

```javascript
const execution = await engine.executeWorkflow('workflow-id', {}, {
  logStderr: true  // See Python agent logs in console
});
```

## Implementation Phases

### ✅ Phase 1: Foundation (Complete)
- Project structure and dependencies
- Python agent with LLM reasoning
- Tool system with FileOpsTool
- Node.js orchestration (WorkflowEngine, PythonBridge, ExecutionManager)
- Basic workflow execution
- Example workflow and test script

### 🔄 Phase 2: AI Agent + Tools (Next)
- WebScraperTool (BeautifulSoup)
- APIClientTool (HTTP requests)
- DataAnalyzerTool (pandas)
- Enhanced agent reasoning loop
- Complex multi-tool workflows

### 📋 Phase 3: REST API
- Express server with routes
- Workflow CRUD operations
- Execution management API
- Real-time execution streaming

### 📋 Phase 4: Scheduling & Events
- Cron-based scheduling
- File watcher triggers
- Webhook endpoints
- Queue management

### 📋 Phase 5: Documentation & Polish
- Comprehensive documentation
- More example workflows
- Error handling improvements
- Tool development guide

## Configuration

### Environment Variables

```env
# Node.js
PORT=3000
PYTHON_PATH=python3
PYTHON_TIMEOUT=300000

# Python/LLM
OLLAMA_API_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
ANTHROPIC_API_KEY=
OPENAI_API_KEY=

# Storage
WORKFLOWS_DIR=./workflows
EXECUTIONS_DIR=./data/executions
ARTIFACTS_DIR=./data/artifacts
```

## Troubleshooting

### Python Agent Not Executing

1. Check Python is accessible:
```bash
python3 --version
```

2. Verify dependencies are installed:
```bash
pip list | grep requests
```

3. Test agent directly:
```bash
cd python
python agent.py --input '{"instruction": "test"}'
```

### Ollama Connection Issues

1. Ensure Ollama is running:
```bash
ollama list
```

2. Check the Ollama API URL in `.env`

3. Test Ollama directly:
```bash
curl http://localhost:11434/api/generate -d '{"model":"llama3.2","prompt":"test","stream":false}'
```

### Workflow Execution Failures

Check execution logs:

```javascript
const execution = await engine.executionManager.loadExecution('execution-id');
console.log(execution.logs);
```

## Technical Details

### Communication Flow

1. **Node.js → Python**: WorkflowEngine calls PythonBridge
2. **PythonBridge**: Spawns Python process with task JSON as CLI argument
3. **Python Agent**: Parses task, uses LLM to reason, executes tools
4. **Python → Node.js**: Outputs result as JSON to stdout
5. **Node.js**: Parses JSON, updates execution state, continues workflow

### Tool Discovery

Tools are auto-discovered by:
1. Scanning `python/tools/` directory
2. Finding classes that inherit from `BaseTool`
3. Instantiating and registering them
4. Generating function schemas for LLM

### Execution Persistence

Each execution creates a JSON file in `data/executions/`:

```json
{
  "execution_id": "exec-2026-01-01...",
  "workflow_id": "my-workflow",
  "status": "completed",
  "started_at": "2026-01-01T12:00:00Z",
  "completed_at": "2026-01-01T12:01:30Z",
  "duration_ms": 90000,
  "steps_completed": 3,
  "outputs": {},
  "logs": []
}
```

## Future Enhancements

- [ ] Parallel step execution
- [ ] Conditional branching in workflows
- [ ] Loop constructs
- [ ] Sub-workflow calling
- [ ] Visual workflow builder (web UI)
- [ ] PostgreSQL backend for scale
- [ ] Workflow versioning
- [ ] Rollback capabilities

## License

MIT License - see repository root LICENSE file

## Contributing

This is a learning project. Feel free to use the code and patterns for your own projects.
