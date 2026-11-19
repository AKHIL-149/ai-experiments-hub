import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from src.core.config import Settings
from src.models.graph import Document, DocumentStatus, Entity, Fact
from src.models.job import Job, JobStatus
from src.models.user import User
from src.services import job_queue, pipeline
from src.services.job_queue import QueueFull
from tests.conftest import FakeLLM, rel

TEXT = "Acme Corp acquired Beta Systems in March 2020."
RAW = [rel("Acme Corp", "acquired", "Beta Systems", TEXT, "March 2020", otype="organization", stype="organization")]
UTC = timezone.utc


@pytest.fixture(autouse=True)
def queue_env(factory, monkeypatch):
    """Queue tests drive the queue by hand: no inline running, small limits, a fake model"""
    monkeypatch.setattr(job_queue, "INLINE", False)
    s = Settings(_env_file=None, max_queued_jobs_per_user=3, job_max_attempts=2, job_stale_seconds=30, verify_facts=False,
                 gleaning_passes=0, auto_resolve=False, index_chunks=False)
    monkeypatch.setattr(job_queue, "get_settings", lambda: s)
    monkeypatch.setattr(pipeline, "get_settings", lambda: s)
    state = type("S", (), {})()
    state.llm = FakeLLM(extract=lambda p: {"relations": RAW})
    monkeypatch.setattr(pipeline, "get_llm", lambda settings=None: state.llm)
    state.settings = s
    return state


def make_user(db, name):
    u = User(username=name, password_hash="x")
    db.add(u)
    db.flush()
    return u


def make_doc(db, owner=None, text=TEXT, title="Doc"):
    d = Document(owner_id=owner, title=title, text=text, char_count=len(text))
    db.add(d)
    db.flush()
    return d


def job_of(db, doc):
    return db.execute(select(Job).where(Job.document_id == doc.id)).scalars().one()


def make_job(db, doc, **kw):
    j = Job(owner_id=doc.owner_id, document_id=doc.id, **kw)
    db.add(j)
    doc.status = DocumentStatus.PENDING
    db.flush()
    return j


# ---------------------------------------------------------------- enqueue

def test_enqueue_creates_a_waiting_job_and_marks_the_document_pending(db):
    d = make_doc(db)
    d.status = DocumentStatus.FAILED
    d.error = "old error"
    job, created = job_queue.enqueue(db, d)
    db.commit()
    assert created and job.status == "queued" and job.kind == "read" and job.attempts == 0 and job.max_attempts == 2
    assert job.owner_id is None and d.status == DocumentStatus.PENDING and d.error is None


def test_a_document_with_an_active_job_gets_that_job_back(db):
    d = make_doc(db)
    first, created = job_queue.enqueue(db, d)
    again, created2 = job_queue.enqueue(db, d)
    assert first.id == again.id and created and not created2
    first.status = "completed"
    db.flush()
    third, created3 = job_queue.enqueue(db, d)
    assert created3 and third.id != first.id          # a finished job does not block a new one


def test_an_account_may_only_have_so_many_active_jobs(db):
    u, v = make_user(db, "ann"), make_user(db, "bob")
    docs = [make_doc(db, u.id, title=f"d{i}") for i in range(4)]
    for d in docs[:3]:
        job_queue.enqueue(db, d)
    with pytest.raises(QueueFull, match="3 documents"):
        job_queue.enqueue(db, docs[3])
    job_queue.enqueue(db, make_doc(db, v.id))           # another account is not affected
    job_of(db, docs[0]).status = "completed"
    db.flush()
    job_queue.enqueue(db, docs[3])                      # finished jobs do not count


# ---------------------------------------------------------------- order

def jobs_at(owner, minutes, n=1):
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return [Job(id=f"{owner}.{i}", owner_id=owner, document_id="d", created_at=base + timedelta(minutes=minutes + i)) for i in range(n)]


def ids(jobs):
    return [j.id for j in jobs]


def test_fair_order_gives_each_account_a_turn():
    a, b = jobs_at(1, 0, 3), jobs_at(2, 5)
    assert ids(job_queue.fair_order(a + b, {})) == ["1.0", "2.0", "1.1", "1.2"]        # B does not wait for all of A's


