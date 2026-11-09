"""
API behaviour found by using the app with real files and hostile input.

Drives the real FastAPI app with TestClient; only the database is replaced.
"""

import shutil
import subprocess
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.models import VideoStatus

FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
needs_ffmpeg = pytest.mark.skipif(not Path(FFMPEG).exists(), reason="ffmpeg not installed")

UNKNOWN = "11111111-2222-4333-8444-555555555555"


@pytest.fixture(scope="module")
def client():
    # These tests make hundreds of requests from one address; the rate limiter
    # (60/minute, tested on its own below) would answer 429 to most of them.
    from src.core.config import settings
    previous = settings.rate_limit_enabled
    settings.rate_limit_enabled = False
    from server import app
    yield TestClient(app)
    settings.rate_limit_enabled = previous


def fake_video(status=VideoStatus.COMPLETED, duration=59.9, **extra):
    video = MagicMock()
    video.external_id = "vid-1"
    video.id = 1
    video.title = "Lab"
    video.file_path = "./uploads/videos/vid-1.mp4"
    video.duration_seconds = duration
    video.processing_status = status
    video.error_message = None
    video.extra_metadata = extra.get("extra_metadata", {})
    video.created_at = datetime(2026, 11, 9, 3, 37, 42)
    video.processed_at = None
    return video


def db_returning(video):
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = video

    @contextmanager
    def get_db():
        yield session
    return get_db, session


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    """Upload into a temp dir and record what would be saved to the database"""
    monkeypatch.chdir(tmp_path)
    get_db, session = db_returning(None)
    with patch("src.api.videos.get_db", get_db):
        yield tmp_path / "uploads" / "videos", session


def make_video(path, seconds=2):
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=blue:s=160x120:d={seconds}",
                    "-pix_fmt", "yuv420p", str(path)], check=True, capture_output=True)
    return path


def upload(client, name, content, **form):
    return client.post("/api/videos/upload", files={"file": (name, content, "video/mp4")},
                       data={"auto_process": "false", **form})


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

class TestUpload:
    @pytest.mark.parametrize("name,content", [
        ("fake.mp4", b"this is not a video"), ("empty.mp4", b""), ("random.mp4", bytes(range(256)) * 12),
    ])
    @needs_ffmpeg
    def test_a_file_that_is_not_a_video_is_refused_and_leaves_nothing_behind(self, client, uploads, name, content):
        folder, session = uploads
        response = upload(client, name, content)
        assert response.status_code == 400
        assert "not a valid video" in response.json()["detail"]
        assert not folder.exists() or list(folder.iterdir()) == []
        session.add.assert_not_called()

    @needs_ffmpeg
    def test_an_audio_only_file_is_accepted_as_audio(self, client, uploads, tmp_path):
        folder, session = uploads
        audio = tmp_path / "a.mp4"
        subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=d=2", "-vn", str(audio)], check=True)
        response = upload(client, "talk.mp4", audio.read_bytes())
        assert response.status_code == 200 and response.json()["media_type"] == "audio"
        assert "Audio uploaded" in response.json()["message"]
        assert session.add.call_args[0][0].media_type == "audio"

    @needs_ffmpeg
    def test_a_text_file_named_mp3_is_refused(self, client, uploads):
        folder, session = uploads
        response = upload(client, "song.mp3", b"this is not audio")
        assert response.status_code == 400 and "not a valid video or audio file" in response.json()["detail"]
        session.add.assert_not_called()

    def test_wrong_extension(self, client, uploads):
        assert upload(client, "notes.txt", b"hello").status_code == 400

    @needs_ffmpeg
    def test_a_real_video_is_accepted_with_its_real_duration(self, client, uploads, tmp_path):
        folder, session = uploads
        response = upload(client, "clip.mp4", make_video(tmp_path / "src.mp4").read_bytes())
        assert response.status_code == 200
        body = response.json()
        assert body["title"] == "clip" and 1.5 < body["duration"] < 2.5
        assert len(list(folder.iterdir())) == 1
        session.add.assert_called_once()

    @needs_ffmpeg
    def test_a_directory_in_the_file_name_never_reaches_the_title(self, client, uploads, tmp_path):
        folder, _ = uploads
        response = upload(client, "../../../tmp/pwn.mp4", make_video(tmp_path / "src.mp4").read_bytes())
        assert response.status_code == 200 and response.json()["title"] == "pwn"
        assert [p.parent for p in folder.iterdir()] == [folder]          # stored under a generated id

    @needs_ffmpeg
    def test_title_and_description_are_capped(self, client, uploads, tmp_path):
        _, session = uploads
        response = upload(client, "c.mp4", make_video(tmp_path / "src.mp4").read_bytes(), title="t" * 5000, description="d" * 9000)
        assert response.status_code == 200 and len(response.json()["title"]) == 200
        assert len(session.add.call_args[0][0].description) == 2000

    @needs_ffmpeg
    def test_a_file_over_the_size_limit_is_refused_and_removed(self, client, uploads, tmp_path, monkeypatch):
        from src.core.config import settings
        folder, session = uploads
        monkeypatch.setattr(settings, "max_video_size_mb", 0)
        response = upload(client, "big.mp4", make_video(tmp_path / "src.mp4").read_bytes())
        assert response.status_code == 413 and "limit" in response.json()["detail"]
        assert not folder.exists() or list(folder.iterdir()) == []
        session.add.assert_not_called()


