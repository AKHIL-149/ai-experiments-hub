"""
The job queue: downloads and video analysis run here, a few at a time, instead of all at once inside
whatever request happened to start them.

Before this, every upload started its own pipeline the moment it arrived. Five uploads meant five Whisper,
CLIP and vision-model runs fighting over one CPU and its memory; a server restart left videos "processing"
for ever; nothing could be cancelled or retried; and a YouTube download froze the whole server while it ran.

How it works
* A job is a row in `jobs` (see models/job.py). Enqueueing is one INSERT, so it is fast and survives restarts.
* Workers (MAX_CONCURRENT_VIDEOS analysis workers, MAX_CONCURRENT_DOWNLOADS download workers) claim the next
  job with a conditional UPDATE, so two workers, or two server processes, never take the same one.
* The next job is chosen fairly: one account with twenty videos queued does not make everyone else wait for
  all twenty (order = how many jobs the account already has running + its place in its own line, then age).
* A running job beats a heartbeat. A job whose heartbeat stopped (the server was killed) is put back in the
  queue, up to JOB_MAX_ATTEMPTS tries; a clean shutdown puts it back without using up a try.
* Cancelling a waiting job is immediate. A running one is asked to stop and does so at the next checkpoint
  (between pipeline stages and after every scene); a transcription that is already running finishes first.
"""

import asyncio
import logging
import os
import socket
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from src.core import database
from src.core.config import settings
from src.models.job import ACTIVE_STATUSES, Job, JobKind, JobStatus
from src.models.video import Video, VideoStatus
from src.utils.input_checks import short_error

logger = logging.getLogger(__name__)

HEARTBEAT_SECONDS = 10
REAPER_SECONDS = 15
POLL_SECONDS = 1.0
LANES = {
    "process": (JobKind.PROCESS.value,),
    "download": (JobKind.DOWNLOAD.value,),
}


class QueueFull(Exception):
    """The account already has as many waiting and running jobs as it may have"""


class JobCancelled(Exception):
    """Raised inside a running job when it should stop: reason is cancelled, shutdown, deleted or lost"""

    def __init__(self, reason: str = "cancelled"):
        super().__init__(reason)
        self.reason = reason


@dataclass
class JobContext:
    """What a runner gets: which job, which video, and a way to notice it should stop"""
    job_id: str
    kind: str
    video_id: str            # the video's public id
    user_id: Optional[int]
    payload: Dict[str, Any] = field(default_factory=dict)

    def check_cancel(self) -> None:
        check_cancel(self.job_id)


Runner = Callable[[JobContext], Awaitable[None]]


class _State:
    shutting_down = False
    loop: Optional[asyncio.AbstractEventLoop] = None
    wake: Optional[asyncio.Event] = None
    runners: Dict[str, Runner] = {}
    tasks: List[asyncio.Task] = []


state = _State()
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


def _session() -> Session:
    return database.SessionLocal()


# ---------------------------------------------------------------------------
# Enqueue and order
# ---------------------------------------------------------------------------

def enqueue(db: Session, video: Video, kind: str, payload: Optional[dict] = None) -> Tuple[Job, bool]:
    """
    Put a job for `video` in the queue. Returns (job, created); a video that already has a waiting or
    running job of this kind gets that job back instead of a second one. The caller commits.
    """
    existing = (
        db.query(Job)
        .filter(Job.video_id == video.id, Job.kind == kind, Job.status.in_(ACTIVE_STATUSES))
        .first()
    )
    if existing is not None:
        return existing, False

    if video.user_id is not None:
        active = db.query(Job).filter(Job.user_id == video.user_id, Job.status.in_(ACTIVE_STATUSES)).count()
        if active >= settings.max_queued_jobs_per_user:
            raise QueueFull(
                f"You already have {active} videos waiting or running (the limit is "
                f"{settings.max_queued_jobs_per_user}): wait for some to finish or cancel one"
            )

    job = Job(
        id=str(uuid.uuid4()), kind=kind, status=JobStatus.QUEUED.value, video_id=video.id, user_id=video.user_id,
        payload=payload or {}, max_attempts=max(1, settings.job_max_attempts), created_at=datetime.utcnow(),
    )
    db.add(job)
    db.flush()
    return job, True


