"""
The job queue (src/services/job_queue.py), its API (/api/jobs) and the way uploads, downloads and
/process use it.

Real SQLite database, real queue code; only the heavy work a job does (Whisper, CLIP, yt-dlp...) is replaced
by small fake runners. Each test makes its own data.
"""

import asyncio
import shutil
import subprocess
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from src.core.config import settings
from src.models import (
    Chapter, Highlight, Scene, SourceType, Summary, Transcript, User, Video, VideoStatus,
)
from src.models.job import Job, JobKind, JobStatus
from src.services import job_queue
from src.services.job_queue import JobCancelled, JobContext, QueueFull

PASSWORD = "correct horse battery"
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
needs_ffmpeg = pytest.mark.skipif(not Path(FFMPEG).exists(), reason="ffmpeg not installed")


class QWorld:
    """A temporary database with helpers to make accounts, videos and jobs"""

    def __init__(self, tmp_path):
        from src.core.database import Base
        import src.models  # noqa: F401

        self.tmp = tmp_path
        self.engine = create_engine(f"sqlite:///{tmp_path / 'q.db'}", connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(self.engine, "connect")
        def _pragmas(conn, _):
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=WAL")

        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False)
        self.n = 0

    @contextmanager
    def get_db(self):
        db = self.Session()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # -- data
    def user(self, name=None):
        self.n += 1
        with self.get_db() as db:
            u = User(username=name or f"user{self.n}", password_hash="x")
            db.add(u)
            db.flush()
            return u.id

    def video(self, owner=None, status=VideoStatus.PENDING, ext=None, file=True, **extra):
        self.n += 1
        ext = ext or f"vid-{self.n}"
        with self.get_db() as db:
            v = Video(external_id=ext, user_id=owner, title=f"title-{ext}", source_type=SourceType.LOCAL,
                      file_path=str(self.tmp / f"{ext}.mp4") if file else None, processing_status=status, **extra)
            db.add(v)
            db.flush()
            return v.id

    def enqueue(self, video_row_id, kind=JobKind.PROCESS.value, payload=None, age=0):
        """Queue a job; `age` (seconds) makes it look older so ordering tests need no sleeping"""
        with self.get_db() as db:
            video = db.query(Video).filter(Video.id == video_row_id).one()
            job, _ = job_queue.enqueue(db, video, kind, payload)
            job.created_at = datetime.utcnow() - timedelta(seconds=age)
            return job.id

    def job(self, job_id):
        with self.get_db() as db:
            j = db.query(Job).filter(Job.id == job_id).one()
            db.expunge(j)
            return j

    def set(self, job_id, **values):
        with self.get_db() as db:
            db.query(Job).filter(Job.id == job_id).update(values)

    def video_row(self, row_id):
        with self.get_db() as db:
            v = db.query(Video).filter(Video.id == row_id).one()
            db.expunge(v)
            return v

    def order(self, kind=JobKind.PROCESS.value):
        with self.get_db() as db:
            return [j.id for j in job_queue.queued_in_lane(db, kind)]


@pytest.fixture
def qw(tmp_path, monkeypatch):
    w = QWorld(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "frames_path", str(tmp_path / "frames"))
    monkeypatch.setattr(settings, "chroma_persist_directory", str(tmp_path / "chroma"))
    monkeypatch.setattr(settings, "max_queued_jobs_per_user", 20)
    monkeypatch.setattr(settings, "job_max_attempts", 2)
    monkeypatch.setattr(settings, "job_stale_seconds", 45)
    monkeypatch.setattr(settings, "max_concurrent_videos", 1)
    monkeypatch.setattr(settings, "max_concurrent_downloads", 1)
    monkeypatch.setattr(settings, "processing_timeout_seconds", 3600)
    for target in ("src.core.database.SessionLocal",):
        monkeypatch.setattr(target, w.Session)
    for target in ("src.core.database.get_db", "src.api.videos.get_db"):
        monkeypatch.setattr(target, w.get_db)
    job_queue.state.shutting_down = False
    job_queue.state.tasks = []
    job_queue.state.runners = {}
    job_queue.state.loop = None
    job_queue.state.wake = None
    return w


# ---------------------------------------------------------------------------
# Enqueue
# ---------------------------------------------------------------------------

class TestEnqueue:
    def test_a_job_is_a_queued_row_owned_by_the_videos_owner(self, qw):
        owner = qw.user()
        video = qw.video(owner)
        job = qw.job(qw.enqueue(video, payload={"url": "x"}))
        assert job.status == "queued" and job.kind == "process" and job.user_id == owner
        assert job.video_id == video and job.payload == {"url": "x"} and job.attempts == 0
        assert job.max_attempts == settings.job_max_attempts

    def test_a_video_with_a_waiting_job_gets_that_job_back(self, qw):
        video = qw.video()
        with qw.get_db() as db:
            v = db.query(Video).one()
            first, created_first = job_queue.enqueue(db, v, "process")
            second, created_second = job_queue.enqueue(db, v, "process")
            assert created_first and not created_second and first.id == second.id
        assert qw.n and len(qw.order()) == 1

    def test_a_running_job_also_blocks_a_second_one(self, qw):
        video = qw.video()
        first = qw.enqueue(video)
        qw.set(first, status="running")
        with qw.get_db() as db:
            again, created = job_queue.enqueue(db, db.query(Video).one(), "process")
            assert not created and again.id == first

    def test_a_finished_job_does_not_block_a_new_one(self, qw):
        video = qw.video()
        qw.set(qw.enqueue(video), status="completed")
        with qw.get_db() as db:
            _, created = job_queue.enqueue(db, db.query(Video).one(), "process")
            assert created

    def test_download_and_process_are_separate_jobs_for_one_video(self, qw):
        video = qw.video()
        qw.enqueue(video, "download")
        qw.enqueue(video, "process")
        with qw.get_db() as db:
            assert db.query(Job).count() == 2

    def test_one_account_cannot_queue_without_limit(self, qw, monkeypatch):
        monkeypatch.setattr(settings, "max_queued_jobs_per_user", 2)
        owner = qw.user()
        qw.enqueue(qw.video(owner))
        running = qw.enqueue(qw.video(owner))
        qw.set(running, status="running")  # running counts too
        third = qw.video(owner)
        with pytest.raises(QueueFull, match="2 videos waiting or running"):
            qw.enqueue(third)
        with qw.get_db() as db:
            assert db.query(Job).count() == 2

    def test_the_limit_is_per_account(self, qw, monkeypatch):
        monkeypatch.setattr(settings, "max_queued_jobs_per_user", 1)
        qw.enqueue(qw.video(qw.user()))
        qw.enqueue(qw.video(qw.user()))  # someone else is not affected
        qw.enqueue(qw.video(None))       # single-user mode has no per-account limit

    def test_finished_jobs_do_not_count_against_the_limit(self, qw, monkeypatch):
        monkeypatch.setattr(settings, "max_queued_jobs_per_user", 1)
        owner = qw.user()
        qw.set(qw.enqueue(qw.video(owner)), status="failed")
        qw.enqueue(qw.video(owner))


