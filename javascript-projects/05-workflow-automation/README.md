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
   Under **Only run this step when…** a step can depend on an earlier result (for example `unhappy.rows > 0`); when the condition is false the step is skipped and its result becomes the text you enter for "If the step is skipped". An AI step can also have a **Longest reply** (`max_tokens`); a reply that hits it is flagged "output cut off".
4. **Save** writes `workflows/<id>.json` (a mistake such as a duplicate step ID or a variable used before it is created is reported instead of saved). **Save & Run** saves and jumps to the Dashboard with the inputs template ready.
5. To edit later, choose it under **Load a saved workflow** > **Load**, change it and Save (saving the workflow you loaded replaces it; saving a new workflow under an existing ID asks first).

Run it from the Dashboard: pick a **Model**, fill in the input JSON, **Execute Workflow**, and the Live Monitor opens by itself.

The **Model** list shows every text model installed in Ollama (embedding models are left out) with its size; "Default" uses `OLLAMA_MODEL`. Your choice is remembered in this browser, applies to every AI step of the run, and is recorded with the run (shown in History and the Monitor). Use **Refresh** after `ollama pull`. A larger model (qwen3:8b or 14b) follows instructions and summarises noticeably better than the 3B default, at the cost of speed and memory. Results of past runs are in Execution History.

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

## Conditional steps, token limits and empty data

```json
{
  "id": "draft_replies",
  "type": "agent",
  "task": { "instruction": "...", "use_tools": false, "max_tokens": 1500 },
  "run_if": { "variable": "unhappy.rows", "operator": ">", "value": 0 },
  "if_skipped": "No unhappy customers this period.",
  "output": "replies"
}
```

- **`run_if`** compares an earlier result (`name` or `name.field`) with a value using `== != > >= < <=`. Numbers compare as numbers. When it is false the step is skipped (shown as "skipped") and `if_skipped` becomes the step's output. Use it instead of asking a small model to "do X, but if there is no data say Y": the engine decides, so the model never sees an empty case.
- **`if_skipped`** may contain `{{variables}}` (inputs or earlier results), e.g. `"No alert: nothing moved {{threshold_pct}}% today."`; one that does not exist fails the step with a clear message.
- **`max_tokens`** (1 to 32768, default 4096, `LLM_MAX_TOKENS` changes the default) caps the length of an AI reply. If a reply hits the cap, the step is marked `truncated`, a warning is logged and the results show an "output cut off" badge.
- **Empty values stop the step.** A blank input, an empty file or an earlier step that produced nothing makes `{{name}}` empty; the next step fails with "`{{name}}` are empty" instead of sending nothing to the model, which would invent data.
- **Thinking models** (qwen3 and similar) reason before answering, which is slow and can use up the whole token limit. Thinking is switched off for workflow steps (`OLLAMA_THINK=true` turns it back on). A reply that comes back empty fails the step with a clear message instead of passing nothing on, and a model that is not installed fails with the `ollama pull` command to run.
- The context window is sized to each prompt (Ollama silently drops the start of a prompt that does not fit).

## Example: Customer Feedback Report

`workflows/examples/customer-feedback-report.json` (built in the visual editor) turns a CSV of customer reviews (columns `id,date,customer,rating,comment`) into a report. Code does the exact work and the AI only writes text:

1. read the CSV (tool)
2. label each review Positive / Neutral / Negative from its rating (`csv_operations`)
3. build the markdown table (`csv_operations`)
4. find the reviews rated 1 or 2 (`csv_operations`)
5. write top problems and actions (AI, skipped when there are no reviews)
6. draft a reply for every unhappy customer (AI, skipped when there are none)
7. save everything as one markdown file (tool)

Inputs: `feedback_csv`, `report_path`. Try it with the sample data:

```json
{"feedback_csv": "examples/customer-feedback.csv", "report_path": "data/artifacts/feedback-report.md"}
```

Tested against 14 kinds of data (all-positive, all-negative, one review, empty file, header only, non-English, emoji, unquoted commas, 60 reviews, a 9 KB comment, prompt injection, braces in the text). Errors and empty data are handled reliably. Writing quality is the weak spot with the default 3B model: it can duplicate or skip a reply, drop a problem from the summary, or repeat injected text as a finding. Use a larger model (`OLLAMA_MODEL`) for real use. A "for each row" step would make the replies deterministic and is not built yet.

## Example: Stock Ticker, Random Portfolio and Portfolio Tracker

Three finance workflows built on the same idea as the feedback report: code does every number, the AI only restates facts. **They read prices and write reports; they never trade, and nothing they write is investment advice.** Every report says so.

| Workflow | Inputs | What it does |
|---|---|---|
| `stock-ticker-update` | `symbols`, `source`, `report_path` | Latest price and day change for a list of tickers, a table and a 3-sentence factual snapshot |
| `create-random-portfolio` | `count`, `seed`, `source`, `portfolio_path` | Makes a random **sample** portfolio (made-up holdings) and saves it as CSV. The same seed always gives the same portfolio |
| `portfolio-tracker` | `portfolio_path`, `source`, `history_path`, `report_path` | Values a portfolio, appends today's total to a history file, and reports totals, positions, trend and a factual commentary |
| `price-alert` | `portfolio_path`, `source`, `threshold_pct`, `log_path`, `alert_path` | Flags positions that moved at least `threshold_pct` percent today (up or down). Every check is logged; the alert file is written only when something qualifies |

A typical sequence (paths are relative to the project):

```json
{"count": 8, "seed": 2026, "source": "yahoo", "portfolio_path": "data/portfolio/random-portfolio.csv"}
{"portfolio_path": "data/portfolio/random-portfolio.csv", "source": "yahoo", "history_path": "data/portfolio/history.csv", "report_path": "data/artifacts/portfolio-report.md"}
```