def test_fair_order_does_not_depend_on_the_order_the_jobs_arrive_in():
    a, b = jobs_at(1, 0, 3), jobs_at(2, 5, 2)
    want = ids(job_queue.fair_order(a + b, {}))
    assert want == ["1.0", "2.0", "1.1", "2.1", "1.2"]
    assert ids(job_queue.fair_order(list(reversed(a)) + list(reversed(b)), {})) == want                    # as a database may return them
    assert ids(job_queue.fair_order([a[2], b[1], a[0], b[0], a[1]], {})) == want


def test_fair_order_serves_the_account_that_waited_longest_since_its_last_turn():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    a, b, c = jobs_at(1, 0, 2), jobs_at(2, 1, 2), jobs_at(3, 2, 2)
    last = {1: base + timedelta(hours=3), 2: base + timedelta(hours=1)}                   # A was served last, C never
    assert ids(job_queue.fair_order(a + b + c, last)) == ["3.0", "2.0", "1.0", "3.1", "2.1", "1.1"]


def test_an_account_with_a_document_running_counts_as_just_served():
    a, b = jobs_at(1, 0, 2), jobs_at(2, 5, 2)
    assert ids(job_queue.fair_order(a + b, {}, {1})) == ["2.0", "1.0", "2.1", "1.1"]
    assert ids(job_queue.fair_order(a + b, {}, {2})) == ["1.0", "2.0", "1.1", "2.1"]
    assert ids(job_queue.fair_order(a, {}, {9})) == ["1.0", "1.1"]                         # a running account with nothing queued is ignored


def test_an_account_with_a_long_backlog_does_not_keep_jumping_the_queue():
    """The flaw in 'place in my own line': once A's first job is done its second becomes first in line, and is older than B's"""
    a, b = jobs_at(1, 0, 3), jobs_at(2, 10)
    after_a_first = a[1:] + b
    assert ids(job_queue.fair_order(after_a_first, {1: datetime(2026, 1, 1, 0, 1, tzinfo=UTC)})) == ["2.0", "1.1", "1.2"]


def test_fair_order_handles_naive_times_empty_input_and_equal_ages():
    old = Job(id="old", owner_id=1, document_id="d", created_at=datetime(2026, 1, 1))              # naive, as SQLite returns them
    new = Job(id="new", owner_id=2, document_id="d", created_at=datetime(2026, 1, 2, tzinfo=UTC))
    assert ids(job_queue.fair_order([new, old], {})) == ["old", "new"]                                  # equal history: the older job first
    assert ids(job_queue.fair_order([new, old], {1: datetime(2025, 1, 1)})) == ["new", "old"]            # but 2 was never served
    assert job_queue.fair_order([], {}) == []
    same = datetime(2026, 1, 1, tzinfo=UTC)
    assert len(job_queue.fair_order([Job(id="x", owner_id=1, document_id="d", created_at=same), Job(id="y", owner_id=2, document_id="d", created_at=same)], {})) == 2


def test_queue_positions_cover_every_waiting_job(db):
    u, v = make_user(db, "ann"), make_user(db, "bob")
    a1, a2, b1 = make_doc(db, u.id), make_doc(db, u.id), make_doc(db, v.id)
    for d in (a1, a2, b1):
        job_queue.enqueue(db, d)
    db.commit()
    pos = job_queue.queue_positions(db)
    assert pos[job_of(db, a1).id] == 1 and pos[job_of(db, b1).id] == 2 and pos[job_of(db, a2).id] == 3


# ---------------------------------------------------------------- claiming

def test_claim_takes_the_next_job_and_marks_it_running(db):
    d = make_doc(db)
    job_queue.enqueue(db, d)
    db.commit()
    job = job_queue.claim_next(db, "w1")
    assert job.status == "running" and job.worker == "w1" and job.attempts == 1 and job.heartbeat_at and job.started_at
    assert job_queue.claim_next(db, "w2") is None


def test_an_account_has_one_document_read_at_a_time_but_others_run_alongside(db):
    u, v = make_user(db, "ann"), make_user(db, "bob")
    a1, a2, b1 = make_doc(db, u.id), make_doc(db, u.id), make_doc(db, v.id)
    for d in (a1, a2, b1):
        job_queue.enqueue(db, d)
    db.commit()
    first, second = job_queue.claim_next(db, "w1"), job_queue.claim_next(db, "w2")
    assert {first.document_id, second.document_id} == {a1.id, b1.id}      # a2 waits for a1
    assert job_queue.claim_next(db, "w3") is None
    first.status = second.status = "completed"
    db.commit()
    assert job_queue.claim_next(db, "w3").document_id == a2.id