# ---------------------------------------------------------------------------
# URLs the server will fetch
# ---------------------------------------------------------------------------

class TestUrls:
    @pytest.fixture
    def db(self):
        get_db, session = db_returning(None)
        with patch("src.api.videos.get_db", get_db):
            yield session

    @pytest.mark.parametrize("url", [
        "http://127.0.0.1:11434/api/tags", "http://169.254.169.254/latest/meta-data/", "http://[::1]:8000/health",
        "http://localhost:8000/api/videos", "http://192.168.0.10/live.m3u8", "http://2130706433/",
    ])
    def test_stream_urls_to_this_computer_or_a_private_network_are_refused(self, client, db, url):
        response = client.post("/api/videos/stream", json={"url": url})
        assert response.status_code == 400 and "public internet" in response.json()["detail"]
        db.add.assert_not_called()

    @pytest.mark.parametrize("url", ["file:///etc/passwd", "rtsp://8.8.8.8/x", "   ", "ftp://8.8.8.8/x"])
    def test_stream_urls_must_be_http(self, client, db, url):
        assert client.post("/api/videos/stream", json={"url": url}).status_code == 400

    @pytest.mark.parametrize("url", ["https://evil.example/?youtube.com", "http://localhost:8000/x?u=youtu.be", "file:///etc/youtube.com"])
    def test_youtube_means_the_host_is_youtube(self, client, db, url):
        response = client.post("/api/videos/youtube", json={"url": url})
        assert response.status_code == 400 and response.json()["detail"] == "Invalid YouTube URL"
        db.add.assert_not_called()

    def test_a_real_youtube_url_is_queued(self, client, db):
        with patch("src.api.videos.download_youtube_video"):
            response = client.post("/api/videos/youtube", json={"url": "https://www.youtube.com/watch?v=abc"})
        assert response.status_code == 200 and response.json()["status"] == "downloading"

    def test_ffmpeg_for_streams_may_only_use_network_protocols(self):
        source = (Path(__file__).resolve().parents[2] / "src" / "api" / "videos.py").read_text()
        assert '"-protocol_whitelist", "http,https,tcp,tls,crypto"' in source


# ---------------------------------------------------------------------------
# Clips
# ---------------------------------------------------------------------------