# ---------------------------------------------------------------------------
# Order and positions
# ---------------------------------------------------------------------------

class TestFairOrder:
    def test_one_account_is_served_in_the_order_it_queued(self, qw):
        owner = qw.user()
        jobs = [qw.enqueue(qw.video(owner), age=100 - i) for i in range(4)]
        assert qw.order() == jobs

    def test_a_long_line_does_not_block_another_account(self, qw):
        a, b = qw.user("a"), qw.user("b")
        a_jobs = [qw.enqueue(qw.video(a), age=100 - i) for i in range(5)]
        b_job = qw.enqueue(qw.video(b), age=1)  # queued last of all
        order = qw.order()
        assert order.index(b_job) == 1                     # right after a's first, not behind all five
        assert [j for j in order if j in a_jobs] == a_jobs  # a's own jobs stay in order

    def test_an_account_that_already_has_a_job_running_waits_behind_one_that_has_not(self, qw):
        a, b = qw.user("a"), qw.user("b")
        running = qw.enqueue(qw.video(a), age=500)
        qw.set(running, status="running")
        a_next = qw.enqueue(qw.video(a), age=400)
        b_job = qw.enqueue(qw.video(b), age=1)
        assert qw.order() == [b_job, a_next]

    def test_accounts_take_turns(self, qw):
        a, b = qw.user("a"), qw.user("b")
        a1, a2, a3 = (qw.enqueue(qw.video(a), age=100 - i) for i in range(3))
        b1, b2 = (qw.enqueue(qw.video(b), age=50 - i) for i in range(2))
        assert qw.order() == [a1, b1, a2, b2, a3]

    def test_positions_count_from_one_in_each_lane(self, qw):
        owner = qw.user()
        p1 = qw.enqueue(qw.video(owner), "process", age=30)
        p2 = qw.enqueue(qw.video(owner), "process", age=20)
        d1 = qw.enqueue(qw.video(owner), "download", age=10)
        with qw.get_db() as db:
            assert job_queue.queue_positions(db) == {p1: 1, p2: 2, d1: 1}

    def test_running_and_finished_jobs_have_no_position(self, qw):
        run, done = qw.enqueue(qw.video(), age=9), qw.enqueue(qw.video(), age=8)
        qw.set(run, status="running")
        qw.set(done, status="completed")
        with qw.get_db() as db:
            assert job_queue.queue_positions(db) == {}


# ---------------------------------------------------------------------------
# Claiming
# ---------------------------------------------------------------------------

