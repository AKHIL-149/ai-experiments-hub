"""
Audio-only files: podcasts, lecture recordings, voice memos, audio-only .mp4.

Real ffmpeg-made audio, the real app and a real SQLite database; the speech model is replaced by fixed
segments and the video-only services are set to explode if they are ever called for audio.
"""

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import pytest

from src.core.config import settings
from src.models import Clip, Frame, Scene, Transcript, Video, VideoStatus
from src.services.job_queue import JobCancelled, JobContext
from tests.api.test_job_queue import PASSWORD, api, qw  # noqa: F401  (fixtures)

FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
needs_ffmpeg = pytest.mark.skipif(not Path(FFMPEG).exists(), reason="ffmpeg not installed")
pytestmark = needs_ffmpeg


def make(path, *args, seconds=3):
    subprocess.run([FFMPEG, "-v", "error", "-y", *args, str(path)], check=True, capture_output=True)
    return Path(path)


def tone(path, seconds=3, *codec):
    return make(path, "-f", "lavfi", "-i", f"sine=frequency=440:d={seconds}", *codec)


def post_file(client, path, **form):
    return client.post("/api/videos/upload", files={"file": (Path(path).name, Path(path).read_bytes(), "audio/mpeg")},
                       data={"auto_process": "false", **form})


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

class TestUpload:
    @pytest.mark.parametrize("name,codec", [
        ("talk.mp3", ["-c:a", "libmp3lame"]), ("talk.wav", []), ("talk.m4a", ["-c:a", "aac"]),
        ("talk.flac", ["-c:a", "flac"]), ("talk.ogg", ["-c:a", "libopus"]), ("talk.opus", ["-c:a", "libopus"]),
        ("talk.aac", ["-c:a", "aac", "-f", "adts"]), ("talk.mp4", ["-vn", "-c:a", "aac"]),
    ])
    def test_every_audio_format_is_accepted_as_audio(self, api, name, codec):
        body = post_file(api.ann, tone(api.w.tmp / name, 3, *codec)).json()
        assert body["media_type"] == "audio" and 2.5 < body["duration"] < 3.6
        assert body["message"] == "Audio uploaded successfully"
        row = api.ann.get(f"/api/videos/{body['video_id']}").json()
        assert row["media_type"] == "audio" and row["file_path"].endswith(Path(name).suffix)

    def test_videos_are_still_videos(self, api):
        clip = make(api.w.tmp / "v.mp4", "-f", "lavfi", "-i", "testsrc=d=2:s=160x120:r=10", "-pix_fmt", "yuv420p")
        body = post_file(api.ann, clip).json()
        assert body["media_type"] == "video" and body["message"] == "Video uploaded successfully"

    def test_a_file_that_is_neither_is_refused_and_leaves_nothing(self, api):
        response = api.ann.post("/api/videos/upload", files={"file": ("fake.mp3", b"not audio at all", "audio/mpeg")},
                                data={"auto_process": "false"})
        assert response.status_code == 400 and "not a valid video or audio file" in response.json()["detail"]
        assert not list((api.w.tmp / "uploads" / "videos").glob("*"))

    def test_the_error_for_a_wrong_extension_lists_audio_formats_too(self, api):
        response = api.ann.post("/api/videos/upload", files={"file": ("notes.txt", b"hi", "text/plain")})
        detail = response.json()["detail"]
        assert response.status_code == 400 and ".mp3" in detail and ".mp4" in detail

    def test_an_mp3_with_cover_art_is_audio(self, api):
        base = tone(api.w.tmp / "t.mp3", 2, "-c:a", "libmp3lame")
        cover = make(api.w.tmp / "c.jpg", "-f", "lavfi", "-i", "color=c=red:s=64x64:d=1", "-frames:v", "1")
        art = api.w.tmp / "art.mp3"
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(base), "-i", str(cover), "-map", "0", "-map", "1", "-c",
                        "copy", "-id3v2_version", "3", "-disposition:v", "attached_pic", str(art)], check=True)
        assert post_file(api.ann, art).json()["media_type"] == "audio"

    def test_upload_queues_the_analysis_like_any_video(self, api):
        body = post_file(api.ann, tone(api.w.tmp / "t.mp3", 2, "-c:a", "libmp3lame"), auto_process="true").json()
        job = api.w.job(body["job_id"])
        assert job.kind == "process" and body["queue_position"] == 1 and "Audio uploaded and queued" in body["message"]

    def test_the_type_is_in_the_list_and_the_status_call(self, api):
        audio = post_file(api.ann, tone(api.w.tmp / "t.mp3", 2, "-c:a", "libmp3lame")).json()["video_id"]
        listing = {v["video_id"]: v for v in api.ann.get("/api/videos").json()["videos"]}
        assert listing[audio]["media_type"] == "audio"

    def test_guests_audio_counts_against_their_limits_too(self, api, monkeypatch):
        monkeypatch.setattr(settings, "guest_max_video_size_mb", 0)
        from fastapi.testclient import TestClient
        guest = TestClient(api.anon.app)
        guest.post("/api/auth/guest")
        response = post_file(guest, tone(api.w.tmp / "t.mp3", 2, "-c:a", "libmp3lame"))
        assert response.status_code == 413


