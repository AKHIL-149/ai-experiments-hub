"""
Background jobs: the queue that downloads and processes videos.

A job is a row, not a function call in memory, so a server restart loses nothing: jobs that were waiting
are still waiting, and a job that was running when the server died is found by its stale heartbeat and
put back in the queue.
"""

import enum
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from src.core.database import Base


class JobKind(str, enum.Enum):
    DOWNLOAD = "download"   # fetch a YouTube video or a stream
    PROCESS = "process"     # the full analysis pipeline


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_STATUSES = (JobStatus.QUEUED.value, JobStatus.RUNNING.value)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True)
    # plain strings, not database enums: adding a kind or a status later must not need an ALTER TYPE
    kind = Column(String(20), nullable=False, index=True)
    status = Column(String(20), nullable=False, default=JobStatus.QUEUED.value, index=True)
    video_id = Column(Integer, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, nullable=True, index=True)  # the video's owner (None in single-user mode)
    payload = Column(JSON, nullable=True)                 # what a download needs: url, title, quality, ...
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=2)
    error = Column(Text, nullable=True)
    cancel_requested = Column(Boolean, nullable=False, default=False)
    worker = Column(String(80), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    heartbeat_at = Column(DateTime, nullable=True)
