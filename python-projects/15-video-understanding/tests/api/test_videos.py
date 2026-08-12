"""
Tests for video management API endpoints
"""

import pytest
from fastapi.testclient import TestClient
from fastapi import BackgroundTasks
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from contextlib import contextmanager
from datetime import datetime
import io
import os
import subprocess

# Import FastAPI app (will need to be created)
# from server import app


def _mock_get_db(mock_session):
    """Build a get_db() replacement usable as `with get_db() as db: ...`"""
    @contextmanager
    def _get_db():
        yield mock_session
    return _get_db


class TestVideoUploadEndpoint:
    """Tests for POST /api/videos/upload"""

    @pytest.fixture
    def mock_video_file(self):
        """Create a mock video file for upload"""
        content = b"fake video content"
        return ("test_video.mp4", io.BytesIO(content), "video/mp4")

    @pytest.mark.asyncio
    async def test_upload_video_success(self, mock_video_file):
        """Test successful video upload"""
        # TODO: Implement with actual FastAPI app
        # client = TestClient(app)
        # response = client.post(
        #     "/api/videos/upload",
        #     files={"file": mock_video_file},
        #     data={"title": "Test Video", "auto_process": "true"}
        # )
        # assert response.status_code == 200
        # assert "video_id" in response.json()
        pass

    @pytest.mark.asyncio
    async def test_upload_video_invalid_format(self):
        """Test upload with invalid video format"""
        # TODO: Test rejection of non-video files
        pass

    @pytest.mark.asyncio
    async def test_upload_video_no_auto_process(self, mock_video_file):
        """Test upload without automatic processing"""
        # TODO: Verify auto_process=false prevents background processing
        pass

    @pytest.mark.asyncio
    async def test_upload_video_custom_title(self, mock_video_file):
        """Test upload with custom title"""
        # TODO: Verify custom title is used instead of filename
        pass


class TestYouTubeVideoEndpoint:
    """Tests for POST /api/videos/youtube"""

    @pytest.mark.asyncio
    async def test_youtube_video_valid_url(self):
        """Test processing valid YouTube URL"""
        # TODO: Mock yt-dlp download
        # Test valid youtube.com and youtu.be URLs
        pass

    @pytest.mark.asyncio
    async def test_youtube_video_invalid_url(self):
        """Test rejection of non-YouTube URLs"""
        # TODO: Test 400 error for invalid URLs
        pass

    @pytest.mark.asyncio
    async def test_youtube_video_with_quality(self):
        """Test YouTube download with quality selection"""
        # TODO: Verify quality parameter is passed to yt-dlp
        pass

    @pytest.mark.asyncio
    @patch('src.api.videos.download_youtube_video')
    async def test_youtube_video_download_failure(self, mock_download):
        """Test handling of download failure"""
        # TODO: Test error handling when download fails
        pass


