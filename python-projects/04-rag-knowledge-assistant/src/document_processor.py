"""Document processing and chunking utilities."""

from pathlib import Path
from typing import List, Dict
import PyPDF2


class Document:
    """Represents a processed document with metadata."""

    def __init__(self, content: str, metadata: Dict[str, str]):
        self.content = content
        self.metadata = metadata

    def __repr__(self):
        return f"Document(source={self.metadata.get('source')}, chars={len(self.content)})"


class DocumentProcessor:
    """Process and chunk documents for RAG."""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def load_file(self, file_path: str) -> List[Document]:
        """Load a file and return chunked documents."""
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if path.suffix.lower() == '.pdf':
            return self._load_pdf(path)
        elif path.suffix.lower() in ['.txt', '.md']:
            return self._load_text(path)
        else:
            raise ValueError(f"Unsupported file type: {path.suffix}")

    def _load_text(self, path: Path) -> List[Document]:
        """Load and chunk a text file."""
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        chunks = self._chunk_text(content)
        return [
            Document(
                content=chunk,
                metadata={
                    'source': str(path),
                    'type': 'text',
                    'chunk_index': i
                }
            )
            for i, chunk in enumerate(chunks)
        ]

    def _load_pdf(self, path: Path) -> List[Document]:
        """Load and chunk a PDF file."""
        documents = []

        with open(path, 'rb') as f:
            pdf_reader = PyPDF2.PdfReader(f)

            for page_num, page in enumerate(pdf_reader.pages):
                text = page.extract_text()
                chunks = self._chunk_text(text)

                for i, chunk in enumerate(chunks):
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

    def _chunk_text(self, text: str) -> List[str]:
        """Chunk text with overlap."""
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]

            # Try to break at sentence boundary
            if end < len(text):
                last_period = chunk.rfind('.')
                last_newline = chunk.rfind('\n')
                break_point = max(last_period, last_newline)

                if break_point > self.chunk_size // 2:
                    chunk = text[start:start + break_point + 1]
                    end = start + break_point + 1

            chunks.append(chunk.strip())
            start = end - self.chunk_overlap

        return [c for c in chunks if c]
