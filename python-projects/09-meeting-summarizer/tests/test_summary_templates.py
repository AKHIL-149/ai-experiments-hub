import json

import pytest

from utils.summary_templates import SummaryTemplateManager

BUILT_IN = ["executive", "detailed", "brief", "meeting_minutes", "technical"]


def result(**changes):
    base = {
        "metadata": {"audio_file": "a.mp3", "source_file": "standup.mp3", "duration_seconds": 90, "format": "mp3"},
        "transcript": {"language": "en"},
        "summary": {"text": "Summary text.", "level": "standard"},
        "actions": {
            "action_items": [{"description": 'Say "hi" to <Bob>', "assignee": "Bob", "priority": "high", "due_date": "Fri", "category": "c", "status": "pending"}],
            "decisions": [{"decision": "Ship", "context": "c", "impact": "i"}],
            "follow_ups": ["Check"],
        },
        "topics": ['A "quoted" topic'],
        "statistics": {"processing_time_seconds": 1.5, "total_cost_usd": 0.0, "cache_hits": 1, "transcription_backend": "whisper-cpp", "llm_provider": "ollama", "llm_model": "llama3.2"},
    }
    base.update(changes)
    return base


@pytest.fixture
def manager():
    return SummaryTemplateManager()


@pytest.mark.parametrize("name", BUILT_IN)
def test_every_built_in_template_renders(manager, name):
    out = manager.render_summary(name, result())
    assert "Summary text." in out and "Template rendering failed" not in out


@pytest.mark.parametrize("name", BUILT_IN)
def test_steps_that_were_switched_off(manager, name):
    # actions / topics are None (not absent): this used to raise AttributeError and fail the job
    out = manager.render_summary(name, result(actions=None, topics=None))
    assert "Summary text." in out


@pytest.mark.parametrize("name", BUILT_IN)
def test_a_result_with_nothing_at_all(manager, name):
    assert manager.render_summary(name, {"summary": None, "actions": None, "topics": None, "metadata": None, "statistics": None, "transcript": None})


def test_filename_prefers_the_uploaded_name(manager):
    assert "standup.mp3" in manager.render_summary("brief", result())


def test_technical_template_produces_valid_json_whatever_the_text(manager):
    out = manager.render_summary("technical", result())
    block = out[out.index("```json") + 7: out.index("```", out.index("```json") + 7)]
    data = json.loads(block)
    assert data["items"][0]["description"] == 'Say "hi" to <Bob>' and data["total"] == 1


def test_technical_template_topics_are_a_valid_python_list(manager):
    import ast
    out = manager.render_summary("technical", result(topics=['A "quoted" topic', "it's <b>bold</b>", "plain"]))
    block = out[out.index("```python") + 9: out.index("```", out.index("```python") + 9)]
    assert ast.literal_eval(block.split("=", 1)[1].strip()) == ['A "quoted" topic', "it's <b>bold</b>", "plain"]


def test_unknown_template_falls_back_to_detailed(manager):
    assert "Meeting Information" in manager.render_summary("does-not-exist", result())


def test_a_broken_template_falls_back_to_a_plain_summary(tmp_path):
    (tmp_path / "broken.md").write_text("{% for x in %}")
    out = SummaryTemplateManager(custom_templates_dir=str(tmp_path)).render_summary("broken", result())
    assert "# Meeting Summary" in out and "Summary text." in out


def test_custom_templates_are_listed_and_used(tmp_path):
    (tmp_path / "standup.md").write_text("STANDUP: {{summary}}")
    manager = SummaryTemplateManager(custom_templates_dir=str(tmp_path))
    assert "standup" in manager.list_available_templates()
    assert manager.render_summary("standup", result()) == "STANDUP: Summary text."


def test_a_custom_template_cannot_reach_outside_its_directory(tmp_path):
    (tmp_path / "secret.txt").write_text("SECRET")
    inner = tmp_path / "templates"; inner.mkdir()
    (tmp_path / "outside.md").write_text("OUTSIDE")
    out = SummaryTemplateManager(custom_templates_dir=str(inner)).render_summary("../outside", result())
    assert "OUTSIDE" not in out


def test_save_custom_template(tmp_path):
    manager = SummaryTemplateManager(custom_templates_dir=str(tmp_path / "t"))
    manager.save_custom_template("mine", "MINE {{filename}}")
    assert manager.render_summary("mine", result()) == "MINE standup.mp3"


def test_all_built_ins_are_listed(manager):
    assert set(BUILT_IN) <= set(manager.list_available_templates())
