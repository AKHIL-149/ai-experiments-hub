"""
Unit tests for video clip API endpoints (AKHIL-425)

Every function under test does `from src.core.database import get_db` /
`from src.models import ...` *locally*, inside the function body - so the
patch targets below are the source modules (src.core.database.get_db,
src.services.highlights.clip_creator.ClipCreator, etc.), not
src.api.clips.<name>, which would not exist as a module-level attribute.
"""

import pytest
from fastapi import BackgroundTasks, HTTPException
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from contextlib import contextmanager
from datetime import datetime


def _mock_get_db(mock_session):
    """Build a get_db() replacement usable as `with get_db() as db: ...`"""
    @contextmanager
    def _get_db():
        yield mock_session
    return _get_db


def _db_with(clip=None, video=None):
    """A MagicMock db session whose .query(Model) dispatches by model name,
    so a function that queries both Clip and Video gets the right mock back
    for each - a single flat `.first.return_value` would answer both
    queries identically, which is wrong."""
    mock_db = MagicMock()

    def query_side_effect(model):
        m = MagicMock()
        name = getattr(model, "__name__", "")
        if name == "Clip":
            m.filter.return_value.first.return_value = clip
            m.filter.return_value.all.return_value = [clip] if clip else []
            m.filter.return_value.count.return_value = 1 if clip else 0
            m.filter.return_value.in_.return_value.all.return_value = [clip] if clip else []
        elif name == "Video":
            m.filter.return_value.first.return_value = video
        return m

    mock_db.query.side_effect = query_side_effect
    return mock_db


def _fake_clip(**overrides):
    from src.models import ClipStatus
    clip = Mock()
    clip.external_id = "clip-abc"
    clip.video_id = 1
    clip.title = "Test Clip"
    clip.description = None
    clip.start_time = 10.0
    clip.end_time = 25.0
    clip.file_path = None
    clip.file_size = None
    clip.format = "mp4"
    clip.resolution = "original"
    clip.status = ClipStatus.PENDING
    clip.error_message = None
    clip.thumbnail_path = None
    clip.created_at = datetime.now()
    clip.completed_at = None
    clip.extra_metadata = {}
    for k, v in overrides.items():
        setattr(clip, k, v)
    return clip


def _fake_video(**overrides):
    video = Mock()
    video.id = 1
    video.external_id = "vid-abc"
    video.file_path = "./data/uploads/vid-abc.mp4"
    for k, v in overrides.items():
        setattr(video, k, v)
    return video


class TestCreateClipEndpoint:
    """POST /api/videos/{video_id}/clip"""

    @pytest.mark.asyncio
    async def test_create_clip_success(self):
        from src.api.clips import create_clip, CreateClipRequest

        video = _fake_video()
        mock_db = _db_with(video=video)
        background_tasks = BackgroundTasks()

        with patch("src.core.database.get_db", _mock_get_db(mock_db)):
            response = await create_clip(
                video_id="vid-abc",
                background_tasks=background_tasks,
                request=CreateClipRequest(start_time=10.0, end_time=25.0, title="My Clip"),
            )

        assert response.status == "pending"
        assert response.duration == 15.0
        assert response.video_id == "vid-abc"

        added_clip = mock_db.add.call_args[0][0]
        assert added_clip.video_id == video.id  # internal FK, not the external string
        assert added_clip.title == "My Clip"
        assert added_clip.start_time == 10.0

        assert len(background_tasks.tasks) == 1
        scheduled = background_tasks.tasks[0]
        assert scheduled.func.__name__ == "create_clip_task"
        assert scheduled.args[1] == "vid-abc"

    @pytest.mark.asyncio
    async def test_create_clip_invalid_time_range_rejected_before_persisting(self):
        from src.api.clips import create_clip, CreateClipRequest

        mock_db = _db_with(video=_fake_video())
        background_tasks = BackgroundTasks()

        with patch("src.core.database.get_db", _mock_get_db(mock_db)):
            with pytest.raises(HTTPException) as exc_info:
                await create_clip(
                    video_id="vid-abc",
                    background_tasks=background_tasks,
                    request=CreateClipRequest(start_time=20.0, end_time=10.0),
                )

        assert exc_info.value.status_code == 400
        mock_db.add.assert_not_called()
        assert len(background_tasks.tasks) == 0

    @pytest.mark.asyncio
    async def test_create_clip_video_not_found(self):
        from src.api.clips import create_clip, CreateClipRequest

        mock_db = _db_with(video=None)
        background_tasks = BackgroundTasks()

        with patch("src.core.database.get_db", _mock_get_db(mock_db)):
            with pytest.raises(HTTPException) as exc_info:
                await create_clip(
                    video_id="nonexistent",
                    background_tasks=background_tasks,
                    request=CreateClipRequest(start_time=0.0, end_time=10.0),
                )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_create_clip_video_without_source_file(self):
        from src.api.clips import create_clip, CreateClipRequest

        mock_db = _db_with(video=_fake_video(file_path=None))
        background_tasks = BackgroundTasks()

        with patch("src.core.database.get_db", _mock_get_db(mock_db)):
            with pytest.raises(HTTPException) as exc_info:
                await create_clip(
                    video_id="vid-abc",
                    background_tasks=background_tasks,
                    request=CreateClipRequest(start_time=0.0, end_time=10.0),
                )

        assert exc_info.value.status_code == 400