class TestClips:
    @pytest.fixture
    def db(self):
        get_db, session = db_returning(fake_video())
        with patch("src.core.database.get_db", get_db), patch("src.api.clips.create_clip_task"):
            yield session

    def clip(self, client, **body):
        return client.post("/api/videos/vid-1/clip", json=body)

    def test_end_past_the_end_of_the_video_is_refused(self, client, db):
        response = self.clip(client, start_time=55, end_time=300)
        assert response.status_code == 400 and "past the end of the video (59.9s)" in response.json()["detail"]
        db.add.assert_not_called()

    def test_start_past_the_end_of_the_video_is_refused(self, client, db):
        response = self.clip(client, start_time=70, end_time=80)
        assert response.status_code == 400 and "start_time" in response.json()["detail"]

    def test_a_clip_inside_the_video_is_accepted_unchanged(self, client, db):
        body = self.clip(client, start_time=10, end_time=20).json()
        assert (body["start_time"], body["end_time"], body["duration"]) == (10, 20, 10)

    def test_a_hair_past_the_end_is_clamped_to_the_real_length(self, client, db):
        body = self.clip(client, start_time=55, end_time=60.3).json()
        assert body["end_time"] == pytest.approx(59.9) and body["duration"] == pytest.approx(4.9)
        stored = db.add.call_args[0][0]
        assert stored.end_time == pytest.approx(59.9)

    @pytest.mark.parametrize("body", [
        {"format": "../../x"}, {"format": "exe"}, {"resolution": "9999p"}, {"title": "t" * 201}, {"description": "d" * 2001},
    ])
    def test_odd_options_are_refused(self, client, db, body):
        assert self.clip(client, start_time=1, end_time=5, **body).status_code == 422

    @pytest.mark.parametrize("fmt", ["mp4", "webm", "gif"])
    def test_supported_formats(self, client, db, fmt):
        assert self.clip(client, start_time=1, end_time=5, format=fmt).status_code == 200


# ---------------------------------------------------------------------------
# Analysis endpoints
# ---------------------------------------------------------------------------

class TestAnalysisGuards:
    def patched(self, video):
        get_db, _ = db_returning(video)
        return patch("src.core.database.get_db", get_db)

    @pytest.mark.parametrize("path", ["highlights/generate", "summarize"])
    def test_background_jobs_are_not_queued_for_an_unknown_video(self, client, path):
        with self.patched(None), patch("src.api.analysis.generate_highlights_task") as t1, patch("src.api.analysis.generate_summary_task") as t2:
            response = client.post(f"/api/videos/{UNKNOWN}/{path}", json={})
        assert response.status_code == 404
        t1.assert_not_called(); t2.assert_not_called()

    @pytest.mark.parametrize("path", ["highlights/generate", "summarize"])
    def test_nor_for_a_video_still_processing(self, client, path):
        with self.patched(fake_video(status=VideoStatus.PROCESSING)):
            response = client.post("/api/videos/vid-1/" + path, json={})
        assert response.status_code == 400 and "not fully processed" in response.json()["detail"]

    def test_finished_video_queues_the_job(self, client):
        with self.patched(fake_video()), patch("src.api.analysis.generate_highlights_task") as task:
            assert client.post("/api/videos/vid-1/highlights/generate", json={}).status_code == 200
        task.assert_called_once()

    def test_timeline_filter_rejects_unknown_event_types(self, client):
        with self.patched(fake_video()), patch("src.api.analysis._build_timeline_events", return_value=[]):
            response = client.post("/api/videos/vid-1/timeline/filter", json={"event_types": ["bogus", "scene"]})
        assert response.status_code == 400 and "bogus" in response.json()["detail"]

    def test_timeline_filter_rejects_a_backwards_range(self, client):
        with self.patched(fake_video()), patch("src.api.analysis._build_timeline_events", return_value=[]):
            assert client.post("/api/videos/vid-1/timeline/filter", json={"start_time": 30, "end_time": 10}).status_code == 400

    @pytest.mark.parametrize("kinds", [["scene"], ["speech"], ["highlight"], ["chapter"], ["scene", "speech"], None])
    def test_timeline_filter_accepts_every_real_event_type(self, client, kinds):
        with self.patched(fake_video()), patch("src.api.analysis._build_timeline_events", return_value=[]):
            assert client.post("/api/videos/vid-1/timeline/filter", json={"event_types": kinds}).status_code == 200


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

