import pytest
from sqlalchemy import func, select

from src.core.config import Settings
from src.models.graph import Document
from src.models.job import Job
from src.services import job_queue
from tests.test_accounts import DOCS, site  # noqa: F401  (the fixture: the real app, sign-in on, a fake model)


@pytest.fixture
def q(site, monkeypatch):
    """The accounts site, with the queue driven by hand and a small per-account limit"""
    s = Settings(_env_file=None, max_queued_jobs_per_user=3, verify_facts=False, gleaning_passes=0, index_chunks=False)
    monkeypatch.setattr(job_queue, "INLINE", False)
    monkeypatch.setattr(job_queue, "get_settings", lambda: s)
    return site


def add(client, key="A", title=None):
    r = client.post("/api/documents/text", json={"title": title or f"Doc {key}", "text": DOCS[key]})
    assert r.status_code == 202, r.text
    return r.json()


def test_upload_queues_a_job_and_the_document_waits(q):
    ann = q.user("ann")
    doc = add(ann)
    assert doc["status"] == "pending" and doc["job"]["status"] == "queued" and doc["job"]["position"] == 1 and doc["job"]["attempts"] == 0
    assert ann.get(f"/api/documents/{doc['id']}").json()["job"]["status"] == "queued"
    assert ann.get("/api/documents").json()["documents"][0]["job"]["id"] == doc["job"]["id"]
    assert ann.get("/api/graph/stats").json()["facts"] == 0                         # nothing is read until a worker takes it


def test_a_worker_reads_it_and_both_the_document_and_the_job_say_so(q):
    ann = q.user("ann")
    doc = add(ann)
    assert job_queue.run_pending() == 1
    got = ann.get(f"/api/documents/{doc['id']}").json()
    assert got["status"] == "completed" and got["job"]["status"] == "completed" and got["job"]["finished_at"] and got["job"]["position"] is None
    assert ann.get("/api/graph/stats").json()["facts"] == 2


def test_an_account_cannot_queue_more_than_its_limit(q):
    ann, bob = q.user("ann"), q.user("bob")
    for _ in range(3):
        add(ann)
    r = ann.post("/api/documents/text", json={"title": "t", "text": DOCS["A"]})
    assert r.status_code == 429 and "3 documents" in r.json()["detail"]
    assert len(ann.get("/api/documents").json()["documents"]) == 3                 # the refused one was not kept
    add(bob)                                                                         # another account is not affected
    job_queue.run_pending()
    assert ann.post("/api/documents/text", json={"title": "t", "text": DOCS["A"]}).status_code == 202   # room again once some are done


def test_jobs_are_listed_with_their_place_in_the_fair_order(q):
    ann, bob = q.user("ann"), q.user("bob")
    a1, a2, b1 = add(ann, "A", "a1"), add(ann, "A", "a2"), add(bob, "B", "b1")
    jobs = {j["document_title"]: j for j in ann.get("/api/jobs").json()["jobs"]}
    assert jobs["a1"]["position"] == 1 and jobs["a2"]["position"] == 3 and set(jobs) == {"a1", "a2"}          # Bob's job sits between
    assert bob.get("/api/jobs").json()["jobs"][0]["position"] == 2
    job_queue.run_pending(max_jobs=1)
    jobs = {j["document_title"]: j for j in ann.get("/api/jobs").json()["jobs"]}
    assert jobs["a1"]["status"] == "completed" and jobs["a2"]["position"] == 2                                  # Bob is next now


def test_the_job_list_can_be_filtered(q):
    ann = q.user("ann")
    add(ann)
    add(ann)
    job_queue.run_pending(max_jobs=1)
    assert len(ann.get("/api/jobs").json()["jobs"]) == 2
    assert [j["status"] for j in ann.get("/api/jobs?status=active").json()["jobs"]] == ["queued"]
    assert [j["status"] for j in ann.get("/api/jobs?status=completed").json()["jobs"]] == ["completed"]
    assert ann.get("/api/jobs?status=banana").status_code == 422


