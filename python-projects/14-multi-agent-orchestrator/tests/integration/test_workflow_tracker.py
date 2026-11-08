"""
Tests for the workflow tracker API and page: who sees which workflow, and what each step shows.

They use the portal tests' throwaway server (its own database), and write step results straight into that
database, because without a worker nothing would run.
"""

import json
import sqlite3
from pathlib import Path

import pytest

# fixtures and helpers of the portal tests: a private server, a client, accounts
from tests.integration.test_portal import PASSWORD, WORKFLOWS, account, admin_headers, guest, http, server  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
TRACKER = "/api/workflow-tracker"

STEPS = [
    {"step_id": "step_1", "name": "Research it", "agent_type": "research", "task_description": "What is X?", "depends_on": []},
    {"step_id": "step_2", "name": "Code it", "agent_type": "code", "task_description": "Write X.", "depends_on": ["step_1"]},
    {"step_id": "step_3", "name": "Plan it", "agent_type": "planner", "task_description": "Plan X.", "depends_on": ["step_2"]},
]


def make_workflow(http, headers, name="a workflow", steps=STEPS):
    response = http.post(WORKFLOWS, headers=headers, json={"name": name, "description": "about " + name, "steps": steps})
    assert response.status_code in (200, 201), response.text
    return response.json()["workflow"]["id"]


def make_agent(server, name):
    """An agent row (the agents API hands creation to a Celery worker, which these tests do not run)"""
    con = sqlite3.connect(server["db"])
    try:
        cursor = con.execute(
            "insert into agents (name, role, status, created_at, updated_at) "
            "values (?, 'CODER', 'IDLE', '2026-01-01 00:00:00', '2026-01-01 00:00:00')", (name,))
        con.commit()
        return cursor.lastrowid
    finally:
        con.close()


def finish_steps(http, server, headers, workflow_id, agent_id, outcomes):
    """Pretend the worker ran the steps: make a task per step and record its state in the database"""
    # every task is made first: an open write on the database file would make the server wait on it
    tasks = {
        step_id: http.post("/api/tasks/", headers=headers, json={
            "title": f"task for {step_id}", "description": "d", "task_type": "research", "auto_execute": False}).json()["id"]
        for step_id in outcomes
    }
    con = sqlite3.connect(server["db"])
    try:
        meta = json.loads(con.execute("select extra_metadata from workflows where id=?", (workflow_id,)).fetchone()[0])
        states = {}
        for step_id, (status, output, error) in outcomes.items():
            con.execute(
                "update tasks set status=?, assigned_agent_id=?, output_data=?, error_message=?, "
                "started_at='2026-01-01 10:00:00', completed_at='2026-01-01 10:00:07' where id=?",
                (status.upper(), agent_id, json.dumps(output) if output is not None else None, error, tasks[step_id]))
            states[step_id] = {"status": status, "task_id": tasks[step_id], "attempts": 1, "result": None}
        meta["step_states"] = states
        con.execute("update workflows set extra_metadata=? where id=?", (json.dumps(meta), workflow_id))
        con.commit()
    finally:
        con.close()


def set_status(server, workflow_id, status):
    con = sqlite3.connect(server["db"])
    con.execute("update workflows set status=? where id=?", (status.upper(), workflow_id))
    con.commit()
    con.close()


