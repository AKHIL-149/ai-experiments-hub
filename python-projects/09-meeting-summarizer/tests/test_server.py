import copy
import io
import json
import os
import time
import uuid
from pathlib import Path
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

import server
from utils.speaker_diarization import SpeakerDiarization
from tests.helpers import FakeLLM

SEGMENTS = [
    {"start": 0.0, "end": 4.0, "text": "Welcome everyone."},
    {"start": 4.0, "end": 9.0, "text": "Thanks for having me."},
    {"start": 21.0, "end": 24.0, "text": "Let us begin."},
]
TURNS = [
    {"start": 0, "end": 4, "speaker": "Speaker 1", "duration": 4},
    {"start": 4, "end": 12, "speaker": "Speaker 2", "duration": 8},
    {"start": 20, "end": 25, "speaker": "Speaker 1", "duration": 5},
]


def sample_result(**changes):
    result = {
        "metadata": {"audio_file": "a.mp3", "source_file": "a.mp3", "analyzed_at": "2026-01-01T00:00:00", "duration_seconds": 25.0},
        "transcript": {"text": "Welcome everyone.\nThanks for having me.\nLet us begin.", "segments": copy.deepcopy(SEGMENTS),
                       "language": "en", "backend": "whisper-cpp", "cached": False},
        "summary": {"text": "The summary.", "level": "standard", "word_count": 3, "cached": False},
        "actions": {"action_items": [{"id": 1, "description": "Send report", "assignee": "Bob", "due_date": "Fri", "priority": "high",
                                      "category": "x", "status": "pending"}],
                    "decisions": [{"id": 1, "decision": "Ship", "context": "c", "impact": "i"}], "follow_ups": ["Check"], "total_actions": 1,
                    "tokens_used": {}},
        "topics": ["Budget", "Hiring"],
        "statistics": {"total_cost_usd": 0.0, "cache_hits": 1, "cache_misses": 1, "processing_time_seconds": 2.0},
        "warnings": [],
    }
    result.update(changes)
    return result


class FakeSummarizer:
    def __init__(self, fail=False):
        self.fail, self.seen = fail, None

    def extract_speaker_key_points(self, speaker_transcript):
        self.seen = speaker_transcript
        if self.fail:
            raise RuntimeError("llm down")
        return {"Speaker 1": ["A point"]}


class FakeAnalyzer:
    def __init__(self, result=None, error=None):
        self.result, self.error = result or sample_result(), error
        self.calls, self.reports = [], []
        self.summarizer = FakeSummarizer()
        self.video_processor = server.video_processor

    def analyze_meeting(self, audio_path, **kwargs):
        self.calls.append({"path": audio_path, **kwargs})
        if kwargs.get("progress_callback"):
            kwargs["progress_callback"]("transcription_done")
            kwargs["progress_callback"]("summarization_done")
        if self.error:
            raise self.error
        result = copy.deepcopy(self.result)
        if not kwargs.get("extract_actions", True):
            result["actions"] = None
        if not kwargs.get("extract_topics", True):
            result["topics"] = None
        return result

    def generate_report(self, result, format="markdown", output_path=None, template=None):
        self.reports.append({"format": format, "path": output_path, "template": template})
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(f"report {format} {template}", encoding="utf-8")
        return "report"


class FakeAudio:
    def __init__(self, errors=None):
        self.errors = errors or []
        self.exported = []

    def validate_audio(self, path):
        return {"valid": not self.errors, "errors": self.errors, "warnings": []}

    def load_audio(self, path):
        return "audio"

    def export_audio(self, audio, path, format="wav"):
        self.exported.append(path)
        Path(path).write_bytes(b"wav")
        return path


def real_diarizer(turns=TURNS, error=None):
    d = SpeakerDiarization.__new__(SpeakerDiarization)
    d.is_available, d.last_error, d.pipeline = True, None, None
    if error:
        def boom(path):
            raise error
        d.diarize = boom
    else:
        d.diarize = lambda path: copy.deepcopy(turns) if turns is not None else None
    return d


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    """Every test starts from an empty server: no jobs, no files, diarizer not loaded"""
    def wipe():
        server.active_jobs.clear()
        server.websocket_connections.clear()
        session = server.db_manager.get_session()
        try:
            from core.database import Job
            session.query(Job).delete()
            session.commit()
        finally:
            session.close()
        for key in ("upload_dir", "output_dir", "temp_dir"):
            for f in Path(server.config[key]).glob("*"):
                f.unlink() if f.is_file() else None
    wipe()
    monkeypatch.setattr(server, "_speaker_diarizer", None)
    monkeypatch.setattr(server, "_speaker_diarizer_loaded", False)
    yield
    wipe()


