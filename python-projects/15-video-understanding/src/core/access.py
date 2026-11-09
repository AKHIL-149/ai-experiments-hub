"""
Who may see which video.

Every endpoint that takes a video, clip or frame id goes through these helpers, so another account's item
answers 404 (the same as an id that does not exist: a 403 would confirm that it is there). Administrators
see everything. With no caller at all the helpers see nothing: forgetting to sign a request in fails closed.
"""

from typing import List, Optional

from sqlalchemy import false
from sqlalchemy.orm import Query, Session

from src.core.auth import current_caller
from src.models.clip import Clip
from src.models.frame import Frame
from src.models.video import Video


def scope_videos(query: Query) -> Query:
    """Limit a Video query to what the current caller may see"""
    caller = current_caller()
    if caller is None:
        return query.filter(false())
    if caller.is_admin:
        return query
    return query.filter(Video.user_id == caller.user_id)


def find_video(db: Session, video_id: str) -> Optional[Video]:
    """The video with this public id if the caller may see it, else None (answer 404)"""
    return scope_videos(db.query(Video).filter(Video.external_id == video_id)).first()


def can_see_video(video: Optional[Video]) -> bool:
    caller = current_caller()
    if video is None or caller is None:
        return False
    return caller.is_admin or video.user_id == caller.user_id


def visible_video_ids(db: Session) -> Optional[List[str]]:
    """Public ids of the videos the caller may see; None means every video (administrators)"""
    caller = current_caller()
    if caller is not None and caller.is_admin:
        return None
    rows = scope_videos(db.query(Video.external_id)).all()
    return [r[0] for r in rows if r[0]]


def restrict_video_ids(db: Session, requested: Optional[List[str]]) -> Optional[List[str]]:
    """
    What a search may look in: the videos asked for, minus the ones the caller may not see.
    None = no limit (an administrator who named no videos). An empty list = nothing to search.
    """
    allowed = visible_video_ids(db)
    if allowed is None:
        return list(requested) if requested else None
    if requested:
        return [v for v in requested if v in set(allowed)]
    return allowed


def can_see_clip(db: Session, clip: Optional[Clip]) -> bool:
    """A clip belongs to whoever owns its video; administrators see every clip"""
    caller = current_caller()
    if clip is None or caller is None:
        return False
    if caller.is_admin:
        return True
    return can_see_video(db.query(Video).filter(Video.id == clip.video_id).first())


def find_clip(db: Session, clip_id: str) -> Optional[Clip]:
    clip = db.query(Clip).filter(Clip.external_id == clip_id).first()
    return clip if can_see_clip(db, clip) else None


def find_frame(db: Session, frame_id: int) -> Optional[Frame]:
    frame = db.query(Frame).filter(Frame.id == frame_id).first()
    if frame is None:
        return None
    video = db.query(Video).filter(Video.id == frame.video_id).first()
    return frame if can_see_video(video) else None


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class ScopedStore:
    """
    A vector store that can only see the videos the caller may see.

    The filter is applied inside the vector search, not to its results afterwards: filtering afterwards
    would let other accounts' videos crowd a person's own out of the top results, and would make the number
    of results depend on what other people uploaded.
    """

    def __init__(self, store, allowed: Optional[List[str]]):
        self._store = store
        self._allowed = allowed  # None = no limit (administrator), [] = nothing

    def __getattr__(self, name):
        return getattr(self._store, name)

    def _search(self, method: str, *args, **kwargs):
        from src.core.vector_store import SearchResult
        allowed, single = self._allowed, kwargs.get("video_id")
        if allowed is not None:
            if allowed == [] or (single and single not in allowed):
                return SearchResult(ids=[], distances=[], metadatas=[], documents=[])
            if not single:
                kwargs["video_ids"] = allowed
        return getattr(self._store, method)(*args, **kwargs)

    def search_frames(self, *a, **k):
        return self._search("search_frames", *a, **k)

    def search_transcripts(self, *a, **k):
        return self._search("search_transcripts", *a, **k)

    def search_scenes(self, *a, **k):
        return self._search("search_scenes", *a, **k)


def scoped_store(store, requested: Optional[List[str]] = None) -> ScopedStore:
    """Wrap a vector store for the current caller; `requested` is the videos the request asked for, if any"""
    from src.core.database import SessionLocal
    db = SessionLocal()
    try:
        allowed = restrict_video_ids(db, requested)
    finally:
        db.close()
    return ScopedStore(store, allowed)