def test_two_workers_cannot_take_the_same_job(db, factory, monkeypatch):
    d = make_doc(db)
    job_queue.enqueue(db, d)
    db.commit()
    stale = job_of(db, d)
    with factory() as other:                                              # another worker got there first
        other.get(Job, stale.id).status = "running"
        other.commit()
    monkeypatch.setattr(job_queue, "fair_order", lambda queued, last, running=frozenset(): [stale])
    assert job_queue.claim_next(db, "w1") is None


# ---------------------------------------------------------------- running

def test_a_job_reads_its_document(db, queue_env):
    d = make_doc(db)
    job_queue.enqueue(db, d)
    db.commit()
    assert job_queue.run_pending() == 1
    db.expire_all()
    assert job_of(db, d).status == "completed" and job_of(db, d).finished_at and d.status == DocumentStatus.COMPLETED
    assert db.scalar(select(func.count()).select_from(Fact)) == 1


def test_a_failed_read_fails_the_job_with_the_reason_and_is_not_retried(db, queue_env):
    from src.services.llm import LLMError
    queue_env.llm = FakeLLM(extract=lambda p: LLMError("Cannot reach Ollama at http://x"))
    d = make_doc(db)
    job_queue.enqueue(db, d)
    db.commit()
    job_queue.run_pending()
    db.expire_all()
    j = job_of(db, d)
    assert j.status == "failed" and "Cannot reach Ollama" in j.error and j.attempts == 1 and d.status == DocumentStatus.FAILED
    assert job_queue.run_pending() == 0                                    # a model that is down is not a reason to retry in a loop


def test_run_pending_reads_documents_in_fair_order_across_accounts(db, queue_env):
    seen = []
    queue_env.llm = FakeLLM(extract=lambda p: (seen.append(p.split("<<<\n")[1].split("\n")[0]), {"relations": []})[1])
    u, v = make_user(db, "ann"), make_user(db, "bob")
    for i in range(3):
        job_queue.enqueue(db, make_doc(db, u.id, text=f"Ann document number {i} is here today."))
    job_queue.enqueue(db, make_doc(db, v.id, text="Bob document is here today."))
    db.commit()
    assert job_queue.run_pending() == 4
    assert seen == ["Ann document number 0 is here today.", "Bob document is here today.", "Ann document number 1 is here today.",
                    "Ann document number 2 is here today."]


# ---------------------------------------------------------------- cancel

def test_cancelling_a_waiting_job_is_immediate(db):
    d = make_doc(db)
    job, _ = job_queue.enqueue(db, d)
    job_queue.request_cancel(db, job)
    db.commit()
    assert job.status == "cancelled" and job.finished_at and d.status == DocumentStatus.FAILED and d.error == "Cancelled"
    assert job_queue.run_pending() == 0


def test_cancelling_finished_jobs_changes_nothing(db):
    d = make_doc(db)
    job, _ = job_queue.enqueue(db, d)
    job.status = "completed"
    job_queue.request_cancel(db, job)
    assert job.status == "completed" and not job.cancel_requested


def long_text(n=40):
    return " ".join(f"Sentence {i} mentions Acme Corp and Beta Systems here today." for i in range(n))


def test_a_running_job_stops_at_the_next_passage_and_leaves_nothing_behind(db, factory, queue_env):
    s = queue_env.settings
    s.chunk_chars, s.chunk_overlap_chars = 400, 0
    d = make_doc(db, text=long_text())
    job_queue.enqueue(db, d)
    db.commit()
    calls = {"n": 0}

    def extract(prompt):
        calls["n"] += 1
        if calls["n"] == 3:                                              # the user presses cancel while the third passage is read
            with factory() as other:
                job_queue.request_cancel(other, other.execute(select(Job)).scalars().one())
                other.commit()
        passage = prompt.split("<<<\n")[1].split("\n>>>")[0]
        return {"relations": [rel("Acme Corp", "partnered with", "Beta Systems", passage.split(".")[0] + ".", otype="organization", stype="organization")]}

    queue_env.llm = FakeLLM(extract=extract)
    job_queue.run_pending()
    db.expire_all()
    assert calls["n"] == 3                                                # it did not read the passages after the cancel
    assert job_of(db, d).status == "cancelled" and d.status == DocumentStatus.FAILED and d.error == "Cancelled"
    assert db.scalar(select(func.count()).select_from(Fact)) == 0 and db.scalar(select(func.count()).select_from(Entity)) == 0
    assert d.chunk_count == 0 and d.chunks_done == 0