class TestCreateClipTask:
    """The create_clip_task background function - the code that was
    previously a complete no-op (the AKHIL-425 bug: a fake success
    response with an id that 404'd on lookup)"""

    @pytest.mark.asyncio
    async def test_successful_creation_updates_clip_to_completed(self):
        from src.api.clips import create_clip_task, CreateClipRequest

        clip_row = _fake_clip()
        video = _fake_video()
        mock_db = _db_with(clip=clip_row, video=video)

        fake_metadata = Mock(output_path="./storage/clips/out.mp4", file_size_bytes=12345)
        fake_processor = Mock()

        with patch("src.core.database.get_db", _mock_get_db(mock_db)), \
             patch("asyncio.to_thread", new=AsyncMock(side_effect=[fake_metadata, None])), \
             patch("src.core.video_processor.create_video_processor", return_value=fake_processor):

            await create_clip_task(
                clip_id="clip-abc",
                video_id="vid-abc",
                config=CreateClipRequest(start_time=10.0, end_time=25.0),
            )

        assert clip_row.status.value == "completed"
        assert clip_row.file_path == "./storage/clips/out.mp4"
        assert clip_row.file_size == 12345
        assert clip_row.completed_at is not None

    @pytest.mark.asyncio
    async def test_ffmpeg_failure_marks_clip_failed_not_silently_lost(self):
        """This is the exact bug this fix addressed: a failed/never-run
        creation used to leave the clip's fake "pending" response
        pointing at nothing. Now it must land as FAILED with a real
        error message."""
        from src.api.clips import create_clip_task, CreateClipRequest

        clip_row = _fake_clip()
        video = _fake_video()
        mock_db = _db_with(clip=clip_row, video=video)

        with patch("src.core.database.get_db", _mock_get_db(mock_db)), \
             patch("asyncio.to_thread", new=AsyncMock(side_effect=RuntimeError("ffmpeg exited 1"))):

            await create_clip_task(
                clip_id="clip-abc",
                video_id="vid-abc",
                config=CreateClipRequest(start_time=10.0, end_time=25.0),
            )

        assert clip_row.status.value == "failed"
        assert "ffmpeg exited 1" in clip_row.error_message

    @pytest.mark.asyncio
    async def test_thumbnail_failure_does_not_fail_the_whole_clip(self):
        """Thumbnail generation is best-effort - losing it shouldn't
        throw away an otherwise-successful clip"""
        from src.api.clips import create_clip_task, CreateClipRequest

        clip_row = _fake_clip()
        video = _fake_video()
        mock_db = _db_with(clip=clip_row, video=video)
        fake_metadata = Mock(output_path="./storage/clips/out.mp4", file_size_bytes=999)

        async def to_thread_side_effect(func, *args, **kwargs):
            # First call is the real clip creation (succeeds); second is
            # the thumbnail extraction (fails)
            if to_thread_side_effect.calls == 0:
                to_thread_side_effect.calls += 1
                return fake_metadata
            raise RuntimeError("no frame at that timestamp")
        to_thread_side_effect.calls = 0

        with patch("src.core.database.get_db", _mock_get_db(mock_db)), \
             patch("asyncio.to_thread", new=to_thread_side_effect), \
             patch("src.core.video_processor.create_video_processor", return_value=Mock()):

            await create_clip_task(
                clip_id="clip-abc",
                video_id="vid-abc",
                config=CreateClipRequest(start_time=10.0, end_time=25.0),
            )

        assert clip_row.status.value == "completed"
        assert clip_row.thumbnail_path is None
        assert clip_row.file_path == "./storage/clips/out.mp4"