# ---------------------------------------------------------------------------
# The analysis
# ---------------------------------------------------------------------------

def fake_transcript(duration):
    """Speech with a pause every ~25 s, as a speaker finishing a thought would leave"""
    segments, t, i = [], 0.0, 0
    while t + 4 < duration:
        segments.append(NS(start=t, end=t + 4, text=f"sentence number {i}", confidence=0.9, language="en", speaker=None))
        t += 4.4 if (i % 6) != 5 else 7.0
        i += 1
    return NS(segments=segments, language="en", duration=duration)


class FakeTranscriber:
    duration = 120.0

    def __init__(self, *args, **kwargs):
        pass

    def transcribe(self, path, use_local=True):
        return fake_transcript(FakeTranscriber.duration)


@pytest.fixture
def speech(qw, monkeypatch):
    """A two-minute audio file and a stand-in for Whisper; every picture-only service raises if it is touched"""
    monkeypatch.setattr(settings, "temp_path", str(qw.tmp / "temp"))
    monkeypatch.setattr("src.services.transcription_service.TranscriptionService", FakeTranscriber)

    def explode(*args, **kwargs):
        raise AssertionError("a picture-only service ran for an audio file")

    for target in (
        "src.services.scene_detection.content_detector.ContentBasedSceneDetector.detect_scenes",
        "src.services.image_captioning.ImageCaptioningService.from_settings",
        "src.services.object_detection.ObjectDetectionService.__init__",
        "src.services.face_detection.FaceDetectionService.__init__",
        "src.services.ocr_service.OCRService.__init__",
        "src.services.action_recognition.ActionRecognitionService.__init__",
        "src.api.videos._get_clip_model",
    ):
        monkeypatch.setattr(target, explode)
    monkeypatch.setattr("src.services.audio_features.AudioFeatureExtractor.extract_segment_features",
                        lambda self, path, start, end: NS(rms_energy=0.05))
    return tone(qw.tmp / "speech.mp3", 120, "-c:a", "libmp3lame")