class TestStreamingVideoEndpoint:
    """Tests for POST /api/videos/stream"""

    @pytest.mark.asyncio
    async def test_streaming_video_http_url(self):
        """A valid http:// URL is accepted, persisted, and scheduled for download"""
        from src.api.videos import process_streaming_video, StreamingVideoRequest

        mock_db = MagicMock()
        background_tasks = BackgroundTasks()

        with patch("src.api.videos.get_db", _mock_get_db(mock_db)):
            response = await process_streaming_video(
                background_tasks=background_tasks,
                request=StreamingVideoRequest(url="http://example.com/video.mp4", title="My Stream"),
                auto_process=True,
            )

        assert response.status == "downloading"
        assert response.video_id

        # A Video row was persisted with the right source metadata
        added_video = mock_db.add.call_args[0][0]
        assert added_video.source_url == "http://example.com/video.mp4"
        assert added_video.title == "My Stream"
        assert added_video.source_type.value == "stream"
        assert added_video.processing_status.value == "downloading"

        # The real download was scheduled, not skipped
        assert len(background_tasks.tasks) == 1
        scheduled = background_tasks.tasks[0]
        assert scheduled.func.__name__ == "download_streaming_video"
        assert scheduled.args == (response.video_id, "http://example.com/video.mp4", "My Stream", True)

    @pytest.mark.asyncio
    async def test_streaming_video_m3u8_playlist(self):
        """An HLS (.m3u8) URL is accepted the same as any other http(s) URL -
        ffmpeg handles the protocol distinction, not this endpoint"""
        from src.api.videos import process_streaming_video, StreamingVideoRequest

        mock_db = MagicMock()
        background_tasks = BackgroundTasks()
        url = "https://example.com/stream/playlist.m3u8"

        with patch("src.api.videos.get_db", _mock_get_db(mock_db)):
            response = await process_streaming_video(
                background_tasks=background_tasks,
                request=StreamingVideoRequest(url=url),
                auto_process=False,
            )

        assert response.status == "downloading"
        added_video = mock_db.add.call_args[0][0]
        assert added_video.source_url == url
        # No title given -> falls back to the generic default
        assert added_video.title == "Streaming Video"

    @pytest.mark.asyncio
    async def test_streaming_video_invalid_protocol(self):
        """Non-HTTP(S) protocols are rejected with 400 before anything is persisted"""
        from fastapi import HTTPException
        from src.api.videos import process_streaming_video, StreamingVideoRequest

        mock_db = MagicMock()
        background_tasks = BackgroundTasks()

        for bad_url in ["ftp://example.com/video.mp4", "file:///etc/passwd", "not-a-url"]:
            with patch("src.api.videos.get_db", _mock_get_db(mock_db)):
                with pytest.raises(HTTPException) as exc_info:
                    await process_streaming_video(
                        background_tasks=background_tasks,
                        request=StreamingVideoRequest(url=bad_url),
                    )
            assert exc_info.value.status_code == 400

        # Nothing should have been persisted or scheduled for any of them
        mock_db.add.assert_not_called()
        assert len(background_tasks.tasks) == 0