class TestClaim:
    def test_the_next_job_is_taken_and_marked_running(self, qw):
        first = qw.enqueue(qw.video(), age=20)
        qw.enqueue(qw.video(), age=10)
        job = job_queue.claim(["process"], "w1")
        assert job.id == first
        row = qw.job(first)
        assert row.status == "running" and row.attempts == 1 and row.worker == "w1"
        assert row.started_at and row.heartbeat_at

    def test_an_empty_queue_gives_none(self, qw):
        assert job_queue.claim(["process"], "w1") is None

    def test_a_worker_only_takes_its_own_kind(self, qw):
        d = qw.enqueue(qw.video(), "download")
        assert job_queue.claim(["process"], "w1") is None
        assert job_queue.claim(["download"], "w2").id == d

    def test_a_job_is_never_taken_twice(self, qw):
        qw.enqueue(qw.video())
        assert job_queue.claim(["process"], "w1") is not None
        assert job_queue.claim(["process"], "w2") is None

    def test_many_workers_racing_each_get_a_different_job(self, qw):
        ids = {qw.enqueue(qw.video(), age=100 - i) for i in range(6)}
        got, lock = [], threading.Lock()

        def grab():
            job = job_queue.claim(["process"], threading.current_thread().name)
            if job is not None:
                with lock:
                    got.append(job.id)

        threads = [threading.Thread(target=grab) for _ in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(got) == 6 and set(got) == ids  # all six taken, none twice

    def test_claim_follows_the_fair_order(self, qw):
        a, b = qw.user("a"), qw.user("b")
        a1 = qw.enqueue(qw.video(a), age=100)
        qw.enqueue(qw.video(a), age=90)
        b1 = qw.enqueue(qw.video(b), age=1)
        assert job_queue.claim(["process"], "w").id == a1
        assert job_queue.claim(["process"], "w").id == b1


# ---------------------------------------------------------------------------
# Stopping a job
# ---------------------------------------------------------------------------

class TestCheckCancel:
    def running(self, qw):
        job = qw.enqueue(qw.video())
        qw.set(job, status="running")
        return job

    def test_a_running_job_that_nobody_cancelled_carries_on(self, qw):
        job_queue.check_cancel(self.running(qw))

    @pytest.mark.parametrize("change,reason", [
        ({"cancel_requested": True}, "cancelled"),
        ({"status": "queued"}, "lost"),      # reaped and handed to another worker
        ({"status": "failed"}, "lost"),
    ])
    def test_the_job_is_told_to_stop(self, qw, change, reason):
        job = self.running(qw)
        qw.set(job, **change)
        with pytest.raises(JobCancelled) as stop:
            job_queue.check_cancel(job)
        assert stop.value.reason == reason

    def test_a_job_whose_row_is_gone_stops(self, qw):
        job = self.running(qw)
        with qw.get_db() as db:
            db.query(Job).delete()
        with pytest.raises(JobCancelled) as stop:
            job_queue.check_cancel(job)
        assert stop.value.reason == "deleted"

    def test_shutdown_stops_everything(self, qw):
        job = self.running(qw)
        job_queue.state.shutting_down = True
        with pytest.raises(JobCancelled) as stop:
            job_queue.check_cancel(job)
        assert stop.value.reason == "shutdown"


class TestCancelAndRetry:
    def cancel(self, qw, job_id):
        with qw.get_db() as db:
            return job_queue.request_cancel(db, db.query(Job).filter(Job.id == job_id).one())

    def test_a_waiting_process_job_is_cancelled_at_once_and_the_video_goes_back_to_pending(self, qw):
        video = qw.video(status=VideoStatus.PENDING)
        job = qw.enqueue(video)
        assert self.cancel(qw, job) == "cancelled"
        assert qw.job(job).status == "cancelled" and qw.job(job).finished_at
        row = qw.video_row(video)
        assert row.processing_status == VideoStatus.PENDING and row.error_message == "Processing cancelled"

    def test_a_waiting_download_with_no_file_leaves_a_failed_video(self, qw):
        video = qw.video(status=VideoStatus.DOWNLOADING, file=False)
        job = qw.enqueue(video, "download", {"source": "youtube", "url": "https://youtu.be/x"})
        self.cancel(qw, job)
        row = qw.video_row(video)
        assert row.processing_status == VideoStatus.FAILED and row.error_message == "Download cancelled"

    def test_a_running_job_is_asked_to_stop_not_cut_off(self, qw):
        job = qw.enqueue(qw.video())
        qw.set(job, status="running")
        assert self.cancel(qw, job) == "running"
        row = qw.job(job)
        assert row.cancel_requested is True and row.status == "running"

    def test_a_finished_job_cannot_be_cancelled(self, qw):
        job = qw.enqueue(qw.video())
        qw.set(job, status="completed")
        assert self.cancel(qw, job) == "completed"
        assert qw.job(job).cancel_requested is False

    def test_a_failed_job_can_be_queued_again_with_its_tries_back(self, qw):
        video = qw.video(status=VideoStatus.FAILED)
        job = qw.enqueue(video)
        qw.set(job, status="failed", attempts=2, error="boom")
        with qw.get_db() as db:
            job_queue.retry(db, db.query(Job).one())
        row = qw.job(job)
        assert row.status == "queued" and row.attempts == 0 and row.error is None and row.cancel_requested is False
        assert qw.video_row(video).processing_status == VideoStatus.PENDING

    def test_retrying_a_download_puts_the_video_back_to_downloading(self, qw):
        video = qw.video(status=VideoStatus.FAILED, file=False)
        job = qw.enqueue(video, "download", {"url": "https://example.com/v.mp4"})
        qw.set(job, status="cancelled")
        with qw.get_db() as db:
            job_queue.retry(db, db.query(Job).one())
        assert qw.video_row(video).processing_status == VideoStatus.DOWNLOADING
        assert qw.job(job).payload == {"url": "https://example.com/v.mp4"}

    @pytest.mark.parametrize("status", ["queued", "running", "completed"])
    def test_only_failed_or_cancelled_jobs_can_be_retried(self, qw, status):
        job = qw.enqueue(qw.video())
        qw.set(job, status=status)
        with qw.get_db() as db:
            with pytest.raises(ValueError, match="failed or cancelled"):
                job_queue.retry(db, db.query(Job).one())

    def test_a_video_cannot_have_two_active_jobs_through_retry(self, qw):
        video = qw.video()
        old = qw.enqueue(video)
        qw.set(old, status="failed")
        qw.enqueue(video)
        with qw.get_db() as db:
            with pytest.raises(ValueError, match="already has a job"):
                job_queue.retry(db, db.query(Job).filter(Job.id == old).one())

    def test_retry_respects_the_account_limit(self, qw, monkeypatch):
        monkeypatch.setattr(settings, "max_queued_jobs_per_user", 1)
        owner = qw.user()
        old = qw.enqueue(qw.video(owner))
        qw.set(old, status="failed")
        qw.enqueue(qw.video(owner))
        with qw.get_db() as db:
            with pytest.raises(QueueFull):
                job_queue.retry(db, db.query(Job).filter(Job.id == old).one())


# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------

class TestRecovery:
    def running(self, qw, heartbeat_age, attempts=1, **video):
        row = qw.video(**video)
        job = qw.enqueue(row)
        beat = None if heartbeat_age is None else datetime.utcnow() - timedelta(seconds=heartbeat_age)
        qw.set(job, status="running", attempts=attempts, heartbeat_at=beat, worker="dead-process")
        return row, job

    def test_a_job_whose_server_died_goes_back_in_the_queue(self, qw):
        _, job = self.running(qw, heartbeat_age=300)
        assert job_queue.reap_stale() == 1
        row = qw.job(job)
        assert row.status == "queued" and row.worker is None and row.attempts == 1  # the try is kept

    def test_a_job_with_a_fresh_heartbeat_is_left_alone(self, qw):
        _, job = self.running(qw, heartbeat_age=5)
        assert job_queue.reap_stale() == 0 and qw.job(job).status == "running"

    def test_a_running_job_that_never_beat_is_stale_too(self, qw):
        _, job = self.running(qw, heartbeat_age=None)
        assert job_queue.reap_stale() == 1 and qw.job(job).status == "queued"

    def test_a_job_that_keeps_being_interrupted_gives_up(self, qw):
        video, job = self.running(qw, heartbeat_age=300, attempts=2, status=VideoStatus.PROCESSING)
        job_queue.reap_stale()
        row = qw.job(job)
        assert row.status == "failed" and "too many times" in row.error and row.finished_at
        v = qw.video_row(video)
        assert v.processing_status == VideoStatus.FAILED and "too many times" in v.error_message

    def test_videos_stuck_from_before_the_queue_are_marked_failed(self, qw):
        stuck = qw.video(status=VideoStatus.PROCESSING)
        downloading = qw.video(status=VideoStatus.DOWNLOADING, file=False)
        with qw.get_db() as db:
            db.query(Video).update({"updated_at": datetime.utcnow() - timedelta(hours=1)})
        assert job_queue.recover_orphan_videos() == 2
        for row in (stuck, downloading):
            v = qw.video_row(row)
            assert v.processing_status == VideoStatus.FAILED and "Reprocess" in v.error_message

    def test_recovery_leaves_videos_that_have_a_job_or_changed_recently_or_are_fine(self, qw):
        with_job = qw.video(status=VideoStatus.PROCESSING)
        qw.set(qw.enqueue(with_job), status="running")
        recent = qw.video(status=VideoStatus.PROCESSING)
        done = qw.video(status=VideoStatus.COMPLETED)
        pending = qw.video(status=VideoStatus.PENDING)
        with qw.get_db() as db:
            db.query(Video).filter(Video.id.in_([with_job, done, pending])).update(
                {"updated_at": datetime.utcnow() - timedelta(hours=1)})
        assert job_queue.recover_orphan_videos() == 0
        assert qw.video_row(with_job).processing_status == VideoStatus.PROCESSING
        assert qw.video_row(recent).processing_status == VideoStatus.PROCESSING
        assert qw.video_row(done).processing_status == VideoStatus.COMPLETED

    def test_old_finished_jobs_are_dropped_active_and_recent_ones_stay(self, qw):
        old, recent, waiting, running = (qw.enqueue(qw.video()) for _ in range(4))
        qw.set(old, status="completed", finished_at=datetime.utcnow() - timedelta(days=10))
        qw.set(recent, status="failed", finished_at=datetime.utcnow() - timedelta(days=1))
        qw.set(running, status="running")
        with qw.get_db() as db:
            assert job_queue.purge_old_jobs(db) == 1
            assert {j.id for j in db.query(Job)} == {recent, waiting, running}


# ---------------------------------------------------------------------------
# Running jobs
# ---------------------------------------------------------------------------

def runner_that(behaviour):
    async def run(ctx: JobContext):
        return await behaviour(ctx)
    return run


async def run_one(qw, behaviour, kind="process", **settings_override):
    """Queue one job with this behaviour, claim it and run it; returns (job id, video row id)"""
    video = qw.video(status=VideoStatus.PROCESSING)
    job_id = qw.enqueue(video, kind)
    job_queue.state.runners = {kind: runner_that(behaviour)}
    claimed = job_queue.claim([kind], "test")
    await job_queue.run_job(claimed)
    return job_id, video


class TestRunJob:
    @pytest.mark.asyncio
    async def test_a_job_that_finishes_is_completed(self, qw):
        seen = {}

        async def work(ctx):
            seen["ctx"] = ctx

        job_id, video = await run_one(qw, work)
        row = qw.job(job_id)
        assert row.status == "completed" and row.finished_at and row.worker is None and row.error is None
        assert seen["ctx"].kind == "process" and seen["ctx"].video_id == f"vid-{qw.n}" or seen["ctx"].video_id

    @pytest.mark.asyncio
    async def test_a_failing_job_is_failed_with_one_readable_line(self, qw):
        async def work(ctx):
            raise RuntimeError("[in#0 @ 0x1234] moov atom not found\nsecond line")

        job_id, _ = await run_one(qw, work)
        row = qw.job(job_id)
        assert row.status == "failed" and "\n" not in row.error and "0x1234" not in row.error

    @pytest.mark.asyncio
    async def test_a_cancelled_job_is_cancelled(self, qw):
        async def work(ctx):
            raise JobCancelled("cancelled")

        job_id, _ = await run_one(qw, work)
        assert qw.job(job_id).status == "cancelled"

    @pytest.mark.asyncio
    async def test_a_shutdown_puts_the_job_back_without_costing_a_try(self, qw):
        async def work(ctx):
            raise JobCancelled("shutdown")

        job_id, _ = await run_one(qw, work)
        row = qw.job(job_id)
        assert row.status == "queued" and row.attempts == 0 and row.worker is None and row.started_at is None

    @pytest.mark.asyncio
    async def test_a_deleted_video_leaves_nothing_to_record(self, qw):
        async def work(ctx):
            with qw.get_db() as db:
                db.query(Video).delete()  # the video (and by cascade the job) is deleted while it runs
            ctx.check_cancel()

        video = qw.video()
        job_id = qw.enqueue(video)
        job_queue.state.runners = {"process": runner_that(work)}
        await job_queue.run_job(job_queue.claim(["process"], "t"))
        with qw.get_db() as db:
            assert db.query(Job).count() == 0

    @pytest.mark.asyncio
    async def test_a_job_that_takes_too_long_is_failed_and_asked_to_stop(self, qw, monkeypatch):
        monkeypatch.setattr(settings, "processing_timeout_seconds", 0.2)

        async def work(ctx):
            await asyncio.sleep(5)

        job_id, video = await run_one(qw, work)
        row = qw.job(job_id)
        assert row.status == "failed" and "Timed out" in row.error and row.cancel_requested is True
        v = qw.video_row(video)
        assert v.processing_status == VideoStatus.FAILED and "Timed out" in v.error_message

    @pytest.mark.asyncio
    async def test_a_kind_without_a_runner_fails_instead_of_hanging(self, qw):
        video = qw.video()
        job_id = qw.enqueue(video)
        job_queue.state.runners = {}
        await job_queue.run_job(job_queue.claim(["process"], "t"))
        assert qw.job(job_id).status == "failed"

    @pytest.mark.asyncio
    async def test_the_heartbeat_keeps_beating_while_a_job_runs(self, qw, monkeypatch):
        monkeypatch.setattr(job_queue, "HEARTBEAT_SECONDS", 0.1)
        beats = []

        async def work(ctx):
            first = qw.job(ctx.job_id).heartbeat_at
            await asyncio.sleep(0.5)
            beats.append((first, qw.job(ctx.job_id).heartbeat_at))

        await run_one(qw, work)
        first, later = beats[0]
        assert later > first

    @pytest.mark.asyncio
    async def test_waiting_videos_are_told_their_place(self, qw):
        sent = []

        async def fake_send(**kwargs):
            sent.append(kwargs)

        waiting = qw.video()
        qw.enqueue(waiting, age=5)
        qw.enqueue(qw.video(), age=4)
        with patch("src.api.websockets.send_progress_update", new=fake_send):
            await job_queue.announce_positions()
        assert [(m["stage"], m["metadata"]["queue_position"]) for m in sent] == [("queued", 1), ("queued", 2)]
        assert "next in line" in sent[0]["message"] and "1 ahead" in sent[1]["message"]


# ---------------------------------------------------------------------------
# The workers
# ---------------------------------------------------------------------------

async def wait_until(check, seconds=10):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return True
        await asyncio.sleep(0.05)
    return False


class TestWorkers:
    @pytest.mark.asyncio
    async def test_jobs_run_one_at_a_time_by_default_and_all_finish(self, qw):
        running, peak, order = [0], [0], []

        async def work(ctx):
            running[0] += 1
            peak[0] = max(peak[0], running[0])
            order.append(ctx.video_id)
            await asyncio.sleep(0.05)
            running[0] -= 1

        ids = [qw.enqueue(qw.video(), age=100 - i) for i in range(4)]
        await job_queue.start({"process": runner_that(work), "download": runner_that(work)})
        try:
            assert await wait_until(lambda: all(qw.job(i).status == "completed" for i in ids))
        finally:
            await job_queue.stop()
        assert peak[0] == 1 and len(order) == 4

    @pytest.mark.asyncio
    async def test_the_number_of_analysis_workers_is_a_setting(self, qw, monkeypatch):
        monkeypatch.setattr(settings, "max_concurrent_videos", 3)
        running, peak = [0], [0]

        async def work(ctx):
            running[0] += 1
            peak[0] = max(peak[0], running[0])
            await asyncio.sleep(0.3)
            running[0] -= 1

        ids = [qw.enqueue(qw.video(), age=100 - i) for i in range(6)]
        await job_queue.start({"process": runner_that(work)})
        try:
            assert await wait_until(lambda: all(qw.job(i).status == "completed" for i in ids))
        finally:
            await job_queue.stop()
        assert peak[0] == 3

    @pytest.mark.asyncio
    async def test_downloads_have_their_own_workers_and_do_not_wait_for_analysis(self, qw):
        release = asyncio.Event()
        finished = []

        async def slow_analysis(ctx):
            await release.wait()

        async def quick_download(ctx):
            finished.append(ctx.job_id)

        analysis = qw.enqueue(qw.video(), "process", age=10)
        download = qw.enqueue(qw.video(), "download", age=5)
        await job_queue.start({"process": runner_that(slow_analysis), "download": runner_that(quick_download)})
        try:
            assert await wait_until(lambda: qw.job(download).status == "completed")
            assert qw.job(analysis).status == "running"   # still busy: the download did not wait for it
        finally:
            release.set()
            await job_queue.stop()

    @pytest.mark.asyncio
    async def test_a_new_job_is_picked_up_at_once(self, qw, monkeypatch):
        monkeypatch.setattr(job_queue, "POLL_SECONDS", 30)   # only the wake-up can start it in time
        done = []

        async def work(ctx):
            done.append(ctx.job_id)

        await job_queue.start({"process": runner_that(work)})
        try:
            await asyncio.sleep(0.2)  # the workers are idle
            started = time.monotonic()
            job = qw.enqueue(qw.video())
            job_queue.notify()
            assert await wait_until(lambda: job in done, 3)
            assert time.monotonic() - started < 2
        finally:
            await job_queue.stop()

    @pytest.mark.asyncio
    async def test_a_waiting_job_is_picked_up_after_a_restart(self, qw):
        """The queue is the database: a job queued before the process started runs when workers start"""
        done = []

        async def work(ctx):
            done.append(ctx.job_id)

        job = qw.enqueue(qw.video())
        await job_queue.start({"process": runner_that(work)})
        try:
            assert await wait_until(lambda: job in done)
        finally:
            await job_queue.stop()

    @pytest.mark.asyncio
    async def test_a_job_the_old_process_was_running_is_run_again_by_the_new_one(self, qw):
        done = []

        async def work(ctx):
            done.append(ctx.job_id)

        job = qw.enqueue(qw.video())
        qw.set(job, status="running", attempts=1, worker="old-process",
               heartbeat_at=datetime.utcnow() - timedelta(minutes=10))
        await job_queue.start({"process": runner_that(work)})
        try:
            assert await wait_until(lambda: qw.job(job).status == "completed")
        finally:
            await job_queue.stop()
        assert done == [job] and qw.job(job).attempts == 2

    @pytest.mark.asyncio
    async def test_a_clean_shutdown_stops_a_running_job_and_returns_it_to_the_queue(self, qw):
        started = asyncio.Event()

        async def work(ctx):
            started.set()
            while True:           # a pipeline: work, then a checkpoint
                await asyncio.sleep(0.05)
                await asyncio.to_thread(ctx.check_cancel)

        job = qw.enqueue(qw.video())
        await job_queue.start({"process": runner_that(work)})
        await asyncio.wait_for(started.wait(), 5)
        await job_queue.stop(grace_seconds=5)
        row = qw.job(job)
        assert row.status == "queued" and row.attempts == 0

    @pytest.mark.asyncio
    async def test_cancelling_a_running_job_stops_it_at_its_next_checkpoint(self, qw):
        started = asyncio.Event()

        async def work(ctx):
            started.set()
            while True:
                await asyncio.sleep(0.05)
                await asyncio.to_thread(ctx.check_cancel)

        video = qw.video(status=VideoStatus.PROCESSING)
        job = qw.enqueue(video)
        await job_queue.start({"process": runner_that(work)})
        try:
            await asyncio.wait_for(started.wait(), 5)
            with qw.get_db() as db:
                job_queue.request_cancel(db, db.query(Job).one())
            assert await wait_until(lambda: qw.job(job).status == "cancelled")
        finally:
            await job_queue.stop()

    @pytest.mark.asyncio
    async def test_one_failing_job_does_not_stop_the_worker(self, qw):
        async def work(ctx):
            if ctx.video_id.endswith("bad"):
                raise RuntimeError("boom")

        bad = qw.enqueue(qw.video(ext="vid-bad"), age=20)
        good = qw.enqueue(qw.video(ext="vid-good"), age=10)
        await job_queue.start({"process": runner_that(work)})
        try:
            assert await wait_until(lambda: qw.job(good).status == "completed")
        finally:
            await job_queue.stop()
        assert qw.job(bad).status == "failed"


# ---------------------------------------------------------------------------
# The pipeline as a job
# ---------------------------------------------------------------------------

class TestPipelineAsAJob:
    def rich_video(self, qw):
        video = qw.video(status=VideoStatus.PROCESSING, ext="vid-p")
        with qw.get_db() as db:
            db.add(Transcript(video_id=video, start_time=0, end_time=1, text="old"))
            db.add(Scene(video_id=video, scene_number=1, start_time=0, end_time=1, duration=1))
            db.add(Summary(video_id=video, content="old summary"))
            db.add(Highlight(video_id=video, title="h", start_time=0, end_time=1))
            db.add(Chapter(video_id=video, chapter_number=1, title="c", start_time=0, end_time=1))
        return video

    def count_analysis(self, qw):
        with qw.get_db() as db:
            return sum(db.query(m).count() for m in (Transcript, Scene, Summary, Highlight, Chapter))

    @pytest.mark.asyncio
    async def test_cancelling_removes_the_partial_results_and_leaves_a_pending_video(self, qw):
        from src.api.videos import process_video_background
        video = self.rich_video(qw)
        ctx = JobContext(job_id="j", kind="process", video_id="vid-p", user_id=None)
        ctx.check_cancel = lambda: None   # no real job row here: the cancellation comes from the analysis itself

        def stops(*args, **kwargs):
            # the analysis had already produced results when it was cancelled
            with qw.get_db() as db:
                db.add(Transcript(video_id=video, start_time=0, end_time=1, text="partial"))
                db.add(Scene(video_id=video, scene_number=9, start_time=0, end_time=1, duration=1))
                db.add(Summary(video_id=video, content="partial"))
            raise JobCancelled("cancelled")

        with patch("src.api.videos._run_video_analysis", side_effect=stops), \
             patch("src.api.websockets.send_progress_update", new=AsyncMock()):
            with pytest.raises(JobCancelled):
                await process_video_background("vid-p", ctx)

        row = qw.video_row(video)
        assert row.processing_status == VideoStatus.PENDING and row.error_message == "Processing cancelled"
        assert self.count_analysis(qw) == 0

    @pytest.mark.asyncio
    async def test_a_shutdown_leaves_the_video_waiting_without_an_error(self, qw):
        from src.api.videos import process_video_background
        video = self.rich_video(qw)
        ctx = JobContext(job_id="j", kind="process", video_id="vid-p", user_id=None)
        ctx.check_cancel = lambda: None

        with patch("src.api.videos._run_video_analysis", side_effect=JobCancelled("shutdown")), \
             patch("src.api.websockets.send_progress_update", new=AsyncMock()):
            with pytest.raises(JobCancelled):
                await process_video_background("vid-p", ctx)

        row = qw.video_row(video)
        assert row.processing_status == VideoStatus.PENDING and row.error_message is None

    @pytest.mark.asyncio
    async def test_a_failure_is_recorded_on_the_video_and_reaches_the_queue(self, qw):
        from src.api.videos import process_video_background
        video = self.rich_video(qw)
        sent = AsyncMock()

        with patch("src.api.videos._run_video_analysis", side_effect=RuntimeError("whisper exploded")), \
             patch("src.api.websockets.send_progress_update", new=AsyncMock()), \
             patch("src.api.websockets.send_processing_error", new=sent):
            with pytest.raises(RuntimeError, match="whisper exploded"):
                await process_video_background("vid-p")

        row = qw.video_row(video)
        assert row.processing_status == VideoStatus.FAILED and "whisper exploded" in row.error_message
        sent.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_the_job_checks_for_cancellation_before_the_analysis_starts(self, qw):
        from src.api.videos import process_video_background
        qw.video(status=VideoStatus.PROCESSING, ext="vid-p")
        calls = []
        ctx = JobContext(job_id="j", kind="process", video_id="vid-p", user_id=None)
        ctx.check_cancel = lambda: (calls.append(1), (_ for _ in ()).throw(JobCancelled("cancelled")))[1]

        with patch("src.api.videos._run_video_analysis") as analysis, \
             patch("src.api.websockets.send_progress_update", new=AsyncMock()):
            with pytest.raises(JobCancelled):
                await process_video_background("vid-p", ctx)
        analysis.assert_not_called()
        assert calls

    @needs_ffmpeg
    def test_the_analysis_stops_at_its_first_checkpoint_when_cancelled(self, qw):
        from src.api.videos import _run_video_analysis
        clip = qw.tmp / "c.mp4"
        subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=d=6:s=320x240:r=10",
                        "-pix_fmt", "yuv420p", str(clip)], check=True, capture_output=True)
        calls = []

        def check():
            calls.append(1)
            raise JobCancelled("cancelled")

        with patch("src.services.scene_detection.content_detector.ContentBasedSceneDetector.detect_scenes",
                   side_effect=AssertionError("scene detection ran after the cancellation")):
            with pytest.raises(JobCancelled):
                _run_video_analysis(str(clip), "vid-c", None, check)
        assert len(calls) == 1   # it stopped there: no scene detection, Whisper or captioning ran


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------

