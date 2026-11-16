"""One account must never see, change, or even detect another account's data, through any endpoint"""
import pytest
from sqlalchemy import func, select

from src.models.graph import Chunk, Document, Entity, Fact
from src.models.resolution import EntityAlias, MergeRecord, MergeSuggestion
from src.services import pipeline
from tests.conftest import ScriptedLLM
from tests.test_accounts import DOCS, RAWS, site  # noqa: F401  (the fixture)


def add(client, key):
    r = client.post("/api/documents/text", json={"title": f"Doc {key}", "text": DOCS[key]})
    assert r.status_code == 202, r.text
    return r.json()["id"]


@pytest.fixture
def two(site):
    """Ann (documents A) and Bob (documents B), each with a finished document"""
    ann, bob = site.user("ann"), site.user("bob")
    ids = {"ann": add(ann, "A"), "bob": add(bob, "B")}
    return site, ann, bob, ids


def names(client):
    return {e["name"] for e in client.get("/api/entities?limit=500").json()["entities"]}


def test_each_account_sees_only_its_own_documents_and_graph(two):
    site, ann, bob, ids = two
    assert [d["title"] for d in ann.get("/api/documents").json()["documents"]] == ["Doc A"]
    assert [d["title"] for d in bob.get("/api/documents").json()["documents"]] == ["Doc B"]
    assert names(ann) == {"Acme Corp", "Beta Systems", "Dana Reyes"} and names(bob) == {"Zed Inc", "Omega Labs", "Orion Works"}
    ga, gb = ann.get("/api/graph").json(), bob.get("/api/graph").json()
    assert {n["name"] for n in ga["nodes"]} == names(ann) and {n["name"] for n in gb["nodes"]} == names(bob)
    assert ann.get("/api/graph/stats").json()["facts"] == 2 and bob.get("/api/graph/stats").json()["facts"] == 2
    assert ann.get("/api/entities?q=zed").json()["entities"] == []


def test_guessing_another_accounts_ids_answers_404_like_an_id_that_does_not_exist(two):
    site, ann, bob, ids = two
    bob_entity = bob.get("/api/entities?q=zed").json()["entities"][0]["id"]
    bob_fact = next(e["id"] for e in bob.get("/api/graph").json()["edges"])
    missing = "0" * 32
    for url in (f"/api/documents/{ids['bob']}", f"/api/entities/{bob_entity}", f"/api/entities/{bob_entity}/neighborhood", f"/api/facts/{bob_fact}"):
        foreign, absent = ann.get(url), ann.get(url.replace(ids["bob"], missing).replace(bob_entity, missing).replace(bob_fact, missing))
        assert foreign.status_code == absent.status_code == 404 and foreign.json() == absent.json(), url
    assert ann.get(f"/api/graph?document_id={ids['bob']}").status_code == 404
    assert ann.delete(f"/api/documents/{ids['bob']}").status_code == 404
    assert ann.post(f"/api/documents/{ids['bob']}/reprocess").status_code == 404
    # and nothing happened to Bob's data
    assert [d["title"] for d in bob.get("/api/documents").json()["documents"]] == ["Doc B"] and bob.get("/api/graph/stats").json()["facts"] == 2


def test_the_same_name_in_two_accounts_is_two_separate_entities(site):
    ann, bob = site.user("ann"), site.user("bob")
    add(ann, "A")
    bob.post("/api/documents/text", json={"title": "Doc A again", "text": DOCS["A"]})     # Bob reads the very same text
    with site.factory() as db:
        rows = db.execute(select(Entity).where(Entity.name == "Acme Corp")).scalars().all()
        assert len(rows) == 2 and {r.owner_id for r in rows} == {ann.user["id"], bob.user["id"]}
        assert db.scalar(select(func.count()).select_from(Fact)) == 4                     # two facts each, not shared
    assert ann.get("/api/graph/stats").json()["facts"] == 2


