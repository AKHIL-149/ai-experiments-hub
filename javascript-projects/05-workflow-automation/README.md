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
- **Dashboard**: View workflows and run them. Pick one in Quick Execute and its required inputs are filled in as a template
- **Execution History**: Browse past executions; open one to see each step's result, the saved report and the logs
- **Workflow Editor**: Build workflows visually (see below), save them to the server, load them again, and run them
- **Live Monitor**: Follow a run live; the results appear under the logs when it finishes

The server listens on `127.0.0.1` only and accepts same-origin requests only, because it can write files and run workflows. Set `HOST` or `CORS_ORIGIN` to change that.

### Building a workflow in the editor

1. **Workflow Editor** > fill in the ID (letters, numbers, `-`, `_`), name and description.
2. **+ Add Step**. A step is either an **AI step** (an instruction for the model) or a **Tool step** (run a tool such as `file_operations` directly; its parameter form comes from the tool itself). Use ↑ / ↓ to reorder.
3. Use `{{name}}` in instructions and parameters to insert a run input or an earlier step's output. Give a step a **Save result as** name to make its result available to later steps (`{{notes.content}}` reads a field of an object result). The editor lists the inputs it detects under the JSON preview.
4. **Save** writes `workflows/<id>.json` (a mistake such as a duplicate step ID or a variable used before it is created is reported instead of saved). **Save & Run** saves and jumps to the Dashboard with the inputs template ready.
5. To edit later, choose it under **Load a saved workflow** > **Load**, change it and Save (saving the workflow you loaded replaces it; saving a new workflow under an existing ID asks first).

Run it from the Dashboard: fill in the input JSON, **Execute Workflow**, and the Live Monitor opens by itself. Results of past runs are in Execution History.

Paths in file steps are relative to the project root and cannot leave it. A saved file under `data/artifacts/` can be viewed in the results panel. AI output and `.md` files are shown formatted (headings, lists, tables, bold); **Show raw text** switches to the plain text. HTML in model output is always escaped.

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

## Example: Meeting Notes to Action Items

`workflows/examples/meeting-actions.json` reads a notes file, has the LLM extract the action items, and saves them as a checklist. Execute it from the dashboard's Quick Execute (pick the workflow and paste the input JSON), or via the API:

```bash
curl -X POST http://localhost:3000/api/workflows/meeting-actions/execute \
  -H 'content-type: application/json' \
  -d '{"inputData": {"notes_path": "examples/meeting-notes.txt", "output_path": "data/artifacts/action-items.md"}}'
```

The response carries an `execution_id`; open it under Execution History (or `GET /api/executions/<id>`) to see each step's log and output.

## Example: Customer Feedback Report

`workflows/examples/customer-feedback-report.json` (built in the visual editor) turns a CSV of customer reviews into a report with five steps: read the CSV (tool), classify every review (AI), write top problems and actions (AI), draft replies to the 1 and 2 star reviews (AI), and save everything as one markdown file (tool). Inputs: `feedback_csv`, `report_path`. Try it with the sample data:

```json
{"feedback_csv": "examples/customer-feedback.csv", "report_path": "data/artifacts/feedback-report.md"}
```

It takes about 10 seconds with `llama3.2` (3B). Small models make mistakes in the analysis; set `OLLAMA_MODEL` to a larger model for better summaries.

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

Optional task fields:

| Field | Meaning |
|---|---|
| `require_tools` | `true` makes the step fail unless the agent actually calls a tool. Use it for steps that must read or write files; otherwise the model may skip the tool and answer from imagination. |

A step also fails if any tool call it makes fails (e.g. file not found), instead of reporting a plausible-sounding summary. Each step's record keeps `details.tools_used` and the raw `details.tool_results`.

#### Tool Step

Runs a tool directly with fixed parameters: no LLM planning, so it is fast and deterministic. Use it for file reads and writes, and keep agent steps for judgment (extracting, summarizing, rewriting).

```json
{
  "id": "read_notes",
  "type": "tool",
  "tool": "file_operations",
  "parameters": { "operation": "read", "path": "{{notes_path}}" },
  "output": "notes"
}
```

A tool step's output is the tool's result object, so a read's text is `{{notes.content}}` (`{{name.field}}` looks inside an output). An agent step can set `"use_tools": false` to skip tool planning for pure-text work.

### Template Variables

Use `{{variable}}` to reference previous step outputs. A step that reads a file outputs the file's content, so the next step receives the real text. Referencing a variable that is neither an input nor an earlier step's `output` fails the step with an "Unresolved template variable" error.

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

Paths are relative to the project root. Paths that escape the project directory (`../`, absolute paths) and secret files (`.env*`, `.git`) are refused, since the paths come from an LLM.

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
HOST=127.0.0.1                # loopback only by default
# CORS_ORIGIN=                # set to allow another origin to call the API
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

# Execution
MAX_CONCURRENT_EXECUTIONS=5   # further API executions get HTTP 429
```

Relative paths resolve against the project root. `/api/health` checks that Python starts and that Ollama is reachable; it does not call the LLM.

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

## REST API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Python and Ollama status |
| GET | `/api/workflows` | List workflows (with the `inputs` each needs) |
| GET | `/api/workflows/:id` | One workflow definition |
| POST | `/api/workflows` | Save `{ "workflow": {...}, "overwrite": false }`; 400 lists problems, 409 if the ID exists |
| POST | `/api/workflows/:id/execute` | Start a run: `{ "inputData": {...} }` |
| GET | `/api/tools` | Tools a step can call, with parameter schemas |
| GET | `/api/executions`, `/api/executions/:id` | History and one run (logs, per-step results) |
| GET | `/api/executions/:id/stream` | Live updates (Server-Sent Events) |
| GET | `/api/artifacts?path=data/artifacts/x.md` | Read a file a workflow saved (only under `data/artifacts`) |

## Tests

```bash
npm test
```

Covers workflow validation and saving (ID rules, duplicate and misordered steps, overwrite protection) and the markdown renderer (including HTML escaping). `node test.js` is a separate live check that needs Python and Ollama.

## Future Enhancements

- [ ] Parallel step execution
- [ ] Conditional branching in workflows
- [ ] Loop constructs
- [ ] Sub-workflow calling
- [ ] PostgreSQL backend for scale
- [ ] Workflow versioning
- [ ] Rollback capabilities

## License

MIT License - see repository root LICENSE file

## Contributing

This is a learning project. Feel free to use the code and patterns for your own projects.
