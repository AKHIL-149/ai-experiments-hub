"""
Removing videos and expired accounts completely.

Deleting a video used to remove the database row and the upload only: its frames, clips, thumbnails and
search embeddings stayed on disk forever (and kept turning up in search results). purge_video removes all
of it. Guests are throwaway accounts: after GUEST_TTL_HOURS they and everything they uploaded are deleted.
"""

import logging
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from src.core.config import settings
from src.models.user import User, UserSession
from src.models.video import Video

logger = logging.getLogger(__name__)

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _remove_file(path: Optional[str]) -> None:
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError as e:
        logger.warning(f"Could not remove {path}: {e}")


def purge_video(db: Session, video: Video, delete_files: bool = True) -> None:
    """Delete a video row (its scenes, frames, clips... follow by cascade) and everything stored for it"""
    ext = video.external_id or ""
    if delete_files:
        _remove_file(video.file_path)
        _remove_file(video.thumbnail_path)
        for clip in list(video.clips):
            _remove_file(clip.file_path)
            _remove_file(clip.thumbnail_path)
        if _SAFE_ID.match(ext):  # never build a path from something that is not a plain id
            shutil.rmtree(Path(settings.frames_path) / ext, ignore_errors=True)

    if _SAFE_ID.match(ext):
        try:
            from src.core.vector_store import VideoVectorStore
            store = VideoVectorStore(persist_directory=Path(settings.chroma_persist_directory))
            store.initialize_collections()
            store.delete_video_embeddings(ext)
        except Exception as e:  # search data must not stop the video from being deleted
            logger.warning(f"Could not remove search embeddings of {ext}: {e}")

    db.delete(video)


def purge_expired_guests(db: Session, now: Optional[datetime] = None) -> int:
    """Delete guests older than GUEST_TTL_HOURS with their videos; returns how many were removed"""
    now = now or datetime.utcnow()
    cutoff = now - timedelta(hours=settings.guest_ttl_hours)
    guests = db.query(User).filter(User.is_guest.is_(True), User.created_at < cutoff).all()
    for guest in guests:
        for video in db.query(Video).filter(Video.user_id == guest.id).all():
            purge_video(db, video)
        db.flush()  # the videos first: there is no ORM link from Video to User, so the order would be a guess
        db.delete(guest)
        db.commit()
    if guests:
        logger.info(f"Removed {len(guests)} expired guest account(s) and their videos")
    return len(guests)


def purge_dead_sessions(db: Session, now: Optional[datetime] = None) -> int:
    now = now or datetime.utcnow()
    removed = (
        db.query(UserSession)
        .filter((UserSession.expires_at < now - timedelta(days=7)) | (UserSession.revoked_at < now - timedelta(days=7)))
        .delete(synchronize_session=False)
    )
    db.commit()
    return removed


def ensure_account_schema(engine) -> None:
    """
    Make an existing database ready for accounts when no migration was run: create_all adds the new tables
    but never adds a column to a table that already exists. `alembic upgrade head` does the same thing.
    """
    insp = inspect(engine)
    if "videos" in insp.get_table_names():
        columns = {c["name"] for c in insp.get_columns("videos")}
        if "user_id" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE videos ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_videos_user_id ON videos (user_id)"))
            logger.info("Added videos.user_id")