def notify() -> None:
    """Wake the workers now instead of at their next poll (safe to call from any thread)"""
    loop, wake = state.loop, state.wake
    if loop is not None and wake is not None:
        try:
            loop.call_soon_threadsafe(wake.set)
        except RuntimeError:  # the loop is closed: shutting down
            pass


def fair_order(db: Session, queued: Sequence[Job]) -> List[Job]:
    """
    The order the queued jobs will start in. Each job's rank is (jobs its account has running) + (its place
    in its own account's line); ties go to the older job. One account's long line therefore interleaves with
    everyone else's instead of blocking it.
    """
    running: Dict[Optional[int], int] = {}
    for user_id, count in (
        db.query(Job.user_id, func.count(Job.id)).filter(Job.status == JobStatus.RUNNING.value).group_by(Job.user_id)
    ):
        running[user_id] = count

    seen: Dict[Optional[int], int] = {}
    ranked = []
    for job in sorted(queued, key=lambda j: (j.created_at, j.id)):
        place = seen.get(job.user_id, 0)
        seen[job.user_id] = place + 1
        ranked.append((running.get(job.user_id, 0) + place, job.created_at, job.id, job))
    ranked.sort(key=lambda r: r[:3])
    return [r[3] for r in ranked]


def queued_in_lane(db: Session, kind: str) -> List[Job]:
    jobs = db.query(Job).filter(Job.status == JobStatus.QUEUED.value, Job.kind == kind).limit(1000).all()
    return fair_order(db, jobs)


def queue_positions(db: Session) -> Dict[str, int]:
    """job id -> place in its lane (1 = starts next), for every waiting job"""
    positions: Dict[str, int] = {}
    for kind in (JobKind.PROCESS.value, JobKind.DOWNLOAD.value):
        for place, job in enumerate(queued_in_lane(db, kind), start=1):
            positions[job.id] = place
    return positions


def active_jobs_for_videos(db: Session, video_ids: Sequence[int]) -> Dict[int, Job]:
    """video row id -> its waiting or running job (the newest if there are several)"""
    if not video_ids:
        return {}
    rows = (
        db.query(Job).filter(Job.video_id.in_(list(video_ids)), Job.status.in_(ACTIVE_STATUSES))
        .order_by(Job.created_at).all()
    )
    return {job.video_id: job for job in rows}


# ---------------------------------------------------------------------------
# Claim, finish, cancel, retry
# ---------------------------------------------------------------------------

def claim(kinds: Sequence[str], worker: str) -> Optional[Job]:
    """Take the next waiting job of these kinds; None when there is none (or another worker was faster)"""
    db = _session()
    try:
        candidates: List[Job] = []
        for kind in kinds:
            candidates.extend(queued_in_lane(db, kind))
        candidates = fair_order(db, candidates)
        for job in candidates[:20]:
            now = datetime.utcnow()
            taken = db.execute(
                update(Job)
                .where(Job.id == job.id, Job.status == JobStatus.QUEUED.value)
                .values(status=JobStatus.RUNNING.value, started_at=now, heartbeat_at=now, worker=worker,
                        attempts=Job.attempts + 1, finished_at=None)
            ).rowcount
            db.commit()
            if taken == 1:
                db.refresh(job)
                db.expunge(job)
                return job
        return None
    finally:
        db.close()


def _video_ext_id(db: Session, video_row_id: int) -> Optional[str]:
    row = db.query(Video.external_id).filter(Video.id == video_row_id).first()
    return row[0] if row else None


def finish(job_id: str, status: JobStatus, error: Optional[str] = None) -> None:
    db = _session()
    try:
        db.execute(
            update(Job).where(Job.id == job_id).values(
                status=status.value, error=(error or None), finished_at=datetime.utcnow(), worker=None
            )
        )
        db.commit()
    finally:
        db.close()


def put_back(job_id: str, use_attempt: bool) -> None:
    """Return a job to the queue (interrupted by a restart): a clean shutdown does not cost a try"""
    db = _session()
    try:
        values = {"status": JobStatus.QUEUED.value, "worker": None, "heartbeat_at": None, "started_at": None}
        if not use_attempt:
            values["attempts"] = Job.attempts - 1  # a running job has always been claimed, so attempts >= 1
        db.execute(update(Job).where(Job.id == job_id, Job.status == JobStatus.RUNNING.value).values(**values))
        db.commit()
    finally:
        db.close()