def test_a_shutdown_puts_the_job_back_without_using_a_try_and_it_runs_again(db, queue_env):
    s = queue_env.settings
    s.chunk_chars, s.chunk_overlap_chars = 400, 0
    d = make_doc(db, text=long_text())
    job_queue.enqueue(db, d)
    db.commit()
    stop = threading.Event()
    n = {"calls": 0}

    def extract(prompt):
        n["calls"] += 1
        if n["calls"] == 2:
            stop.set()
        return {"relations": []}

    queue_env.llm = FakeLLM(extract=extract)
    claimed = job_queue.claim_next(db, "w1")
    outcome = job_queue.run_job(claimed.id, "w1", stop)
    db.expire_all()
    j = job_of(db, d)
    assert outcome == "shutdown" and j.status == "queued" and j.attempts == 0 and j.worker is None and j.heartbeat_at is None
    assert d.status == DocumentStatus.PENDING and d.error is None and d.chunk_count == 0
    queue_env.llm = FakeLLM(extract=lambda p: {"relations": []})
    assert job_queue.run_pending() == 1
    db.expire_all()
    assert job_of(db, d).status == "completed" and job_of(db, d).attempts == 1


def test_a_job_taken_over_by_someone_else_is_left_alone(db, factory, queue_env):
    d = make_doc(db, text=long_text())
    job_queue.enqueue(db, d)
    db.commit()

    def extract(prompt):
        with factory() as other:                                          # the reaper decided this worker was dead
            j = other.execute(select(Job)).scalars().one()
            j.worker, j.status = "somebody-else", "running"
            other.commit()
        return {"relations": []}

    queue_env.llm = FakeLLM(extract=extract)
    claimed = job_queue.claim_next(db, "w1")
    assert job_queue.run_job(claimed.id, "w1") == "lost"
    db.expire_all()
    j = job_of(db, d)
    assert j.worker == "somebody-else" and j.status == "running"          # not overwritten with this worker's result


def test_a_job_deleted_while_running_stops_quietly(db, factory, queue_env):
    d = make_doc(db, text=long_text())
    job_queue.enqueue(db, d)
    db.commit()

    def extract(prompt):
        with factory() as other:
            other.delete(other.execute(select(Job)).scalars().one())
            other.commit()
        return {"relations": []}

    queue_env.llm = FakeLLM(extract=extract)
    claimed = job_queue.claim_next(db, "w1")
    assert job_queue.run_job(claimed.id, "w1") == "deleted"
    assert db.scalar(select(func.count()).select_from(Job)) == 0


def test_checkpoint_reasons(db):
    from src.services.cancel import JobCancelled
    d = make_doc(db)
    job_queue.enqueue(db, d)
    db.commit()
    j = job_queue.claim_next(db, "w1")
    job_queue.check(j.id, "w1")                                           # fine
    with pytest.raises(JobCancelled) as e:
        job_queue.check(j.id, "other-worker")
    assert e.value.reason == "lost"
    with pytest.raises(JobCancelled) as e:
        job_queue.check("nope", "w1")
    assert e.value.reason == "deleted"
    stop = threading.Event()
    stop.set()
    with pytest.raises(JobCancelled) as e:
        job_queue.check(j.id, "w1", stop)
    assert e.value.reason == "shutdown"
    j.cancel_requested = True
    db.commit()
    with pytest.raises(JobCancelled) as e:
        job_queue.check(j.id, "w1")
    assert e.value.reason == "cancelled"


# ---------------------------------------------------------------- stale jobs and restarts

def running_job(db, doc, ago, attempts=1, **kw):
    j = make_job(db, doc, status="running", worker="dead", attempts=attempts, max_attempts=2,
                 heartbeat_at=datetime.now(UTC) - timedelta(seconds=ago), started_at=datetime.now(UTC) - timedelta(seconds=ago), **kw)
    doc.status = DocumentStatus.PROCESSING
    db.flush()
    return j


def test_a_job_with_a_stale_heartbeat_goes_back_in_the_queue(db):
    stale, fresh = make_doc(db, title="stale"), make_doc(db, title="fresh")
    js, jf = running_job(db, stale, ago=120), running_job(db, fresh, ago=5)
    db.commit()
    assert job_queue.reap_stale(db) == (1, 0)
    db.commit()
    assert js.status == "queued" and js.worker is None and js.heartbeat_at is None and stale.status == DocumentStatus.PENDING
    assert jf.status == "running" and fresh.status == DocumentStatus.PROCESSING


