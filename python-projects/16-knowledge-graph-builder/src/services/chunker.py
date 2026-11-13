"""Split text into overlapping chunks on sentence boundaries, keeping character offsets"""
import re
from dataclasses import dataclass

_SENTENCE_END = re.compile(r"(?<=[.!?])[\"')\]]*\s+|\n{2,}")


@dataclass
class TextChunk:
    index: int
    start: int
    end: int
    text: str


def sentence_spans(text: str) -> list[tuple[int, int]]:
    spans, pos = [], 0
    for m in _SENTENCE_END.finditer(text):
        end = m.end()
        if text[pos:end].strip():
            spans.append((pos, end))
        pos = end
    if text[pos:].strip():
        spans.append((pos, len(text)))
    return spans


def _split_long(text: str, start: int, end: int, size: int) -> list[tuple[int, int]]:
    """A single 'sentence' longer than a chunk (no punctuation): cut it on spaces"""
    out, pos = [], start
    while end - pos > size:
        cut = pos + size
        space = text.rfind(" ", pos, cut)
        out.append((pos, space if space > pos else cut))
        pos = out[-1][1]
    out.append((pos, end))
    return out


def chunk_text(text: str, size: int = 1500, overlap: int = 200) -> list[TextChunk]:
    if size < 100:
        raise ValueError("chunk size too small")
    if not 0 <= overlap < size:
        raise ValueError("overlap must be smaller than the chunk size")
    if not text.strip():
        return []
    pieces: list[tuple[int, int]] = []
    for s, e in sentence_spans(text):
        pieces.extend(_split_long(text, s, e, size) if e - s > size else [(s, e)])

    chunks: list[TextChunk] = []
    i = 0
    while i < len(pieces):
        start = pieces[i][0]
        j = i
        while j + 1 < len(pieces) and pieces[j + 1][1] - start <= size:
            j += 1
        end = pieces[j][1]
        chunks.append(TextChunk(len(chunks), start, end, text[start:end]))
        if j + 1 >= len(pieces):
            break
        # the next chunk starts with the whole sentences that fit in the overlap, but always moves forward
        k = j + 1
        while k - 1 > i and end - pieces[k - 1][0] <= overlap:
            k -= 1
        i = k
    return chunks
