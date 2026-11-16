"""The job queue: documents are read here, a few at a time, instead of inside whichever request uploaded them.

Before this a document was read in a background task of the request that started it: a restart left documents "processing" for
ever, nothing could be cancelled, and one person's pile of uploads kept everyone else waiting behind a single lock.

How it works
* A job is a row in `jobs`. Enqueueing is one INSERT, so it is fast and survives restarts.
* Worker threads (MAX_CONCURRENT_DOCUMENTS of them) claim the next job with a conditional UPDATE, so two workers, or two
  server processes, never take the same one.
* The next job is chosen fairly, round robin between accounts: one account with ten documents queued does not make everyone
  else wait for all ten (the account served least recently goes first). An account never has two documents read at once.
* A running job beats a heartbeat from its own thread, even while a long model call is in progress. A job whose heartbeat stopped
  (the server was killed) is put back in the queue, up to JOB_MAX_ATTEMPTS tries; a clean shutdown puts it back for free.
* Cancelling a waiting job is immediate. A running one stops at its next checkpoint (before every passage) and leaves nothing behind.
"""
import logging
import os
import socket
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from src.core import database
from src.core.config import get_settings
from src.models.graph import Document, DocumentStatus
from src.models.job import ACTIVE, Job, JobKind, JobStatus
from src.services import pipeline
from src.services.cancel import JobCancelled

log = logging.getLogger(__name__)

HEARTBEAT_SECONDS = 10
REAPER_SECONDS = 15
POLL_SECONDS = 1.0
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
INLINE = False   # tests: run a job in the thread that enqueued it, as a background task used to


class QueueFull(Exception):
    """The account already has as many waiting and running jobs as it may have"""


class _State:
    wake = threading.Event()
    stop_event: threading.Event | None = None   # set when the running workers must stop; a fresh one per start()
    threads: list[threading.Thread] = []


state = _State()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- enqueue and order

def enqueue(db: Session, doc: Document, kind: str = JobKind.READ.value) -> tuple[Job, bool]:
    """Put a job for `doc` in the queue. Returns (job, created): a document that already has a waiting or running job gets
    that job back. Raises QueueFull. The caller commits and then calls notify()."""
    existing = db.execute(select(Job).where(Job.document_id == doc.id, Job.kind == kind, Job.status.in_(ACTIVE))).scalars().first()
    if existing is not None:
        return existing, False
    s = get_settings()
    active = len(db.execute(select(Job.id).where(Job.owner_id == doc.owner_id, Job.status.in_(ACTIVE))).all())
    if active >= s.max_queued_jobs_per_user:
        raise QueueFull(f"You already have {active} documents waiting or being read (the limit is {s.max_queued_jobs_per_user}): "
                        "wait for some to finish or cancel one")
    job = Job(kind=kind, status=JobStatus.QUEUED.value, owner_id=doc.owner_id, document_id=doc.id,
              max_attempts=max(1, s.job_max_attempts), created_at=_now())
    db.add(job)
    doc.status, doc.error, doc.finished_at = DocumentStatus.PENDING, None, None
    db.flush()
    return job, True


def notify() -> None:
    """Wake the workers now instead of at their next poll"""
    state.wake.set()
    if INLINE:
        run_pending()


_LONG_AGO = datetime(1970, 1, 1, tzinfo=timezone.utc)


def fair_order(queued: list[Job], last_started: dict, running_owners: set | frozenset = frozenset()) -> list[Job]:
    """The order queued jobs will start in: round robin between accounts. The account served least recently goes first (one
    that never was goes before everyone); each account's own jobs keep their age order. An account with a document running
    counts as just served. Without this an account with a long backlog would always be 'first in its own line' and keep
    jumping ahead of newer accounts."""
    lines: dict = {}
    for j in sorted(queued, key=lambda j: _aware(j.created_at)):
        lines.setdefault(j.owner_id, []).append(j)
    served = {o: (_aware(last_started.get(o)) or _LONG_AGO) for o in lines}
    clock = max([t for t in served.values()] + [_aware(j.created_at) for j in queued] + [_LONG_AGO]) + timedelta(seconds=1)
    for o in running_owners:
        if o in served:
            served[o] = clock
    out = []
    while lines:
        owner = min(lines, key=lambda o: (served[o], _aware(lines[o][0].created_at)))
        out.append(lines[owner].pop(0))
        if not lines[owner]:
            del lines[owner]
        clock += timedelta(seconds=1)
        served[owner] = clock
    return out


def _history(db: Session) -> tuple[dict, set]:
    """When each account last had a job started, and which accounts have a document being read right now"""
    last = {o: t for o, t in db.execute(select(Job.owner_id, func.max(Job.started_at)).group_by(Job.owner_id)).all()}
    running = {o for (o,) in db.execute(select(Job.owner_id).where(Job.status == JobStatus.RUNNING.value)).all()}
    return last, running


def queue_positions(db: Session) -> dict[str, int]:
    """job id -> 1-based place among all waiting jobs, in the order they will start"""
    queued = db.execute(select(Job).where(Job.status == JobStatus.QUEUED.value)).scalars().all()
    last, running = _history(db)
    return {j.id: i for i, j in enumerate(fair_order(queued, last, running), 1)}


