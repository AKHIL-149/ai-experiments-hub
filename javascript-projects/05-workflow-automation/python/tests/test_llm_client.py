"""Run from the project root: python3 -m pytest python/tests -q"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import llm_client
from llm_client import LLMClient, context_window_for
from agent import WorkflowAgent


class FakeResponse:
    status_code = 200

    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


@pytest.fixture
def client(monkeypatch):
    c = LLMClient("ollama", "test-model")
    c.sent = []
    c.done_reason = "stop"

    def fake_post(url, json=None, timeout=None):
        c.sent.append({"payload": json, "timeout": timeout})
        return FakeResponse({"response": "text", "done_reason": c.done_reason})

    monkeypatch.setattr(llm_client.requests, "post", fake_post)
    return c


def test_context_window_fits_prompt_plus_reply_in_1024_steps():
    assert context_window_for("short", 100) == 4096                      # never below the minimum
    assert context_window_for("x" * 30000, 4096) % 1024 == 0
    assert context_window_for("x" * 30000, 4096) >= 30000 // 3 + 4096    # prompt and reply both fit
    assert context_window_for("x" * 10_000_000, 4096) == llm_client.MAX_CONTEXT  # capped


def test_ollama_request_carries_context_and_reply_limits(client):
    client.generate("x" * 12000, max_tokens=2000)
    options = client.sent[0]["payload"]["options"]
    assert options["num_predict"] == 2000
    assert options["num_ctx"] >= 12000 // 3 + 2000


def test_default_reply_limit_is_not_the_old_1000(client):
    client.generate("hi")
    assert client.sent[0]["payload"]["options"]["num_predict"] == llm_client.DEFAULT_MAX_TOKENS >= 4096


def test_truncated_flag_follows_done_reason_and_resets(client):
    client.done_reason = "length"
    client.generate("hi")
    assert client.truncated is True
    client.done_reason = "stop"
    client.generate("hi")
    assert client.truncated is False


def test_request_timeout_is_configurable(client, monkeypatch):
    monkeypatch.setenv("OLLAMA_TIMEOUT", "17")
    client.generate("hi")
    assert client.sent[0]["timeout"] == 17


@pytest.mark.parametrize("value", [0, -5, 40000, 2.5, "100", True])
def test_bad_task_max_tokens_is_rejected(value):
    with pytest.raises(ValueError, match="max_tokens"):
        WorkflowAgent._task_max_tokens({"max_tokens": value})


def test_task_max_tokens_accepts_valid_or_missing():
    assert WorkflowAgent._task_max_tokens({}) is None
    assert WorkflowAgent._task_max_tokens({"max_tokens": 1}) == 1
    assert WorkflowAgent._task_max_tokens({"max_tokens": 32768}) == 32768


def test_agent_reports_truncation_and_the_limit_it_used(monkeypatch):
    agent = WorkflowAgent.__new__(WorkflowAgent)
    agent.tools_used, agent.execution_steps = [], []
    agent.llm_client = type("L", (), {"truncated": True, "generate": lambda self, p, **k: "cut"})()
    result = agent.execute({"instruction": "write", "use_tools": False, "max_tokens": 50})
    assert result["success"] and result["truncated"] is True and result["max_tokens"] == 50


def test_agent_returns_an_error_result_for_a_bad_limit():
    agent = WorkflowAgent.__new__(WorkflowAgent)
    agent.tools_used, agent.execution_steps = [], []
    agent.llm_client = None
    result = agent.execute({"instruction": "x", "use_tools": False, "max_tokens": 0})
    assert result["success"] is False and "max_tokens" in result["error"]
