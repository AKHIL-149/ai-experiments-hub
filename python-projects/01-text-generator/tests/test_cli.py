import sys
from pathlib import Path

import pytest

import generator
from llm_client import GenerationError


class StubClient:
    """Stands in for LLMClient inside generator.main."""

    last = None

    def __init__(self, backend="ollama", model=None):
        self.backend, self.model = backend, model or "stub-model"
        self.truncated = False
        self.reply = "generated text"
        self.calls = []
        StubClient.last = self

    def generate(self, prompt, max_tokens, temperature):
        self.calls.append((prompt, max_tokens, temperature))
        if self.reply is Exception:
            raise GenerationError("backend exploded")
        return self.reply


@pytest.fixture
def cli(monkeypatch, capsys):
    monkeypatch.setattr(generator, "LLMClient", StubClient)
    monkeypatch.setattr(generator, "setup_environment", lambda: None)

    def run(*argv):
        monkeypatch.setattr(sys, "argv", ["generate.py", *argv])
        code = 0
        try:
            generator.main()
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return run


def test_tty_output_is_decorated(cli, monkeypatch):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    code, out, err = cli("hello")
    assert code == 0 and "=" * 70 in out and "generated text" in out


def test_piped_output_is_just_the_text(cli):
    # capsys replaces stdout with a non-tty, like a pipe
    code, out, err = cli("hello")
    assert code == 0 and out == "generated text\n"


def test_plain_flag_forces_plain_output(cli, monkeypatch):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    code, out, err = cli("--plain", "hello")
    assert out == "generated text\n"


def test_plain_prompt_prints_result(cli):
    code, out, err = cli("hello")
    assert code == 0
    assert "generated text" in out
    assert "stub-model" in err
    assert StubClient.last.calls == [("hello", 1000, 0.7)]


def test_template_applied_to_prompt(cli):
    cli("--template", "email", "thank the team")
    prompt = StubClient.last.calls[0][0]
    assert "thank the team" in prompt and "professional email" in prompt.lower()


def test_flags_passed_through(cli):
    cli("--max-tokens", "77", "--temperature", "0.25", "--backend", "openai", "--model", "m", "x")
    assert StubClient.last.calls == [("x", 77, 0.25)]
    assert (StubClient.last.backend, StubClient.last.model) == ("openai", "m")


@pytest.mark.parametrize("prompt", ["", "   ", "\n\t"])
def test_empty_prompt_rejected(cli, prompt):
    code, out, err = cli(prompt)
    assert code == 1 and "empty" in err and out == ""


@pytest.mark.parametrize("temp", ["-0.1", "2.1"])
def test_temperature_bounds(cli, temp):
    code, _, err = cli("--temperature", temp, "hi")
    assert code == 1 and "temperature" in err


def test_anthropic_temperature_cap(cli):
    code, _, err = cli("--backend", "anthropic", "--temperature", "1.5", "hi")
    assert code == 1 and "Anthropic" in err
    assert cli("--backend", "anthropic", "--temperature", "1.0", "hi")[0] == 0


@pytest.mark.parametrize("n", ["0", "-5"])
def test_max_tokens_must_be_positive(cli, n):
    code, _, err = cli("--max-tokens", n, "hi")
    assert code == 1 and "max-tokens" in err


def test_truncation_warning(cli, monkeypatch):
    orig = StubClient.__init__

    def init(self, *a, **k):
        orig(self, *a, **k)
        self.truncated = True

    monkeypatch.setattr(StubClient, "__init__", init)
    code, out, err = cli("--max-tokens", "12", "hi")
    assert code == 0 and "cut off" in err and "12" in err


def test_empty_model_response_is_an_error(cli, monkeypatch):
    orig = StubClient.__init__

    def init(self, *a, **k):
        orig(self, *a, **k)
        self.reply = "  \n"

    monkeypatch.setattr(StubClient, "__init__", init)
    code, out, err = cli("hi")
    assert code == 1 and "empty response" in err


def test_empty_truncated_response_explains_thinking_models(cli, monkeypatch):
    orig = StubClient.__init__

    def init(self, *a, **k):
        orig(self, *a, **k)
        self.reply, self.truncated = "", True

    monkeypatch.setattr(StubClient, "__init__", init)
    code, out, err = cli("hi")
    assert code == 1 and "reasoning" in err and "--max-tokens" in err


def test_backend_error_message_and_exit_code(cli, monkeypatch):
    orig = StubClient.__init__

    def init(self, *a, **k):
        orig(self, *a, **k)
        self.reply = Exception

    monkeypatch.setattr(StubClient, "__init__", init)
    code, out, err = cli("hi")
    assert code == 1 and "backend exploded" in err and "Traceback" not in err


def test_output_file_created_with_parents_and_newline(cli, tmp_path):
    target = tmp_path / "deep" / "nested" / "out.txt"
    code, out, err = cli("hi", "-o", str(target))
    assert code == 0
    assert target.read_text() == "generated text\n"
    assert out == ""
    assert "saved" in err


def test_output_file_overwrites(cli, tmp_path):
    target = tmp_path / "out.txt"
    target.write_text("OLD")
    cli("hi", "-o", str(target))
    assert target.read_text() == "generated text\n"


def test_keyboard_interrupt_exit_code(cli, monkeypatch):
    def interrupt(self, *a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(StubClient, "generate", interrupt)
    code, _, err = cli("hi")
    assert code == 1 and "cancelled" in err.lower()


def test_unknown_template_and_backend_are_usage_errors(cli):
    assert cli("--template", "nope", "hi")[0] == 2
    assert cli("--backend", "bard", "hi")[0] == 2


def test_setup_environment_loads_project_env(tmp_path, monkeypatch):
    monkeypatch.undo()  # use the real setup_environment
    import importlib
    gen = importlib.reload(generator)
    loaded = []
    monkeypatch.setattr(gen, "load_dotenv", lambda p: loaded.append(Path(p)))
    gen.setup_environment()
    # must look at the project's own .env when present, else repo-root .env
    project_env = Path(gen.__file__).resolve().parent.parent / ".env"
    root_env = project_env.parent.parent.parent / ".env"
    assert all(p in (project_env, root_env) for p in loaded)