Run the tracker on different days and the history file builds a trend (reruns on the same day count once). `examples/sample-portfolio.csv` is a ready-made portfolio. Your own portfolio is a CSV with the columns `symbol,shares,cost_basis` (cost_basis = price paid per share); repeated symbols are merged.

### Price alert

`price-alert` is deliberately **free of AI text**: the check, the table and the message are all produced by code, so an alert can never contradict the numbers (an earlier version with a model-written description once said "Eight positions moved" when one had). It needs `threshold_pct` between 0 (exclusive) and 100, e.g. `3`; a move of exactly the threshold counts.

- When something qualifies, `alert_path` is written (symbol, direction, price, previous close, move, effect on the position, and the whole portfolio's move today).
- When nothing does, the alert step is shown as **skipped** with the sentence "No alert: none of 8 positions moved at least 3% (largest move LLY +2.10%)" and **no file is written**. A quiet check does not remove an earlier alert file, so read the "as of" line in it.
- Every check appends `check time, price date, number of alerts, symbols, threshold` to `log_path`, so you can see it ran even when it stayed quiet.

The project has no scheduler yet, so something has to start the workflow. The API is enough, for example from your system's cron every 30 minutes on weekdays (the server must be running; adjust the port and paths):

```bash
*/30 * * * 1-5 curl -s -X POST http://127.0.0.1:3000/api/workflows/price-alert/execute -H 'Content-Type: application/json' -d '{"inputData": {"portfolio_path": "data/portfolio/random-portfolio.csv", "source": "yahoo", "threshold_pct": 3, "log_path": "data/portfolio/alert-log.csv", "alert_path": "data/artifacts/price-alert.md"}}'
```

Nothing is sent to you: the alert is a file and a result in the UI. Prices are delayed and a daily move is measured against the previous close, so this is not a real-time alerting system.

**Price sources.** `source` is `yahoo` or `simulated`:
- `yahoo` gives real, delayed prices from Yahoo Finance's public chart endpoint. It needs no key but is **unofficial and undocumented**: it can change, rate-limit or stop working, and it is meant for personal, informational use. A symbol it cannot find is reported and left out of the totals.
- `simulated` gives made-up prices (stable within a day, different tomorrow). It works offline and is labelled "simulated" everywhere. It invents a price for any symbol, so use it for demos only.

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

### CsvOpsTool (`csv_operations`)

Exact work on CSV *text* (usually `{{something.content}}` from a file read), so the AI does not have to filter or count:

| operation | what it does |
|---|---|
| `filter` | keep rows where `column` `operator` `value` (`< <= > >= == != contains`; numbers compare as numbers) |
| `label` | add `new_column` from numeric `ranges`, e.g. `4-5:Positive,3:Neutral,1-2:Negative` |
| `to_markdown` | markdown table, optional `columns` |
| `count` | number of data rows |

Results carry `rows` (and `total` for filter) so `run_if` can test them. `if_empty` is returned instead when nothing is left. A row with more cells than the header (unquoted commas in the last column) is repaired by joining the extra text onto the last column and reported as `repaired_rows`.

### MarketDataTool (`market_data`)

`symbols` (comma-separated, up to 25, e.g. `AAPL,BRK-B,^GSPC`) and `source` (`yahoo` or `simulated`). Returns a CSV of `symbol,price,prev_close,change,change_pct,currency,as_of,source`, a one-line `summary`, `up`/`down` counts and a `notes` line naming any symbol it could not price. Read-only. `MARKET_DATA_TIMEOUT` (seconds, default 10) limits each request.

### PortfolioOpsTool (`portfolio_operations`)

| operation | what it does |
|---|---|
| `generate` | random sample holdings from 40 well-known US companies: `count` (1-25), `seed` (any whole number), `source`; cost basis is set within 30% of the current price |
| `alerts` | `holdings`, `source`, `threshold` (percent): the positions whose move today is at least the threshold, biggest first, with `count`, `symbols`, a `summary` sentence, a markdown table and a `log_line` |
| `value` | prices `holdings` CSV and returns value, cost, gain/loss, day change and weights per position, plus totals (`total_value`, `day_change_pct`, `largest_position_symbol`, ...), a markdown table and a `history_row` |
| `trend` | summarises a history file (`date,total_value,total_cost,day_change,positions`): period change, best and worst day; damaged lines are ignored |

All arithmetic is done here, tested against hand-calculated figures, and the totals are given to the AI as text to restate rather than to work out.

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
LLM_MAX_TOKENS=4096           # default cap on one AI reply (a step can set max_tokens)
OLLAMA_TIMEOUT=240            # seconds to wait for one model reply
OLLAMA_MAX_CTX=32768          # largest context window requested
OLLAMA_THINK=false            # true lets thinking models reason before answering
MARKET_DATA_TIMEOUT=10        # seconds to wait for each price request
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
| POST | `/api/workflows/:id/execute` | Start a run: `{ "inputData": {...}, "options": { "model": "qwen3:8b" } }` (`options.model` is optional; 400 for a bad name) |
| GET | `/api/models` | Installed text models and the default (502 with an empty list when Ollama is not running) |
| GET | `/api/tools` | Tools a step can call, with parameter schemas |
| GET | `/api/executions`, `/api/executions/:id` | History and one run (logs, per-step results) |
| GET | `/api/executions/:id/stream` | Live updates (Server-Sent Events) |
| GET | `/api/artifacts?path=data/artifacts/x.md` | Read a file a workflow saved (only under `data/artifacts`) |

## Tests

```bash
npm test                              # Node: engine, validation, execution records, markdown renderer, example workflows
python3 -m pytest python/tests -q     # Python: csv_operations, market_data, portfolio_operations, LLM client limits
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