def test_cancelling_a_waiting_job(q):
    ann = q.user("ann")
    doc = add(ann)
    r = ann.post(f"/api/jobs/{doc['job']['id']}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    got = ann.get(f"/api/documents/{doc['id']}").json()
    assert got["status"] == "failed" and got["error"] == "Cancelled"
    assert job_queue.run_pending() == 0
    assert ann.post(f"/api/jobs/{doc['job']['id']}/cancel").status_code == 409                  # already over
    assert ann.post("/api/jobs/nope/cancel").status_code == 404


def test_cancelling_a_running_job_asks_it_to_stop(q, factory):
    ann = q.user("ann")
    doc = add(ann)
    with factory() as db:
        claimed = job_queue.claim_next(db, "w1")
        job_id = claimed.id
    r = ann.post(f"/api/jobs/{job_id}/cancel").json()
    assert r["status"] == "running" and r["cancel_requested"] is True                          # it stops at its next checkpoint
    assert job_queue.run_job(job_id, "w1") == "cancelled"
    got = ann.get(f"/api/documents/{doc['id']}").json()
    assert got["job"]["status"] == "cancelled" and got["status"] == "failed" and got["error"] == "Cancelled"


def test_a_document_that_is_waiting_cannot_be_deleted_or_queued_twice(q):
    ann = q.user("ann")
    doc = add(ann)
    assert ann.delete(f"/api/documents/{doc['id']}").status_code == 409
    assert ann.post(f"/api/documents/{doc['id']}/reprocess").status_code == 409
    ann.post(f"/api/jobs/{doc['job']['id']}/cancel")
    assert ann.delete(f"/api/documents/{doc['id']}").status_code == 204
    with q.factory() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 0                             # the job went with its document


def test_reading_again_queues_a_new_job(q):
    ann = q.user("ann")
    doc = add(ann)
    job_queue.run_pending()
    r = ann.post(f"/api/documents/{doc['id']}/reprocess")
    assert r.status_code == 202 and r.json()["job"]["status"] == "queued" and r.json()["job"]["id"] != doc["job"]["id"]
    job_queue.run_pending()
    assert len(ann.get("/api/jobs").json()["jobs"]) == 2 and ann.get(f"/api/documents/{doc['id']}").json()["status"] == "completed"


def test_reading_again_is_limited_like_uploading(q):
    ann = q.user("ann")
    docs = [add(ann) for _ in range(3)]
    job_queue.run_pending(max_jobs=1)
    extra = add(ann)                                                                           # 2 waiting + 1 new = 3
    r = ann.post(f"/api/documents/{docs[0]['id']}/reprocess")
    assert r.status_code == 429


def test_another_accounts_jobs_answer_404(q):
    ann, bob = q.user("ann"), q.user("bob")
    doc = add(ann)
    job_id = doc["job"]["id"]
    missing = "00000000-0000-0000-0000-000000000000"
    for method, url in (("get", f"/api/jobs/{job_id}"), ("post", f"/api/jobs/{job_id}/cancel")):
        foreign, absent = getattr(bob, method)(url), getattr(bob, method)(url.replace(job_id, missing))
        assert foreign.status_code == absent.status_code == 404 and foreign.json() == absent.json()
    assert bob.get("/api/jobs").json()["jobs"] == []
    assert ann.get(f"/api/jobs/{job_id}").json()["status"] == "queued"                           # untouched


def test_jobs_need_a_sign_in(q):
    c = q.client()
    assert c.get("/api/jobs").status_code == 401 and c.post("/api/jobs/x/cancel").status_code == 401


def test_deleting_an_account_removes_its_jobs_too(q):
    ann = q.user("ann")
    add(ann)
    with q.factory() as db:
        from src.models.user import User
        db.delete(db.get(User, ann.user["id"]))
        db.commit()
        assert db.scalar(select(func.count()).select_from(Job)) == 0 and db.scalar(select(func.count()).select_from(Document)) == 0


def test_the_server_starts_and_stops_the_workers(tmp_path, monkeypatch):
    import server
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker
    from src.core import database
    from tests.conftest import use_settings
    use_settings(monkeypatch, require_login=True)
    monkeypatch.setattr(server, "get_settings", lambda: Settings(_env_file=None, job_workers_enabled=True, max_concurrent_documents=2))
    monkeypatch.setattr(job_queue, "get_settings", lambda: Settings(_env_file=None, max_concurrent_documents=2))
    engine = database.make_engine(f"sqlite:///{tmp_path}/s.db")
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine, autoflush=False, expire_on_commit=False))
    with TestClient(server.app):
        assert len(job_queue.state.threads) == 3                                               # two workers and the reaper
    assert job_queue.state.threads == []