class TestAudioAnalysis:
    def test_audio_is_transcribed_and_cut_into_sections_without_any_picture_work(self, speech):
        from src.api.videos import _run_video_analysis
        calls = []
        result = _run_video_analysis(str(speech), "aud-1", lambda i, n: calls.append((i, n)), None, "audio")

        assert result["sampled_frame_paths"] == [] and result["audio_only"] is True
        assert len(result["transcription"].segments) > 20
        scenes = [item["scene"] for item in result["scenes"]]
        assert len(scenes) >= 3 and scenes[0].start_time == 0.0 and scenes[-1].end_time == pytest.approx(
            result["transcription"].duration, abs=1.0)
        assert all(a.end_time == pytest.approx(b.start_time) for a, b in zip(scenes, scenes[1:]))
        for item in result["scenes"]:
            assert item["keyframe_path"] is None and item["caption"] == "" and item["objects"] == []
            assert item["faces"] == [] and item["ocr_text"] == "" and item["clip_embedding"] is None
            assert item["audio_energy"] == pytest.approx(0.5)      # rms 0.05 scaled like a video scene's
            assert item["activity_ratio"] == 0.0 and item["dominant_action"] is None
        assert calls == [(i, len(scenes)) for i in range(len(scenes))]   # progress after every section

    def test_sections_with_speech_are_dialogue_and_the_rest_unknown(self, speech, monkeypatch):
        from src.api.videos import _run_video_analysis
        spoken = _run_video_analysis(str(speech), "aud-t1", None, None, "audio")["scenes"]
        assert {item["scene"].scene_type.value for item in spoken} == {"dialogue"}
        monkeypatch.setattr(FakeTranscriber, "transcribe", lambda self, path, use_local=True: NS(
            segments=[], language="en", duration=120.0))
        music = _run_video_analysis(str(speech), "aud-t2", None, None, "audio")["scenes"]
        assert {item["scene"].scene_type.value for item in music} == {"unknown"}

    def test_a_long_speaker_with_no_pauses_still_gets_sections(self, speech, monkeypatch):
        from src.api.videos import _run_video_analysis
        monkeypatch.setattr(FakeTranscriber, "transcribe", lambda self, path, use_local=True: NS(
            segments=[NS(start=i * 4.0, end=i * 4.0 + 3.9, text="x", confidence=1, language="en", speaker=None)
                      for i in range(29)], language="en", duration=120.0))
        sections = _run_video_analysis(str(speech), "aud-2", None, None, "audio")["scenes"]
        assert len(sections) >= 2

    def test_transcript_segments_past_the_end_of_the_audio_are_dropped(self, speech, monkeypatch):
        from src.api.videos import _run_video_analysis
        monkeypatch.setattr(FakeTranscriber, "transcribe", lambda self, path, use_local=True: NS(
            segments=[NS(start=0, end=5, text="real", confidence=1, language="en", speaker=None),
                      NS(start=500, end=510, text="invented", confidence=1, language="en", speaker=None)],
            language="en", duration=120.0))
        segments = _run_video_analysis(str(speech), "aud-3", None, None, "audio")["transcription"].segments
        assert [s.text for s in segments] == ["real"]

    def test_the_analysis_checks_for_cancellation_between_stages_and_sections(self, speech):
        from src.api.videos import _run_video_analysis
        count = []

        def check():
            count.append(1)

        result = _run_video_analysis(str(speech), "aud-4", None, check, "audio")
        # after extracting the audio, after transcribing, and before each section
        assert len(count) == 2 + len(result["scenes"])

        def stop():
            raise JobCancelled("cancelled")

        with pytest.raises(JobCancelled):
            _run_video_analysis(str(speech), "aud-5", None, stop, "audio")

    def test_a_video_is_still_analysed_as_a_video(self, speech, monkeypatch):
        from src.api import videos
        seen = {}
        monkeypatch.setattr(videos, "_run_audio_analysis", lambda *a, **k: seen.setdefault("audio", True))
        # a video goes through the picture pipeline: its first step (frame extraction) fails on a tone,
        # which proves the audio branch was not taken
        with pytest.raises(Exception):
            videos._run_video_analysis(str(speech), "vid-x", None, None, "video")
        assert "audio" not in seen