def test_questions_never_use_another_accounts_facts_or_passages(two, monkeypatch):
    site, ann, bob, ids = two
    seen = []
    llm = ScriptedLLM(plan=lambda q: {"start": ["Zed Inc"], "steps": [{"relation": "founded", "direction": "out"}]},
                      answer=lambda p: (seen.append(p), {"found": False, "answer": "not found", "cited": []})[1])
    monkeypatch.setattr("src.api.query.get_llm", lambda s=None: llm)
    # Ann asks about Bob's company: it is not in her graph
    for mode in ("graph", "subgraph", "hybrid", "vector"):
        r = ann.post("/api/ask", json={"question": "Who founded Orion Works? Tell me about Zed Inc", "mode": mode})
        assert r.status_code == 200
    evidence = [p.split("\n\n", 1)[1] for p in seen]          # what the model was shown, without the question itself
    assert evidence and not any("Zed" in e or "Orion" in e or "Omega" in e for e in evidence)
    seen.clear()
    r = bob.post("/api/ask", json={"question": "What did Zed Inc found?", "mode": "hybrid"})
    assert any("Orion Works" in p.split("\n\n", 1)[1] for p in seen) and not any("Acme" in p for p in seen)
    r = ann.post("/api/ask", json={"question": "anything", "document_id": ids["bob"]})
    assert r.status_code == 404


def test_passage_search_only_finds_the_callers_own_passages(two):
    site, ann, bob, ids = two
    from src.services.embedding import top_chunks
    with site.factory() as db:
        mine = top_chunks(db, __import__("tests.conftest", fromlist=["FakeEmbedder"]).FakeEmbedder(), "Zed Inc bought Omega Labs", 10, owner_id=ann.user["id"])
        assert mine and all(db.get(Document, c.document_id).owner_id == ann.user["id"] for c, _ in mine)
        assert all("Zed" not in c.text for c, _ in mine)


def test_link_path_and_chain_only_see_the_callers_graph(two):
    site, ann, bob, ids = two
    assert ann.get("/api/query/link", params={"q": "Zed Inc and Omega Labs"}).json() == {"entities": []}
    assert [e["name"] for e in ann.get("/api/query/link", params={"q": "Acme Corp"}).json()["entities"]] == ["Acme Corp"]
    assert ann.get("/api/query/path", params={"from": "Zed Inc", "to": "Omega Labs"}).status_code == 404
    bob_entity = bob.get("/api/entities?q=zed").json()["entities"][0]["id"]
    assert ann.get("/api/query/path", params={"from": bob_entity, "to": bob_entity}).status_code == 404       # an id is not a way in
    assert ann.post("/api/query/chain", json={"start": "Zed Inc", "steps": [{"relation": "founded"}]}).status_code == 404
    assert ann.post("/api/query/chain", json={"start": bob_entity, "steps": [{"relation": "founded"}]}).status_code == 404
    ok = bob.post("/api/query/chain", json={"start": "Zed Inc", "steps": [{"relation": "founded"}]}).json()
    assert ok["answers"] == ["Orion Works"]


def test_the_search_index_is_counted_and_rebuilt_per_account(two):
    site, ann, bob, ids = two
    sa, sb = ann.get("/api/index/status").json(), bob.get("/api/index/status").json()
    assert sa["passages"] == sb["passages"] == 1 and sa["passages_indexed"] == sb["passages_indexed"] == 1
    assert sa["facts"] == sb["facts"] == 2 and sa["facts_indexed"] == 0
    assert ann.post("/api/index/rebuild").json()["facts_added"] == 2
    assert ann.get("/api/index/status").json()["facts_indexed"] == 2 and bob.get("/api/index/status").json()["facts_indexed"] == 0


# ---------------------------------------------------------------- resolution

@pytest.fixture
def duplicated(site):
    """Ann has 'Acme Corp' and 'Acme Labs' (a suggestion), Bob has 'Acme Corp' too"""
    ann, bob = site.user("ann"), site.user("bob")
    with site.factory() as db:
        def ent(owner, name):
            e = Entity(owner_id=owner.user["id"], name=name, key=name.lower(), type="organization")
            db.add(e)
            db.flush()
            return e
        ea1, ea2, eb1, eb2 = ent(ann, "Acme"), ent(ann, "Acme Labs"), ent(bob, "Acme"), ent(bob, "Acme Labs")
        db.commit()
        ids = {"ann": (ea1.id, ea2.id), "bob": (eb1.id, eb2.id)}
    return site, ann, bob, ids


