import sys

import pytest

import assistant
from conftest import FakeEmbedding, FakeLLM
from rag_engine import RAGEngine
from vector_store import VectorStore


@pytest.fixture
def cli(monkeypatch, capsys, tmp_path):
    db = str(tmp_path / "db")
    llm = FakeLLM()

    def factory(chunk_size=500, chunk_overlap=50, neighbors=2):
        return RAGEngine(chunk_size=chunk_size, chunk_overlap=chunk_overlap, neighbors=neighbors,
                         vector_store=VectorStore("tests", db), embedding_service=FakeEmbedding(), llm_client=llm)

    monkeypatch.setattr(assistant, "RAGEngine", factory)
    monkeypatch.setattr(assistant, "setup_environment", lambda: None)

    def run(*argv, tty=False):
        monkeypatch.setattr(sys, "argv", ["assistant.py", *argv])
        monkeypatch.setattr(sys.stdout, "isatty", lambda: tty, raising=False)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
        code = 0
        try:
            assistant.main()
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        c = capsys.readouterr()
        return code, c.out, c.err

    run.llm = llm
    return run


def test_add_summary_and_exit_codes(cli, make_file):
    good = make_file("a.txt", "Alpha content here.")
    code, out, err = cli("add", str(good))
    assert code == 0 and "Indexed 1 file(s), 1 chunks (1 new" in out
    code, out, err = cli("add", str(good))
    assert code == 0 and "1 unchanged" in out


def test_add_with_failures_exits_nonzero_but_indexes_the_rest(cli, make_file, tmp_path):
    good, empty = make_file("a.txt", "Alpha content here."), make_file("e.txt", "")
    code, out, err = cli("add", str(good), str(empty), str(tmp_path / "missing.txt"))
    assert code == 1 and "2 file(s) failed" in err and "no extractable text" in err
    assert "Indexed 1" in err
    assert cli("stats")[1].count("a.txt") == 1


def test_stats_lists_documents(cli, make_file):
    cli("add", str(make_file("a.txt", "Alpha.")), str(make_file("b.txt", "Beta.")))
    code, out, _ = cli("stats")
    assert code == 0 and "Documents: 2" in out and "Chunks: 2" in out and "a.txt (1 chunks)" in out


def test_piped_query_prints_only_the_answer(cli, make_file):
    cli("add", str(make_file("a.txt", "Bananas are yellow fruit.")))
    code, out, err = cli("query", "what", "color", "are", "bananas")
    assert code == 0 and out == "stub answer [1]\n"


def test_tty_query_shows_frame_and_sources(cli, make_file):
    cli("add", str(make_file("a.txt", "Bananas are yellow fruit.")))
    code, out, err = cli("query", "bananas", tty=True)
    assert "Answer:" in out and "Sources:" in out and "a.txt" in out and "keyword match" in out
    assert "stub answer" in cli("query", "bananas", "--plain", tty=True)[1]
    assert "Sources:" not in cli("query", "bananas", "--plain", tty=True)[1]


def test_query_on_empty_kb_is_an_error(cli):
    code, out, err = cli("query", "anything")
    assert code == 1 and "knowledge base is empty" in err


@pytest.mark.parametrize("argv,message", [
    (["query", "x", "--top-k", "0"], "--top-k"),
    (["query", "x", "--temperature", "9"], "--temperature"),
    (["query", "x", "--temperature", "-1"], "--temperature"),
    (["add"], "No files"),
    (["remove"], "No files"),
    (["query", "  "], "No query"),
    (["add", "x.txt", "--chunk-size", "100", "--chunk-overlap", "200"], "overlap"),
    (["add", "x.txt", "--chunk-size", "0"], "chunk size"),
])
def test_argument_validation(cli, argv, message):
    code, out, err = cli(*argv)
    assert code == 1 and message in err and "Traceback" not in err


def test_remove(cli, make_file):
    f = make_file("a.txt", "Alpha.")
    cli("add", str(f))
    assert cli("remove", str(f))[0] == 0
    code, out, err = cli("remove", str(f))
    assert code == 1 and "Not in the knowledge base" in err


def test_clear_requires_confirmation_when_not_interactive(cli, make_file):
    cli("add", str(make_file("a.txt", "Alpha.")))
    code, out, err = cli("clear")
    assert code == 1 and "--yes" in err and "Chunks: 1" in cli("stats")[1]
    code, out, err = cli("clear", "--yes")
    assert code == 0 and "Chunks: 0" in cli("stats")[1]


def test_truncation_warning(cli, make_file):
    cli("add", str(make_file("a.txt", "Bananas are yellow.")))
    cli.llm.truncated = True
    assert "cut off" in cli("query", "bananas")[2]


def test_llm_errors_are_clean(cli, make_file, monkeypatch):
    from llm_client import GenerationError
    cli("add", str(make_file("a.txt", "Bananas are yellow.")))
    monkeypatch.setattr(cli.llm, "generate", lambda *a, **k: (_ for _ in ()).throw(GenerationError("Cannot reach Ollama")))
    code, out, err = cli("query", "bananas")
    assert code == 1 and "Cannot reach Ollama" in err and "Traceback" not in err


def test_tty_sources_label_adjacent_context(cli, make_file):
    cli("add", str(make_file("a.txt", "Alpha paragraph one. " * 30)), "--chunk-size", "100", "--chunk-overlap", "10")
    code, out, err = cli("query", "alpha", "--top-k", "1", tty=True)
    assert "adjacent context" in out and "similarity:" in out


def test_negative_neighbors_rejected(cli):
    code, out, err = cli("query", "x", "--neighbors", "-1")
    assert code == 1 and "--neighbors" in err