def test_a_job_that_used_all_its_tries_fails_with_a_reason(db):
    d = make_doc(db)
    j = running_job(db, d, ago=120, attempts=2)
    db.commit()
    assert job_queue.reap_stale(db) == (0, 1)
    db.commit()
    assert j.status == "failed" and "tried 2 times" in j.error and j.finished_at
    assert d.status == DocumentStatus.FAILED and "tried 2 times" in d.error


def test_a_running_job_without_any_heartbeat_is_judged_by_when_it_started(db):
    d = make_doc(db)
    j = running_job(db, d, ago=120)
    j.heartbeat_at = None
    db.commit()
    assert job_queue.reap_stale(db) == (1, 0)


def test_stale_times_from_sqlite_without_a_timezone_are_understood(db):
    d = make_doc(db)
    j = running_job(db, d, ago=120)
    db.commit()
    db.expire_all()
    assert job_queue._aware(j.heartbeat_at).tzinfo is not None
    assert job_queue.reap_stale(db, now=datetime.now(UTC) + timedelta(seconds=1)) == (1, 0)


def test_startup_recovery(db):
    u = make_user(db, "ann")
    crashed, waiting, orphan, fine, orphan_pending = (make_doc(db, u.id, title=t) for t in ("crashed", "waiting", "orphan", "fine", "orphan2"))
    running_job(db, crashed, ago=300)
    job_queue.enqueue(db, waiting)
    orphan.status = DocumentStatus.PROCESSING                              # was being read, no job row (from before the queue existed)
    orphan_pending.status = DocumentStatus.PENDING
    fine.status = DocumentStatus.COMPLETED
    db.commit()
    assert job_queue.recover_orphans() == {"requeued": 1, "failed": 0, "interrupted_documents": 2}
    db.expire_all()
    assert crashed.status == DocumentStatus.PENDING and waiting.status == DocumentStatus.PENDING and fine.status == DocumentStatus.COMPLETED
    assert orphan.status == DocumentStatus.FAILED and "restart" in orphan.error and orphan_pending.status == DocumentStatus.FAILED
    assert job_queue.recover_orphans() == {"requeued": 0, "failed": 0, "interrupted_documents": 0}


def test_old_finished_jobs_are_forgotten_but_active_ones_are_not(db):
    old, active, recent = make_doc(db, title="o"), make_doc(db, title="a"), make_doc(db, title="r")
    jo = make_job(db, old, status="completed", finished_at=datetime.now(UTC) - timedelta(days=40))
    ja = make_job(db, active, status="queued")
    jr = make_job(db, recent, status="failed", finished_at=datetime.now(UTC) - timedelta(days=2))
    db.commit()
    assert job_queue.purge_old_jobs(30) == 1
    assert {j.id for j in db.execute(select(Job)).scalars()} == {ja.id, jr.id}


def test_purging_never_touches_a_waiting_or_running_job_even_with_a_stale_finish_time(db):
    """A job that is still active has no finish time; if one ever had an old one it must still not be deleted"""
    a, b = make_doc(db, title="a"), make_doc(db, title="b")
    old = datetime.now(UTC) - timedelta(days=90)
    queued = make_job(db, a, status="queued", finished_at=old)
    running = make_job(db, b, status="running", finished_at=old)
    db.commit()
    assert job_queue.purge_old_jobs(30) == 0
    assert {j.id for j in db.execute(select(Job)).scalars()} == {queued.id, running.id}


def test_a_run_that_finds_it_lost_the_job_puts_it_back_without_using_a_try(db, queue_env, monkeypatch):
    d = make_doc(db)
    job_queue.enqueue(db, d)
    db.commit()
    monkeypatch.setattr(job_queue.pipeline, "process_document", lambda *a, **k: "lost")
    claimed = job_queue.claim_next(db, "w1")
    assert job_queue.run_job(claimed.id, "w1") == "lost"
    db.expire_all()
    j = job_of(db, d)
    assert j.status == "queued" and j.attempts == 0 and j.worker is None and j.started_at is None and j.heartbeat_at is None


# ---------------------------------------------------------------- the heartbeat and the worker threads

