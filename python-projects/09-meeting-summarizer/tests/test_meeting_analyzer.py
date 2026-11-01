import json
import re
import subprocess

import pytest

from core.audio_processor import AudioProcessor
from core.cache_manager import CacheManager
from core.meeting_analyzer import MeetingAnalyzer
from core.transcription_service import NoSpeechError
from tests.helpers import FakeLLM, needs_ffmpeg

SEGMENTS = [
    {"start": 0.0, "end": 3.0, "text": "Welcome to the meeting."},
    {"start": 3.0, "end": 6.0, "text": "We will ship on Friday."},
]
ACTIONS = json.dumps({
    "action_items": [{"description": "Send the report", "assignee": "Bob", "due_date": "Friday", "priority": "high", "category": "Docs"}],
    "decisions": [{"decision": "Ship on Friday", "context": "Launch", "impact": "None"}],
    "follow_ups": ["Check legal"],
})


class FakeTranscription:
    backend = "fake-backend"

    def __init__(self, error=None, text=None, segments=SEGMENTS):
        self.error, self.calls = error, []
        self.text = text if text is not None else "\n".join(s["text"] for s in segments)
        self.segments = segments

    def transcribe(self, audio_path, language=None, use_cache=True):
        self.calls.append((audio_path, language))
        if self.error:
            raise self.error
        return {"text": self.text, "segments": self.segments, "language": "en", "backend": "fake-backend", "cached": False}


def analyzer(tmp_path, replies=None, transcription=None, cache=False, llm=None):
    llm = llm or FakeLLM(replies or ["A summary.", ACTIONS, "Topic one\nTopic two"])
    return MeetingAnalyzer(
        transcription_service=transcription or FakeTranscription(),
        llm_client=llm,
        cache_manager=CacheManager(cache_dir=str(tmp_path / "cache")) if cache else None,
        audio_processor=AudioProcessor(),
    ), llm