def check_cancel(job_id: str) -> None:
    """Called by a running job at its checkpoints: raises JobCancelled when it should stop"""
    if state.shutting_down:
        raise JobCancelled("shutdown")
    db = _session()
    try:
        row = db.query(Job.status, Job.cancel_requested).filter(Job.id == job_id).first()
    finally:
        db.close()
    if row is None:
        raise JobCancelled("deleted")
    if row.status != JobStatus.RUNNING.value:
        raise JobCancelled("lost")  # reaped and handed to someone else while this one was still working
    if row.cancel_requested:
        raise JobCancelled("cancelled")


def request_cancel(db: Session, job: Job) -> str:
    """
    Cancel a job. A waiting one is cancelled on the spot (its video goes back to how it was before it was
    queued); a running one is asked to stop at its next checkpoint. Returns the job's new status.
    """
    if job.status == JobStatus.QUEUED.value:
        job.status = JobStatus.CANCELLED.value
        job.finished_at = datetime.utcnow()
        job.error = None
        restore_video_after_stop(db, job)
    elif job.status == JobStatus.RUNNING.value:
        job.cancel_requested = True
    return job.status


def restore_video_after_stop(db: Session, job: Job) -> None:
    """A job that stopped without finishing leaves its video in a state the person can act on"""
    video = db.query(Video).filter(Video.id == job.video_id).first()
    if video is None:
        return
    if job.kind == JobKind.DOWNLOAD.value and not video.file_path:
        video.processing_status = VideoStatus.FAILED
        video.error_message = "Download cancelled"
    elif video.processing_status in (VideoStatus.PROCESSING, VideoStatus.PENDING, VideoStatus.DOWNLOADING):
        video.processing_status = VideoStatus.PENDING
        video.error_message = "Processing cancelled"


def retry(db: Session, job: Job) -> Job:
    """Queue a failed or cancelled job again (same row, so its id stays valid for the page)"""
    if job.status not in (JobStatus.FAILED.value, JobStatus.CANCELLED.value):
        raise ValueError("Only a failed or cancelled job can be retried")
    clash = (
        db.query(Job)
        .filter(Job.video_id == job.video_id, Job.kind == job.kind, Job.status.in_(ACTIVE_STATUSES), Job.id != job.id)
        .first()
    )
    if clash is not None:
        raise ValueError("This video already has a job waiting or running")
    if job.user_id is not None:
        active = db.query(Job).filter(Job.user_id == job.user_id, Job.status.in_(ACTIVE_STATUSES)).count()
        if active >= settings.max_queued_jobs_per_user:
            raise QueueFull(f"You already have {active} videos waiting or running")

    job.status = JobStatus.QUEUED.value
    job.attempts = 0
    job.error = None
    job.cancel_requested = False
    job.worker = None
    job.started_at = job.finished_at = job.heartbeat_at = None
    job.created_at = datetime.utcnow()

    video = db.query(Video).filter(Video.id == job.video_id).first()
    if video is not None:
        video.error_message = None
        video.processing_status = (
            VideoStatus.DOWNLOADING if job.kind == JobKind.DOWNLOAD.value else VideoStatus.PENDING
        )
    return job


# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------

def reap_stale(now: Optional[datetime] = None) -> int:
    """
    Running jobs whose heartbeat stopped belong to a process that died. Put them back in the queue (or fail
    them when they have used all their tries). Returns how many were found.
    """
    now = now or datetime.utcnow()
    cutoff = now - timedelta(seconds=settings.job_stale_seconds)
    db = _session()
    try:
        stale = (
            db.query(Job)
            .filter(Job.status == JobStatus.RUNNING.value, (Job.heartbeat_at.is_(None)) | (Job.heartbeat_at < cutoff))
            .all()
        )
        for job in stale:
            if job.attempts < job.max_attempts:
                job.status = JobStatus.QUEUED.value
                job.worker = job.heartbeat_at = job.started_at = None
                logger.warning(f"Job {job.id} was interrupted (no heartbeat): queued again, try {job.attempts + 1}")
            else:
                job.status = JobStatus.FAILED.value
                job.error = "Interrupted by a server restart too many times"
                job.finished_at = now
                job.worker = None
                video = db.query(Video).filter(Video.id == job.video_id).first()
                if video is not None:
                    video.processing_status = VideoStatus.FAILED
                    video.error_message = job.error
                logger.error(f"Job {job.id} gave up after {job.attempts} tries")
        db.commit()
        return len(stale)
    finally:
        db.close()