@pytest.fixture
def client():
    with TestClient(server.app) as c:
        yield c


@pytest.fixture
def analyzer(monkeypatch):
    fake, audio = FakeAnalyzer(), FakeAudio()
    monkeypatch.setattr(server, "create_meeting_analyzer", lambda: (fake, audio))
    fake.audio = audio
    return fake


def upload(client, name="meeting.mp3", content=b"audio bytes"):
    response = client.post("/api/upload", files={"file": (name, io.BytesIO(content), "audio/mpeg")})
    return response


def new_job(client, name="meeting.mp3"):
    return upload(client, name).json()["job_id"]


def run(client, job_id, **params):
    response = client.post(f"/api/analyze/{job_id}", params=params)
    assert response.status_code == 200, response.text
    return wait(client, job_id)


def wait(client, job_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/api/jobs/{job_id}").json()
        if data["status"] in ("completed", "failed", "cancelled"):
            return data
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def upload_files():
    return sorted(p.name for p in Path(server.config["upload_dir"]).glob("*"))


def output_files():
    return sorted(p.name for p in Path(server.config["output_dir"]).glob("*"))


# ------------------------------------------------------------------ basics

class TestBasics:
    def test_health(self, client):
        data = client.get("/api/health").json()
        assert data["status"] == "ok" and data["services"]["transcription"] == "whisper-cpp"

    def test_speaker_model_is_not_loaded_until_asked_for(self, client, monkeypatch):
        # Loading takes ~25 s and several network requests: it must not happen at startup
        assert client.get("/api/health").json()["services"]["speaker_identification"] is None
        calls = []
        monkeypatch.setattr(server, "create_speaker_diarization", lambda token: calls.append(token) or real_diarizer())
        assert server.get_speaker_diarizer() is not None and server.get_speaker_diarizer() is not None
        assert len(calls) == 1                                   # loaded once, reused
        assert client.get("/api/health").json()["services"]["speaker_identification"] is True

    def test_unavailable_speaker_model_is_remembered(self, client, monkeypatch):
        calls = []
        monkeypatch.setattr(server, "create_speaker_diarization", lambda token: calls.append(1))
        assert server.get_speaker_diarizer() is None and server.get_speaker_diarizer() is None
        assert len(calls) == 1
        assert client.get("/api/health").json()["services"]["speaker_identification"] is False

    def test_page_and_templates(self, client):
        assert client.get("/").status_code == 200
        templates = client.get("/api/templates").json()["templates"]
        assert {"executive", "detailed", "brief", "meeting_minutes", "technical"} <= set(templates)

    def test_unexpected_errors_do_not_leak(self, monkeypatch):
        def boom(job_id):
            raise RuntimeError("secret path /Users/x/db.sqlite exploded")
        monkeypatch.setattr(server.db_manager, "get_job", boom)
        with TestClient(server.app, raise_server_exceptions=False) as c:
            response = c.get(f"/api/jobs/{uuid.uuid4()}")
        assert response.status_code == 500
        assert response.json() == {"detail": "Something went wrong on the server"}


class TestMain:
    def run_main(self, monkeypatch, **env):
        seen = {}
        monkeypatch.setattr(server.uvicorn, "run", lambda app, **kwargs: seen.update(kwargs))
        for name in ("HOST", "PORT", "RELOAD"):
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        server.main()
        return seen

    def test_listens_on_loopback_by_default(self, monkeypatch):
        # there is no login: the server must not be reachable from the network unless asked
        assert self.run_main(monkeypatch)["host"] == "127.0.0.1"

    def test_host_and_port_can_be_set(self, monkeypatch):
        seen = self.run_main(monkeypatch, HOST="0.0.0.0", PORT="9100")
        assert (seen["host"], seen["port"]) == ("0.0.0.0", 9100)


class TestCors:
    def test_own_origins_by_default(self):
        assert server.cors_origins(None, "8000") == ["http://localhost:8000", "http://127.0.0.1:8000"]
        assert server.cors_origins(None, "9000") == ["http://localhost:9000", "http://127.0.0.1:9000"]

    def test_configured_origins(self):
        assert server.cors_origins("https://a.example, https://b.example ,", "8000") == ["https://a.example", "https://b.example"]
        assert server.cors_origins("", "8000") == []                       # explicitly none

    def test_foreign_pages_get_no_access(self, client):
        evil = client.get("/api/jobs", headers={"Origin": "http://evil.example"})
        assert "access-control-allow-origin" not in evil.headers
        own = client.get("/api/jobs", headers={"Origin": "http://localhost:8000"})
        assert own.headers["access-control-allow-origin"] == "http://localhost:8000"
        assert "access-control-allow-credentials" not in own.headers

    def test_preflight_from_a_foreign_page_is_refused(self, client):
        response = client.options("/api/jobs/x", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "DELETE"})
        assert response.status_code == 400