# ---------------------------------------------------------------- claiming and running

def claim_next(db: Session, worker: str = WORKER_ID) -> Job | None:
    """Take the next job that may start now, or None. Accounts that already have a document being read are skipped
    (one at a time per account)."""
    queued = db.execute(select(Job).where(Job.status == JobStatus.QUEUED.value)).scalars().all()
    last, running = _history(db)
    for job in fair_order([j for j in queued if j.owner_id not in running], last, running):
        now = _now()
        taken = db.execute(update(Job).where(Job.id == job.id, Job.status == JobStatus.QUEUED.value).values(
            status=JobStatus.RUNNING.value, worker=worker, started_at=now, heartbeat_at=now, attempts=Job.attempts + 1,
            error=None)).rowcount
        db.commit()
        if taken:
            db.expire(job)
            return job
    return None


def check(job_id: str, worker: str = WORKER_ID, stop: threading.Event | None = None) -> None:
    """The pipeline's checkpoint: raises JobCancelled when this job must stop"""
    with database.SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            raise JobCancelled("deleted")
        if job.status != JobStatus.RUNNING.value or job.worker != worker:
            raise JobCancelled("lost")
        if stop is not None and stop.is_set():
            raise JobCancelled("shutdown")
        if job.cancel_requested:
            raise JobCancelled("cancelled")


class _Heartbeat(threading.Thread):
    """Keeps a running job alive while the worker is busy in a long model call"""

    def __init__(self, job_id: str, worker: str):
        super().__init__(daemon=True, name=f"heartbeat-{job_id[:8]}")
        self.job_id, self.worker, self._stop_event = job_id, worker, threading.Event()

    def run(self):
        while not self._stop_event.wait(HEARTBEAT_SECONDS):
            try:
                with database.session_scope() as db:
                    db.execute(update(Job).where(Job.id == self.job_id, Job.status == JobStatus.RUNNING.value, Job.worker == self.worker)
                               .values(heartbeat_at=_now()))
            except Exception:
                log.exception("Heartbeat for job %s failed", self.job_id)

    def stop(self):
        self._stop_event.set()


def run_job(job_id: str, worker: str = WORKER_ID, stop: threading.Event | None = None) -> str:
    """Run a claimed job to the end and record how it ended. Returns the outcome (see pipeline.process_document)."""
    with database.SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return "deleted"
        doc_id = job.document_id
    beat = _Heartbeat(job_id, worker)
    beat.start()
    try:
        outcome = pipeline.process_document(doc_id, checkpoint=lambda: check(job_id, worker, stop))
    except Exception:  # process_document does not raise; this is only a guard so the job never stays "running"
        log.exception("Job %s crashed", job_id)
        outcome = "failed"
    finally:
        beat.stop()
    _finish(job_id, worker, outcome)
    return outcome


def _finish(job_id: str, worker: str, outcome: str) -> None:
    with database.session_scope() as db:
        job = db.get(Job, job_id)
        if job is None or job.worker != worker or job.status != JobStatus.RUNNING.value:
            return  # deleted, or the reaper already took it over
        now = _now()
        if outcome == "completed":
            job.status, job.finished_at = JobStatus.COMPLETED.value, now
        elif outcome == "cancelled":
            job.status, job.finished_at = JobStatus.CANCELLED.value, now
        elif outcome in ("shutdown", "lost"):  # stopped by the server, not by the user: run again, and do not count the try
            job.status, job.worker, job.started_at, job.heartbeat_at = JobStatus.QUEUED.value, None, None, None
            job.attempts = max(job.attempts - 1, 0)
        else:
            doc = db.get(Document, job.document_id)
            job.status, job.finished_at = JobStatus.FAILED.value, now
            job.error = (doc.error if doc is not None else None) or "The document could not be read"


def run_pending(max_jobs: int = 1000, worker: str = WORKER_ID) -> int:
    """Run waiting jobs in this thread until none can start. Used by tests and by `python -m src.services.job_queue`."""
    done = 0
    while done < max_jobs:
        with database.SessionLocal() as db:
            job = claim_next(db, worker)
            job_id = job.id if job else None
        if job_id is None:
            return done
        run_job(job_id, worker)
        done += 1
    return done


# ---------------------------------------------------------------- cancelling, retrying, recovering

def request_cancel(db: Session, job: Job) -> Job:
    """A waiting job is cancelled at once; a running one is asked to stop and does so at its next checkpoint. The caller commits."""
    if job.status == JobStatus.QUEUED.value:
        job.status, job.finished_at = JobStatus.CANCELLED.value, _now()
        doc = db.get(Document, job.document_id)
        if doc is not None and doc.status == DocumentStatus.PENDING:
            doc.status, doc.error, doc.finished_at = DocumentStatus.FAILED, "Cancelled", _now()
    elif job.status == JobStatus.RUNNING.value:
        job.cancel_requested = True
    return job