def recover_orphan_videos(now: Optional[datetime] = None) -> int:
    """
    Videos left "processing" or "downloading" by a version that had no queue (or by a crash) have no job to
    finish them. Mark them failed so the person can press Reprocess instead of waiting for ever.
    """
    now = now or datetime.utcnow()
    cutoff = now - timedelta(seconds=max(settings.job_stale_seconds, 120))
    db = _session()
    try:
        busy = {r[0] for r in db.query(Job.video_id).filter(Job.status.in_(ACTIVE_STATUSES)).all()}
        stuck = (
            db.query(Video)
            .filter(Video.processing_status.in_([VideoStatus.PROCESSING, VideoStatus.DOWNLOADING]),
                    Video.updated_at < cutoff)
            .all()
        )
        count = 0
        for video in stuck:
            if video.id in busy:
                continue
            video.processing_status = VideoStatus.FAILED
            video.error_message = "Interrupted by a server restart: use Reprocess to run it again"
            count += 1
        db.commit()
        if count:
            logger.warning(f"{count} video(s) were stuck mid-processing from before the restart: marked failed")
        return count
    finally:
        db.close()


def purge_old_jobs(db: Session, days: int = 7, now: Optional[datetime] = None) -> int:
    """Finished jobs are history, not state: drop the ones older than a week"""
    cutoff = (now or datetime.utcnow()) - timedelta(days=days)
    removed = (
        db.query(Job)
        .filter(Job.status.in_([JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value]),
                Job.finished_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return removed


# ---------------------------------------------------------------------------
# Running jobs
# ---------------------------------------------------------------------------

async def _heartbeat(job_id: str) -> None:
    def beat():
        db = _session()
        try:
            db.execute(update(Job).where(Job.id == job_id, Job.status == JobStatus.RUNNING.value)
                       .values(heartbeat_at=datetime.utcnow()))
            db.commit()
        finally:
            db.close()

    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        try:
            await asyncio.to_thread(beat)
        except Exception as e:  # a missed beat is not worth killing the job for
            logger.warning(f"Heartbeat failed for job {job_id}: {e}")


async def run_job(job: Job) -> None:
    """Run one claimed job with its runner and record how it ended"""
    runner = state.runners.get(job.kind)
    db = _session()
    try:
        video_id = _video_ext_id(db, job.video_id)
    finally:
        db.close()

    if runner is None or video_id is None:
        await asyncio.to_thread(finish, job.id, JobStatus.FAILED, "The video no longer exists" if video_id is None
                                else f"No runner for {job.kind} jobs")
        return

    ctx = JobContext(job_id=job.id, kind=job.kind, video_id=video_id, user_id=job.user_id,
                     payload=dict(job.payload or {}))
    beat = asyncio.create_task(_heartbeat(job.id))
    try:
        await asyncio.wait_for(runner(ctx), timeout=settings.processing_timeout_seconds)
        await asyncio.to_thread(finish, job.id, JobStatus.COMPLETED)
    except JobCancelled as stop:
        if stop.reason == "shutdown":
            await asyncio.to_thread(put_back, job.id, False)
        elif stop.reason == "lost":
            logger.warning(f"Job {job.id} was taken over by another worker: leaving it alone")
        elif stop.reason == "deleted":
            logger.info(f"Job {job.id} stopped: its video was deleted")
        else:
            await asyncio.to_thread(finish, job.id, JobStatus.CANCELLED)
    except asyncio.TimeoutError:
        await asyncio.to_thread(_ask_to_stop, job.id)  # the analysis thread stops at its next checkpoint
        await asyncio.to_thread(finish, job.id, JobStatus.FAILED,
                                f"Timed out after {settings.processing_timeout_seconds} seconds")
        await asyncio.to_thread(_fail_video, job.id, f"Timed out after {settings.processing_timeout_seconds} seconds")
    except Exception as e:
        logger.error(f"Job {job.id} ({job.kind}) failed: {e}", exc_info=True)
        await asyncio.to_thread(finish, job.id, JobStatus.FAILED, short_error(e))
    finally:
        beat.cancel()
        await announce_positions()


def _ask_to_stop(job_id: str) -> None:
    db = _session()
    try:
        db.execute(update(Job).where(Job.id == job_id).values(cancel_requested=True))
        db.commit()
    finally:
        db.close()


def _fail_video(job_id: str, message: str) -> None:
    db = _session()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job is not None:
            video = db.query(Video).filter(Video.id == job.video_id).first()
            if video is not None:
                video.processing_status = VideoStatus.FAILED
                video.error_message = message
        db.commit()
    finally:
        db.close()


def _waiting_snapshot() -> List[Tuple[str, int, str]]:
    """(video public id, position, kind) for every waiting job"""
    db = _session()
    try:
        out = []
        for kind in (JobKind.PROCESS.value, JobKind.DOWNLOAD.value):
            for place, job in enumerate(queued_in_lane(db, kind), start=1):
                ext = _video_ext_id(db, job.video_id)
                if ext:
                    out.append((ext, place, kind))
        return out
    finally:
        db.close()


async def announce_positions() -> None:
    """Tell every waiting video where it stands (over its WebSocket), best effort"""
    try:
        from src.api.websockets import send_progress_update
        for video_id, place, kind in await asyncio.to_thread(_waiting_snapshot):
            await send_progress_update(
                video_id=video_id, stage="queued", progress=0.0,
                message=("Waiting to start: next in line" if place == 1 else f"Waiting in the queue: {place - 1} ahead"),
                metadata={"queue_position": place, "kind": kind},
            )
    except Exception as e:
        logger.debug(f"Could not announce queue positions: {e}")


async def worker_loop(lane: str, name: str) -> None:
    kinds = LANES[lane]
    logger.info(f"Queue worker {name} started ({lane})")
    while not state.shutting_down:
        try:
            job = await asyncio.to_thread(claim, kinds, f"{WORKER_ID}/{name}")
        except Exception as e:
            logger.error(f"Queue worker {name} could not claim a job: {e}")
            await asyncio.sleep(5)
            continue
        if job is None:
            wake = state.wake
            if wake is not None:
                try:
                    await asyncio.wait_for(wake.wait(), timeout=POLL_SECONDS)
                except asyncio.TimeoutError:
                    pass
                wake.clear()
            else:
                await asyncio.sleep(POLL_SECONDS)
            continue
        logger.info(f"Queue worker {name} took job {job.id} ({job.kind}), try {job.attempts}")
        await run_job(job)
    logger.info(f"Queue worker {name} stopped")


async def reaper_loop() -> None:
    while not state.shutting_down:
        try:
            if await asyncio.to_thread(reap_stale):
                notify()
        except Exception as e:
            logger.warning(f"Queue reaper failed: {e}")
        for _ in range(REAPER_SECONDS):  # in short steps so a shutdown does not wait for the whole interval
            if state.shutting_down:
                return
            await asyncio.sleep(1)


async def start(runners: Dict[str, Runner]) -> None:
    """Start the workers in the running event loop (called once, from the server's startup)"""
    state.shutting_down = False
    state.loop = asyncio.get_running_loop()
    state.wake = asyncio.Event()
    state.runners = dict(runners)

    await asyncio.to_thread(reap_stale)
    await asyncio.to_thread(recover_orphan_videos)

    state.tasks = [asyncio.create_task(reaper_loop())]
    for i in range(max(1, settings.max_concurrent_videos)):
        state.tasks.append(asyncio.create_task(worker_loop("process", f"process-{i + 1}")))
    for i in range(max(1, settings.max_concurrent_downloads)):
        state.tasks.append(asyncio.create_task(worker_loop("download", f"download-{i + 1}")))
    notify()


async def stop(grace_seconds: float = 20.0) -> None:
    """
    Stop taking jobs. Running ones stop at their next checkpoint and go back in the queue without losing a
    try; whatever has not finished within the grace period is left to the stale-heartbeat recovery.
    """
    state.shutting_down = True
    notify()
    tasks, state.tasks = state.tasks, []
    if tasks:
        done, pending = await asyncio.wait(tasks, timeout=grace_seconds)
        for task in pending:
            task.cancel()
    state.loop = None
    state.wake = None