class TestDownloads:
    def test_a_stream_download_is_stopped_as_soon_as_the_job_is_cancelled(self, qw):
        from src.api.videos import _download_stream_blocking
        ctx = JobContext(job_id="j", kind="download", video_id="v", user_id=None)
        checks = [0]

        def check():
            checks[0] += 1
            if checks[0] >= 2:
                raise JobCancelled("cancelled")

        ctx.check_cancel = check
        started = time.monotonic()
        with pytest.raises(JobCancelled):
            _download_stream_blocking(["sleep", "61.5"], str(qw.tmp / "nope.mp4"), ctx, 300)
        assert time.monotonic() - started < 6  # not 60: the process was killed
        assert subprocess.run(["pgrep", "-f", "sleep 61.5"], capture_output=True).returncode != 0  # and is really gone

    def test_a_stream_download_that_takes_too_long_is_stopped(self, qw):
        from src.api.videos import _download_stream_blocking
        ctx = JobContext(job_id="j", kind="download", video_id="v", user_id=None)
        ctx.check_cancel = lambda: None
        with pytest.raises(RuntimeError, match="too long"):
            _download_stream_blocking(["sleep", "60"], str(qw.tmp / "nope.mp4"), ctx, 1)

    def test_a_failing_ffmpeg_reports_its_error(self, qw):
        from src.api.videos import _download_stream_blocking
        ctx = JobContext(job_id="j", kind="download", video_id="v", user_id=None)
        ctx.check_cancel = lambda: None
        with pytest.raises(RuntimeError, match="ffmpeg failed"):
            _download_stream_blocking(["sh", "-c", "echo broken >&2; exit 3"], str(qw.tmp / "nope.mp4"), ctx, 30)

    @pytest.mark.asyncio
    async def test_a_cancelled_download_removes_its_partial_file_and_fails_the_video(self, qw):
        from src.api.videos import download_streaming_video
        video = qw.video(status=VideoStatus.DOWNLOADING, ext="vid-d", file=False)
        part = qw.tmp / "data" / "uploads"
        part.mkdir(parents=True)
        (part / "vid-d.mp4").write_bytes(b"half")
        ctx = JobContext(job_id="j", kind="download", video_id="vid-d", user_id=None)

        def cancelled(*args, **kwargs):
            raise JobCancelled("cancelled")

        with patch("src.api.videos._download_stream_blocking", side_effect=cancelled), \
             patch("src.api.websockets.send_progress_update", new=AsyncMock()):
            with pytest.raises(JobCancelled):
                await download_streaming_video("vid-d", "https://example.com/v.mp4", None, True, ctx)

        assert not (part / "vid-d.mp4").exists()
        row = qw.video_row(video)
        assert row.processing_status == VideoStatus.FAILED and row.error_message == "Download cancelled"

    @pytest.mark.asyncio
    async def test_a_finished_download_queues_the_analysis_for_a_worker_not_inline(self, qw):
        from src.api.videos import download_streaming_video
        owner = qw.user()
        video = qw.video(owner, status=VideoStatus.DOWNLOADING, ext="vid-q", file=False)
        ctx = JobContext(job_id="j", kind="download", video_id="vid-q", user_id=owner)
        ctx.check_cancel = lambda: None
        (qw.tmp / "data" / "uploads").mkdir(parents=True)

        with patch("src.api.videos._download_stream_blocking"), \
             patch("src.api.videos.os.path.exists", return_value=True), \
             patch("src.api.videos.get_video_duration", new=AsyncMock(return_value=12.5)), \
             patch("src.api.websockets.send_progress_update", new=AsyncMock()):
            await download_streaming_video("vid-q", "https://example.com/v.mp4", "Title", True, ctx)

        row = qw.video_row(video)
        assert row.processing_status == VideoStatus.PENDING and row.duration_seconds == 12.5
        with qw.get_db() as db:
            jobs = db.query(Job).all()
            assert [(j.kind, j.status, j.user_id) for j in jobs] == [("process", "queued", owner)]

    @pytest.mark.asyncio
    async def test_a_youtube_video_over_the_size_limit_fails_clearly(self, qw):
        from src.api.videos import download_youtube_video
        video = qw.video(status=VideoStatus.DOWNLOADING, ext="vid-y", file=False)
        ctx = JobContext(job_id="j", kind="download", video_id="vid-y", user_id=None)
        ctx.check_cancel = lambda: None

        # yt-dlp skips a too-large video without an error: no file appears
        with patch("src.api.videos._download_youtube_blocking", return_value=({"title": "Big"}, "./data/uploads/vid-y.mp4")), \
             patch("src.api.websockets.send_progress_update", new=AsyncMock()), \
             patch("src.api.websockets.send_processing_error", new=AsyncMock()):
            with pytest.raises(RuntimeError, match="larger than the 5 MB limit"):
                await download_youtube_video("vid-y", "https://youtu.be/x", None, "best", True, ctx, 5)
        assert qw.video_row(video).processing_status == VideoStatus.FAILED

    def test_youtube_is_downloaded_with_a_size_limit_and_no_playlists(self, qw):
        from src.api.videos import _download_youtube_blocking
        seen = {}

        class FakeYDL:
            def __init__(self, opts):
                seen.update(opts)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def extract_info(self, url, download):
                return {"title": "t"}

        ctx = JobContext(job_id="j", kind="download", video_id="v", user_id=None)
        with patch("yt_dlp.YoutubeDL", FakeYDL):
            _download_youtube_blocking("https://youtu.be/x", "vid-y", "720p", ctx, 9)
        assert seen["max_filesize"] == 9 * 1024 * 1024 and seen["noplaylist"] is True
        assert "height<=720" in seen["format"] and seen["progress_hooks"]


