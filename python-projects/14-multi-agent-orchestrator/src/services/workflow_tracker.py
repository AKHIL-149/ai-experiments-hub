"""
Read-only view of workflows for the tracker page: how far each one is, and what every step's task produced.

The workflow engine keeps step state in Workflow.extra_metadata (step_states) and each step runs as a Task
whose output_data holds the agent's answer. Agents answer in different shapes (research/analysis: `summary`,
writer: `content`, code: `code` + `explanation`), so `summarize_output` turns any of them into one readable
form for the page.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from src.models import Agent, Task, Workflow

# The first of these keys that holds text is the main answer of a step.
TEXT_KEYS = ("summary", "content", "full_plan", "analysis", "plan", "result", "output", "text", "explanation")
ACTIVE_STATUSES = {"pending", "running", "paused"}
FINISHED_STEP = {"completed", "failed", "skipped"}


def plain(value: Any) -> str:
    """'completed' for both the string "completed" and WorkflowStatus.COMPLETED / 'COMPLETED'"""
    return str(getattr(value, "value", value) or "").lower()


def iso(moment: Optional[Any]) -> Optional[str]:
    """Timestamps are stored as naive UTC; say so, so the browser shows them in the viewer's own time"""
    if moment is None:
        return None
    if isinstance(moment, str):
        return moment if moment.endswith("Z") or "+" in moment[10:] else moment + "Z"
    return moment.isoformat() + "Z"


def seconds_between(start: Optional[Any], end: Optional[Any]) -> Optional[float]:
    def parse(value):
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", ""))
            except ValueError:
                return None
        return value

    start, end = parse(start), parse(end)
    if start is None or end is None:
        return None
    return round(max(0.0, (end - start).total_seconds()), 1)


def summarize_output(output: Any) -> Dict[str, Any]:
    """
    One readable form for whatever an agent returned:
    {text, code, language, explanation, metrics, raw}; text/code/language/explanation may be None.
    """
    if output is None:
        return {"text": None, "code": None, "language": None, "explanation": None, "metrics": {}, "raw": None}
    if not isinstance(output, dict):
        return {"text": str(output), "code": None, "language": None, "explanation": None, "metrics": {}, "raw": output}

    code = output.get("code") if isinstance(output.get("code"), str) and output["code"].strip() else None
    language = output.get("language") if isinstance(output.get("language"), str) else None
    explanation = output.get("explanation") if isinstance(output.get("explanation"), str) and output["explanation"].strip() else None

    text = None
    for key in TEXT_KEYS:
        value = output.get(key)
        # code answers keep their prose in `explanation`, which is shown on its own below the code
        if key == "explanation" and code:
            continue
        if isinstance(value, str) and value.strip():
            text = value
            break

    metrics = {}
    for key in ("word_count", "tokens_used", "cost"):
        if isinstance(output.get(key), (int, float)):
            metrics[key] = output[key]

    return {"text": text, "code": code, "language": language, "explanation": explanation, "metrics": metrics, "raw": output}


def step_counts(steps: List[Dict[str, Any]], states: Dict[str, Any]) -> Dict[str, Any]:
    counts = {"total": len(steps), "completed": 0, "failed": 0, "running": 0, "pending": 0}
    for step in steps:
        state = plain(states.get(step["step_id"], {}).get("status")) or "pending"
        if state == "completed":
            counts["completed"] += 1
        elif state == "failed":
            counts["failed"] += 1
        elif state in ("running", "ready"):
            counts["running"] += 1
        else:
            counts["pending"] += 1
    counts["percentage"] = round(counts["completed"] / counts["total"] * 100, 1) if counts["total"] else 0.0
    return counts


def workflow_timeline(workflow: Workflow) -> Dict[str, Any]:
    meta = workflow.extra_metadata or {}
    started = workflow.started_at or meta.get("started_at")
    finished = workflow.completed_at or meta.get("completed_at")
    end = finished if finished else (datetime.utcnow() if plain(workflow.status) in ACTIVE_STATUSES else None)
    return {
        "created_at": iso(workflow.created_at),
        "started_at": iso(started),
        "completed_at": iso(finished),
        "duration_seconds": seconds_between(started, end) if started else None,
    }


def summarize_workflow(workflow: Workflow) -> Dict[str, Any]:
    meta = workflow.extra_metadata or {}
    steps, states = meta.get("steps", []), meta.get("step_states", {})
    current = next(
        (s["name"] for s in steps if plain(states.get(s["step_id"], {}).get("status")) in ("running", "ready")), None
    )
    return {
        "id": workflow.id,
        "name": workflow.name,
        "description": workflow.description,
        "status": plain(workflow.status),
        "progress": step_counts(steps, states),
        "current_step": current,
        "timeline": workflow_timeline(workflow),
    }


def list_workflows(
    session: Session, owner_id: Optional[int] = None, status: Optional[str] = None, limit: int = 50, offset: int = 0
) -> Dict[str, Any]:
    query = session.query(Workflow)
    if owner_id is not None:
        query = query.filter(Workflow.created_by == owner_id)
    if status:
        query = query.filter(Workflow.status == status)
    total = query.count()
    rows = query.order_by(desc(Workflow.created_at), desc(Workflow.id)).limit(limit).offset(offset).all()
    return {"total": total, "limit": limit, "offset": offset, "workflows": [summarize_workflow(w) for w in rows]}


def workflow_detail(session: Session, workflow_id: int) -> Optional[Dict[str, Any]]:
    workflow = session.query(Workflow).filter(Workflow.id == workflow_id).first()
    if workflow is None:
        return None

    meta = workflow.extra_metadata or {}
    steps, states = meta.get("steps", []), meta.get("step_states", {})
    names = {s["step_id"]: s["name"] for s in steps}

    task_ids = [st["task_id"] for st in states.values() if st.get("task_id")]
    tasks = {t.id: t for t in session.query(Task).filter(Task.id.in_(task_ids)).all()} if task_ids else {}
    agent_ids = {t.assigned_agent_id for t in tasks.values() if t.assigned_agent_id}
    agents = {a.id: a.name for a in session.query(Agent).filter(Agent.id.in_(agent_ids)).all()} if agent_ids else {}

    detail_steps = []
    for number, step in enumerate(steps, start=1):
        state = states.get(step["step_id"], {})
        task = tasks.get(state.get("task_id"))
        output = summarize_output(task.output_data if task else state.get("result"))
        error = (task.error_message if task and task.error_message else None) or state.get("error")
        status = plain(state.get("status")) or "pending"

        started = (task.started_at if task and task.started_at else None) or state.get("started_at")
        finished = (task.completed_at if task and task.completed_at else None) or state.get("completed_at")
        detail_steps.append({
            "number": number,
            "step_id": step["step_id"],
            "name": step["name"],
            "agent_type": step.get("agent_type"),
            "description": step.get("task_description"),
            "depends_on": [{"step_id": d, "name": names.get(d, d)} for d in step.get("depends_on", [])],
            "status": status,
            "attempts": state.get("attempts", 0),
            "task": None if task is None else {
                "id": task.id,
                "status": plain(task.status),
                "agent_id": task.assigned_agent_id,
                "agent_name": agents.get(task.assigned_agent_id),
                "started_at": iso(started),
                "completed_at": iso(finished),
                "duration_seconds": seconds_between(started, finished) if finished else None,
            },
            "output": output,
            "error": error,
        })

    summary = summarize_workflow(workflow)
    summary.update({
        "steps": detail_steps,
        "error": workflow.error_message,
    })
    return summary