def reap_stale(db: Session, now: datetime | None = None) -> tuple[int, int]:
    """Jobs that say they are running but whose heartbeat stopped: back in the queue, or failed once they used all their tries.
    Returns (requeued, failed). The caller commits."""
    now = now or _now()
    cutoff = now - timedelta(seconds=get_settings().job_stale_seconds)
    requeued = failed = 0
    for job in db.execute(select(Job).where(Job.status == JobStatus.RUNNING.value)).scalars().all():
        beat = _aware(job.heartbeat_at) or _aware(job.started_at) or _aware(job.created_at)
        if beat >= cutoff:
            continue
        doc = db.get(Document, job.document_id)
        if job.attempts >= job.max_attempts:
            job.status, job.finished_at = JobStatus.FAILED.value, now
            job.error = f"The worker stopped while reading this document (tried {job.attempts} times)"
            if doc is not None:
                doc.status, doc.error, doc.finished_at = DocumentStatus.FAILED, job.error, now
            failed += 1
        else:
            job.status, job.worker, job.started_at, job.heartbeat_at = JobStatus.QUEUED.value, None, None, None
            if doc is not None:
                doc.status = DocumentStatus.PENDING
            requeued += 1
    return requeued, failed


def recover_orphans() -> dict:
    """At startup: put back jobs whose worker died, and mark documents that are 'pending' or 'processing' with no job as interrupted."""
    with database.session_scope() as db:
        requeued, failed = reap_stale(db)
        active_docs = select(Job.document_id).where(Job.status.in_(ACTIVE))
        orphans = db.execute(select(Document).where(Document.status.in_([DocumentStatus.PROCESSING, DocumentStatus.PENDING]),
                                                    ~Document.id.in_(active_docs))).scalars().all()
        for doc in orphans:
            doc.status, doc.finished_at = DocumentStatus.FAILED, _now()
            doc.error = "Interrupted by a server restart. Use 'Read again' to process it."
        return {"requeued": requeued, "failed": failed, "interrupted_documents": len(orphans)}


def purge_old_jobs(days: int = 30) -> int:
    """Forget finished jobs older than `days` (the document keeps its own status and error)"""
    cutoff = _now() - timedelta(days=days)
    with database.session_scope() as db:
        return db.execute(Job.__table__.delete().where(Job.status.not_in(ACTIVE), Job.finished_at < cutoff)).rowcount


# ---------------------------------------------------------------- the worker threads

def _worker_loop(index: int, stop: threading.Event) -> None:
    worker = f"{WORKER_ID}#{index}"
    while not stop.is_set():
        try:
            with database.SessionLocal() as db:
                job = claim_next(db, worker)
                job_id = job.id if job else None
            if job_id:
                run_job(job_id, worker, stop)
                continue
        except Exception:
            log.exception("Worker %s failed", worker)
        state.wake.wait(POLL_SECONDS)
        state.wake.clear()


def _reaper_loop(stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            with database.session_scope() as db:
                requeued, failed = reap_stale(db)
            if requeued or failed:
                log.warning("Reaped stale jobs: %d requeued, %d failed", requeued, failed)
                notify()
        except Exception:
            log.exception("Reaper failed")
        if stop.wait(REAPER_SECONDS):
            return


def start(workers: int | None = None) -> None:
    if state.threads:
        return
    stop = state.stop_event = threading.Event()
    state.wake.clear()
    n = workers or get_settings().max_concurrent_documents
    state.threads = [threading.Thread(target=_worker_loop, args=(i, stop), daemon=True, name=f"job-worker-{i}") for i in range(n)]
    state.threads.append(threading.Thread(target=_reaper_loop, args=(stop,), daemon=True, name="job-reaper"))
    for t in state.threads:
        t.start()
    log.info("Job queue started with %d worker(s)", n)


def release_my_jobs() -> int:
    """Hand back the jobs this process's workers still hold (the model call they are in did not end in time): queued again,
    and the try is not counted. Returns how many."""
    with database.session_scope() as db:
        mine = db.execute(select(Job).where(Job.status == JobStatus.RUNNING.value, Job.worker.like(f"{WORKER_ID}#%"))).scalars().all()
        for job in mine:
            job.status, job.worker, job.started_at, job.heartbeat_at = JobStatus.QUEUED.value, None, None, None
            job.attempts = max(job.attempts - 1, 0)
            doc = db.get(Document, job.document_id)
            if doc is not None:
                doc.status, doc.error, doc.finished_at = DocumentStatus.PENDING, None, None
        return len(mine)


def stop(timeout: float = 10.0) -> None:
    """Stop the workers. A running job is stopped at its next checkpoint (before its next model call) and put back in the queue
    without using up a try. A worker deep in a model call cannot be interrupted: after `timeout` its job is handed back anyway
    and the thread is left to die with the process; a restarted server reads the document again from the start."""
    if state.stop_event is not None:
        state.stop_event.set()
    state.wake.set()
    for t in state.threads:
        t.join(timeout / max(len(state.threads), 1))
    state.threads, state.stop_event = [], None
    try:
        released = release_my_jobs()
        if released:
            log.info("Handed back %d job(s) that were still running at shutdown", released)
    except Exception:
        log.exception("Could not hand back running jobs at shutdown")