class TestAnalyzeMeeting:
    def test_result_shape(self, tone_wav, tmp_path):
        result = analyzer(tmp_path)[0].analyze_meeting(str(tone_wav))
        assert result["summary"]["text"] == "A summary." and result["summary"]["level"] == "standard"
        assert result["topics"] == ["Topic one", "Topic two"]
        assert result["actions"]["total_actions"] == 1
        assert result["transcript"]["segments"] == SEGMENTS
        assert result["transcript"]["text"] == "Welcome to the meeting.\nWe will ship on Friday."
        assert result["metadata"]["duration_seconds"] == 3.0 and result["metadata"]["source_file"] == "tone.wav"
        assert result["warnings"] == []
        assert result["statistics"]["transcription_backend"] == "fake-backend"

    def test_language_is_passed_to_the_transcriber(self, tone_wav, tmp_path):
        transcription = FakeTranscription()
        analyzer(tmp_path, transcription=transcription)[0].analyze_meeting(str(tone_wav), language="es")
        assert transcription.calls[0][1] == "es"

    def test_steps_can_be_switched_off(self, tone_wav, tmp_path):
        a, llm = analyzer(tmp_path, ["A summary."])
        result = a.analyze_meeting(str(tone_wav), extract_actions=False, extract_topics=False)
        assert result["actions"] is None and result["topics"] is None
        assert len(llm.calls) == 1

    def test_no_speech_stops_the_analysis(self, tone_wav, tmp_path):
        a, llm = analyzer(tmp_path, transcription=FakeTranscription(error=NoSpeechError("No speech was detected in this recording.")))
        with pytest.raises(NoSpeechError):
            a.analyze_meeting(str(tone_wav))
        assert llm.calls == []                   # nothing was sent to the model

    def test_all_levels(self, tone_wav, tmp_path):
        a, _ = analyzer(tmp_path, ["brief", "standard", "detailed", ACTIONS, "T"])
        result = a.analyze_meeting(str(tone_wav), summary_level="detailed", all_levels=True)
        assert {k: v["text"] for k, v in result["summary_levels"].items()} == {"brief": "brief", "standard": "standard", "detailed": "detailed"}
        assert result["summary"]["text"] == "detailed"

    def test_summaries_are_cached_per_level(self, tone_wav, tmp_path):
        a, llm = analyzer(tmp_path, ["S1", ACTIONS, "T", ACTIONS, "T"], cache=True)
        first = a.analyze_meeting(str(tone_wav))
        second = a.analyze_meeting(str(tone_wav))
        assert second["summary"]["text"] == "S1" and second["summary"]["cached"] is True
        assert first["summary"]["cached"] is False

    def test_progress_events_in_order_and_a_failing_callback_is_ignored(self, tone_wav, tmp_path):
        events = []
        analyzer(tmp_path)[0].analyze_meeting(str(tone_wav), progress_callback=events.append)
        assert events == ["transcription_done", "summarization_done"]

        def broken(event):
            raise RuntimeError("callback bug")
        assert analyzer(tmp_path)[0].analyze_meeting(str(tone_wav), progress_callback=broken)["summary"]["text"]

    def test_unreadable_model_answer_becomes_a_warning(self, tone_wav, tmp_path):
        a, _ = analyzer(tmp_path, ["S", "I'm ready to help, paste the transcript", "T"])
        result = a.analyze_meeting(str(tone_wav))
        assert result["actions"]["parse_failed"] is True
        assert any("could not be read" in w for w in result["warnings"])

    def test_context_window_filled_becomes_a_warning(self, tone_wav, tmp_path):
        a, _ = analyzer(tmp_path, llm=FakeLLM([ACTIONS] * 5, truncated=True))
        result = a.analyze_meeting(str(tone_wav))
        assert any("OLLAMA_NUM_CTX" in w for w in result["warnings"])

    @needs_ffmpeg
    def test_video_audio_is_extracted_and_the_temp_track_removed(self, tmp_path):
        video = tmp_path / "meeting.mp4"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                        "-f", "lavfi", "-i", "testsrc=size=160x120:rate=5", "-t", "3", "-pix_fmt", "yuv420p", str(video)], check=True)
        a, _ = analyzer(tmp_path)
        a.video_processor.temp_dir = tmp_path / "vtemp"; a.video_processor.temp_dir.mkdir()
        result = a.analyze_meeting(str(video))
        assert result["metadata"]["source_file"] == "meeting.mp4"
        assert list((tmp_path / "vtemp").iterdir()) == []


def full_result(**changes):
    result = {
        "metadata": {"audio_file": "a.mp3", "source_file": "standup.mp3", "analyzed_at": "2026-01-01T00:00:00", "duration_seconds": 61.0},
        "transcript": {"text": "Hello world.", "segments": SEGMENTS, "language": "en", "backend": "whisper-cpp", "cached": False},
        "summary": {"text": "Summary text.", "level": "standard", "word_count": 2, "cached": False},
        "actions": {"action_items": [{"id": 1, "description": "Send report", "assignee": "Bob", "due_date": "Fri", "priority": "high", "category": "x", "status": "pending"}],
                    "decisions": [{"id": 1, "decision": "Ship", "context": "c", "impact": "i"}], "follow_ups": ["Check"], "total_actions": 1},
        "topics": ["Budget"],
        "statistics": {"total_cost_usd": 0.0, "cache_hits": 0, "cache_misses": 2, "processing_time_seconds": 1.5},
        "warnings": [],
    }
    result.update(changes)
    return result


FORMATS = ["markdown", "json", "html", "txt"]


@pytest.fixture
def reporter(tmp_path):
    return analyzer(tmp_path)[0]


