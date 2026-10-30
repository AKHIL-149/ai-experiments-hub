"""Document processing and chunking utilities."""

import re
from pathlib import Path
from typing import List, Dict, Optional

import PyPDF2


class Document:
    """Represents a processed document with metadata."""

    def __init__(self, content: str, metadata: Dict[str, str]):
        self.content = content
        self.metadata = metadata

    def __repr__(self):
        return f"Document(source={self.metadata.get('source')}, chars={len(self.content)})"


def decode_text_bytes(data: bytes) -> str:
    """Decode a text file: UTF-8 (with or without BOM), then Windows-1252."""
    if b"\x00" in data:
        raise ValueError("does not look like a text file (contains binary data)")
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


# A sentence ends at . ! ? followed by whitespace, so "3.14" and "e.g.x" are not split points
_SENTENCE_END = re.compile(r"[.!?](?=\s)")


class DocumentProcessor:
    """Process and chunk documents for RAG."""

    SUPPORTED = ('.pdf', '.txt', '.md')

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        if chunk_size < 1:
            raise ValueError("chunk size must be at least 1")
        if chunk_overlap < 0:
            raise ValueError("chunk overlap cannot be negative")
        if chunk_overlap >= chunk_size:
            raise ValueError(
                f"chunk overlap ({chunk_overlap}) must be smaller than chunk size ({chunk_size})"
            )
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def load_file(self, file_path: str) -> List[Document]:
        """Load a file and return chunked documents."""
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if path.is_dir():
            raise ValueError(f"{file_path} is a directory, not a file")

        suffix = path.suffix.lower()
        if suffix == '.pdf':
            documents = self._load_pdf(path)
        elif suffix in ('.txt', '.md'):
            documents = self._load_text(path)
        else:
            raise ValueError(
                f"Unsupported file type: {path.suffix or '(none)'} "
                f"(supported: {', '.join(self.SUPPORTED)})"
            )

        if not documents:
            raise ValueError(
                f"{path.name} contains no extractable text"
                + (" (a scanned PDF needs OCR first)" if suffix == '.pdf' else "")
            )
        return documents

    def _load_text(self, path: Path) -> List[Document]:
        """Load and chunk a text file."""
        content = decode_text_bytes(path.read_bytes())

        return [
            Document(
                content=chunk,
                metadata={
                    'source': str(path),
                    'type': 'text',
                    'chunk_index': i
                }
            )
            for i, chunk in enumerate(self._chunk_text(content))
        ]

    def _load_pdf(self, path: Path) -> List[Document]:
        """Load and chunk a PDF file (blank pages are skipped)."""
        documents = []

        with open(path, 'rb') as f:
            pdf_reader = PyPDF2.PdfReader(f)
            if pdf_reader.is_encrypted:
                raise ValueError(f"{path.name} is password-protected")

            for page_num, page in enumerate(pdf_reader.pages):
                text = page.extract_text() or ""

                for i, chunk in enumerate(self._chunk_text(text)):
                    documents.append(
                        Document(
                            content=chunk,
                            metadata={
                                'source': str(path),
                                'type': 'pdf',
                                'page': page_num + 1,
                                'chunk_index': i
                            }
                        )
                    )

        return documents

    def _chunk_text(self, text: Optional[str]) -> List[str]:
        """Split text into overlapping chunks, preferring paragraph, then sentence, then word breaks."""
        text = (text or "").strip()
        if not text:
            return []
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0
        length = len(text)

        while start < length:
            end = min(start + self.chunk_size, length)

            if end < length:
                end = self._best_break(text, start, end)

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            if end >= length:
                break
            # Always move forward, even with a large overlap
            start = max(end - self.chunk_overlap, start + 1)

        return chunks

    def _best_break(self, text: str, start: int, end: int) -> int:
        """Pick where to cut text[start:end]: paragraph > sentence > word > hard cut."""
        window = text[start:end]
        minimum = self.chunk_size // 2

        paragraph = window.rfind("\n\n")
        if paragraph > minimum:
            return start + paragraph + 2

        sentence_ends = [m.end() for m in _SENTENCE_END.finditer(window)]
        newline = window.rfind("\n") + 1
        best = max(sentence_ends[-1] if sentence_ends else 0, newline)
        if best > minimum:
            return start + best

        space = window.rfind(" ")
        if space > minimum:
            return start + space + 1

        return end