# ------------------------------------------------------------------ uploads

class TestUpload:
    def test_audio_is_stored_under_the_job_id(self, client):
        data = upload(client, "Q3 review.mp3", b"abc").json()
        uuid.UUID(data["job_id"])
        assert data["filename"] == "Q3 review.mp3" and data["size_bytes"] == 3
        assert upload_files() == [f"{data['job_id']}.mp3"]
        row = server.db_manager.get_job(data["job_id"])
        assert row.filename == "Q3 review.mp3" and row.status == "queued"

    def test_video_is_accepted(self, client):
        assert upload(client, "talk.mp4").status_code == 200

    def test_extension_is_case_insensitive(self, client):
        assert upload(client, "TALK.MP3").status_code == 200

    @pytest.mark.parametrize("name", ["notes.txt", "malware.exe", "noextension", "archive.mp3.zip", ".mp3x"])
    def test_other_types_are_refused(self, client, name):
        response = upload(client, name)
        assert response.status_code == 400 and "Invalid file type" in response.json()["detail"]
        assert upload_files() == []

    def test_empty_file_is_refused_and_leaves_nothing(self, client):
        response = upload(client, content=b"")
        assert response.status_code == 400 and "empty" in response.json()["detail"]
        assert upload_files() == [] and client.get("/api/jobs").json()["jobs"] == []

    def test_too_large_is_refused_while_streaming_and_leaves_nothing(self, client, monkeypatch):
        monkeypatch.setitem(server.config, "max_audio_size_mb", 1)
        response = upload(client, content=b"x" * (1024 * 1024 + 1))
        assert response.status_code == 413 and "Maximum size: 1 MB" in response.json()["detail"]
        assert upload_files() == []

    def test_a_file_exactly_at_the_limit_is_accepted(self, client, monkeypatch):
        monkeypatch.setitem(server.config, "max_audio_size_mb", 1)
        assert upload(client, content=b"x" * (1024 * 1024)).status_code == 200

    def test_uploaded_file_is_written_in_pieces(self, client, monkeypatch):
        monkeypatch.setattr(server, "UPLOAD_CHUNK_BYTES", 10)
        data = upload(client, content=b"0123456789" * 5).json()
        assert data["size_bytes"] == 50
        assert (Path(server.config["upload_dir"]) / f"{data['job_id']}.mp3").read_bytes() == b"0123456789" * 5

    @pytest.mark.parametrize("sent,stored", [
        ("../../etc/passwd.mp3", "passwd.mp3"),
        ("C:\\Users\\me\\meeting.mp3", "meeting.mp3"),
        ("  spaced.mp3  ", "spaced.mp3"),
    ])
    def test_the_stored_name_is_a_base_name_without_control_characters(self, client, sent, stored):
        assert upload(client, sent).json()["filename"] == stored

    @pytest.mark.parametrize("raw,clean", [
        ("nice\x00\x1fname.mp3", "nicename.mp3"), ("a\x7fb\nc.mp3", "abc.mp3"), ("tab\there.mp3", "tabhere.mp3"),
        ("../../x/y.mp3", "y.mp3"), ("..\\..\\y.mp3", "y.mp3"), ("/etc/passwd", "passwd"), ("..", "upload"),
    ])
    def test_safe_filename_strips_directories_and_control_characters(self, raw, clean):
        assert server.safe_filename(raw) == clean

    def test_safe_filename_limits(self):
        assert len(server.safe_filename("a" * 500 + ".mp3")) == 200
        assert server.safe_filename(None) == "upload" and server.safe_filename("") == "upload"


# ------------------------------------------------------------------ analyze: validation