class TestDownloadStreamingVideoTask:
    """Tests for the download_streaming_video background task
    (the actual ffmpeg download logic, AKHIL-423)"""

    def _mock_video_row(self):
        """A Mock standing in for the SQLAlchemy Video row, with settable attrs"""
        video = Mock()
        video.title = None
        video.file_path = None
        video.duration_seconds = None
        video.processing_status = None
        video.error_message = None
        return video

    @pytest.mark.asyncio
    async def test_successful_download_updates_video_and_triggers_processing(self):
        from src.api.videos import download_streaming_video

        mock_video = self._mock_video_row()
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_video

        fake_ffmpeg_result = Mock(returncode=0, stderr="")

        with patch("src.api.videos.get_db", _mock_get_db(mock_db)), \
             patch("src.api.videos.os.path.exists", return_value=True), \
             patch("asyncio.to_thread", new=AsyncMock(return_value=fake_ffmpeg_result)), \
             patch("src.api.videos.get_video_duration", new=AsyncMock(return_value=123.4)), \
             patch("src.api.videos.process_video_background", new=AsyncMock()) as mock_process, \
             patch("src.api.websockets.send_progress_update", new=AsyncMock()), \
             patch("src.api.websockets.send_processing_error", new=AsyncMock()):

            await download_streaming_video(
                video_id="vid-123",
                url="http://example.com/video.mp4",
                title="My Stream",
                auto_process=True,
            )

        # Real duration and file path were written to the Video row
        assert mock_video.duration_seconds == 123.4
        assert mock_video.file_path == "./data/uploads/vid-123.mp4"
        assert mock_video.title == "My Stream"
        assert mock_video.processing_status.value == "processing"
        # Auto-process was actually invoked, not just claimed
        mock_process.assert_awaited_once_with("vid-123")

    @pytest.mark.asyncio
    async def test_download_without_auto_process_stays_pending(self):
        from src.api.videos import download_streaming_video

        mock_video = self._mock_video_row()
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_video
        fake_ffmpeg_result = Mock(returncode=0, stderr="")

        with patch("src.api.videos.get_db", _mock_get_db(mock_db)), \
             patch("src.api.videos.os.path.exists", return_value=True), \
             patch("asyncio.to_thread", new=AsyncMock(return_value=fake_ffmpeg_result)), \
             patch("src.api.videos.get_video_duration", new=AsyncMock(return_value=60.0)), \
             patch("src.api.videos.process_video_background", new=AsyncMock()) as mock_process, \
             patch("src.api.websockets.send_progress_update", new=AsyncMock()), \
             patch("src.api.websockets.send_processing_error", new=AsyncMock()):

            await download_streaming_video(
                video_id="vid-456", url="http://example.com/video.mp4", title=None, auto_process=False,
            )

        assert mock_video.processing_status.value == "pending"
        mock_process.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ffmpeg_failure_marks_video_failed_not_silently_lost(self):
        """This is the exact bug AKHIL-423 fixed: a failed download used to
        vanish silently (Video row never existed). Now it must land as FAILED
        with a real error message, and auto-process must never run."""
        from src.api.videos import download_streaming_video

        mock_video = self._mock_video_row()
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_video

        fake_ffmpeg_result = Mock(returncode=1, stderr="Connection refused")

        with patch("src.api.videos.get_db", _mock_get_db(mock_db)), \
             patch("src.api.videos.os.path.exists", return_value=False), \
             patch("asyncio.to_thread", new=AsyncMock(return_value=fake_ffmpeg_result)), \
             patch("src.api.videos.process_video_background", new=AsyncMock()) as mock_process, \
             patch("src.api.websockets.send_progress_update", new=AsyncMock()), \
             patch("src.api.websockets.send_processing_error", new=AsyncMock()) as mock_error:

            await download_streaming_video(
                video_id="vid-789", url="http://bad.example.com/nope.mp4", title=None, auto_process=True,
            )

        assert mock_video.processing_status.value == "failed"
        assert "Connection refused" in mock_video.error_message
        mock_process.assert_not_awaited()
        mock_error.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ffmpeg_command_includes_safety_duration_cap(self):
        """A truly live (infinite) stream must not hang the pipeline forever -
        verify the -t cap is actually passed to ffmpeg, not just documented"""
        from src.api.videos import download_streaming_video

        mock_video = self._mock_video_row()
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_video

        captured_cmd = {}

        async def fake_to_thread(func, *args, **kwargs):
            # args[0] is the ffmpeg argv list passed to subprocess.run
            captured_cmd["cmd"] = args[0]
            return Mock(returncode=0, stderr="")

        with patch("src.api.videos.get_db", _mock_get_db(mock_db)), \
             patch("src.api.videos.os.path.exists", return_value=True), \
             patch("asyncio.to_thread", new=fake_to_thread), \
             patch("src.api.videos.get_video_duration", new=AsyncMock(return_value=10.0)), \
             patch("src.api.videos.process_video_background", new=AsyncMock()), \
             patch("src.api.websockets.send_progress_update", new=AsyncMock()), \
             patch("src.api.websockets.send_processing_error", new=AsyncMock()):

            await download_streaming_video(
                video_id="vid-cap", url="http://example.com/live.m3u8", title=None, auto_process=False,
            )

        cmd = captured_cmd["cmd"]
        assert cmd[0] == "ffmpeg"
        assert "-t" in cmd
        assert cmd[cmd.index("-t") + 1] == "3600"
        assert "-c" in cmd and cmd[cmd.index("-c") + 1] == "copy"


class TestListVideosEndpoint:
    """Tests for GET /api/videos"""

    @pytest.mark.asyncio
    async def test_list_videos_default_pagination(self):
        """Test listing videos with default pagination"""
        # TODO: Test page=1, page_size=20 defaults
        pass

    @pytest.mark.asyncio
    async def test_list_videos_custom_pagination(self):
        """Test listing videos with custom pagination"""
        # TODO: Test custom page and page_size
        pass

    @pytest.mark.asyncio
    async def test_list_videos_filter_by_status(self):
        """Test filtering videos by processing status"""
        # TODO: Test status filter (pending, processing, completed, failed)
        pass

    @pytest.mark.asyncio
    async def test_list_videos_filter_by_source_type(self):
        """Test filtering videos by source type"""
        # TODO: Test source_type filter (local, youtube, stream)
        pass

    @pytest.mark.asyncio
    async def test_list_videos_empty_result(self):
        """Test listing when no videos exist"""
        # TODO: Test empty list response
        pass