class TestPipelinePersistence:
    def audio_video(self, qw, ext="aud-p"):
        return qw.video(status=VideoStatus.PROCESSING, ext=ext, media_type="audio")

    @pytest.mark.asyncio
    async def test_an_audio_file_is_saved_as_sections_and_transcript_with_no_frames(self, qw, speech, monkeypatch):
        from src.api import videos
        video = self.audio_video(qw)
        with qw.get_db() as db:
            db.query(Video).update({"file_path": str(speech)})
        monkeypatch.setattr(videos, "_get_embedding_model",
                            lambda: NS(encode=lambda texts: [[float(len(t) % 7), 1.0, 0.0] for t in texts]))
        sent = []

        async def stage(**kwargs):
            sent.append(kwargs["stage"])

        async def nothing(**kwargs):
            return None

        with patch("src.api.websockets.send_stage_complete", new=stage), \
             patch("src.api.websockets.send_progress_update", new=nothing), \
             patch("src.api.websockets.send_processing_complete", new=nothing), \
             patch("src.api.analysis.generate_summary_task", new=AsyncMock()), \
             patch("src.api.analysis.generate_highlights_task", new=AsyncMock()), \
             patch("src.api.analysis.generate_chapters_task", new=AsyncMock()):
            await videos.process_video_background("aud-p", None)

        with qw.get_db() as db:
            v = db.query(Video).one()
            assert v.processing_status == VideoStatus.COMPLETED and v.media_type == "audio"
            scenes = db.query(Scene).order_by(Scene.start_time).all()
            assert len(scenes) >= 3 and all(s.keyframe_path is None and s.description == "" for s in scenes)
            assert scenes[0].extra_metadata["audio_energy"] == pytest.approx(0.5)
            assert db.query(Frame).count() == 0
            assert db.query(Transcript).count() > 20
        # the stages a listener can follow: no frames, no scene detection, no visual analysis
        assert sent == ["transcription", "sections", "embeddings", "summarization"]

    @pytest.mark.asyncio
    async def test_the_search_index_gets_transcript_embeddings_and_no_frame_embeddings(self, qw, speech, monkeypatch):
        import numpy as np
        from src.api import videos
        from src.core.vector_store import VideoVectorStore
        self.audio_video(qw)
        with qw.get_db() as db:
            db.query(Video).update({"file_path": str(speech)})
        monkeypatch.setattr(videos, "_get_embedding_model",
                            lambda: NS(encode=lambda texts: np.array([[1.0, float(i), 0.5] for i, _ in enumerate(texts)])))
        with patch("src.api.websockets.send_stage_complete", new=AsyncMock()), \
             patch("src.api.websockets.send_progress_update", new=AsyncMock()), \
             patch("src.api.websockets.send_processing_complete", new=AsyncMock()), \
             patch("src.api.analysis.generate_summary_task", new=AsyncMock()), \
             patch("src.api.analysis.generate_highlights_task", new=AsyncMock()), \
             patch("src.api.analysis.generate_chapters_task", new=AsyncMock()):
            await videos.process_video_background("aud-p", None)

        store = VideoVectorStore(persist_directory=Path(settings.chroma_persist_directory))
        store.initialize_collections()
        found = store.get_video_embeddings("aud-p")
        assert len(found["transcripts"]["ids"]) > 20
        assert len(found.get("frames", {}).get("ids") or []) == 0

    @pytest.mark.asyncio
    async def test_the_job_announces_transcription_not_frame_extraction(self, qw, speech, monkeypatch):
        from src.api import videos
        self.audio_video(qw)
        with qw.get_db() as db:
            db.query(Video).update({"file_path": str(speech)})
        first = []

        async def progress(**kwargs):
            first.append((kwargs["stage"], kwargs["message"]))
            raise JobCancelled("cancelled")   # enough: stop at the first message

        ctx = JobContext(job_id="j", kind="process", video_id="aud-p", user_id=None)
        ctx.check_cancel = lambda: None
        with patch("src.api.websockets.send_progress_update", new=progress):
            with pytest.raises(JobCancelled):
                await videos.process_video_background("aud-p", ctx)
        assert first == [("transcription", "Transcribing the audio...")]


# ---------------------------------------------------------------------------
# Clips
# ---------------------------------------------------------------------------

@pytest.fixture
def clip_world(api, monkeypatch):
    """Real ffmpeg clips, made inside the request like the app does (TestClient runs background tasks)"""
    monkeypatch.chdir(api.w.tmp)
    (api.w.tmp / "storage" / "clips").mkdir(parents=True)
    monkeypatch.setattr("src.api.clips.get_db", api.w.get_db, raising=False)
    return api