class TestAnalyzeValidation:
    @pytest.mark.parametrize("bad", ["abc", "*", "%2A", "1234", "zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz", "..%2F..%2Fetc"])
    def test_malformed_job_ids(self, client, bad):
        response = client.post(f"/api/analyze/{bad}")
        assert response.status_code in (400, 404)

    @pytest.mark.parametrize("bad", ["abc", "*", "not-a-uuid", "1234"])
    def test_malformed_ids_are_refused_by_every_job_endpoint(self, client, bad):
        for method, path in [("get", f"/api/jobs/{bad}"), ("post", f"/api/jobs/{bad}/cancel"), ("delete", f"/api/jobs/{bad}"),
                             ("get", f"/api/jobs/{bad}/download"), ("post", f"/api/analyze/{bad}")]:
            response = getattr(client, method)(path)
            assert response.status_code == 400, path
            assert response.json()["detail"] == "Invalid job id"

    def test_a_glob_id_never_reaches_someone_elses_upload(self, client, analyzer):
        first = new_job(client)
        assert client.post("/api/analyze/*").status_code == 400            # used to analyze an arbitrary upload
        assert analyzer.calls == [] and first not in server.active_jobs

    def test_unknown_job(self, client):
        assert client.post(f"/api/analyze/{uuid.uuid4()}").status_code == 404

    def test_job_whose_file_is_gone(self, client):
        job_id = new_job(client)
        Path(server.config["upload_dir"], f"{job_id}.mp3").unlink()
        assert client.post(f"/api/analyze/{job_id}").status_code == 404

    @pytest.mark.parametrize("query,message", [
        ("summary_level=banana", "Invalid summary_level"),
        ("summary_level=", "Invalid summary_level"),
        ("output_format=exe", "Invalid output_format"),
        ("output_format=/../zz_probe_outside.md", "Invalid output_format"),
        ("output_format=../../server.py", "Invalid output_format"),
        ("output_format=", "Invalid output_format"),
        ("template=nope", "Unknown template"),
        ("template=../../etc/passwd", "Unknown template"),
        ("language=--help", "Invalid language"),
        ("language=english", "Invalid language"),
        ("language=EN", "Invalid language"),
    ])
    def test_bad_options_are_refused_and_queue_nothing(self, client, analyzer, query, message):
        job_id = new_job(client)
        response = client.post(f"/api/analyze/{job_id}?{query}")
        assert response.status_code == 400 and message in response.json()["detail"]
        assert analyzer.calls == [] and job_id not in server.active_jobs
        assert server.db_manager.get_job(job_id).status == "queued"

    def test_unknown_template_error_lists_the_choices(self, client):
        detail = client.post(f"/api/analyze/{new_job(client)}?template=nope").json()["detail"]
        assert "executive" in detail and "standup" in detail

    @pytest.mark.parametrize("query", ["summary_level=brief", "summary_level=detailed", "output_format=json", "output_format=html",
                                       "output_format=txt", "output_format=md", "language=en", "language=auto", "language=",
                                       "template=executive", "template=standup", "all_levels=true", "identify_speakers=true"])
    def test_valid_options_are_accepted(self, client, analyzer, query):
        job_id = new_job(client)
        assert client.post(f"/api/analyze/{job_id}?{query}").status_code == 200

    def test_a_running_job_cannot_be_started_again(self, client, analyzer):
        job_id = new_job(client)
        server.active_jobs[job_id] = {"status": "processing"}
        response = client.post(f"/api/analyze/{job_id}")
        assert response.status_code == 409 and "already being analyzed" in response.json()["detail"]
        server.active_jobs[job_id] = {"status": "queued"}
        assert client.post(f"/api/analyze/{job_id}").status_code == 409

    def test_a_finished_job_can_be_run_again(self, client, analyzer):
        job_id = new_job(client)
        assert run(client, job_id)["status"] == "completed"
        assert run(client, job_id, summary_level="brief")["status"] == "completed"
        assert [c["summary_level"] for c in analyzer.calls] == ["standard", "brief"]

    def test_the_file_comes_from_the_database_not_a_directory_search(self, client, analyzer):
        job_id = new_job(client)
        # leftovers a crashed run could leave next to the upload - a glob picked one of these up
        for stray in (f"{job_id}.mp3.txt", f"{job_id}.mp3.wav", f"{job_id}_diarize.wav"):
            (Path(server.config["upload_dir"]) / stray).write_bytes(b"stray")
        run(client, job_id)
        assert Path(analyzer.calls[0]["path"]).name == f"{job_id}.mp3"


# ------------------------------------------------------------------ analyze: lifecycle

