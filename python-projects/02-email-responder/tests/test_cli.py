import io
import sys

import pytest

import responder
from llm_client import GenerationError


class Stub:
    last = None
    reply = "Hi Sarah,\n\nSounds good.\n\nBest,\nBob"
    truncated = False
    error = None

    def __init__(self, model=None):
        self.model = model or "stub"
        self.truncated = Stub.truncated
        self.calls = []
        Stub.last = self

    def generate(self, prompt, temperature, max_tokens):
        self.calls.append((prompt, temperature, max_tokens))
        if Stub.error:
            raise Stub.error
        return Stub.reply


@pytest.fixture
def cli(monkeypatch, capsys):
    Stub.reply, Stub.truncated, Stub.error = "Hi Sarah,\n\nSounds good.\n\nBest,\nBob", False, None
    monkeypatch.setattr(responder, "OllamaClient", Stub)
    monkeypatch.setattr(responder, "setup_environment", lambda: None)

    def run(*argv, stdin=None):
        monkeypatch.setattr(sys, "argv", ["respond.py", *argv])
        if stdin is not None:
            monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(stdin)))
        code = 0
        try:
            responder.main()
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        c = capsys.readouterr()
        return code, c.out, c.err

    return run


def test_basic_reply_piped_is_plain(cli):
    code, out, err = cli("Can we meet?")
    assert code == 0 and out == "Hi Sarah,\n\nSounds good.\n\nBest,\nBob\n"


def test_tty_output_is_framed(cli, monkeypatch):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    assert "=" * 70 in cli("Can we meet?")[1]
    assert "=" * 70 not in cli("--plain", "Can we meet?")[1]


def test_defaults_passed_to_model(cli):
    cli("Can we meet?")
    prompt, temp, max_tokens = Stub.last.calls[0]
    assert (temp, max_tokens) == (0.7, 1000) and "Can we meet?" in prompt


def test_flags_passed(cli):
    cli("-t", "decline", "-i", "next week", "-n", "Akhil", "--temperature", "0.2", "--max-tokens", "55", "-m", "mm", "Join us?")
    prompt, temp, mt = Stub.last.calls[0]
    assert (temp, mt, Stub.last.model) == (0.2, 55, "mm")
    assert "next week" in prompt and "Sign off with the name Akhil" in prompt and "declining" in prompt


@pytest.mark.parametrize("body", ["", "   ", "\n\t "])
def test_empty_email_rejected(cli, body):
    Stub.last = None
    code, out, err = cli(body)
    assert code == 1 and "empty" in err and Stub.last is None


def test_no_input_rejected(cli):
    code, _, err = cli()
    assert code == 1 and "Provide email" in err


def test_empty_file_rejected(cli, tmp_path):
    f = tmp_path / "e.txt"
    f.write_text("  \n")
    code, _, err = cli("-f", str(f))
    assert code == 1 and "empty" in err


def test_file_input_and_warning_when_both(cli, tmp_path):
    f = tmp_path / "e.txt"
    f.write_text("Can we meet from file?")
    code, out, err = cli("-f", str(f), "ignored body")
    assert code == 0 and "using the file" in err
    assert "from file" in Stub.last.calls[0][0] and "ignored body" not in Stub.last.calls[0][0]


def test_stdin_input(cli):
    code, out, err = cli("-f", "-", stdin=b"Question from stdin?")
    assert code == 0 and "Question from stdin?" in Stub.last.calls[0][0]


def test_cp1252_file(cli, tmp_path):
    f = tmp_path / "o.txt"
    f.write_bytes("I don’t know, José".encode("cp1252"))
    assert cli("-f", str(f))[0] == 0 and "I don’t know, José" in Stub.last.calls[0][0]


def test_binary_and_missing_and_directory_files(cli, tmp_path):
    b = tmp_path / "b.bin"
    b.write_bytes(bytes(range(256)))
    assert cli("-f", str(b))[0] == 1
    code, _, err = cli("-f", str(tmp_path / "nope.txt"))
    assert code == 1 and "not found" in err.lower()
    code, _, err = cli("-f", str(tmp_path))
    assert code == 1 and "Traceback" not in err


def test_unknown_template(cli):
    code, _, err = cli("-t", "nope", "hi")
    assert code == 1 and "list-templates" in err


def test_template_case_insensitive(cli):
    assert cli("-t", "Follow-Up", "hi")[0] == 0


def test_list_templates(cli):
    code, out, _ = cli("--list-templates")
    assert code == 0 and out.count(" - ") == 8


@pytest.mark.parametrize("t", ["-1", "2.5", "99"])
def test_temperature_validated(cli, t):
    code, _, err = cli("--temperature", t, "hi")
    assert code == 1 and "temperature" in err


@pytest.mark.parametrize("n", ["0", "-3"])
def test_max_tokens_validated(cli, n):
    assert cli("--max-tokens", n, "hi")[0] == 1


def test_preamble_stripped_from_output(cli):
    Stub.reply = "Here is a potential email response:\n\nHi Bob,\n\nYes.\n\nBest,\nAl"
    code, out, _ = cli("hi")
    assert out == "Hi Bob,\n\nYes.\n\nBest,\nAl\n"


def test_truncation_warning(cli):
    Stub.truncated = True
    code, out, err = cli("--max-tokens", "9", "hi")
    assert code == 0 and "cut off" in err and "9" in err


def test_empty_reply_is_error_with_thinking_hint(cli):
    Stub.reply, Stub.truncated = "", True
    code, _, err = cli("hi")
    assert code == 1 and "reasoning" in err


def test_backend_error_clean(cli):
    Stub.error = GenerationError("Cannot reach Ollama at x")
    code, out, err = cli("hi")
    assert code == 1 and "Cannot reach Ollama" in err and "Traceback" not in err


def test_output_file(cli, tmp_path):
    t = tmp_path / "a" / "b" / "reply.txt"
    code, out, err = cli("hi", "-o", str(t))
    assert code == 0 and out == "" and t.read_text() == "Hi Sarah,\n\nSounds good.\n\nBest,\nBob\n"


def test_keyboard_interrupt(cli, monkeypatch):
    monkeypatch.setattr(Stub, "generate", lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()))
    code, _, err = cli("hi")
    assert code == 1 and "cancelled" in err.lower()
