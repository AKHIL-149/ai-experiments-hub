"""Turn an uploaded file or pasted text into plain text"""
import io
import re
from pathlib import Path

TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".text"}
ALLOWED_EXTENSIONS = TEXT_EXTENSIONS | {".pdf", ".docx"}


class ReadError(ValueError):
    """The file cannot be turned into text (message is safe to show to the user)"""


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def read_bytes(filename: str, data: bytes) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ReadError(f"Unsupported file type '{ext or filename}'. Use: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    if not data:
        raise ReadError("The file is empty")
    if ext in TEXT_EXTENSIONS:
        # UTF-16 decodes almost any byte pair, so only trust it when the file says it is UTF-16 (byte-order mark)
        encodings = ["utf-8-sig"] + (["utf-16"] if data[:2] in (b"\xff\xfe", b"\xfe\xff") else []) + ["latin-1"]
        for enc in encodings:
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
    elif ext == ".pdf":
        text = _read_pdf(data)
    else:
        text = _read_docx(data)
    text = clean_text(text)
    if not text:
        raise ReadError("No text found in the file" + (" (a scanned PDF needs OCR first)" if ext == ".pdf" else ""))
    return text


def _read_pdf(data: bytes) -> str:
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ReadError("The PDF is password protected")
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    except ReadError:
        raise
    except Exception as exc:
        raise ReadError(f"The PDF could not be read ({type(exc).__name__})") from exc


def _read_docx(data: bytes) -> str:
    import docx
    try:
        d = docx.Document(io.BytesIO(data))
        parts = [p.text for p in d.paragraphs]
        for table in d.tables:
            for row in table.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        return "\n\n".join(parts)
    except Exception as exc:
        raise ReadError(f"The Word file could not be read ({type(exc).__name__})") from exc