class TestLifecycle:
    def test_completed_job(self, client, analyzer):
        job_id = new_job(client, "Weekly sync.mp3")
        data = run(client, job_id)
        assert data["status"] == "completed" and data["download_url"] == f"/api/jobs/{job_id}/download"
        result = data["result"]
        assert result["summary"] == "The summary." and result["topics"] == ["Budget", "Hiring"]
        assert result["action_items_count"] == 1 and result["statistics"]["cache_hits"] == 1
        assert result["actions"]["action_items"][0]["description"] == "Send report"
        assert result["actions"]["decisions"][0]["decision"] == "Ship" and result["actions"]["follow_ups"] == ["Check"]
        assert result["transcript"].startswith("Welcome everyone.") and result["warnings"] == []
        row = server.db_manager.get_job(job_id)
        assert row.status == "completed" and row.summary_text == "The summary." and row.action_items_count == 1
        assert row.progress_percent == 100

    def test_the_users_options_reach_the_analyzer(self, client, analyzer):
        run(client, new_job(client), summary_level="detailed", extract_actions="false", extract_topics="false", language="es", all_levels="true")
        call = analyzer.calls[0]
        assert (call["summary_level"], call["extract_actions"], call["extract_topics"], call["language"], call["all_levels"]) == \
               ("detailed", False, False, "es", True)

    def test_the_report_names_the_original_file(self, client, analyzer):
        job_id = new_job(client, "Quarterly Review.mp3")
        run(client, job_id)
        assert server.active_jobs[job_id]["result"]["metadata"]["source_file"] == "Quarterly Review.mp3"

    def test_status_when_steps_are_switched_off(self, client, analyzer):
        # used to be a bare 500: the status endpoint called .get() on None
        data = run(client, new_job(client), extract_actions="false", extract_topics="false")
        assert data["status"] == "completed"
        assert data["result"]["action_items_count"] == 0 and data["result"]["topics"] == []
        assert data["result"]["actions"] == {"action_items": [], "decisions": [], "follow_ups": []}

    def test_status_after_eviction_falls_back_to_the_database(self, client, analyzer):
        job_id = new_job(client)
        run(client, job_id)
        server.active_jobs.clear()
        data = client.get(f"/api/jobs/{job_id}").json()
        assert data["status"] == "completed" and data["result"]["summary"] == "The summary." and data["result"]["action_items_count"] == 1

    @pytest.mark.parametrize("fmt,ext,passed", [("markdown", "md", "markdown"), ("md", "md", "markdown"), ("json", "json", "json"),
                                                ("html", "html", "html"), ("txt", "txt", "txt")])
    def test_report_goes_to_the_expected_file_and_nowhere_else(self, client, analyzer, fmt, ext, passed):
        job_id = new_job(client)
        run(client, job_id, output_format=fmt)
        assert output_files() == [f"{job_id}_analysis.{ext}"]
        assert analyzer.reports[0]["format"] == passed
        assert Path(analyzer.reports[0]["path"]).resolve().parent == Path(server.config["output_dir"]).resolve()

    def test_a_template_always_produces_markdown(self, client, analyzer):
        job_id = new_job(client)
        run(client, job_id, template="executive", output_format="json")
        assert output_files() == [f"{job_id}_analysis.md"]
        assert analyzer.reports[0]["template"] == "executive"

    def test_analyzer_errors_become_a_short_failure_message(self, client, analyzer):
        analyzer.error = ValueError("No speech was detected in this recording.\nTraceback (most recent call last): ...")
        job_id = new_job(client)
        data = run(client, job_id)
        assert data["status"] == "failed" and data["error"] == "No speech was detected in this recording."
        assert server.db_manager.get_job(job_id).error_message == "No speech was detected in this recording."
        assert output_files() == []

    def test_very_long_errors_are_cut(self, client, analyzer):
        analyzer.error = RuntimeError("x" * 1000)
        error = run(client, new_job(client))["error"]
        assert len(error) == 300 and error.endswith("…")

    def test_validation_failure_is_one_string(self, client, analyzer):
        analyzer.audio.errors = ["This file could not be read as MP3 audio.", "Second problem"]
        data = run(client, new_job(client))
        assert data["status"] == "failed" and data["error"] == "This file could not be read as MP3 audio.; Second problem"
        assert analyzer.calls == []

    def test_a_failed_job_can_be_retried(self, client, analyzer):
        analyzer.error = RuntimeError("temporary")
        job_id = new_job(client)
        assert run(client, job_id)["status"] == "failed"
        analyzer.error = None
        data = run(client, job_id)
        assert data["status"] == "completed"
        assert server.db_manager.get_job(job_id).error_message is None

    def test_progress_is_recorded(self, client, analyzer):
        job_id = new_job(client)
        run(client, job_id)
        stages = [json.loads(p.read_text()).get("current_stage") for p in Path(server.config["progress_dir"]).glob(f"{job_id}*.json")]
        assert stages and stages[0] in ("completed", "report_generation")

    def test_video_audio_is_extracted_and_the_temp_track_removed(self, client, analyzer, monkeypatch, tmp_path):
        track = tmp_path / "track.mp3"; track.write_bytes(b"x")
        monkeypatch.setattr(server.video_processor, "extract_audio", lambda path: str(track))
        data = run(client, new_job(client, "talk.mp4"))
        assert data["status"] == "completed"
        assert analyzer.calls[0]["path"] == str(track)
        assert not track.exists()

    def test_a_video_without_audio_fails_with_a_clear_message(self, client, analyzer, monkeypatch):
        from utils.video_processor import VideoError
        def no_audio(path):
            raise VideoError("This video has no audio track, so there is nothing to transcribe.")
        monkeypatch.setattr(server.video_processor, "extract_audio", no_audio)
        data = run(client, new_job(client, "mute.mp4"))
        assert data["status"] == "failed" and data["error"] == "This video has no audio track, so there is nothing to transcribe."


