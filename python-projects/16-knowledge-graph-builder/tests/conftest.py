import sys
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core import database  # noqa: E402
from src.services import extraction  # noqa: E402


class FakeLLM:
    """Scripted model: `extract` and `verify` are callables returning the JSON the real model would give"""
    name = "fake:model"

    def __init__(self, extract=None, verify=None):
        self.extract = extract or (lambda prompt: {"relations": []})
        self.verify = verify or (lambda prompt: "supported")
        self.calls = []

    def generate_json(self, system, prompt, schema):
        if system == extraction.VERIFY_SYSTEM:
            self.calls.append(("verify", prompt))
            out = self.verify(prompt)
            return out if isinstance(out, dict) else {"answer": "yes" if out == "supported" else "no"}
        self.calls.append(("extract", prompt))
        out = self.extract(prompt)
        if isinstance(out, Exception):
            raise out
        return out

    def count(self, kind):
        return sum(1 for k, _ in self.calls if k == kind)


def rel(subject, predicate, obj, evidence, start="", end="", stype="person", otype="organization"):
    return {"subject": subject, "subject_type": stype, "predicate": predicate, "object": obj, "object_type": otype,
            "start": start, "end": end, "evidence": evidence}


@pytest.fixture
def factory(tmp_path, monkeypatch):
    """A fresh SQLite database; code that opens its own session (the pipeline) uses it too"""
    engine = database.make_engine(f"sqlite:///{tmp_path}/test.db")
    database.Base.metadata.drop_all(bind=engine)
    from src import models  # noqa: F401
    database.Base.metadata.create_all(bind=engine)
    f = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionLocal", f)
    yield f
    engine.dispose()


@pytest.fixture
def db(factory):
    s = factory()
    yield s
    s.close()