def test_the_heartbeat_keeps_a_job_alive_during_a_long_call(db, monkeypatch):
    monkeypatch.setattr(job_queue, "HEARTBEAT_SECONDS", 0.05)
    d = make_doc(db)
    job_queue.enqueue(db, d)
    db.commit()
    j = job_queue.claim_next(db, "w1")
    first = j.heartbeat_at
    beat = job_queue._Heartbeat(j.id, "w1")
    beat.start()
    time.sleep(0.4)
    beat.stop()
    beat.join(1)
    db.expire_all()
    assert job_queue._aware(db.get(Job, j.id).heartbeat_at) > job_queue._aware(first)
    assert not beat.is_alive()


def test_the_heartbeat_does_not_touch_a_job_that_is_not_ours(db, monkeypatch):
    monkeypatch.setattr(job_queue, "HEARTBEAT_SECONDS", 0.05)
    d = make_doc(db)
    job_queue.enqueue(db, d)
    db.commit()
    j = job_queue.claim_next(db, "w1")
    before = job_queue._aware(j.heartbeat_at)
    beat = job_queue._Heartbeat(j.id, "somebody-else")
    beat.start()
    time.sleep(0.25)
    beat.stop()
    db.expire_all()
    assert job_queue._aware(db.get(Job, j.id).heartbeat_at) == before


def wait_for(cond, seconds=8.0):
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_worker_threads_pick_up_new_jobs_and_stop_cleanly(db, factory, monkeypatch):
    job_queue.start(workers=1)
    try:
        d = make_doc(db)
        job_queue.enqueue(db, d)
        db.commit()
        job_queue.notify()
        done = lambda: factory().get(Job, job_of(db, d).id).status == "completed"  # noqa: E731
        assert wait_for(done)
    finally:
        job_queue.stop()
    assert job_queue.state.threads == [] and job_queue.state.stop_event is None


def test_starting_twice_starts_one_set_of_workers(db):
    job_queue.start(workers=2)
    try:
        threads = list(job_queue.state.threads)
        job_queue.start(workers=2)
        assert job_queue.state.threads == threads and len(threads) == 3      # two workers and the reaper
    finally:
        job_queue.stop()


def test_stopping_the_workers_while_a_document_is_being_read_requeues_it(db, factory, queue_env):
    s = queue_env.settings
    s.chunk_chars, s.chunk_overlap_chars = 400, 0
    d = make_doc(db, text=long_text())
    job_queue.enqueue(db, d)
    db.commit()
    started, release = threading.Event(), threading.Event()

    def extract(prompt):
        started.set()
        release.wait(5)
        return {"relations": []}

    queue_env.llm = FakeLLM(extract=extract)
    job_queue.start(workers=1)
    job_queue.notify()
    assert started.wait(5)                                                # the worker is inside a model call
    threading.Timer(0.3, release.set).start()
    job_queue.stop(timeout=6)
    with factory() as check:
        j = check.execute(select(Job)).scalars().one()
        assert j.status == "queued" and j.attempts == 0 and check.get(Document, d.id).status == DocumentStatus.PENDING


def test_jobs_still_running_when_the_workers_are_stopped_are_handed_back_for_free(db, factory, queue_env):
    d = make_doc(db)
    job_queue.enqueue(db, d)
    db.commit()
    started, release = threading.Event(), threading.Event()

    def extract(prompt):
        started.set()
        release.wait(10)                      # a model call that outlasts the shutdown
        return {"relations": []}

    queue_env.llm = FakeLLM(extract=extract)
    job_queue.start(workers=1)
    job_queue.notify()
    assert started.wait(5)
    t0 = time.time()
    job_queue.stop(timeout=0.6)               # cannot wait for the model call
    assert time.time() - t0 < 3
    with factory() as check:
        j = check.execute(select(Job)).scalars().one()
        assert j.status == "queued" and j.attempts == 0 and j.worker is None and check.get(Document, d.id).status == DocumentStatus.PENDING
    release.set()                             # the abandoned thread wakes up: it must not overwrite what shutdown recorded
    time.sleep(1.0)
    with factory() as check:
        j = check.execute(select(Job)).scalars().one()
        assert j.status == "queued" and j.attempts == 0


def test_release_only_touches_this_processes_jobs(db):
    mine, theirs = make_doc(db, title="mine"), make_doc(db, title="theirs")
    jm = make_job(db, mine, status="running", worker=f"{job_queue.WORKER_ID}#0", attempts=1)
    jt = make_job(db, theirs, status="running", worker="otherhost:1#0", attempts=1)
    db.commit()
    assert job_queue.release_my_jobs() == 1
    db.expire_all()
    assert jm.status == "queued" and jm.attempts == 0 and jt.status == "running" and jt.attempts == 1