class TestMemory:
    def test_only_the_newest_finished_jobs_stay_in_memory(self, client, analyzer, monkeypatch):
        monkeypatch.setitem(server.config, "max_finished_jobs_in_memory", 2)
        ids = []
        for _ in range(5):
            ids.append(new_job(client)); run(client, ids[-1]); time.sleep(0.01)
        assert len(server.active_jobs) == 2 and set(server.active_jobs) == set(ids[-2:])
        # evicted jobs are still answered, from the database
        assert client.get(f"/api/jobs/{ids[0]}").json()["result"]["summary"] == "The summary."

    def test_running_jobs_are_never_evicted(self, monkeypatch):
        monkeypatch.setitem(server.config, "max_finished_jobs_in_memory", 0)
        server.active_jobs["run"] = {"status": "processing"}
        server.active_jobs["q"] = {"status": "queued"}
        server.active_jobs["done"] = {"status": "completed", "completed_at": "2026-01-01"}
        server.evict_finished_jobs()
        assert set(server.active_jobs) == {"run", "q"}


# ------------------------------------------------------------------ download / cancel / delete / list

class TestDownload:
    @pytest.mark.parametrize("fmt,ext,mime", [("markdown", ".md", "text/markdown"), ("json", ".json", "application/json"),
                                              ("html", ".html", "text/html"), ("txt", ".txt", "text/plain")])
    def test_type_and_a_name_the_user_recognises(self, client, analyzer, fmt, ext, mime):
        job_id = new_job(client, "Board meeting.mp3")
        run(client, job_id, output_format=fmt)
        response = client.get(f"/api/jobs/{job_id}/download")
        assert response.status_code == 200 and response.headers["content-type"].startswith(mime)
        disposition = unquote(response.headers["content-disposition"])
        assert disposition.startswith("attachment") and f"Board meeting_analysis{ext}" in disposition
        assert response.text.startswith("report")

    def test_download_after_the_job_left_memory(self, client, analyzer):
        job_id = new_job(client)
        run(client, job_id)
        server.active_jobs.clear()
        assert client.get(f"/api/jobs/{job_id}/download").status_code == 200

    def test_not_completed_and_unknown(self, client, analyzer):
        job_id = new_job(client)
        assert client.get(f"/api/jobs/{job_id}/download").status_code == 400
        assert client.get(f"/api/jobs/{uuid.uuid4()}/download").status_code == 404

    def test_report_file_missing(self, client, analyzer):
        job_id = new_job(client)
        run(client, job_id)
        Path(server.active_jobs[job_id]["output_file"]).unlink()
        assert client.get(f"/api/jobs/{job_id}/download").status_code == 404


