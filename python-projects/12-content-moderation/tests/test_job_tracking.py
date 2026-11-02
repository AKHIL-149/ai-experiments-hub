"""
Moderation jobs: their rows, their status, and what happens when a task fails.

Found by running the app: update_job_status() existed but nothing called it, so all 26 jobs stayed 'queued'
for ever (the analytics said "0 completed, 0% success", the queue statistics "13 queued" with Redis empty);
the job row was written after the task was sent, and the content status ("processing") after that, so a
fast worker's decision could be overwritten; a job that failed for good left its content "processing" for
ever; and without a worker nothing said why submissions never finished.
"""

import uuid
from datetime import datetime

import pytest

from src.core.database import (
    ContentItem, ContentStatus, ContentType, DatabaseManager, JobStatus, ModerationJob, User
)
from src.core import queue_manager as qm
from src.workers import base_worker, job_tracker
from src.workers.base_worker import BaseClassificationTask


@pytest.fixture
def db():
    manager = DatabaseManager()
    manager.create_tables()
    return manager


@pytest.fixture
def content(db):
    with db.get_session() as session:
        suffix = uuid.uuid4().hex[:8]
        user = User(username=f"jt_{suffix}", email=f"jt_{suffix}@example.com", password_hash="x")
        session.add(user)
        session.commit()
        item = ContentItem(user_id=user.id, content_type=ContentType.TEXT, text_content="hello",
                           status=ContentStatus.PROCESSING)
        session.add(item)
        session.commit()
        return item.id


def add_job(db, content_id, task_id=None, status=JobStatus.QUEUED):
    task_id = task_id or str(uuid.uuid4())
    with db.get_session() as session:
        session.add(ModerationJob(content_id=content_id, status=status, queue_name="default", celery_task_id=task_id))
        session.commit()
    return task_id


def job_of(db, task_id):
    with db.get_session() as session:
        job = session.query(ModerationJob).filter_by(celery_task_id=task_id).first()
        session.expunge(job)
        return job


def content_status(db, content_id):
    with db.get_session() as session:
        return session.query(ContentItem).filter_by(id=content_id).first().status


class TestMarkJob:
    def test_processing_sets_the_start_time(self, db, content):
        task = add_job(db, content)
        assert job_tracker.mark_job(task, JobStatus.PROCESSING)
        job = job_of(db, task)
        assert job.status == JobStatus.PROCESSING and job.started_at is not None

    def test_completed_records_the_time_and_the_result(self, db, content):
        task = add_job(db, content)
        job_tracker.mark_job(task, JobStatus.PROCESSING)
        job_tracker.mark_job(task, JobStatus.COMPLETED, result_data={"category": "clean", "confidence": 0.9, "nested": {"x": 1}})
        job = job_of(db, task)
        assert job.status == JobStatus.COMPLETED and job.completed_at is not None
        assert job.processing_time_seconds is not None and job.processing_time_seconds >= 0
        assert job.result_data == {"category": "clean", "confidence": 0.9}      # only plain values are stored

    def test_failed_keeps_the_error(self, db, content):
        task = add_job(db, content)
        job_tracker.mark_job(task, JobStatus.FAILED, error="boom" * 1000, retry_count=3)
        job = job_of(db, task)
        assert job.status == JobStatus.FAILED and job.retry_count == 3 and len(job.last_error) == 2000

    def test_a_late_start_does_not_undo_completion(self, db, content):
        task = add_job(db, content)
        job_tracker.mark_job(task, JobStatus.COMPLETED)
        job_tracker.mark_job(task, JobStatus.PROCESSING)
        assert job_of(db, task).status == JobStatus.COMPLETED

    def test_an_unknown_task_is_reported_not_raised(self, db):
        assert job_tracker.mark_job("no-such-task", JobStatus.PROCESSING) is False


class TestWorkerHooks:
    """The task base class reports what a worker does"""

    class Fake:
        class request:
            retries = 2
        updates = []

        def update_state(self, **kw):
            self.updates.append(kw)

    def test_a_started_task_is_processing(self, db, content):
        task = add_job(db, content)
        BaseClassificationTask.before_start(self.Fake(), task, [content], {})
        assert job_of(db, task).status == JobStatus.PROCESSING

    def test_a_successful_task_is_completed_with_its_result(self, db, content):
        task = add_job(db, content)
        BaseClassificationTask.on_success(self.Fake(), {"category": "spam", "confidence": 0.9}, task, [content], {})
        job = job_of(db, task)
        assert job.status == JobStatus.COMPLETED and job.result_data["category"] == "spam"

    def test_a_retry_is_recorded(self, db, content):
        task = add_job(db, content)
        BaseClassificationTask.on_retry(self.Fake(), RuntimeError("model down"), task, [content], {}, None)
        job = job_of(db, task)
        assert job.status == JobStatus.RETRYING and job.retry_count == 3 and job.last_error == "model down"

    def test_a_task_that_failed_for_good_is_failed_and_its_content_goes_to_the_moderators(self, db, content):
        task = add_job(db, content)
        BaseClassificationTask.on_failure(self.Fake(), RuntimeError("gave up"), task, [content, "text"], {}, None)
        assert job_of(db, task).status == JobStatus.FAILED
        assert content_status(db, content) == ContentStatus.FLAGGED

    def test_content_a_person_already_decided_is_left_alone(self, db, content):
        with db.get_session() as session:
            session.query(ContentItem).filter_by(id=content).first().status = ContentStatus.APPROVED
            session.commit()
        job_tracker.flag_for_review(content)
        assert content_status(db, content) == ContentStatus.APPROVED

    def test_tracking_never_breaks_the_task(self, db, monkeypatch):
        monkeypatch.setattr(job_tracker, "DatabaseManager", lambda: (_ for _ in ()).throw(RuntimeError("db down")))
        assert job_tracker.mark_job("t", JobStatus.PROCESSING) is False
        job_tracker.flag_for_review("c")           # no exception


