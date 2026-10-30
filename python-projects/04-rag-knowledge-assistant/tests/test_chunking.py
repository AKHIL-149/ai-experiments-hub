import signal

import pytest

from document_processor import DocumentProcessor, decode_text_bytes

LOREM = (
    "Alpha sentence one is here. Beta sentence two follows right after it. "
    "Gamma sentence three is a bit longer than the others, to vary lengths. "
    "Delta four. Epsilon five has the number 3.14159 inside it. Zeta six ends here.\n\n"
) * 12


@pytest.fixture(autouse=True)
def no_hangs():
    """Fail instead of hanging forever if a chunking loop never ends."""
    def boom(*a):
        raise TimeoutError("chunking did not terminate")
    signal.signal(signal.SIGALRM, boom)
    signal.alarm(10)
    yield
    signal.alarm(0)


@pytest.mark.parametrize("size,overlap", [(500, 50), (100, 20), (80, 0), (200, 199), (37, 5)])
def test_chunks_terminate_nonempty_and_bounded(size, overlap):
    chunks = DocumentProcessor(size, overlap)._chunk_text(LOREM)
    assert chunks and all(c.strip() for c in chunks)
    assert all(len(c) <= size for c in chunks)


@pytest.mark.parametrize("size,overlap", [(100, 20), (200, 40), (500, 50)])
def test_every_word_of_the_text_is_covered(size, overlap):
    chunks = DocumentProcessor(size, overlap)._chunk_text(LOREM)
    joined = " ".join(chunks)
    for word in set(LOREM.split()):
        assert word in joined


@pytest.mark.parametrize("size,overlap", [(0, 0), (-5, 0), (100, 100), (100, 150), (100, -1)])
def test_invalid_sizes_rejected_instead_of_hanging(size, overlap):
    with pytest.raises(ValueError):
        DocumentProcessor(size, overlap)


@pytest.mark.parametrize("text", ["", "   ", "\n\n \t\n", None])
def test_blank_text_gives_no_chunks(text):
    assert DocumentProcessor()._chunk_text(text) == []


def test_short_text_is_one_chunk():
    assert DocumentProcessor(500, 50)._chunk_text("  hello world  ") == ["hello world"]


def test_never_splits_inside_a_number():
    text = "The value of pi is 3.14159 and e is 2.71828 which are constants. " * 6
    for chunk in DocumentProcessor(60, 10)._chunk_text(text):
        assert not chunk.endswith(("3.", "2.", "3.14159 and e is 2."))


def test_prefers_paragraph_then_sentence_breaks():
    chunks = DocumentProcessor(200, 20)._chunk_text(LOREM)
    assert sum(c.rstrip().endswith((".", "!", "?")) for c in chunks) >= len(chunks) - 1


def test_breaks_at_words_when_no_punctuation():
    chunks = DocumentProcessor(50, 10)._chunk_text("word " * 100)
    assert all(c.endswith("word") for c in chunks)


def test_no_whitespace_text_still_terminates():
    assert len(DocumentProcessor(100, 10)._chunk_text("x" * 1000)) > 5


# ---- loading files
def test_txt_and_md_load(make_file):
    for name in ("a.txt", "b.md"):
        docs = DocumentProcessor().load_file(str(make_file(name, "Some real content.")))
        assert docs[0].content == "Some real content." and docs[0].metadata["chunk_index"] == 0


@pytest.mark.parametrize("content", ["", "   \n\n"])
def test_empty_files_rejected(make_file, content):
    with pytest.raises(ValueError, match="no extractable text"):
        DocumentProcessor().load_file(str(make_file("e.txt", content)))


def test_cp1252_file_decodes(make_file):
    text = "I don’t think “Müller” costs 5 €"
    docs = DocumentProcessor().load_file(str(make_file("o.txt", text, "cp1252")))
    assert docs[0].content == text


def test_utf8_bom_removed(make_file):
    docs = DocumentProcessor().load_file(str(make_file("b.txt", "Hello", "utf-8-sig")))
    assert docs[0].content == "Hello"


def test_binary_and_unsupported_and_missing_and_directory(make_file, tmp_path):
    p = DocumentProcessor()
    with pytest.raises(ValueError, match="binary"):
        decode_text_bytes(bytes(range(256)))
    with pytest.raises(ValueError, match="Unsupported file type: .json"):
        p.load_file(str(make_file("d.json", "{}")))
    with pytest.raises(FileNotFoundError):
        p.load_file(str(tmp_path / "nope.txt"))
    with pytest.raises(ValueError, match="directory"):
        p.load_file(str(tmp_path))


def test_pdf_pages_and_metadata(make_pdf):
    docs = DocumentProcessor().load_file(str(make_pdf("f.pdf", ["First page text.", "Second page text."])))
    assert [(d.metadata["page"], d.content) for d in docs] == [(1, "First page text."), (2, "Second page text.")]
    assert all(d.metadata["type"] == "pdf" for d in docs)


def test_pdf_blank_pages_skipped(make_pdf):
    docs = DocumentProcessor().load_file(str(make_pdf("m.pdf", ["Real text.", ""])))
    assert [d.metadata["page"] for d in docs] == [1]


def test_pdf_without_text_rejected(make_pdf):
    with pytest.raises(ValueError, match="OCR"):
        DocumentProcessor().load_file(str(make_pdf("b.pdf", ["", ""])))