class TestCancelAndDelete:
    def test_cancel_a_running_job(self, client):
        job_id = new_job(client)
        server.active_jobs[job_id] = {"status": "processing", "progress": {}}
        server.db_manager.update_job(job_id, status="processing")
        assert client.post(f"/api/jobs/{job_id}/cancel").json() == {"job_id": job_id, "status": "cancelled"}
        assert server.active_jobs[job_id]["cancel_requested"] is True
        assert client.get(f"/api/jobs/{job_id}").json()["status"] == "cancelled"
        assert server.db_manager.get_job(job_id).status == "cancelled"

    def test_cancel_a_queued_job_that_is_only_in_the_database(self, client):
        job_id = new_job(client)
        assert client.post(f"/api/jobs/{job_id}/cancel").json()["status"] == "cancelled"

    def test_cancel_a_finished_job_is_refused(self, client, analyzer):
        job_id = new_job(client)
        run(client, job_id)
        response = client.post(f"/api/jobs/{job_id}/cancel")
        assert response.status_code == 400 and "already completed" in response.json()["detail"]

    def test_cancel_unknown(self, client):
        assert client.post(f"/api/jobs/{uuid.uuid4()}/cancel").status_code == 404

    def test_delete_removes_the_row_the_upload_and_the_report(self, client, analyzer):
        job_id = new_job(client)
        run(client, job_id)
        assert client.delete(f"/api/jobs/{job_id}").json() == {"message": "Job deleted"}
        assert upload_files() == [] and output_files() == []
        assert client.get(f"/api/jobs/{job_id}").status_code == 404 and job_id not in server.active_jobs

    def test_delete_removes_the_saved_progress_state_too(self, client, analyzer):
        job_id = new_job(client)
        run(client, job_id)
        progress = Path(server.config["progress_dir"]) / f"{job_id}.json"
        assert progress.exists()
        client.delete(f"/api/jobs/{job_id}")
        assert not progress.exists()

    def test_delete_a_job_that_never_ran(self, client):
        job_id = new_job(client)
        assert client.delete(f"/api/jobs/{job_id}").status_code == 200 and upload_files() == []

    def test_deleting_a_running_job_stops_caring_about_its_result(self, client):
        job_id = new_job(client)
        live = {"status": "processing"}
        server.active_jobs[job_id] = live
        assert client.delete(f"/api/jobs/{job_id}").status_code == 200
        assert live["cancel_requested"] is True and live["status"] == "cancelled"

    def test_delete_unknown(self, client):
        assert client.delete(f"/api/jobs/{uuid.uuid4()}").status_code == 404

    def test_delete_touches_only_that_job(self, client, analyzer):
        a, b = new_job(client), new_job(client)
        run(client, a); run(client, b)
        client.delete(f"/api/jobs/{a}")
        assert upload_files() == [f"{b}.mp3"] and output_files() == [f"{b}_analysis.md"]


class TestListJobs:
    def test_newest_first_with_original_names(self, client):
        first = new_job(client, "one.mp3"); time.sleep(0.01); second = new_job(client, "two.mp3")
        data = client.get("/api/jobs").json()
        assert [j["filename"] for j in data["jobs"]] == ["two.mp3", "one.mp3"] and data["total"] == 2
        assert {j["job_id"] for j in data["jobs"]} == {first, second}

    def test_paging_and_filtering(self, client, analyzer):
        ids = [new_job(client) for _ in range(5)]
        run(client, ids[0])
        assert len(client.get("/api/jobs?limit=2").json()["jobs"]) == 2
        assert len(client.get("/api/jobs?limit=2&offset=4").json()["jobs"]) == 1
        assert [j["job_id"] for j in client.get("/api/jobs?status=completed").json()["jobs"]] == [ids[0]]
        assert len(client.get("/api/jobs?status=queued").json()["jobs"]) == 4

    @pytest.mark.parametrize("query,code", [("limit=0", 422), ("limit=-1", 422), ("limit=201", 422), ("limit=abc", 422),
                                            ("offset=-1", 422), ("status=evil", 400)])
    def test_bad_paging_is_refused(self, client, query, code):
        assert client.get(f"/api/jobs?{query}").status_code == code

    def test_live_status_overrides_the_stored_one(self, client):
        job_id = new_job(client)
        server.active_jobs[job_id] = {"status": "processing", "progress": {"progress_percent": 45}}
        job = client.get("/api/jobs").json()["jobs"][0]
        assert (job["status"], job["progress_percent"]) == ("processing", 45)


# ------------------------------------------------------------------ speakers

