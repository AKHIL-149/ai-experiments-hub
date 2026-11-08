"""Unit tests for the workflow tracker's result reader and progress maths (no server, no database)."""

from datetime import datetime

import pytest

from src.models.workflow import WorkflowStatus
from src.services import workflow_tracker as tracker
from src.services.workflow_tracker import (
    iso, plain, seconds_between, step_counts, summarize_output,
)


class TestSummarizeOutput:
    def test_research_answer_is_its_summary(self):
        out = summarize_output({"topic": "t", "findings": [{"title": "Overview", "content": ""}], "summary": "The answer.", "tokens_used": 9})
        assert out["text"] == "The answer."
        assert out["code"] is None and out["metrics"] == {"tokens_used": 9}

    def test_writer_answer_is_its_content(self):
        out = summarize_output({"content": "Dear reader", "sections": [], "word_count": 2, "cost": 0.0})
        assert out["text"] == "Dear reader" and out["metrics"] == {"word_count": 2, "cost": 0.0}

    def test_code_answer_keeps_code_and_explanation_apart(self):
        out = summarize_output({"language": "python", "code": "print(1)", "explanation": "Prints one."})
        assert out["code"] == "print(1)" and out["language"] == "python"
        assert out["explanation"] == "Prints one."
        assert out["text"] is None  # the explanation is shown under the code, not twice

    def test_planner_answer_is_its_full_plan(self):
        # the planner returns {goal, plan_type, tasks, dependencies, full_plan}: without full_plan its step showed nothing
        out = summarize_output({"goal": "g", "plan_type": "task_breakdown", "tasks": [], "dependencies": [], "full_plan": "Task 1: ..."})
        assert out["text"] == "Task 1: ..."

    def test_blank_strings_are_not_an_answer(self):
        out = summarize_output({"summary": "   ", "content": "", "code": "  ", "explanation": ""})
        assert out["text"] is None and out["code"] is None and out["explanation"] is None

    def test_first_known_key_wins(self):
        assert summarize_output({"content": "c", "summary": "s"})["text"] == "s"

    def test_no_output_and_odd_shapes(self):
        assert summarize_output(None)["text"] is None and summarize_output(None)["raw"] is None
        assert summarize_output("plain words")["text"] == "plain words"
        assert summarize_output(["a", "b"])["text"] == "['a', 'b']"
        assert summarize_output({})["text"] is None

    def test_non_numbers_are_not_metrics(self):
        assert summarize_output({"tokens_used": "lots", "cost": None, "word_count": 3})["metrics"] == {"word_count": 3}

    def test_raw_output_is_kept_whole(self):
        raw = {"summary": "s", "extra": {"a": 1}}
        assert summarize_output(raw)["raw"] == raw


class TestHelpers:
    @pytest.mark.parametrize("value, expected", [
        ("completed", "completed"), ("COMPLETED", "completed"), (WorkflowStatus.RUNNING, "running"), (None, ""),
    ])
    def test_plain(self, value, expected):
        assert plain(value) == expected

    def test_timestamps_are_marked_utc(self):
        assert iso(datetime(2026, 1, 2, 3, 4, 5)) == "2026-01-02T03:04:05Z"
        assert iso("2026-01-02T03:04:05.5") == "2026-01-02T03:04:05.5Z"
        assert iso("2026-01-02T03:04:05Z") == "2026-01-02T03:04:05Z"
        assert iso(None) is None

    def test_seconds_between(self):
        a, b = datetime(2026, 1, 1, 0, 0, 0), datetime(2026, 1, 1, 0, 1, 5, 500000)
        assert seconds_between(a, b) == 65.5
        assert seconds_between(a.isoformat() + "Z", b.isoformat()) == 65.5
        assert seconds_between(b, a) == 0.0  # never negative
        assert seconds_between(None, b) is None and seconds_between(a, None) is None
        assert seconds_between("garbage", b) is None


class TestStepCounts:
    STEPS = [{"step_id": f"s{i}"} for i in range(1, 5)]

    def test_counts_every_state(self):
        states = {"s1": {"status": "completed"}, "s2": {"status": "failed"}, "s3": {"status": "running"}}
        counts = step_counts(self.STEPS, states)
        assert counts == {"total": 4, "completed": 1, "failed": 1, "running": 1, "pending": 1, "percentage": 25.0}

    def test_ready_counts_as_running_and_unknown_as_pending(self):
        counts = step_counts(self.STEPS, {"s1": {"status": "ready"}, "s2": {"status": "skipped"}})
        assert counts["running"] == 1 and counts["pending"] == 3

    def test_no_steps_is_zero_percent(self):
        assert step_counts([], {})["percentage"] == 0.0

    def test_all_done_is_a_hundred(self):
        states = {s["step_id"]: {"status": "completed"} for s in self.STEPS}
        assert step_counts(self.STEPS, states)["percentage"] == 100.0


def test_readable_keys_are_unique_and_known():
    assert len(set(tracker.TEXT_KEYS)) == len(tracker.TEXT_KEYS)
    assert "full_plan" in tracker.TEXT_KEYS and "summary" in tracker.TEXT_KEYS and "content" in tracker.TEXT_KEYS