class TestAccess:
    @pytest.mark.parametrize("path", [TRACKER, TRACKER + "/1"])
    def test_needs_a_sign_in(self, http, path):
        assert http.get(path).status_code == 401

    def test_page_and_assets_are_served(self, http):
        page = http.get("/workflow-tracker")
        assert page.status_code == 200 and "Workflow Tracker" in page.text
        assert page.headers["cache-control"] == "no-store"
        assert "/static/js/portal.js" in page.text  # the page signs you in like every other page
        assert http.get("/static/js/tracker.js").status_code == 200
        assert http.get("/static/css/tracker.css").status_code == 200

    def test_dashboard_links_to_the_tracker(self, http):
        assert "/workflow-tracker" in http.get("/dashboard").text

    def test_nobody_else_sees_your_workflows(self, http, admin_headers):
        _, mine, _ = account(http)
        _, theirs, _ = account(http)
        workflow_id = make_workflow(http, mine, "private flow")

        assert workflow_id in [w["id"] for w in http.get(TRACKER, headers=mine).json()["workflows"]]
        assert workflow_id not in [w["id"] for w in http.get(TRACKER, headers=theirs).json()["workflows"]]
        assert http.get(f"{TRACKER}/{workflow_id}", headers=theirs).status_code == 404
        assert http.get(f"{TRACKER}/{workflow_id}", headers=mine).status_code == 200
        # the admin sees everything
        assert workflow_id in [w["id"] for w in http.get(TRACKER, headers=admin_headers).json()["workflows"]]
        assert http.get(f"{TRACKER}/{workflow_id}", headers=admin_headers).status_code == 200

    def test_a_guest_sees_only_their_own(self, http):
        guest_headers, _ = guest(http)
        _, other, _ = account(http)
        make_workflow(http, other, "not the guest's")
        assert http.get(TRACKER, headers=guest_headers).json() == {"total": 0, "limit": 50, "offset": 0, "workflows": []}

    def test_unknown_workflow_is_a_404(self, http):
        _, headers, _ = account(http)
        assert http.get(f"{TRACKER}/999999", headers=headers).status_code == 404


class TestList:
    def test_new_workflow_is_pending_with_zero_progress(self, http):
        _, headers, _ = account(http)
        workflow_id = make_workflow(http, headers, "fresh")
        (row,) = http.get(TRACKER, headers=headers).json()["workflows"]
        assert row["id"] == workflow_id and row["name"] == "fresh" and row["status"] == "pending"
        assert row["progress"] == {"total": 3, "completed": 0, "failed": 0, "running": 0, "pending": 3, "percentage": 0.0}
        assert row["current_step"] is None
        assert row["timeline"]["created_at"].endswith("Z")

    def test_newest_first(self, http):
        _, headers, _ = account(http)
        first = make_workflow(http, headers, "first")
        second = make_workflow(http, headers, "second")
        assert [w["id"] for w in http.get(TRACKER, headers=headers).json()["workflows"]] == [second, first]

    def test_status_filter_and_validation(self, http, server):
        _, headers, _ = account(http)
        done = make_workflow(http, headers, "done one")
        waiting = make_workflow(http, headers, "waiting one")
        set_status(server, done, "completed")

        ids = lambda status: [w["id"] for w in http.get(TRACKER, params={"status": status}, headers=headers).json()["workflows"]]
        assert ids("completed") == [done]
        assert ids("pending") == [waiting]
        assert ids("failed") == []
        assert http.get(TRACKER, params={"status": "nonsense"}, headers=headers).status_code == 400

    @pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}])
    def test_paging_is_bounded(self, http, params):
        _, headers, _ = account(http)
        assert http.get(TRACKER, params=params, headers=headers).status_code == 422

    def test_paging_works(self, http):
        _, headers, _ = account(http)
        ids = [make_workflow(http, headers, f"w{i}") for i in range(3)]
        page = http.get(TRACKER, params={"limit": 2, "offset": 1}, headers=headers).json()
        assert page["total"] == 3 and [w["id"] for w in page["workflows"]] == [ids[1], ids[0]]