class TestSpeakerIdentification:
    def test_labels_come_from_the_transcript_timestamps(self, client, analyzer, monkeypatch):
        monkeypatch.setattr(server, "get_speaker_diarizer", lambda: real_diarizer())
        data = run(client, new_job(client), identify_speakers="true")
        sd = data["result"]["speaker_diarization"]
        assert sd["approximate"] is False
        assert [(s["speaker"], s["text"]) for s in sd["speaker_transcript"]] == [
            ("Speaker 1", "Welcome everyone."), ("Speaker 2", "Thanks for having me."), ("Speaker 1", "Let us begin.")]
        assert [s["end"] - s["start"] for s in sd["speaker_transcript"]] == [4.0, 5.0, 3.0]       # real times, not an even split
        assert sd["statistics"]["total_speakers"] == 2
        assert sd["key_points"] == {"Speaker 1": ["A point"]} and data["result"]["warnings"] == []
        assert analyzer.summarizer.seen == sd["speaker_transcript"]

    def test_the_temporary_wav_is_removed(self, client, analyzer, monkeypatch):
        monkeypatch.setattr(server, "get_speaker_diarizer", lambda: real_diarizer())
        job_id = new_job(client)
        run(client, job_id, identify_speakers="true")
        assert analyzer.audio.exported and upload_files() == [f"{job_id}.mp3"]

    def test_not_requested_means_not_run(self, client, analyzer, monkeypatch):
        monkeypatch.setattr(server, "get_speaker_diarizer", lambda: pytest.fail("loaded the speaker model without being asked"))
        assert "speaker_diarization" not in run(client, new_job(client))["result"]

    def test_unavailable_is_reported_not_silently_ignored(self, client, analyzer, monkeypatch):
        monkeypatch.setattr(server, "get_speaker_diarizer", lambda: None)
        data = run(client, new_job(client), identify_speakers="true")
        assert data["status"] == "completed" and "speaker_diarization" not in data["result"]
        assert any("not available" in w for w in data["result"]["warnings"])

    def test_no_speakers_found(self, client, analyzer, monkeypatch):
        monkeypatch.setattr(server, "get_speaker_diarizer", lambda: real_diarizer(turns=None))
        data = run(client, new_job(client), identify_speakers="true")
        assert data["status"] == "completed" and any("found no speakers" in w for w in data["result"]["warnings"])

    def test_a_crash_does_not_fail_the_job(self, client, analyzer, monkeypatch):
        monkeypatch.setattr(server, "get_speaker_diarizer", lambda: real_diarizer(error=RuntimeError("pyannote exploded")))
        data = run(client, new_job(client), identify_speakers="true")
        assert data["status"] == "completed"
        assert any("Speaker identification failed: pyannote exploded" in w for w in data["result"]["warnings"])

    def test_without_timestamps_the_labels_are_flagged_approximate(self, client, analyzer, monkeypatch):
        analyzer.result = sample_result(transcript={"text": "One. Two. Three.", "segments": [], "language": "en", "backend": "openai", "cached": False})
        monkeypatch.setattr(server, "get_speaker_diarizer", lambda: real_diarizer())
        data = run(client, new_job(client), identify_speakers="true")
        assert data["result"]["speaker_diarization"]["approximate"] is True
        assert any("rough guess" in w for w in data["result"]["warnings"])

    def test_failing_key_points_keep_the_rest(self, client, analyzer, monkeypatch):
        analyzer.summarizer.fail = True
        monkeypatch.setattr(server, "get_speaker_diarizer", lambda: real_diarizer())
        data = run(client, new_job(client), identify_speakers="true")
        sd = data["result"]["speaker_diarization"]
        assert sd["key_points"] == {} and sd["statistics"]["total_speakers"] == 2
        assert any("key points could not be generated" in w for w in data["result"]["warnings"])


# ------------------------------------------------------------------ housekeeping

class TestHousekeeping:
    def age(self, path, seconds):
        old = time.time() - seconds
        os.utime(path, (old, old))

    def test_old_leftovers_are_removed_real_uploads_and_recent_files_are_kept(self, scratch):
        uploads = Path(server.config["upload_dir"])
        real = uploads / f"{uuid.uuid4()}.mp3"
        leftovers = [uploads / f"{uuid.uuid4()}.mp3.txt", uploads / f"{uuid.uuid4()}.mp3.wav", uploads / f"{uuid.uuid4()}_diarize.wav", uploads / "random.wav"]
        recent = uploads / f"{uuid.uuid4()}.mp3.txt"
        for f in [real, recent, *leftovers]:
            f.write_bytes(b"x")
        for f in [real, *leftovers]:
            self.age(f, 7200)
        server.cleanup_stray_upload_files()
        assert real.exists() and recent.exists()
        assert all(not f.exists() for f in leftovers)

    def test_startup_cleans_up_and_fails_interrupted_jobs(self):
        job_id = str(uuid.uuid4())
        server.db_manager.create_job(job_id, "x.mp3", "nowhere.mp3")
        server.db_manager.mark_job_processing(job_id)
        stray = Path(server.config["upload_dir"]) / "old.wav"
        stray.write_bytes(b"x"); self.age(stray, 7200)
        with TestClient(server.app):
            pass
        row = server.db_manager.get_job(job_id)
        assert row.status == "failed" and row.error_message == "Interrupted by server restart"
        assert not stray.exists()


class TestWebSocket:
    def test_not_a_job_id(self, client):
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/not-a-job"):
                pass

    def test_current_progress_is_sent_on_connect(self, client):
        job_id = str(uuid.uuid4())
        server.active_jobs[job_id] = {"status": "processing", "progress": {"progress_percent": 42, "current_stage": "transcription"}}
        with client.websocket_connect(f"/ws/{job_id}") as ws:
            assert ws.receive_json() == {"progress_percent": 42, "current_stage": "transcription"}
        assert job_id not in server.websocket_connections            # cleaned up after disconnect