class TestGetVideoEndpoint:
    """Tests for GET /api/videos/{video_id}"""

    @pytest.mark.asyncio
    async def test_get_video_success(self):
        """Test retrieving existing video"""
        # TODO: Test successful video retrieval
        pass

    @pytest.mark.asyncio
    async def test_get_video_not_found(self):
        """Test retrieving non-existent video"""
        # TODO: Test 404 error
        pass

    @pytest.mark.asyncio
    async def test_get_video_complete_metadata(self):
        """Test video response includes all metadata"""
        # TODO: Verify all fields present in response
        pass


class TestDeleteVideoEndpoint:
    """Tests for DELETE /api/videos/{video_id}"""

    @pytest.mark.asyncio
    async def test_delete_video_with_files(self):
        """Test deleting video with file deletion"""
        # TODO: Test delete_files=true removes video files
        pass

    @pytest.mark.asyncio
    async def test_delete_video_keep_files(self):
        """Test deleting video metadata only"""
        # TODO: Test delete_files=false keeps files
        pass

    @pytest.mark.asyncio
    async def test_delete_video_not_found(self):
        """Test deleting non-existent video"""
        # TODO: Test 404 error
        pass


class TestVideoStatusEndpoint:
    """Tests for GET /api/videos/{video_id}/status"""

    @pytest.mark.asyncio
    async def test_get_status_pending(self):
        """Test status for pending video"""
        # TODO: Test pending status response
        pass

    @pytest.mark.asyncio
    async def test_get_status_processing(self):
        """Test status for processing video"""
        # TODO: Test processing status with progress
        pass

    @pytest.mark.asyncio
    async def test_get_status_completed(self):
        """Test status for completed video"""
        # TODO: Test completed status
        pass

    @pytest.mark.asyncio
    async def test_get_status_failed(self):
        """Test status for failed video"""
        # TODO: Test failed status with error message
        pass


class TestProcessVideoEndpoint:
    """Tests for POST /api/videos/{video_id}/process"""

    @pytest.mark.asyncio
    async def test_process_video_default_config(self):
        """Test processing with default configuration"""
        # TODO: Test all processing stages enabled by default
        pass

    @pytest.mark.asyncio
    async def test_process_video_custom_config(self):
        """Test processing with custom configuration"""
        # TODO: Test selective processing stages
        pass

    @pytest.mark.asyncio
    async def test_process_video_already_processing(self):
        """Test processing video that's already being processed"""
        # TODO: Test 409 conflict error
        pass

    @pytest.mark.asyncio
    async def test_process_video_not_found(self):
        """Test processing non-existent video"""
        # TODO: Test 404 error
        pass

    @pytest.mark.asyncio
    async def test_process_video_background_task(self):
        """/process schedules the real process_video_background pipeline
        (process_video_pipeline was a dead stub, deleted in AKHIL-414)"""
        from fastapi import BackgroundTasks
        from src.api.processing import process_video
        from src.models import VideoStatus

        mock_video = Mock(file_path="./data/uploads/vid-1.mp4", processing_status=None)
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_video
        background_tasks = BackgroundTasks()

        with patch("src.core.database.get_db", _mock_get_db(mock_db)), \
             patch("src.api.videos.process_video_background", new=AsyncMock()) as mock_pipeline:
            response = await process_video(video_id="vid-1", background_tasks=background_tasks, request=None)

        assert response.status == "processing"
        assert mock_video.processing_status == VideoStatus.PROCESSING
        assert len(background_tasks.tasks) == 1
        # process_video imports process_video_background locally, so the
        # scheduled callable should be this exact patched mock
        assert background_tasks.tasks[0].func is mock_pipeline
        assert background_tasks.tasks[0].args == ("vid-1",)


class TestReprocessVideoEndpoint:
    """Tests for POST /api/videos/{video_id}/reprocess"""

    @pytest.mark.asyncio
    async def test_reprocess_scenes_only(self):
        """Test reprocessing scenes only"""
        # TODO: Test selective reprocessing
        pass

    @pytest.mark.asyncio
    async def test_reprocess_multiple_stages(self):
        """Test reprocessing multiple stages"""
        # TODO: Test multiple reprocess flags
        pass

    @pytest.mark.asyncio
    async def test_reprocess_no_stages_selected(self):
        """Test reprocess request with no stages selected"""
        # TODO: Test validation error or no-op
        pass