def audio_video(api, owner, ext="aud-c", seconds=30):
    path = tone(api.w.tmp / f"{ext}.mp3", seconds, "-c:a", "libmp3lame")
    row = api.w.video(owner, status=VideoStatus.COMPLETED, ext=ext, media_type="audio")
    with api.w.get_db() as db:
        db.query(Video).filter(Video.id == row).update({"file_path": str(path), "duration_seconds": float(seconds)})
    return ext


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name:format=duration",
                          "-of", "json", str(path)], capture_output=True, text=True).stdout
    import json
    data = json.loads(out)
    return [s["codec_type"] for s in data["streams"]], float(data["format"]["duration"])


class TestAudioClips:
    def test_a_clip_of_audio_is_an_mp3_by_default(self, clip_world):
        api = clip_world
        ext = audio_video(api, api.ann.user["id"])
        clip = api.ann.post(f"/api/videos/{ext}/clip", json={"start_time": 5, "end_time": 12}).json()
        assert clip["format"] == "mp3"
        done = api.ann.get(f"/api/clips/{clip['clip_id']}").json()
        assert done["status"] == "completed" and done["thumbnail_path"] is None and done["file_size"] > 0
        download = api.ann.get(f"/api/clips/{clip['clip_id']}/download")
        assert download.status_code == 200 and download.headers["content-type"] == "audio/mpeg"
        assert ".mp3" in download.headers["content-disposition"]
        out = api.w.tmp / "got.mp3"
        out.write_bytes(download.content)
        kinds, seconds = probe(out)
        assert kinds == ["audio"] and seconds == pytest.approx(7.0, abs=0.2)

    def test_the_audio_clip_has_no_thumbnail(self, clip_world):
        api = clip_world
        ext = audio_video(api, api.ann.user["id"])
        clip = api.ann.post(f"/api/videos/{ext}/clip", json={"start_time": 0, "end_time": 5}).json()
        assert api.ann.get(f"/api/clips/{clip['clip_id']}/thumbnail").status_code == 404

    @pytest.mark.parametrize("fmt", ["mp4", "webm", "gif"])
    def test_audio_cannot_be_clipped_as_a_picture_format(self, clip_world, fmt):
        api = clip_world
        ext = audio_video(api, api.ann.user["id"])
        response = api.ann.post(f"/api/videos/{ext}/clip", json={"start_time": 0, "end_time": 5, "format": fmt})
        assert response.status_code == 400 and "audio file" in response.json()["detail"]
        with api.w.get_db() as db:
            assert db.query(Clip).count() == 0     # nothing was created

    def test_a_clip_without_sound_cannot_be_an_mp3(self, clip_world):
        api = clip_world
        ext = audio_video(api, api.ann.user["id"])
        response = api.ann.post(f"/api/videos/{ext}/clip", json={"start_time": 0, "end_time": 5, "include_audio": False})
        assert response.status_code == 400 and "include_audio" in response.json()["detail"]

    def test_fades_work_on_sound(self, clip_world):
        api = clip_world
        ext = audio_video(api, api.ann.user["id"])
        clip = api.ann.post(f"/api/videos/{ext}/clip", json={"start_time": 0, "end_time": 6, "add_fade": True}).json()
        assert api.ann.get(f"/api/clips/{clip['clip_id']}").json()["status"] == "completed"

    def test_the_sound_of_a_video_can_be_taken_as_mp3(self, clip_world):
        api = clip_world
        path = make(api.w.tmp / "v.mp4", "-f", "lavfi", "-i", "testsrc=d=6:s=160x120:r=10", "-f", "lavfi", "-i",
                    "sine=d=6", "-shortest", "-pix_fmt", "yuv420p")
        row = api.w.video(api.ann.user["id"], status=VideoStatus.COMPLETED, ext="vid-a")
        with api.w.get_db() as db:
            db.query(Video).filter(Video.id == row).update({"file_path": str(path), "duration_seconds": 6.0})
        clip = api.ann.post("/api/videos/vid-a/clip", json={"start_time": 1, "end_time": 4, "format": "mp3"}).json()
        done = api.ann.get(f"/api/clips/{clip['clip_id']}").json()
        assert clip["format"] == "mp3" and done["status"] == "completed" and done["thumbnail_path"] is None
        out = api.w.tmp / "sound.mp3"
        out.write_bytes(api.ann.get(f"/api/clips/{clip['clip_id']}/download").content)
        assert probe(out)[0] == ["audio"]                     # the picture is gone

    def test_a_video_defaults_to_mp4_as_before(self, clip_world):
        api = clip_world
        path = make(api.w.tmp / "v.mp4", "-f", "lavfi", "-i", "testsrc=d=6:s=160x120:r=10", "-pix_fmt", "yuv420p")
        row = api.w.video(api.ann.user["id"], status=VideoStatus.COMPLETED, ext="vid-b")
        with api.w.get_db() as db:
            db.query(Video).filter(Video.id == row).update({"file_path": str(path), "duration_seconds": 6.0})
        clip = api.ann.post("/api/videos/vid-b/clip", json={"start_time": 0, "end_time": 3}).json()
        assert clip["format"] == "mp4"
        assert probe(self._download(api, clip["clip_id"]))[0].count("video") == 1

    @staticmethod
    def _download(api, clip_id):
        out = api.w.tmp / f"{clip_id}.bin"
        out.write_bytes(api.ann.get(f"/api/clips/{clip_id}/download").content)
        return out

    def test_a_reel_of_audio_clips_is_one_mp3_as_long_as_its_parts(self, clip_world):
        api = clip_world
        ext = audio_video(api, api.ann.user["id"])
        one = api.ann.post(f"/api/videos/{ext}/clip", json={"start_time": 0, "end_time": 5}).json()["clip_id"]
        two = api.ann.post(f"/api/videos/{ext}/clip", json={"start_time": 10, "end_time": 18}).json()["clip_id"]
        reel = api.ann.post("/api/clips/highlight-reel", json={"title": "r", "clip_ids": [one, two]}).json()
        assert reel["format"] == "mp3"
        got = api.ann.get(f"/api/clips/{reel['clip_id']}").json()
        assert got["status"] == "completed" and got["format"] == "mp3"
        kinds, seconds = probe(self._download(api, reel["clip_id"]))
        assert kinds == ["audio"] and seconds == pytest.approx(13.0, abs=0.4)

    def test_a_reel_cannot_mix_sound_and_picture(self, clip_world):
        api = clip_world
        ext = audio_video(api, api.ann.user["id"])
        sound = api.ann.post(f"/api/videos/{ext}/clip", json={"start_time": 0, "end_time": 5}).json()["clip_id"]
        path = make(api.w.tmp / "v.mp4", "-f", "lavfi", "-i", "testsrc=d=6:s=160x120:r=10", "-pix_fmt", "yuv420p")
        row = api.w.video(api.ann.user["id"], status=VideoStatus.COMPLETED, ext="vid-m")
        with api.w.get_db() as db:
            db.query(Video).filter(Video.id == row).update({"file_path": str(path), "duration_seconds": 6.0})
        picture = api.ann.post("/api/videos/vid-m/clip", json={"start_time": 0, "end_time": 3}).json()["clip_id"]
        response = api.ann.post("/api/clips/highlight-reel", json={"title": "r", "clip_ids": [sound, picture]})
        assert response.status_code == 400 and "mix" in response.json()["detail"]

    def test_batches_are_checked_before_any_clip_is_made(self, clip_world):
        api = clip_world
        ext = audio_video(api, api.ann.user["id"])
        body = {"video_id": ext, "clips": [{"start_time": 0, "end_time": 5}, {"start_time": 6, "end_time": 9, "format": "gif"}]}
        response = api.ann.post(f"/api/videos/{ext}/clips/batch", json=body)
        assert response.status_code == 400
        with api.w.get_db() as db:
            assert db.query(Clip).count() == 0

    def test_a_batch_of_audio_clips_with_a_reel(self, clip_world):
        api = clip_world
        ext = audio_video(api, api.ann.user["id"])
        body = {"video_id": ext, "create_highlight_reel": True,
                "clips": [{"start_time": 0, "end_time": 5}, {"start_time": 6, "end_time": 11}]}
        response = api.ann.post(f"/api/videos/{ext}/clips/batch", json=body)
        assert response.status_code == 200 and [c["format"] for c in response.json()["clips"]] == ["mp3", "mp3"]
        with api.w.get_db() as db:
            formats = sorted(c.format for c in db.query(Clip).all())
        assert formats == ["mp3", "mp3", "mp3"]      # two clips and the reel

    def test_a_batch_for_someone_elses_video_is_not_found(self, clip_world):
        api = clip_world
        ext = audio_video(api, api.ann.user["id"])
        response = api.bob.post(f"/api/videos/{ext}/clips/batch",
                                json={"video_id": ext, "clips": [{"start_time": 0, "end_time": 5}]})
        assert response.status_code == 404