class TestReports:
    @pytest.mark.parametrize("fmt", FORMATS)
    def test_every_format_renders(self, reporter, fmt):
        report = reporter.generate_report(full_result(), format=fmt)
        assert "Summary text." in report and "standup.mp3" in report

    @pytest.mark.parametrize("fmt", FORMATS)
    def test_every_format_survives_steps_switched_off(self, reporter, fmt):
        # actions and topics are None - not absent - when those steps are off
        report = reporter.generate_report(full_result(actions=None, topics=None), format=fmt)
        assert "Summary text." in report

    @pytest.mark.parametrize("fmt", FORMATS)
    def test_every_format_survives_an_empty_action_result(self, reporter, fmt):
        empty = {"action_items": [], "decisions": [], "follow_ups": [], "total_actions": 0}
        assert reporter.generate_report(full_result(actions=empty), format=fmt)

    def test_report_is_written_to_disk(self, reporter, tmp_path):
        out = tmp_path / "deep" / "report.md"
        reporter.generate_report(full_result(), output_path=str(out))
        assert "Summary text." in out.read_text(encoding="utf-8")

    def test_json_report_round_trips(self, reporter):
        assert json.loads(reporter.generate_report(full_result(), format="json"))["summary"]["text"] == "Summary text."

    def test_all_levels_are_listed(self, reporter):
        levels = {l: {"text": f"{l} text", "word_count": 1, "cached": False} for l in ("brief", "standard", "detailed")}
        md = reporter.generate_report(full_result(summary_levels=levels), format="markdown")
        assert "## Summary (Brief)" in md and "detailed text" in md

    def test_notes_section_lists_warnings(self, reporter):
        for fmt in ("markdown", "html", "txt"):
            report = reporter.generate_report(full_result(warnings=["Something to know."]), format=fmt)
            assert "Something to know." in report, fmt


class TestHtmlEscaping:
    EVIL = '<script>alert("x")</script>'

    def test_nothing_from_the_recording_or_the_model_is_markup(self, reporter):
        result = full_result(
            transcript={"text": self.EVIL, "segments": [], "language": "en", "backend": "b", "cached": False},
            summary={"text": self.EVIL, "level": "standard"},
            topics=[self.EVIL],
            warnings=[self.EVIL],
            actions={"action_items": [{"id": 1, "description": self.EVIL, "assignee": self.EVIL, "due_date": self.EVIL, "priority": self.EVIL}],
                     "decisions": [{"id": 1, "decision": self.EVIL, "context": self.EVIL}], "follow_ups": [], "total_actions": 1},
        )
        result["metadata"]["source_file"] = self.EVIL
        report = reporter.generate_report(result, format="html")
        assert "<script>" not in report
        assert report.count("&lt;script&gt;") >= 8

    def test_summary_levels_are_escaped_too(self, reporter):
        levels = {"brief": {"text": self.EVIL}, "standard": {"text": "ok"}, "detailed": {"text": "ok"}}
        assert "<script>" not in reporter.generate_report(full_result(summary_levels=levels), format="html")

    def test_line_breaks_survive(self, reporter):
        html = reporter.generate_report(full_result(summary={"text": "line one\nline two", "level": "standard"}), format="html")
        assert "line one<br>line two" in html

    def test_ampersands_and_quotes(self, reporter):
        html = reporter.generate_report(full_result(topics=['R&D "plans"']), format="html")
        assert "R&amp;D &quot;plans&quot;" in html


class TestSpeakersInReports:
    DIAR = {
        "statistics": {"speakers": {"Speaker 1": {"percentage": 70.0, "total_time": 420}, "Speaker 2": {"percentage": 30.0, "total_time": 180}}},
        "key_points": {"Speaker 1": ["Funds the trip"]},
        "speaker_transcript": [{"speaker": "Speaker 1", "text": "Hello."}, {"speaker": "Speaker 2", "text": "Hi."}],
        "approximate": False,
    }

    def test_markdown_lists_speakers_and_labels_the_transcript(self, reporter):
        md = reporter.generate_report(full_result(speaker_diarization=self.DIAR), format="markdown")
        assert "## Speakers" in md and "**Speaker 1**: 70.0% of speaking time (7.0 min)" in md
        assert "  - Funds the trip" in md
        assert "**Speaker 1:** Hello." in md and "**Speaker 2:** Hi." in md
        assert "approximate" not in md

    def test_the_busiest_speaker_comes_first(self, reporter):
        md = reporter.generate_report(full_result(speaker_diarization=self.DIAR), format="markdown")
        assert md.index("**Speaker 1**:") < md.index("**Speaker 2**:")

    def test_approximate_labels_are_flagged(self, reporter):
        md = reporter.generate_report(full_result(speaker_diarization={**self.DIAR, "approximate": True}), format="markdown")
        assert "Speaker labels are approximate" in md
