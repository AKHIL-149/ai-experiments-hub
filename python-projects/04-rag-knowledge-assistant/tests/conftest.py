import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from llm_client import LLMClient  # noqa: E402
from rag_engine import RAGEngine  # noqa: E402
from vector_store import VectorStore  # noqa: E402


class FakeEmbedding:
    """Deterministic bag-of-words embeddings: no model download, similar words -> similar vectors."""

    dim = 64

    def __init__(self):
        self.calls = 0

    def _vec(self, text):
        v = np.zeros(self.dim)
        for word in text.lower().split():
            h = int(hashlib.md5(word.strip(".,:;!?").encode()).hexdigest(), 16)
            v[h % self.dim] += 1.0
        n = np.linalg.norm(v)
        return (v / n if n else v).tolist()

    def embed_documents(self, texts):
        self.calls += 1
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


class FakeLLM(LLMClient):
    """Records prompts instead of calling Ollama."""

    def __init__(self, reply="stub answer [1]"):
        super().__init__()
        self.reply = reply
        self.prompts = []
        self.truncated = False

    def generate(self, prompt, temperature=0.7, max_tokens=1000):
        self.prompts.append(prompt)
        return self.reply


@pytest.fixture
def engine(tmp_path):
    return RAGEngine(
        vector_store=VectorStore("test", str(tmp_path / "db")),
        embedding_service=FakeEmbedding(),
        llm_client=FakeLLM(),
    )


@pytest.fixture
def make_file(tmp_path):
    def make(name, text, encoding="utf-8"):
        p = tmp_path / name
        p.write_bytes(text.encode(encoding))
        return p
    return make


def build_pdf(pages, path):
    """Write a minimal text PDF ("" makes a blank page)."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{3 + i * 2} 0 R" for i in range(len(pages)))
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>")
    font_id = 3 + len(pages) * 2
    for i, text in enumerate(pages):
        pid, cid = 3 + i * 2, 4 + i * 2
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {cid} 0 R "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>"
        )
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET" if text else ""
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    objs.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out, offsets = "%PDF-1.4\n", []
    for i, o in enumerate(objs):
        offsets.append(len(out))
        out += f"{i + 1} 0 obj\n{o}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n"
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    Path(path).write_text(out)
    return Path(path)


@pytest.fixture
def make_pdf(tmp_path):
    return lambda name, pages: build_pdf(pages, tmp_path / name)