class TestDetail:
    def test_steps_before_anything_ran(self, http):
        _, headers, _ = account(http)
        detail = http.get(f"{TRACKER}/{make_workflow(http, headers)}", headers=headers).json()
        assert [s["name"] for s in detail["steps"]] == ["Research it", "Code it", "Plan it"]
        assert [s["number"] for s in detail["steps"]] == [1, 2, 3]
        assert [s["status"] for s in detail["steps"]] == ["pending"] * 3
        assert detail["steps"][1]["depends_on"] == [{"step_id": "step_1", "name": "Research it"}]
        assert detail["steps"][0]["task"] is None and detail["steps"][0]["output"]["text"] is None
        assert detail["steps"][0]["description"] == "What is X?"

    def test_every_kind_of_result_is_readable(self, http, server):
        _, headers, _ = account(http)
        agent = make_agent(server, "Coder Agent")
        workflow_id = make_workflow(http, headers)
        finish_steps(http, server, headers, workflow_id, agent, {
            "step_1": ("completed", {"summary": "X is a thing.", "findings": [], "tokens_used": 12, "cost": 0.0}, None),
            "step_2": ("completed", {"language": "python", "code": "def x(): ...", "explanation": "Defines x."}, None),
            "step_3": ("completed", {"goal": "g", "tasks": [], "full_plan": "Task 1: do it", "plan_type": "task_breakdown"}, None),
        })
        steps = http.get(f"{TRACKER}/{workflow_id}", headers=headers).json()["steps"]

        assert steps[0]["output"]["text"] == "X is a thing." and steps[0]["output"]["metrics"] == {"tokens_used": 12, "cost": 0.0}
        assert steps[1]["output"]["code"] == "def x(): ..." and steps[1]["output"]["language"] == "python"
        assert steps[1]["output"]["explanation"] == "Defines x." and steps[1]["output"]["text"] is None
        assert steps[2]["output"]["text"] == "Task 1: do it"
        # who ran it and for how long (the task row says 10:00:00 to 10:00:07)
        assert steps[0]["task"]["agent_name"] == "Coder Agent" and steps[0]["task"]["agent_id"] == agent
        assert steps[0]["task"]["duration_seconds"] == 7.0
        assert steps[0]["task"]["started_at"] == "2026-01-01T10:00:00Z"
        assert all(s["output"]["raw"] is not None for s in steps)

    def test_progress_failure_and_error_text(self, http, server):
        _, headers, _ = account(http)
        agent = make_agent(server, "Some Agent")
        workflow_id = make_workflow(http, headers)
        finish_steps(http, server, headers, workflow_id, agent, {
            "step_1": ("completed", {"summary": "ok"}, None),
            "step_2": ("failed", None, "model not found"),
        })
        detail = http.get(f"{TRACKER}/{workflow_id}", headers=headers).json()
        assert detail["progress"] == {"total": 3, "completed": 1, "failed": 1, "running": 0, "pending": 1, "percentage": 33.3}
        assert detail["steps"][1]["status"] == "failed" and detail["steps"][1]["error"] == "model not found"
        assert detail["steps"][2]["status"] == "pending" and detail["steps"][2]["task"] is None
        # the list shows the same progress
        row = next(w for w in http.get(TRACKER, headers=headers).json()["workflows"] if w["id"] == workflow_id)
        assert row["progress"] == detail["progress"]

    def test_a_running_step_is_the_current_step(self, http, server):
        _, headers, _ = account(http)
        agent = make_agent(server, "Runner")
        workflow_id = make_workflow(http, headers)
        finish_steps(http, server, headers, workflow_id, agent, {
            "step_1": ("completed", {"summary": "ok"}, None), "step_2": ("running", None, None)})
        set_status(server, workflow_id, "running")
        row = http.get(TRACKER, headers=headers).json()["workflows"][0]
        assert row["status"] == "running" and row["current_step"] == "Code it"
        assert row["progress"]["running"] == 1

    def test_text_from_a_model_comes_back_as_data_not_markup(self, http, server):
        _, headers, _ = account(http)
        agent = make_agent(server, "Writer")
        workflow_id = make_workflow(http, headers, "<img src=x onerror=alert(1)>")
        finish_steps(http, server, headers, workflow_id, agent, {"step_1": ("completed", {"content": "<script>alert(1)</script>"}, None)})
        response = http.get(f"{TRACKER}/{workflow_id}", headers=headers)
        assert response.headers["content-type"].startswith("application/json")
        assert response.json()["steps"][0]["output"]["text"] == "<script>alert(1)</script>"


def test_page_script_never_writes_model_text_as_html():
    """Step results are written by a language model: the page must only ever set them as text"""
    source = (ROOT / "static" / "js" / "tracker.js").read_text()
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
        assert forbidden not in source, forbidden