class TestGetScenesEndpoint:
    """Tests for GET /api/videos/{video_id}/scenes"""

    @pytest.mark.asyncio
    async def test_get_scenes_success(self):
        """Test retrieving scenes for processed video"""
        # TODO: Test scenes list response
        pass

    @pytest.mark.asyncio
    async def test_get_scenes_no_scenes(self):
        """Test retrieving scenes for video without scenes"""
        # TODO: Test empty scenes list
        pass

    @pytest.mark.asyncio
    async def test_get_scenes_metadata(self):
        """Test scene metadata completeness"""
        # TODO: Verify all scene fields present
        pass


class TestGetTranscriptEndpoint:
    """Tests for GET /api/videos/{video_id}/transcript"""

    @pytest.mark.asyncio
    async def test_get_transcript_success(self):
        """Test retrieving full transcript"""
        # TODO: Test transcript response
        pass

    @pytest.mark.asyncio
    async def test_get_transcript_filter_by_speaker(self):
        """Test filtering transcript by speaker"""
        # TODO: Test speaker_id filter
        pass

    @pytest.mark.asyncio
    async def test_get_transcript_no_audio(self):
        """Test transcript for video without audio"""
        # TODO: Test empty transcript response
        pass


class TestGetFramesEndpoint:
    """Tests for GET /api/videos/{video_id}/frames"""

    @pytest.mark.asyncio
    async def test_get_frames_default_pagination(self):
        """Test frames with default pagination"""
        # TODO: Test page=1, page_size=50
        pass

    @pytest.mark.asyncio
    async def test_get_frames_custom_page_size(self):
        """Test frames with custom page size"""
        # TODO: Test custom page_size (max 200)
        pass

    @pytest.mark.asyncio
    async def test_get_frames_keyframes_only(self):
        """Test filtering keyframes only"""
        # TODO: Test keyframes_only=true
        pass

    @pytest.mark.asyncio
    async def test_get_frames_filter_by_scene(self):
        """Test filtering frames by scene"""
        # TODO: Test scene_id filter
        pass

    @pytest.mark.asyncio
    async def test_get_frames_page_out_of_range(self):
        """Test requesting page beyond available frames"""
        # TODO: Test empty frames list for high page numbers
        pass


class TestGetKeyframesEndpoint:
    """Tests for GET /api/videos/{video_id}/keyframes"""

    @pytest.mark.asyncio
    async def test_get_keyframes_all(self):
        """Test retrieving all keyframes"""
        # TODO: Test keyframes endpoint
        pass