def test_resolution_runs_and_lists_per_account(duplicated):
    site, ann, bob, ids = duplicated
    assert ann.post("/api/resolution/run").json()["suggestions_new"] == 1
    assert len(ann.get("/api/resolution/suggestions").json()["suggestions"]) == 1
    assert bob.get("/api/resolution/suggestions").json()["suggestions"] == []         # Bob has not run it yet
    assert bob.post("/api/resolution/run").json()["suggestions_new"] == 1
    with site.factory() as db:
        assert {s.owner_id for s in db.execute(select(MergeSuggestion)).scalars()} == {ann.user["id"], bob.user["id"]}


def test_another_accounts_suggestions_and_merges_cannot_be_touched(duplicated):
    site, ann, bob, ids = duplicated
    ann.post("/api/resolution/run")
    sid = ann.get("/api/resolution/suggestions").json()["suggestions"][0]["id"]
    assert bob.post(f"/api/resolution/suggestions/{sid}/accept").status_code == 404
    assert bob.post(f"/api/resolution/suggestions/{sid}/reject").status_code == 404
    assert len(ann.get("/api/resolution/suggestions").json()["suggestions"]) == 1                  # still pending, untouched
    # Bob cannot merge Ann's entities, even by id, and cannot mix his with hers
    assert bob.post("/api/entities/merge", json={"keep_id": ids["ann"][0], "absorb_id": ids["ann"][1]}).status_code == 404
    assert bob.post("/api/entities/merge", json={"keep_id": ids["bob"][0], "absorb_id": ids["ann"][1]}).status_code == 404
    assert bob.post("/api/entities/merge", json={"keep_id": ids["ann"][0], "absorb_id": ids["bob"][1]}).status_code == 404
    rec = ann.post("/api/entities/merge", json={"keep_id": ids["ann"][0], "absorb_id": ids["ann"][1]}).json()
    assert bob.post(f"/api/resolution/merges/{rec['id']}/undo").status_code == 404
    assert bob.get("/api/resolution/merges").json()["merges"] == [] and len(ann.get("/api/resolution/merges").json()["merges"]) == 1
    assert ann.post(f"/api/resolution/merges/{rec['id']}/undo").status_code == 200
    with site.factory() as db:
        assert db.scalar(select(func.count()).select_from(Entity).where(Entity.owner_id == bob.user["id"])) == 2   # Bob's untouched


def test_merged_names_are_aliases_only_for_their_owner(site):
    ann, bob = site.user("ann"), site.user("bob")
    add(ann, "A")                       # Ann's 'ACME' is merged into 'Acme Corp' automatically
    with site.factory() as db:
        assert [(a.name, a.owner_id) for a in db.execute(select(EntityAlias)).scalars()] == [("ACME", ann.user["id"])]
    bob.post("/api/documents/text", json={"title": "B", "text": DOCS["A"]})
    with site.factory() as db:
        mine = {(e.owner_id, e.name) for e in db.execute(select(Entity)).scalars()}
        assert (bob.user["id"], "Acme Corp") in mine and (bob.user["id"], "ACME") not in mine       # Bob's own merge, own alias
        assert {a.owner_id for a in db.execute(select(EntityAlias)).scalars()} == {ann.user["id"], bob.user["id"]}


def test_writes_of_one_account_do_not_wait_for_a_document_of_another(duplicated):
    site, ann, bob, ids = duplicated
    lock = pipeline.owner_lock(bob.user["id"])
    assert lock.acquire(blocking=False)
    try:
        assert bob.post("/api/resolution/run").status_code == 409          # Bob's own document is being read
        assert ann.post("/api/resolution/run").status_code == 200           # Ann is not affected
        assert bob.post("/api/index/rebuild").status_code == 409
    finally:
        lock.release()


def test_deleting_a_document_only_removes_what_only_it_supported(two):
    site, ann, bob, ids = two
    assert ann.delete(f"/api/documents/{ids['ann']}").status_code == 204
    assert ann.get("/api/graph/stats").json() == {"entities": 0, "entities_by_type": {}, "facts": 0, "sources": 0, "top_predicates": []}
    assert bob.get("/api/graph/stats").json()["facts"] == 2