# ---------------------------------------------------------------------------
# The API
# ---------------------------------------------------------------------------

@pytest.fixture
def api(qw, monkeypatch):
    """The real app on the temporary database, with two ordinary accounts and an administrator"""
    pytest.importorskip("fastapi")
    monkeypatch.setattr(settings, "require_login", True)
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    for target in ("src.core.login_gate.SessionLocal",):
        monkeypatch.setattr(target, qw.Session)
    monkeypatch.setattr("src.api.auth.get_db", qw.get_db)
    monkeypatch.setattr("src.core.auth._SCRYPT_N", 2 ** 4)

    async def _no_dispatch(self, request, call_next):
        return await call_next(request)

    from src.core.middleware import RateLimitMiddleware
    monkeypatch.setattr(RateLimitMiddleware, "dispatch", _no_dispatch)
    from src.api import auth as auth_api
    auth_api.login_failures.events.clear()
    auth_api.creations.events.clear()

    from server import app

    def signup(name):
        client = TestClient(app)
        response = client.post("/api/auth/register", json={"username": name, "password": PASSWORD})
        assert response.status_code == 200, response.text
        client.user = response.json()
        return client

    return NS(w=qw, root=signup("root"), ann=signup("ann"), bob=signup("bob"), anon=TestClient(app))