class TestBackgroundTasks:
    """Tests for background task functions"""

    @pytest.mark.asyncio
    async def test_get_video_duration(self):
        """ffprobe output is parsed into a real float duration.
        (subprocess is imported locally inside get_video_duration, so the
        patch target is the shared `subprocess` module, not
        src.api.videos.subprocess - that attribute doesn't exist)"""
        import json
        from src.api.videos import get_video_duration

        fake_result = Mock(stdout=json.dumps({"format": {"duration": "213.061"}}))

        with patch("subprocess.run", return_value=fake_result):
            duration = await get_video_duration("./data/uploads/some_video.mp4")

        assert duration == 213.061

    @pytest.mark.asyncio
    @patch('src.core.video_processor.VideoProcessor')
    async def test_process_video_background(self, mock_processor):
        """Test background video processing"""
        # TODO: Test full processing pipeline execution
        pass

    def test_run_video_analysis_reports_progress_per_scene(self):
        """_run_video_analysis invokes progress_callback(index, total) once
        per scene, so the frontend gets granular updates during the
        longest-running stage (BLIP/YOLO/OCR/CLIP per scene) instead of
        going silent for the whole stage - confirmed live: without this,
        the UI sat at "Waiting for processing to start..." the entire time
        despite the backend genuinely processing."""
        from types import SimpleNamespace
        from src.api.videos import _run_video_analysis

        fake_scenes = [
            SimpleNamespace(scene_id=i, start_time=float(i), end_time=float(i + 1),
                             keyframe_timestamp=float(i), middle_timestamp=float(i))
            for i in range(3)
        ]

        mock_processor = Mock()
        mock_processor.extract_frames.return_value = []
        mock_processor.extract_audio.return_value = None
        mock_processor.extract_single_frame.return_value = None

        mock_transcriber = Mock()
        mock_transcriber.transcribe.return_value = Mock(segments=[], language="en", duration=3.0)

        mock_action_service = Mock()
        mock_action_service.recognize_actions.return_value = Mock(actions=[])

        mock_audio_extractor = Mock()
        mock_audio_extractor.extract_segment_features.return_value = Mock(rms_energy=0.1)

        progress_calls = []

        with patch("src.core.video_processor.create_video_processor", return_value=mock_processor), \
             patch("src.services.scene_detection.content_detector.ContentBasedSceneDetector") as mock_detector_cls, \
             patch("src.services.transcription_service.TranscriptionService", return_value=mock_transcriber), \
             patch("src.services.image_captioning.ImageCaptioningService"), \
             patch("src.services.object_detection.ObjectDetectionService"), \
             patch("src.services.face_detection.FaceDetectionService"), \
             patch("src.services.ocr_service.OCRService"), \
             patch("src.services.action_recognition.ActionRecognitionService", return_value=mock_action_service), \
             patch("src.services.audio_features.AudioFeatureExtractor", return_value=mock_audio_extractor), \
             patch("src.api.videos._get_clip_model"), \
             patch("src.core.config.settings") as mock_settings:

            mock_settings.diarization_use_auth_token = False
            mock_settings.hf_token = None
            mock_settings.frames_path = "/tmp/frames"
            mock_settings.temp_path = "/tmp/temp"
            mock_settings.whisper_model = "base"
            mock_settings.scene_threshold = 30.0
            mock_settings.min_scene_length = 1.0

            mock_detector_cls.return_value.detect_scenes.return_value = fake_scenes

            _run_video_analysis(
                "video.mp4", "video-uuid",
                progress_callback=lambda idx, total: progress_calls.append((idx, total)),
            )

        assert progress_calls == [(0, 3), (1, 3), (2, 3)]

    @pytest.mark.asyncio
    @patch('yt_dlp.YoutubeDL')
    async def test_download_youtube_video(self, mock_ytdl):
        """Test YouTube video download"""
        # TODO: Test yt-dlp integration
        pass

    @pytest.mark.asyncio
    @patch('subprocess.run')
    async def test_download_streaming_video(self, mock_subprocess):
        """Test streaming video download with ffmpeg"""
        # TODO: Test ffmpeg streaming download
        pass


class TestErrorHandling:
    """Tests for error handling scenarios"""

    @pytest.mark.asyncio
    async def test_upload_exceeds_size_limit(self):
        """Test upload with file exceeding size limit"""
        # TODO: Test file size validation
        pass

    @pytest.mark.asyncio
    async def test_upload_disk_space_error(self):
        """Test upload when disk space is full"""
        # TODO: Test disk space error handling
        pass

    @pytest.mark.asyncio
    async def test_processing_timeout(self):
        """Test handling of processing timeout"""
        # TODO: Test timeout error handling
        pass

    @pytest.mark.asyncio
    async def test_invalid_video_codec(self):
        """Test handling of unsupported video codec"""
        # TODO: Test codec validation
        pass


class TestConcurrentOperations:
    """Tests for concurrent operations"""

    @pytest.mark.asyncio
    async def test_concurrent_uploads(self):
        """Test multiple concurrent uploads"""
        # TODO: Test concurrent upload handling
        pass

    @pytest.mark.asyncio
    async def test_concurrent_processing(self):
        """Test processing multiple videos simultaneously"""
        # TODO: Test concurrent processing
        pass

    @pytest.mark.asyncio
    async def test_process_while_uploading(self):
        """Test starting processing while upload in progress"""
        # TODO: Test race condition handling
        pass


# Integration test fixtures
@pytest.fixture
def test_app():
    """Create test FastAPI application"""
    # TODO: Import and configure test app
    pass


@pytest.fixture
def test_client(test_app):
    """Create test client"""
    # TODO: Create TestClient
    pass


@pytest.fixture
def sample_video_path():
    """Path to sample test video"""
    # TODO: Provide sample video for integration tests
    pass


@pytest.fixture
async def uploaded_video(test_client, sample_video_path):
    """Upload a test video for use in other tests"""
    # TODO: Upload video and return video_id
    pass


# Run tests with: pytest tests/api/test_videos.py -v