class TestGetListDeleteClip:
    @pytest.mark.asyncio
    async def test_get_clip_not_found(self):
        from src.api.clips import get_clip

        mock_db = _db_with(clip=None)
        with patch("src.core.database.get_db", _mock_get_db(mock_db)):
            with pytest.raises(HTTPException) as exc_info:
                await get_clip("nonexistent")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_clip_found_maps_video_external_id(self):
        from src.api.clips import get_clip
        from src.models import ClipStatus

        clip_row = _fake_clip(status=ClipStatus.COMPLETED, file_path="./storage/clips/out.mp4")
        video = _fake_video()
        mock_db = _db_with(clip=clip_row, video=video)

        with patch("src.core.database.get_db", _mock_get_db(mock_db)):
            response = await get_clip("clip-abc")

        # video_id in the response must be the public external id, not the
        # internal integer FK stored on the Clip row
        assert response.video_id == "vid-abc"
        assert response.status == "completed"

    @pytest.mark.asyncio
    async def test_delete_clip_removes_file_and_row(self):
        from src.api.clips import delete_clip

        clip_row = _fake_clip(file_path="./storage/clips/out.mp4")
        mock_db = _db_with(clip=clip_row)

        with patch("src.core.database.get_db", _mock_get_db(mock_db)), \
             patch("os.path.exists", return_value=True), \
             patch("os.remove") as mock_remove:
            result = await delete_clip("clip-abc", delete_file=True)

        assert result["success"] is True
        mock_remove.assert_called_once_with("./storage/clips/out.mp4")
        mock_db.delete.assert_called_once_with(clip_row)

    @pytest.mark.asyncio
    async def test_delete_clip_not_found(self):
        from src.api.clips import delete_clip

        mock_db = _db_with(clip=None)
        with patch("src.core.database.get_db", _mock_get_db(mock_db)):
            with pytest.raises(HTTPException) as exc_info:
                await delete_clip("nonexistent")
        assert exc_info.value.status_code == 404