def test_deleting_an_account_removes_its_data_and_nobody_elses(two):
    site, ann, bob, ids = two
    with site.factory() as db:
        from src.models.user import User
        db.delete(db.get(User, ann.user["id"]))
        db.commit()
        assert db.scalar(select(func.count()).select_from(Document).where(Document.owner_id == ann.user["id"])) == 0
        assert db.scalar(select(func.count()).select_from(Entity).where(Entity.owner_id == ann.user["id"])) == 0
        assert db.scalar(select(func.count()).select_from(Fact).where(Fact.owner_id == ann.user["id"])) == 0
        assert db.scalar(select(func.count()).select_from(Chunk)) == 1
    assert bob.get("/api/graph/stats").json()["facts"] == 2


# ---------------------------------------------------------------- the owner's own operations still work (positive checks)

def test_an_account_can_follow_paths_and_neighbourhoods_in_its_own_graph(two):
    site, ann, bob, ids = two
    r = ann.get("/api/query/path", params={"from": "Acme Corp", "to": "Dana Reyes"}).json()
    assert [p["text"] for p in r["paths"][0]] == ["Acme Corp hired Dana Reyes (2021..)"]
    acme = ann.get("/api/entities?q=acme").json()["entities"][0]["id"]
    n = ann.get(f"/api/entities/{acme}/neighborhood?depth=1").json()
    assert {x["name"] for x in n["nodes"]} == {"Acme Corp", "Beta Systems", "Dana Reyes"} and len(n["edges"]) == 2


def test_questions_in_every_mode_do_find_the_callers_own_facts_and_passages(two, monkeypatch):
    site, ann, bob, ids = two
    seen = []
    llm = ScriptedLLM(plan=lambda q: {"start": ["Acme Corp"], "steps": [{"relation": "acquired", "direction": "out"}]},
                      answer=lambda p: (seen.append(p), {"found": True, "answer": "Beta Systems", "cited": []})[1])
    monkeypatch.setattr("src.api.query.get_llm", lambda s=None: llm)
    for mode, expect in (("graph", "Acme Corp acquired Beta Systems"), ("subgraph", "Acme Corp acquired Beta Systems"),
                         ("hybrid", "Passages:"), ("vector", "Passages:")):
        seen.clear()
        assert ann.post("/api/ask", json={"question": "What did Acme Corp acquire?", "mode": mode}).status_code == 200
        assert seen and expect in seen[0], mode
    assert "Acme Corp acquired Beta Systems in March 2020" in seen[0]          # the passage itself (vector mode, last)


def test_an_account_accepts_and_rejects_its_own_suggestions_and_undoes_its_own_merges(site):
    ann = site.user("ann")
    owner = ann.user["id"]
    with site.factory() as db:
        from src.models.graph import FactSource
        did, cid = None, None
        d = Document(owner_id=owner, title="d", text="x" * 30, char_count=30)
        db.add(d)
        db.flush()
        c = Chunk(document_id=d.id, index=0, start=0, end=30, text="x" * 30)
        db.add(c)
        ent = lambda n, t="organization": Entity(owner_id=owner, name=n, key=n.lower(), type=t)  # noqa: E731
        acme, labs, beta, zed, zed_labs = ent("Acme"), ent("Acme Labs"), ent("Beta"), ent("Zed"), ent("Zed Labs")
        db.add_all([acme, labs, beta, zed, zed_labs])
        db.flush()
        for subj in (acme, labs):          # the same fact on both: merging folds them into one (and undo must restore the copy)
            f = Fact(owner_id=owner, subject_id=subj.id, predicate="partnered with", object_id=beta.id)
            db.add(f)
            db.flush()
            db.add(FactSource(fact_id=f.id, document_id=d.id, chunk_id=c.id, evidence=f"{subj.name} partnered with Beta."))
        for subj in (zed, zed_labs):
            f = Fact(owner_id=owner, subject_id=subj.id, predicate="partnered with", object_id=beta.id)
            db.add(f)
        db.commit()
        ids = {"acme": acme.id, "labs": labs.id, "zed": zed.id, "zed_labs": zed_labs.id}
    assert ann.post("/api/resolution/run").json()["suggestions_new"] == 2
    sugg = {frozenset((s["a"]["name"], s["b"]["name"])): s["id"] for s in ann.get("/api/resolution/suggestions").json()["suggestions"]}
    acme_id, zed_id = sugg[frozenset(("Acme", "Acme Labs"))], sugg[frozenset(("Zed", "Zed Labs"))]
    rec = ann.post(f"/api/resolution/suggestions/{acme_id}/accept", json={"keep_id": ids["acme"]})
    assert rec.status_code == 200 and rec.json()["kept"] == "Acme"
    assert ann.post(f"/api/resolution/suggestions/{zed_id}/reject").status_code == 204
    assert len(ann.get("/api/resolution/suggestions?status=rejected").json()["suggestions"]) == 1
    with site.factory() as db:
        assert db.scalar(select(func.count()).select_from(Fact).where(Fact.subject_id == ids["acme"])) == 1      # folded into one
        record = db.execute(select(MergeRecord)).scalar_one()
        assert record.owner_id == owner and db.execute(select(EntityAlias)).scalar_one().owner_id == owner
    assert ann.post(f"/api/resolution/merges/{rec.json()['id']}/undo").status_code == 200
    with site.factory() as db:
        labs_entity = db.get(Entity, ids["labs"])
        assert labs_entity is not None and labs_entity.owner_id == owner                       # the restored entity is Ann's again
        restored = db.execute(select(Fact).where(Fact.subject_id == ids["labs"])).scalar_one()
        assert restored.owner_id == owner                                                      # and so is its restored fact
    assert [x["name"] for x in ann.get("/api/entities?q=labs").json()["entities"]] == ["Acme Labs", "Zed Labs"]