class TestReconcile:
    def test_jobs_of_content_that_was_already_moderated_are_completed(self, db, content):
        with db.get_session() as session:
            item = session.query(ContentItem).filter_by(id=content).first()
            item.status, item.moderated_at = ContentStatus.APPROVED, datetime(2026, 1, 1)
            session.commit()
        task = add_job(db, content)
        assert job_tracker.reconcile_jobs() >= 1
        job = job_of(db, task)
        assert job.status == JobStatus.COMPLETED and job.completed_at == datetime(2026, 1, 1)

    def test_jobs_still_in_flight_are_left_open(self, db, content):
        task = add_job(db, content)
        job_tracker.reconcile_jobs()
        assert job_of(db, task).status == JobStatus.QUEUED

    def test_jobs_of_deleted_content_are_failed(self, db):
        task = add_job(db, "deleted-content-id")
        job_tracker.reconcile_jobs()
        assert job_of(db, task).status == JobStatus.FAILED

    def test_it_is_idempotent(self, db, content):
        with db.get_session() as session:
            item = session.query(ContentItem).filter_by(id=content).first()
            item.status, item.moderated_at = ContentStatus.REJECTED, datetime.utcnow()
            session.commit()
        add_job(db, content)
        job_tracker.reconcile_jobs()
        assert job_tracker.reconcile_jobs() == 0


class TestEnqueue:
    @pytest.fixture
    def manager(self, db):
        return qm.QueueManager()

    def test_the_job_exists_before_the_task_is_sent_and_uses_the_same_task_id(self, db, content, manager, monkeypatch):
        seen = {}

        def apply_async(args, queue, priority, task_id):
            seen["job_before_send"] = job_of(db, task_id)
            seen["args"], seen["queue"], seen["task_id"] = args, queue, task_id
        monkeypatch.setattr(qm.classify_text_task, "apply_async", apply_async)
        job = manager.create_text_job(content, "hello", priority=5)
        assert seen["job_before_send"] is not None and seen["job_before_send"].status == JobStatus.QUEUED
        assert seen["task_id"] == job.celery_task_id and seen["queue"] == "high" and seen["args"] == [content, "hello", 5]

    def test_a_send_that_fails_leaves_a_failed_job_and_raises(self, db, content, manager, monkeypatch):
        def apply_async(**kw):
            raise ConnectionError("redis is down")
        monkeypatch.setattr(qm.classify_text_task, "apply_async", apply_async)
        with pytest.raises(ConnectionError):
            manager.create_text_job(content, "hello")
        with db.get_session() as session:
            job = session.query(ModerationJob).filter_by(content_id=content).first()
            assert job.status == JobStatus.FAILED and "redis is down" in job.last_error

    @pytest.mark.parametrize("method,args", [("create_image_job", ("f.png",)), ("create_video_job", ("f.mp4",))])
    def test_image_and_video_jobs_are_tracked_the_same_way(self, db, content, manager, monkeypatch, method, args):
        sent = []
        task = qm.classify_image_task if method == "create_image_job" else qm.classify_video_task
        monkeypatch.setattr(task, "apply_async", lambda **kw: sent.append(kw))
        job = getattr(manager, method)(content, *args)
        assert sent[0]["task_id"] == job.celery_task_id and job.status == JobStatus.QUEUED

    def test_queue_statistics_follow_the_job_status(self, db, content, manager):
        before = manager.get_queue_stats()["default"]
        task = add_job(db, content)
        assert manager.get_queue_stats()["default"]["queued"] == before["queued"] + 1
        job_tracker.mark_job(task, JobStatus.COMPLETED)
        assert manager.get_queue_stats()["default"]["queued"] == before["queued"]


class TestWorkerStatus:
    def test_a_worker_that_answers_is_available(self, monkeypatch):
        import celery_app

        class Inspect:
            def ping(self):
                return {"worker1@host": {"ok": "pong"}}
        monkeypatch.setattr(celery_app.app.control, "inspect", lambda timeout=1.0: Inspect())
        assert qm.QueueManager().worker_status() == {"available": True, "workers": 1}

    def test_no_answer_means_no_worker(self, monkeypatch):
        import celery_app

        class Inspect:
            def ping(self):
                return None
        monkeypatch.setattr(celery_app.app.control, "inspect", lambda timeout=1.0: Inspect())
        assert qm.QueueManager().worker_status() == {"available": False, "workers": 0}

    def test_a_broker_error_means_no_worker_not_a_crash(self, monkeypatch):
        import celery_app

        def broken(timeout=1.0):
            raise ConnectionError("no redis")
        monkeypatch.setattr(celery_app.app.control, "inspect", broken)
        status = qm.QueueManager().worker_status()
        assert status["available"] is False and "no redis" in status["error"]

    def test_the_answer_is_cached_briefly(self, monkeypatch):
        import celery_app
        calls = []

        class Inspect:
            def ping(self):
                calls.append(1)
                return {"w": {}}
        monkeypatch.setattr(celery_app.app.control, "inspect", lambda timeout=1.0: Inspect())
        manager = qm.QueueManager()
        manager.worker_status()
        manager.worker_status()
        assert len(calls) == 1
        assert len([manager.worker_status(max_age_seconds=0)]) and len(calls) == 2
