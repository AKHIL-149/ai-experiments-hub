import re

import pytest

from src.services.chunker import chunk_text

SENT = "Sentence number {} says something about Acme and Beta."


def text(n=60):
    return " ".join(SENT.format(i) for i in range(n))


@pytest.mark.parametrize("size,overlap", [(400, 100), (400, 0), (300, 299), (1500, 200)])
def test_offsets_size_coverage_and_progress(size, overlap):
    t = text()
    chunks = chunk_text(t, size, overlap)
    assert all(t[c.start:c.end] == c.text for c in chunks)
    assert all(c.end - c.start <= size for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert all(b.start > a.start for a, b in zip(chunks, chunks[1:]))
    for m in re.finditer(r"Sentence number \d+ says something about Acme and Beta\.", t):
        assert any(c.start <= m.start() and m.end() <= c.end for c in chunks), "a sentence was cut in two"


def test_overlap_repeats_whole_sentences():
    chunks = chunk_text(text(), 400, 120)
    for a, b in zip(chunks, chunks[1:]):
        shared = a.end - b.start
        assert 0 < shared <= 120
        assert b.start == 0 or text()[b.start - 1] == " "


def test_zero_overlap_does_not_repeat():
    chunks = chunk_text(text(), 400, 0)
    assert all(a.end <= b.start for a, b in zip(chunks, chunks[1:]))


def test_short_text_is_one_chunk():
    chunks = chunk_text("Just one sentence here.", 500, 50)
    assert len(chunks) == 1 and chunks[0].text == "Just one sentence here."


def test_text_without_punctuation_is_cut_on_spaces():
    chunks = chunk_text("word " * 1000, 300, 50)
    assert max(c.end - c.start for c in chunks) <= 300
    assert all(not c.text.endswith("wor") for c in chunks)
    assert len(chunks) > 10


def test_empty_and_invalid():
    assert chunk_text("   \n ", 300, 50) == []
    with pytest.raises(ValueError):
        chunk_text("abc", 50, 10)
    with pytest.raises(ValueError):
        chunk_text("abc" * 100, 300, 300)


def test_paragraph_breaks_split_sentences():
    t = "First paragraph without final punctuation\n\nSecond paragraph here."
    chunks = chunk_text(t, 100, 0)
    assert "".join(c.text for c in chunks).replace("\n", "") != ""
    assert any("Second paragraph" in c.text for c in chunks)