class TestStatus:
    @pytest.fixture(autouse=True)
    def clean(self):
        from src.api import websockets
        websockets._latest_progress.clear()
        yield
        websockets._latest_progress.clear()

    def status(self, client, video):
        get_db, _ = db_returning(video)
        with patch("src.api.videos.get_db", get_db):
            return client.get("/api/videos/vid-1/status").json()

    def test_progress_and_stage_follow_the_pipeline(self, client):
        from src.api import websockets
        websockets._latest_progress["vid-1"] = {"stage": "scene_analysis", "progress": 40.0, "message": "Analyzing scene 2/5..."}
        body = self.status(client, fake_video(status=VideoStatus.PROCESSING))
        assert (body["status"], body["progress"], body["stage"]) == ("processing", 40.0, "scene_analysis")

    def test_processing_without_news_yet(self, client):
        body = self.status(client, fake_video(status=VideoStatus.PROCESSING))
        assert (body["progress"], body["stage"]) == (0.0, "processing")

    def test_completed_is_100_even_with_old_progress_lying_around(self, client):
        from src.api import websockets
        websockets._latest_progress["vid-1"] = {"stage": "embeddings", "progress": 80.0, "message": ""}
        body = self.status(client, fake_video(status=VideoStatus.COMPLETED))
        assert (body["progress"], body["stage"]) == (100.0, "completed")

    def test_started_at_is_when_this_run_began_not_when_the_file_was_uploaded(self, client):
        body = self.status(client, fake_video(status=VideoStatus.PROCESSING, extra_metadata={"processing_started_at": "2026-11-09T05:01:12.500000"}))
        assert body["started_at"].startswith("2026-11-09T05:01:12")

    def test_without_a_recorded_start_it_falls_back_to_the_upload_time(self, client):
        assert self.status(client, fake_video())["started_at"].startswith("2026-11-09T03:37:42")

    def test_progress_forgets_old_videos(self):
        from src.api import websockets
        import asyncio
        for i in range(websockets._MAX_TRACKED + 25):
            asyncio.run(websockets.send_progress_update(f"v{i}", "x", 1.0, "m"))
        assert len(websockets._latest_progress) == websockets._MAX_TRACKED
        websockets.forget_progress("v300")
        assert websockets.get_latest_progress("v300") is None


# ---------------------------------------------------------------------------
# Who may call the API from a web page
# ---------------------------------------------------------------------------

class TestCors:
    def preflight(self, client, origin):
        return client.options("/api/videos", headers={"Origin": origin, "Access-Control-Request-Method": "DELETE"})

    @pytest.mark.parametrize("origin", ["http://evil.example", "https://attacker.test", "http://localhost.evil.example", "null"])
    def test_other_web_pages_are_not_allowed(self, client, origin):
        assert "access-control-allow-origin" not in self.preflight(client, origin).headers
        simple = client.get("/health", headers={"Origin": origin})
        assert "access-control-allow-origin" not in simple.headers

    @pytest.mark.parametrize("origin", ["http://localhost:3000", "http://localhost:8000", "http://127.0.0.1:8000"])
    def test_the_apps_own_pages_are_allowed(self, client, origin):
        assert self.preflight(client, origin).headers.get("access-control-allow-origin") == origin

    def test_the_default_bind_address_is_loopback(self):
        from src.core.config import Settings
        assert Settings.model_fields["api_host"].default == "127.0.0.1"


# ---------------------------------------------------------------------------
# Frontend files must not be served from a stale browser cache
# ---------------------------------------------------------------------------

class TestFrontendCaching:
    @pytest.mark.parametrize("path", ["/", "/static/app.js", "/static/index.html", "/static/styles.css"])
    def test_pages_and_scripts_are_revalidated_on_every_load(self, client, path):
        response = client.get(path, headers={"Accept": "text/html"})   # "/" serves the page only to browsers
        assert response.status_code == 200 and "text/html" in response.headers["content-type"] or path.startswith("/static")
        assert response.headers["cache-control"] == "no-cache"

    def test_an_unchanged_file_is_a_cheap_304(self, client):
        etag = client.get("/static/app.js").headers["etag"]
        assert client.get("/static/app.js", headers={"If-None-Match": etag}).status_code == 304


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class TestRateLimiter:
    @pytest.fixture
    def limited(self):
        from fastapi import FastAPI
        from src.core.middleware import RateLimitMiddleware
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, max_requests=3, window_seconds=60)

        @app.get("/api/x")
        def api():
            return {"ok": True}

        @app.get("/static/app.js")
        def script():
            return {"ok": True}

        @app.get("/health")
        def health():
            return {"ok": True}
        return TestClient(app)

    def test_api_calls_are_limited(self, limited):
        assert [limited.get("/api/x").status_code for _ in range(5)] == [200, 200, 200, 429, 429]

    def test_the_apps_own_page_files_and_health_are_not_counted(self, limited):
        assert all(limited.get("/static/app.js").status_code == 200 for _ in range(20))
        assert all(limited.get("/health").status_code == 200 for _ in range(20))
        assert limited.get("/api/x").status_code == 200