def job_of(api, client, video_row):
    with api.w.get_db() as db:
        return db.query(Job).filter(Job.video_id == video_row).order_by(Job.created_at.desc()).first().id


class TestJobsApi:
    def test_the_list_shows_your_jobs_with_positions_and_a_summary(self, api):
        ann, bob = api.ann.user["id"], api.bob.user["id"]
        mine1 = api.w.enqueue(api.w.video(ann), age=30)
        mine2 = api.w.enqueue(api.w.video(ann), age=20)
        theirs = api.w.enqueue(api.w.video(bob), age=10)
        body = api.ann.get("/api/jobs").json()
        assert {j["job_id"] for j in body["jobs"]} == {mine1, mine2}
        by_id = {j["job_id"]: j for j in body["jobs"]}
        assert by_id[mine1]["queue_position"] == 1 and by_id[mine2]["queue_position"] == 3  # bob's takes the 2nd turn
        assert by_id[mine1]["video_title"].startswith("title-")
        assert body["queue"] == {"queued": 2, "running": 0, "analysis_workers": 1, "download_workers": 1}
        assert theirs not in str(body)

    def test_administrators_see_everyones(self, api):
        a = api.w.enqueue(api.w.video(api.ann.user["id"]))
        b = api.w.enqueue(api.w.video(api.bob.user["id"]))
        assert {j["job_id"] for j in api.root.get("/api/jobs").json()["jobs"]} == {a, b}

    def test_active_jobs_come_first_then_newest(self, api):
        ann = api.ann.user["id"]
        done = api.w.enqueue(api.w.video(ann), age=1)
        api.w.set(done, status="completed")
        waiting = api.w.enqueue(api.w.video(ann), age=500)
        assert [j["job_id"] for j in api.ann.get("/api/jobs").json()["jobs"]] == [waiting, done]

    def test_filters(self, api):
        ann = api.ann.user["id"]
        p = api.w.enqueue(api.w.video(ann), "process")
        d = api.w.enqueue(api.w.video(ann), "download")
        api.w.set(d, status="failed")
        assert [j["job_id"] for j in api.ann.get("/api/jobs", params={"kind": "download"}).json()["jobs"]] == [d]
        assert [j["job_id"] for j in api.ann.get("/api/jobs", params={"status": "queued"}).json()["jobs"]] == [p]
        assert api.ann.get("/api/jobs", params={"status": "nonsense"}).status_code == 400
        assert api.ann.get("/api/jobs", params={"kind": "nonsense"}).status_code == 400
        assert api.ann.get("/api/jobs", params={"limit": 0}).status_code == 422

    def test_other_accounts_get_not_found_for_everything_about_a_job(self, api):
        job = api.w.enqueue(api.w.video(api.ann.user["id"]))
        for method, path in (("get", f"/api/jobs/{job}"), ("post", f"/api/jobs/{job}/cancel"), ("post", f"/api/jobs/{job}/retry")):
            assert getattr(api.bob, method)(path).status_code == 404, path
        assert api.w.job(job).status == "queued"
        assert api.ann.get(f"/api/jobs/{job}").status_code == 200
        assert api.root.get(f"/api/jobs/{job}").status_code == 200
        assert api.bob.get("/api/jobs/does-not-exist").status_code == 404

    def test_everything_needs_a_sign_in(self, api):
        for method, path in (("get", "/api/jobs"), ("get", "/api/jobs/x"), ("post", "/api/jobs/x/cancel"), ("post", "/api/jobs/x/retry")):
            assert getattr(api.anon, method)(path).status_code == 401

    def test_cancel_and_retry_round_trip(self, api):
        ann = api.ann.user["id"]
        video = api.w.video(ann)
        job = api.w.enqueue(video)
        cancelled = api.ann.post(f"/api/jobs/{job}/cancel")
        assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled" and cancelled.json()["queue_position"] is None
        assert api.ann.post(f"/api/jobs/{job}/cancel").status_code == 409  # already finished
        again = api.ann.post(f"/api/jobs/{job}/retry")
        assert again.status_code == 200 and again.json()["status"] == "queued" and again.json()["queue_position"] == 1
        assert api.ann.post(f"/api/jobs/{job}/retry").status_code == 409     # it is waiting again

    def test_cancelling_a_running_job_reports_the_request(self, api):
        job = api.w.enqueue(api.w.video(api.ann.user["id"]))
        api.w.set(job, status="running")
        body = api.ann.post(f"/api/jobs/{job}/cancel").json()
        assert body["status"] == "running" and body["cancel_requested"] is True

    def test_retry_over_the_account_limit_is_refused(self, api, monkeypatch):
        monkeypatch.setattr(settings, "max_queued_jobs_per_user", 1)
        ann = api.ann.user["id"]
        old = api.w.enqueue(api.w.video(ann))
        api.w.set(old, status="failed")
        api.w.enqueue(api.w.video(ann))
        assert api.ann.post(f"/api/jobs/{old}/retry").status_code == 429