class TestClipFormatRules:
    def request(self, **kw):
        from src.api.clips import CreateClipRequest
        return CreateClipRequest(start_time=0, end_time=5, **kw)

    @pytest.mark.parametrize("media,asked,expected", [
        ("video", None, "mp4"), ("audio", None, "mp3"), ("video", "webm", "webm"), ("video", "gif", "gif"),
        ("video", "mp3", "mp3"), ("audio", "mp3", "mp3"), (None, None, "mp4"),
    ])
    def test_the_format_a_clip_gets(self, media, asked, expected):
        from src.api.clips import resolve_clip_format
        assert resolve_clip_format(media, self.request(format=asked)) == expected

    @pytest.mark.parametrize("asked", ["mp4", "webm", "gif"])
    def test_audio_with_a_picture_format_is_refused(self, asked):
        from fastapi import HTTPException
        from src.api.clips import resolve_clip_format
        with pytest.raises(HTTPException) as info:
            resolve_clip_format("audio", self.request(format=asked))
        assert info.value.status_code == 400

    def test_mp3_needs_sound(self):
        from fastapi import HTTPException
        from src.api.clips import resolve_clip_format
        with pytest.raises(HTTPException):
            resolve_clip_format("audio", self.request(include_audio=False))
        with pytest.raises(HTTPException):
            resolve_clip_format("video", self.request(format="mp3", include_audio=False))

    def test_an_unknown_format_is_still_rejected_by_the_schema(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self.request(format="wav")

    def test_the_clip_command_for_sound_has_no_picture_and_uses_mp3(self):
        from src.services.highlights.clip_creator import ClipConfig, ClipCreator
        creator = ClipCreator(output_dir="/tmp")
        command = creator._build_ffmpeg_command("in.mp3", "out.mp3", 5, 7, ClipConfig(output_format="mp3", audio_only=True,
                                                                                        fade_in_duration=0.5, fade_out_duration=0.5))
        assert "-vn" in command and command[command.index("-c:a") + 1] == "libmp3lame"
        assert "-c:v" not in command and "-vf" not in command and "libx264" not in command
        assert command[command.index("-af") + 1] == "afade=t=in:st=0:d=0.5,afade=t=out:st=6.5:d=0.5"

    def test_the_clip_command_for_video_is_unchanged(self):
        from src.services.highlights.clip_creator import ClipConfig, ClipCreator
        command = ClipCreator(output_dir="/tmp")._build_ffmpeg_command("in.mp4", "out.mp4", 5, 7, ClipConfig())
        assert "libx264" in command and "-vn" not in command


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------

class TestAudioDownloads:
    def fake_ydl(self, seen):
        class FakeYDL:
            def __init__(self, opts):
                seen.update(opts)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def extract_info(self, url, download):
                return {"title": "Episode 12", "duration": 1800}
        return FakeYDL

    def test_youtube_audio_only_downloads_the_sound_as_mp3(self, qw):
        from src.api.videos import _download_youtube_blocking
        seen = {}
        ctx = JobContext(job_id="j", kind="download", video_id="v", user_id=None)
        with patch("yt_dlp.YoutubeDL", self.fake_ydl(seen)):
            info, path = _download_youtube_blocking("https://youtu.be/x", "vid-y", "audio", ctx, 50)
        assert path == "./data/uploads/vid-y.mp3"
        assert seen["format"] == "bestaudio/best" and "merge_output_format" not in seen
        assert seen["postprocessors"][0]["key"] == "FFmpegExtractAudio" and seen["postprocessors"][0]["preferredcodec"] == "mp3"
        assert seen["max_filesize"] == 50 * 1024 * 1024 and seen["noplaylist"] is True

    def test_youtube_video_downloads_are_unchanged(self, qw):
        from src.api.videos import _download_youtube_blocking
        seen = {}
        ctx = JobContext(job_id="j", kind="download", video_id="v", user_id=None)
        with patch("yt_dlp.YoutubeDL", self.fake_ydl(seen)):
            _, path = _download_youtube_blocking("https://youtu.be/x", "vid-y", "720p", ctx, 50)
        assert path.endswith(".mp4") and "height<=720" in seen["format"] and seen["merge_output_format"] == "mp4"
        assert "postprocessors" not in seen

    @pytest.mark.asyncio
    async def test_a_finished_youtube_audio_download_is_saved_as_audio(self, qw):
        from src.api.videos import download_youtube_video
        video = qw.video(status=VideoStatus.DOWNLOADING, ext="vid-ya", file=False)
        ctx = JobContext(job_id="j", kind="download", video_id="vid-ya", user_id=None)
        ctx.check_cancel = lambda: None
        target = qw.tmp / "ep.mp3"
        tone(target, 2, "-c:a", "libmp3lame")
        with patch("src.api.videos._download_youtube_blocking", return_value=({"title": "Episode 12", "duration": 1800}, str(target))), \
             patch("src.api.websockets.send_progress_update", new=AsyncMock()):
            await download_youtube_video("vid-ya", "https://youtu.be/x", None, "audio", False, ctx, 50)
        row = qw.video_row(video)
        assert row.media_type == "audio" and row.title == "Episode 12" and row.processing_status == VideoStatus.PENDING

    @pytest.mark.asyncio
    async def test_a_stream_that_is_only_sound_is_saved_as_audio(self, qw):
        from src.api.videos import download_streaming_video
        video = qw.video(status=VideoStatus.DOWNLOADING, ext="vid-sa", file=False)
        ctx = JobContext(job_id="j", kind="download", video_id="vid-sa", user_id=None)
        ctx.check_cancel = lambda: None
        (qw.tmp / "data" / "uploads").mkdir(parents=True)
        tone(qw.tmp / "data" / "uploads" / "vid-sa.mp4", 2, "-vn", "-c:a", "aac")

        with patch("src.api.videos._download_stream_blocking"), \
             patch("src.api.websockets.send_progress_update", new=AsyncMock()):
            await download_streaming_video("vid-sa", "https://example.com/radio.mp3", "Radio", False, ctx)
        assert qw.video_row(video).media_type == "audio"


# ---------------------------------------------------------------------------
# Status while the summary is still being written
# ---------------------------------------------------------------------------

class TestStatusWhileSummarising:
    def test_a_completed_video_whose_job_still_runs_reports_the_live_progress(self, api):
        """The analysis marks a video completed before the summary, highlights and chapters exist"""
        row = api.w.video(api.ann.user["id"], status=VideoStatus.COMPLETED, ext="late")
        job = api.w.enqueue(row)
        api.w.set(job, status="running")
        with patch("src.api.websockets.get_latest_progress",
                   return_value={"stage": "summarization", "progress": 95.0, "message": "Generating..."}):
            body = api.ann.get("/api/videos/late/status").json()
        assert body["progress"] == 95.0 and body["stage"] == "summarization" and body["job_status"] == "running"

    def test_a_finished_video_reports_100(self, api):
        api.w.video(api.ann.user["id"], status=VideoStatus.COMPLETED, ext="done")
        body = api.ann.get("/api/videos/done/status").json()
        assert body["progress"] == 100.0 and body["job_id"] is None