class TestDownloadClip:
    @pytest.mark.asyncio
    async def test_download_not_ready_returns_400(self):
        from src.api.clips import download_clip
        from src.models import ClipStatus

        clip_row = _fake_clip(status=ClipStatus.PROCESSING)
        mock_db = _db_with(clip=clip_row)

        with patch("src.core.database.get_db", _mock_get_db(mock_db)):
            with pytest.raises(HTTPException) as exc_info:
                await download_clip("clip-abc")
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_download_missing_file_returns_404(self):
        from src.api.clips import download_clip
        from src.models import ClipStatus

        clip_row = _fake_clip(status=ClipStatus.COMPLETED, file_path="./storage/clips/gone.mp4")
        mock_db = _db_with(clip=clip_row)

        with patch("src.core.database.get_db", _mock_get_db(mock_db)), \
             patch("os.path.exists", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await download_clip("clip-abc")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_download_success_returns_file_response(self):
        from src.api.clips import download_clip
        from src.models import ClipStatus
        from fastapi.responses import FileResponse

        clip_row = _fake_clip(status=ClipStatus.COMPLETED, file_path="./storage/clips/out.mp4")
        mock_db = _db_with(clip=clip_row)

        with patch("src.core.database.get_db", _mock_get_db(mock_db)), \
             patch("os.path.exists", return_value=True):
            response = await download_clip("clip-abc")

        assert isinstance(response, FileResponse)


class TestHighlightReel:
    @pytest.mark.asyncio
    async def test_reel_rejects_missing_clip_ids(self):
        from src.api.clips import create_highlight_reel, CreateHighlightReelRequest

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []  # none found

        with patch("src.core.database.get_db", _mock_get_db(mock_db)):
            with pytest.raises(HTTPException) as exc_info:
                await create_highlight_reel(
                    background_tasks=BackgroundTasks(),
                    request=CreateHighlightReelRequest(title="Reel", clip_ids=["a", "b"]),
                )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_reel_rejects_incomplete_clips(self):
        from src.api.clips import create_highlight_reel, CreateHighlightReelRequest
        from src.models import ClipStatus

        clip1 = _fake_clip(external_id="a", status=ClipStatus.COMPLETED)
        clip2 = _fake_clip(external_id="b", status=ClipStatus.PROCESSING)
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [clip1, clip2]

        with patch("src.core.database.get_db", _mock_get_db(mock_db)):
            with pytest.raises(HTTPException) as exc_info:
                await create_highlight_reel(
                    background_tasks=BackgroundTasks(),
                    request=CreateHighlightReelRequest(title="Reel", clip_ids=["a", "b"]),
                )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_reel_task_success_concatenates_and_completes(self):
        from src.api.clips import create_highlight_reel_task
        from src.models import ClipStatus

        reel_row = _fake_clip(external_id="reel-1", status=ClipStatus.PENDING)
        clip_a = _fake_clip(external_id="a", file_path="./storage/clips/a.mp4", start_time=0, end_time=10)
        clip_b = _fake_clip(external_id="b", file_path="./storage/clips/b.mp4", start_time=0, end_time=10)

        mock_db = MagicMock()

        def query_side_effect(model):
            m = MagicMock()
            name = getattr(model, "__name__", "")
            if name == "Clip":
                m.filter.return_value.first.return_value = reel_row
                m.filter.return_value.all.return_value = [clip_a, clip_b]
            return m
        mock_db.query.side_effect = query_side_effect

        fake_reel_meta = Mock(output_path="./storage/clips/reel_out.mp4", file_size_bytes=54321)

        with patch("src.core.database.get_db", _mock_get_db(mock_db)), \
             patch("asyncio.to_thread", new=AsyncMock(return_value=fake_reel_meta)):

            await create_highlight_reel_task(
                reel_id="reel-1",
                clip_ids=["a", "b"],
                title="Reel",
                transition_type="fade",
                transition_duration=0.5,
            )

        assert reel_row.status.value == "completed"
        assert reel_row.file_path == "./storage/clips/reel_out.mp4"
        assert reel_row.file_size == 54321

    @pytest.mark.asyncio
    async def test_reel_task_missing_source_file_marks_failed(self):
        from src.api.clips import create_highlight_reel_task
        from src.models import ClipStatus

        reel_row = _fake_clip(external_id="reel-1", status=ClipStatus.PENDING)
        clip_a = _fake_clip(external_id="a", file_path=None)  # never actually created

        mock_db = MagicMock()

        def query_side_effect(model):
            m = MagicMock()
            name = getattr(model, "__name__", "")
            if name == "Clip":
                m.filter.return_value.first.return_value = reel_row
                m.filter.return_value.all.return_value = [clip_a]
            return m
        mock_db.query.side_effect = query_side_effect

        with patch("src.core.database.get_db", _mock_get_db(mock_db)):
            await create_highlight_reel_task(
                reel_id="reel-1",
                clip_ids=["a"],
                title="Reel",
                transition_type="fade",
                transition_duration=0.5,
            )

        assert reel_row.status.value == "failed"
        assert reel_row.error_message