@needs_ffmpeg
class TestQueueingFromTheApi:
    def make_video(self, api, seconds=2):
        path = api.w.tmp / "in.mp4"
        subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=blue:s=160x120:d={seconds}",
                        "-pix_fmt", "yuv420p", str(path)], check=True, capture_output=True)
        return path

    def upload(self, client, path, auto="true"):
        return client.post("/api/videos/upload", files={"file": ("in.mp4", path.read_bytes(), "video/mp4")},
                           data={"auto_process": auto})

    def test_an_upload_is_queued_not_started(self, api):
        response = self.upload(api.ann, self.make_video(api))
        body = response.json()
        assert response.status_code == 200 and body["job_id"] and body["queue_position"] == 1
        assert "queued" in body["message"]
        job = api.w.job(body["job_id"])
        assert job.status == "queued" and job.kind == "process" and job.user_id == api.ann.user["id"]

    def test_an_upload_without_auto_process_queues_nothing(self, api):
        body = self.upload(api.ann, self.make_video(api), auto="false").json()
        assert body["job_id"] is None and body["queue_position"] is None
        with api.w.get_db() as db:
            assert db.query(Job).count() == 0

    def test_several_uploads_line_up_instead_of_all_starting(self, api):
        clip = self.make_video(api)
        positions = [self.upload(api.ann, clip).json()["queue_position"] for _ in range(3)]
        assert positions == [1, 2, 3]

    def test_the_status_and_list_say_where_a_video_stands(self, api):
        clip = self.make_video(api)
        first = self.upload(api.ann, clip).json()
        second = self.upload(api.ann, clip).json()
        status = api.ann.get(f"/api/videos/{second['video_id']}/status").json()
        assert status["stage"] == "queued" and status["queue_position"] == 2 and status["job_status"] == "queued"
        assert status["progress"] == 0.0
        listing = {v["video_id"]: v for v in api.ann.get("/api/videos").json()["videos"]}
        assert listing[first["video_id"]]["queue_position"] == 1 and listing[first["video_id"]]["job_id"] == first["job_id"]
        one = api.ann.get(f"/api/videos/{first['video_id']}").json()
        assert one["job_status"] == "queued" and one["queue_position"] == 1

    def test_a_video_without_a_job_has_no_queue_fields(self, api):
        body = self.upload(api.ann, self.make_video(api), auto="false").json()
        status = api.ann.get(f"/api/videos/{body['video_id']}/status").json()
        assert status["job_id"] is None and status["queue_position"] is None and status["stage"] == "pending"

    def test_process_queues_and_a_second_request_is_refused(self, api):
        body = self.upload(api.ann, self.make_video(api), auto="false").json()
        first = api.ann.post(f"/api/videos/{body['video_id']}/process", json={})
        assert first.status_code == 200 and first.json()["status"] == "queued" and first.json()["queue_position"] == 1
        second = api.ann.post(f"/api/videos/{body['video_id']}/process", json={})
        assert second.status_code == 409 and "waiting in the queue" in second.json()["detail"]
        again = api.ann.post(f"/api/videos/{body['video_id']}/reprocess", json={})
        assert again.status_code == 409

    def test_a_video_being_processed_is_refused_as_before(self, api):
        video = api.w.video(api.ann.user["id"], status=VideoStatus.PROCESSING, ext="busy")
        assert api.ann.post("/api/videos/busy/process", json={}).status_code == 409

    def test_the_account_limit_applies_to_new_uploads(self, api, monkeypatch):
        monkeypatch.setattr(settings, "max_queued_jobs_per_user", 2)
        clip = self.make_video(api)
        assert self.upload(api.ann, clip).status_code == 200
        assert self.upload(api.ann, clip).status_code == 200
        refused = self.upload(api.ann, clip)
        assert refused.status_code == 429 and "waiting or running" in refused.json()["detail"]
        assert len(list((api.w.tmp / "uploads" / "videos").glob("*"))) == 2   # the refused one was never saved
        assert self.upload(api.bob, clip).status_code == 200                  # someone else is fine

    def test_deleting_a_waiting_video_removes_its_job(self, api):
        body = self.upload(api.ann, self.make_video(api)).json()
        assert api.ann.delete(f"/api/videos/{body['video_id']}").status_code == 200
        with api.w.get_db() as db:
            assert db.query(Job).count() == 0

    def test_deleting_a_video_that_is_being_processed_asks_its_job_to_stop(self, api):
        body = self.upload(api.ann, self.make_video(api)).json()
        api.w.set(body["job_id"], status="running")
        api.ann.delete(f"/api/videos/{body['video_id']}")
        # the row went with the video; the running job finds that at its next checkpoint
        with pytest.raises(JobCancelled) as stop:
            job_queue.check_cancel(body["job_id"])
        assert stop.value.reason == "deleted"

    def test_stream_and_youtube_links_queue_a_download_with_everything_it_needs(self, api):
        with patch("src.api.videos.check_public_http_url", lambda url: url):
            stream = api.ann.post("/api/videos/stream", json={"url": "https://example.com/v.m3u8", "title": "S"}).json()
        youtube = api.ann.post("/api/videos/youtube", json={"url": "https://youtu.be/abc", "download_quality": "720p"}).json()
        s, y = api.w.job(stream["job_id"]), api.w.job(youtube["job_id"])
        assert (s.kind, s.status) == ("download", "queued") and (y.kind, y.status) == ("download", "queued")
        assert s.payload["source"] == "stream" and s.payload["url"] == "https://example.com/v.m3u8" and s.payload["title"] == "S"
        assert y.payload["source"] == "youtube" and y.payload["quality"] == "720p" and y.payload["auto_process"] is True
        assert y.payload["max_mb"] == settings.yt_dlp_max_filesize_mb  # the smaller of that and the upload limit
        assert s.payload["max_mb"] == settings.max_video_size_mb
        assert stream["queue_position"] == 1 and youtube["queue_position"] == 2   # one download lane: youtube waits behind the stream

    def test_a_guest_has_a_smaller_download_limit(self, api, monkeypatch):
        monkeypatch.setattr(settings, "guest_max_video_size_mb", 7)
        guest = TestClient(api.anon.app)
        guest.post("/api/auth/guest")
        with patch("src.api.videos.check_public_http_url", lambda url: url):
            body = guest.post("/api/videos/stream", json={"url": "https://example.com/v.mp4"}).json()
        assert api.w.job(body["job_id"]).payload["max_mb"] == 7
