# Usage Guide

This is a verified, tested-live guide to what this project actually does today. Several other `.md` files in this folder (`HOW_TO_USE.md`, `WORKFLOW_GUIDE.md`, `QUICK_WORKFLOW_DEMO.md`, etc.) were written before task execution and workflow advancement were real - they describe aspirational behavior (a planner agent that decomposes tasks, automatic DAG estimation) that doesn't exist in the code. This guide only describes what has been run and confirmed working.

## What this actually is

A FastAPI + Celery app that runs tasks through specialized LLM agents, either one at a time or chained into a dependency-ordered workflow (DAG). By default every agent calls a local Ollama model - no API key needed. Four agent roles are seeded out of the box: **Research**, **Writer**, **Coder**, **Reviewer** (a `Data Analyst`/researcher-adjacent role also exists in `seed_data.py` but isn't required to get started).

## 1. Start everything

You need three things running: Ollama, the FastAPI server, and a Celery worker.

```bash
# Ollama (once)
ollama pull llama3.2

# From python-projects/14-multi-agent-orchestrator/
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # defaults already point at local Ollama + SQLite
./migrate.sh upgrade

# Terminal 1
python3 server.py

# Terminal 2 - the -Q flags are not optional, see "Troubleshooting" below
PYTHONPATH=. celery -A celery_app worker --loglevel=info -Q celery,tasks,agents,orchestration,monitoring
```

Dashboard: **http://localhost:8001/dashboard**

## 2. Run a single task

Simplest way: dashboard → **Create Task** → pick an agent type, priority, and description → submit. It auto-executes and you can click into it from the task list to see the real LLM output once it completes.

Via API:

```bash
curl -X POST http://localhost:8001/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Summarize REST vs GraphQL",
    "description": "Summarize the key tradeoffs between REST and GraphQL APIs in 3 bullet points.",
    "task_type": "research",
    "priority": 5,
    "auto_execute": true
  }'
```

`task_type` drives which agent role gets auto-assigned: `research` → Research agent, `writer`/`documentation` → Writer, `code`/`coding` → Coder, `review`/`code_review` → Reviewer.

## 3. Run a workflow (multi-step, dependency-chained)

Dashboard → **Create Workflow** → add steps, check "Runs after the previous step" on any step that depends on the one before it → **Create & Start Workflow**. The panel polls and shows each step's status live.

Via API, a 2-step research → write chain:

```bash
curl -X POST http://localhost:8001/api/workflow-engine/workflows \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Research and Write Demo",
    "steps": [
      {"step_id": "step_1", "name": "Research", "agent_type": "research",
       "task_description": "Research the top 3 benefits of automated testing.",
       "depends_on": []},
      {"step_id": "step_2", "name": "Write", "agent_type": "writer",
       "task_description": "Write a short paragraph summarizing why automated testing matters.",
       "depends_on": ["step_1"]}
    ]
  }'
# then: POST /api/workflow-engine/workflows/{id}/start
# poll: GET  /api/workflow-engine/workflows/{id}/status
```

When step 1 finishes, the engine automatically creates and enqueues step 2 - you don't re-trigger anything manually. `GET .../status` returns each step's status, its underlying `task_id`, and its `result` once done.

## 4. Known limitation: steps don't see each other's real output

This is the one thing to know before building a "real" multi-step pipeline: **a step's `task_description` is static text - the actual output of a prior step is never injected into a dependent step's prompt.** The dependency graph controls *ordering* (step 2 won't start until step 1 finishes), not *data flow*.

In practice this means a step like `"Review the code from the previous step"` has no code to look at - the agent only sees that sentence, and (especially for the `code` agent type, which defaults to code-*generation* mode) will typically just invent something plausible-but-wrong rather than operate on the real prior result. Confirmed live: asking a workflow's step 3 to "review the blog post from step 2" produced an unrelated block of Python code, because the Coder agent had no blog post to review and defaulted to writing code instead.

**Workaround** - fetch the real prior output and feed it into the next step yourself, either as a standalone follow-up task or before creating the dependent step:

```python
import requests

# 1. Get the real output from the step you depend on
prior = requests.get("http://localhost:8001/api/tasks/118").json()
real_code = prior["output_data"]["code"]

# 2. Create the next task with that real content embedded via input_data,
#    and (for the code agent specifically) set task_type explicitly -
#    it defaults to "generate" otherwise, even for a review request.
requests.post("http://localhost:8001/api/tasks", json={
    "title": "Review the real implementation",
    "description": "Code review",
    "task_type": "code",
    "input_data": {
        "task_type": "review",   # generate | review | debug | refactor
        "code": real_code,
        "language": "python"
    },
    "auto_execute": True
})
```

## 5. Full worked example: a mid-level dev task

This is a real run, verified live, of "implement a feature → write tests → get it reviewed" - the kind of chain a mid-level engineer would actually do.

**Step 1 - Implement** (workflow step, `agent_type: code`): asked for a thread-safe LRU cache with `get`/`put` and capacity eviction. Got a correct, working implementation using `OrderedDict` + a `Lock`.

**Step 2 - Add tests**: run natively as a workflow step, this just wrote *another* LRU cache implementation instead of tests (the limitation above). Fixed by fetching the real step-1 code and resubmitting as a standalone task with the code embedded in `requirements` and an explicit instruction *not* to reimplement the class - that produced real `pytest` functions (`test_basic_get_put`, `test_eviction_when_over_capacity`, etc.) against the actual class. Even then, two of the four tests were subtly wrong (a zero-capacity edge case, a bad recency assertion) - a fair reflection of what to expect from a small local model, worth an actual human review pass before trusting generated tests.

**Step 3 - Review**: same fix applied (`input_data.task_type = "review"`, `input_data.code = <real implementation>`) produced a genuinely useful review - flagged missing input validation, no logging, O(n) eviction cost, and the lack of tests.

Net result: implementation and review were solid once given real content; test generation needed a much more explicit prompt and still needed a human to catch two bad assertions. That's a realistic picture of what to expect from this stack today, not a sales pitch.

## 6. Troubleshooting

These are the three root causes of "task stuck on pending forever" found and fixed during testing - if you're extending this app and hit that symptom again, check these first:

1. **Worker not listening on the right queue.** `celery_app.py`'s `task_routes` sends different task types to separate queues (`tasks`, `agents`, `orchestration`, `monitoring`). A worker started without `-Q` only consumes the default `celery` queue - anything else is silently dropped with zero error. Always start with `-Q celery,tasks,agents,orchestration,monitoring` (see the start command above).
2. **Wrong Celery app resolved.** `@shared_task` binds to whichever Celery app is "current" in the process at call time, not necessarily the one it was decorated under. Every module that publishes a task now explicitly does `import celery_app` at the top for this reason - don't remove it, and add it to any new worker/service module that calls `.delay()`.
3. **SQLite "database is locked".** Multiple worker processes writing to the same SQLite file at once used to crash instantly instead of waiting. `src/core/database.py` now sets WAL mode + a 30s busy_timeout on every connection - this only matters if you swap in a different DB setup.

## Reference

- [README.md](README.md) - install steps, architecture, API overview
- [WORKFLOW_GUIDE.md](WORKFLOW_GUIDE.md), [HOW_TO_USE.md](HOW_TO_USE.md) - older, pre-dates working task execution; kept for history, not accurate