def test_rebuilding_the_index_embeds_only_the_callers_passages(two):
    site, ann, bob, ids = two
    with site.factory() as db:
        from src.models.embedding import Embedding
        db.query(Embedding).delete()
        db.commit()
    r = ann.post("/api/index/rebuild").json()
    assert r["passages_added"] == 1 and r["facts_added"] == 2
    assert ann.get("/api/index/status").json()["passages_indexed"] == 1 and bob.get("/api/index/status").json()["passages_indexed"] == 0


def test_embedding_helpers_with_an_owner_leave_other_owners_passages_alone(two):
    site, ann, bob, ids = two
    from src.models.embedding import Embedding
    from src.services.embedding import ensure_chunk_embeddings
    from tests.conftest import FakeEmbedder
    with site.factory() as db:
        db.query(Embedding).delete()
        db.commit()
        assert ensure_chunk_embeddings(db, FakeEmbedder(), owner_id=ann.user["id"]) == 1
        assert db.scalar(select(func.count()).select_from(Embedding)) == 1
        assert ensure_chunk_embeddings(db, FakeEmbedder(), owner_id=bob.user["id"]) == 1
        assert ensure_chunk_embeddings(db, FakeEmbedder()) == 0


def test_a_guests_allowance_counts_only_their_own_documents(site, monkeypatch):
    from tests.conftest import use_settings
    use_settings(monkeypatch, require_login=True, guest_max_documents=2)
    ann = site.user("ann")
    for _ in range(3):
        add(ann, "A")
    g = site.client()
    g.post("/api/auth/guest")
    assert g.post("/api/documents/text", json={"title": "t", "text": DOCS["B"]}).status_code == 202
    assert g.post("/api/documents/text", json={"title": "t", "text": DOCS["B"]}).status_code == 202
    assert g.post("/api/documents/text", json={"title": "t", "text": DOCS["B"]}).status_code == 403


def test_passages_that_were_never_indexed_are_indexed_for_the_caller_when_they_ask(two, monkeypatch):
    site, ann, bob, ids = two
    from src.models.embedding import Embedding
    with site.factory() as db:
        db.query(Embedding).delete()
        db.commit()
    seen = []
    llm = ScriptedLLM(answer=lambda p: (seen.append(p), {"found": True, "answer": "x", "cited": []})[1])
    monkeypatch.setattr("src.api.query.get_llm", lambda s=None: llm)
    assert ann.post("/api/ask", json={"question": "What did Acme Corp acquire?", "mode": "vector"}).status_code == 200
    assert seen and "Acme Corp acquired Beta Systems" in seen[0] and "Zed" not in seen[0]
    with site.factory() as db:
        mine = {db.get(Chunk, e.chunk_id).document_id for e in db.query(Embedding).all()}
        assert mine == {ids["ann"]}                      # only Ann's passage was indexed; Bob's was left alone
