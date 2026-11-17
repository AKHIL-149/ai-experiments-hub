import sys
import zlib
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import select
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
        self.max_tokens = []     # the cap each call asked for

    def generate_json(self, system, prompt, schema, max_tokens=None):
        self.max_tokens.append(max_tokens)
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


@pytest.fixture(autouse=True)
def no_real_embedder(monkeypatch):
    """Reading a document would call the real embedding model; tests that want one install a fake"""
    from src.services import pipeline
    monkeypatch.setattr(pipeline, "get_embedder", lambda settings=None: None)


# ---------------------------------------------------------------- small graphs and fake models for the tests

def _graph_world(db):
    from src.models.graph import Chunk, Document, DocumentStatus, Entity, Fact, FactSource
    from src.services.text_utils import entity_key
    docs = {}

    class W:
        pass
    w = W()
    w.db = db

    def _doc(title="D"):
        if title not in docs:
            d = Document(title=title, text="x" * 50, char_count=50, status=DocumentStatus.COMPLETED)
            db.add(d)
            db.flush()
            ch = Chunk(document_id=d.id, index=0, start=0, end=50, text=f"Passage of {title}. " + "x" * 20)
            db.add(ch)
            db.flush()
            docs[title] = (d.id, ch.id)
        return docs[title]

    _doc()
    w.doc, w.chunk = docs["D"]
    w.docs, w.new_doc = docs, _doc

    def ent(name, etype="organization"):
        e = Entity(name=name, key=entity_key(name), type=etype)
        db.add(e)
        db.flush()
        return e

    def fact(s, p, o=None, value="", frm="", to="", quote=None, title="D", id=None, verified=False, doc=None, chunk=None):
        did, cid = (doc, chunk) if doc else _doc(title)
        f = Fact(subject_id=s.id, predicate=p, object_id=o.id if o else None, object_value=value, valid_from=frm, valid_to=to,
                 **({"id": id} if id else {}))
        db.add(f)
        db.flush()
        db.add(FactSource(fact_id=f.id, document_id=did, chunk_id=cid, verified=verified,
                          evidence=quote or f"{s.name} {p} {o.name if o else value}."))
        db.flush()
        return f

    w.ent, w.fact = ent, fact
    return w


@pytest.fixture
def world(db):
    return _graph_world(db)


class FakeEmbedder:
    """Word-overlap vectors with a few synonyms, so tests can rely on 'bought' being close to 'acquired'"""
    name = "fake:embed"
    SYN = {"bought": "acquired", "purchased": "acquired", "acquire": "acquired", "created": "founded", "established": "founded",
           "founder": "founded", "found": "founded", "studied": "attended", "attend": "attended", "went": "attended"}
    DIM = 256

    def __init__(self):
        self.calls = []

    def embed(self, texts, kind="document"):
        self.calls.append((kind, list(texts)))
        out = []
        for t in texts:
            v = np.zeros(self.DIM, dtype=np.float32)
            for w in "".join(c.lower() if c.isalnum() else " " for c in t).split():
                v[zlib.crc32(self.SYN.get(w, w).encode()) % self.DIM] += 1.0
            out.append(v.tolist())
        return out


class ScriptedLLM(FakeLLM):
    """Answers the three kinds of call a question makes: plan, answer (and the extraction ones are not used here)"""

    def __init__(self, plan=None, answer=None):
        super().__init__()
        self.plan_fn = plan or (lambda q: {"start": [], "steps": []})
        self.answer_fn = answer or (lambda prompt: {"found": False, "answer": "not found", "cited": []})
        self.prompts = {"plan": [], "answer": []}

    def generate_json(self, system, prompt, schema, max_tokens=None):
        from src.services import ask
        if system == ask.PLAN_SYSTEM:
            self.prompts["plan"].append(prompt)
            r = self.plan_fn(prompt)
        elif system.startswith(ask.ANSWER_SYSTEM):
            self.prompts["answer"].append(prompt)
            r = self.answer_fn(prompt)
        else:
            raise AssertionError("unexpected call")
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture
def story(world):
    """Veltra acquired Soro; Imani founded Soro; Imani attended Tamsen; Tamsen is in Kellmar; Kellmar is in Dravia"""
    w, db = world, world.db
    ent = world.ent
    w.veltra, w.soro, w.imani = ent("Veltra Dynamics"), ent("Soro Labs"), ent("Imani Okafor", "person")
    w.tamsen, w.kellmar, w.dravia = ent("University of Tamsen"), ent("Kellmar", "place"), ent("Dravia", "place")
    w.north, w.pennant, w.ravi = ent("Northfield College"), ent("Pennant Robotics"), ent("Ravi Anand", "person")
    w.f_acq = world.fact(w.veltra, "acquired", w.soro, frm="2018", title="d01")
    w.f_found = world.fact(w.imani, "founded", w.soro, frm="2011", title="d02")
    w.f_att = world.fact(w.imani, "studied at", w.tamsen, title="d03")
    w.f_loc = world.fact(w.tamsen, "located in", w.kellmar, title="d04")
    w.f_loc2 = world.fact(w.north, "located in", w.kellmar, title="d04")
    w.f_dr = world.fact(w.kellmar, "is a city in", w.dravia, title="d05")
    w.f_ravi = world.fact(w.ravi, "founded", w.pennant, title="d10")
    w.f_inv = world.fact(w.veltra, "invested in", w.pennant, frm="2022", title="d10")
    w.f_ravi_att = world.fact(w.ravi, "studied at", w.north, title="d11")
    w.f_emp = world.fact(w.soro, "employs", value="40 people", title="d02")
    db.commit()
    return w


def use_settings(monkeypatch, **overrides):
    """Make the sign-in code (and anything else that asks) see these settings"""
    from src.core.config import Settings
    s = Settings(_env_file=None, **overrides)
    for mod in ("src.core.auth", "src.core.login_gate", "src.api.auth", "src.api.documents"):
        monkeypatch.setattr(f"{mod}.get_settings", lambda s=s: s)
    return s


@pytest.fixture(autouse=True)
def single_user_mode(monkeypatch):
    """Most tests run as the one local user (no sign-in); the accounts tests turn sign-in on"""
    return use_settings(monkeypatch, require_login=False)


@pytest.fixture(autouse=True)
def fresh_throttles():
    from src.api import auth as auth_api
    for t in (auth_api.login_failures, auth_api.creations):
        t.events.clear()


@pytest.fixture(autouse=True)
def jobs_run_inline(monkeypatch):
    """Without worker threads, a job runs in the request that enqueued it (as the old background task did); the queue tests turn this off"""
    from src.services import job_queue
    monkeypatch.setattr(job_queue, "INLINE", True)
