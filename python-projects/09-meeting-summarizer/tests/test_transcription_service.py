import json
import os
import stat
import sys
from pathlib import Path

import pytest
from pydub import AudioSegment

from core.audio_processor import AudioProcessor
from core.cache_manager import CacheManager
from core.transcription_service import (
    TranscriptionService, NoSpeechError, clean_transcript_text, MIN_TRANSCRIPT_WORDS,
)
from tests.helpers import needs_ffmpeg

# A stand-in for whisper-cli. It records its arguments, then writes JSON in whisper.cpp's format
# ("transcription": [{"offsets": {"from": ms, "to": ms}, "text": ...}]) next to --output-file.
FAKE_WHISPER = '''#!{python}
import json, os, sys
args = sys.argv[1:]
log = os.environ["FAKE_WHISPER_LOG"]
with open(log, "a") as f:
    f.write(json.dumps(args) + "\\n")
if os.environ.get("FAKE_WHISPER_FAIL"):
    sys.stderr.write("model exploded")
    sys.exit(3)
if os.environ.get("FAKE_WHISPER_NO_OUTPUT"):
    sys.exit(0)
prefix = args[args.index("--output-file") + 1]
segments = json.loads(os.environ["FAKE_WHISPER_SEGMENTS"])
doc = {{
    "result": {{"language": os.environ.get("FAKE_WHISPER_LANG", "en")}},
    "transcription": [
        {{"offsets": {{"from": int(a * 1000), "to": int(b * 1000)}}, "text": text}} for a, b, text in segments
    ],
}}
with open(prefix + ".json", "w") as f:
    json.dump(doc, f)
'''

SPEECH = [
    [0.0, 2.5, " Welcome everyone to the meeting."],
    [2.5, 6.0, " [BLANK_AUDIO]"],
    [6.0, 9.0, " Let us review the budget (coughs) first."],
    [9.0, 11.0, " >> Sounds good to me."],
]


@pytest.fixture
def whisper(tmp_path, monkeypatch):
    script = tmp_path / "whisper-cli"
    script.write_text(FAKE_WHISPER.format(python=sys.executable))
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    model = tmp_path / "ggml-base.en.bin"
    model.write_bytes(b"model")
    log = tmp_path / "calls.log"
    monkeypatch.setenv("FAKE_WHISPER_LOG", str(log))
    monkeypatch.setenv("FAKE_WHISPER_SEGMENTS", json.dumps(SPEECH))
    for name in ("FAKE_WHISPER_FAIL", "FAKE_WHISPER_NO_OUTPUT", "FAKE_WHISPER_LANG"):
        monkeypatch.delenv(name, raising=False)

    class Setup:
        path, model_path, calls_file = script, model, log
        def calls(self):
            return [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
    return Setup()


def service(whisper, tmp_path, cache=False, model=None):
    return TranscriptionService(
        backend="whisper-cpp",
        cache_manager=CacheManager(cache_dir=str(tmp_path / "cache")) if cache else None,
        whisper_cpp_path=str(whisper.path),
        whisper_model_path=str(model or whisper.model_path),
        temp_dir=str(tmp_path / "temp"),
    )


def work_dirs(tmp_path):
    temp = tmp_path / "temp"
    return list(temp.iterdir()) if temp.exists() else []


class TestCleanTranscriptText:
    @pytest.mark.parametrize("raw,expected", [
        ("[BLANK_AUDIO]", ""),
        ("[ Foreign Language ]", ""),
        ("[ Inaudible ]", ""),
        ("(airplane engine roaring)", ""),
        ("*music*", ""),
        ("♪ la la ♪", "la la"),
        ("Hello [pause] there (coughs) friend", "Hello there friend"),
        (">> All right, thank you.", ">> All right, thank you."),
        ("", ""),
        (None, ""),
    ])
    def test_cleaning(self, raw, expected):
        assert clean_transcript_text(raw) == expected


class TestWhisperCpp:
    def test_segments_with_times_and_cleaned_text(self, whisper, tone_wav, tmp_path):
        result = service(whisper, tmp_path).transcribe(str(tone_wav))
        assert result["segments"] == [
            {"start": 0.0, "end": 2.5, "text": "Welcome everyone to the meeting."},
            {"start": 6.0, "end": 9.0, "text": "Let us review the budget first."},
            {"start": 9.0, "end": 11.0, "text": ">> Sounds good to me."},
        ]
        assert result["text"] == "Welcome everyone to the meeting.\nLet us review the budget first.\n>> Sounds good to me."
        assert result["backend"] == "whisper-cpp" and result["cached"] is False
        assert result["language"] == "en"
        assert result["duration"] == 3.0

    def test_command_line(self, whisper, tone_wav, tmp_path):
        service(whisper, tmp_path).transcribe(str(tone_wav))
        (args,) = whisper.calls()
        assert args[args.index("-m") + 1] == str(whisper.model_path)
        assert "--output-json" in args and "--no-prints" in args
        assert args[args.index("--max-len") + 1] == "100" and "--split-on-word" in args
        assert "-l" not in args          # English-only model: no language flag needed

    def test_multilingual_model_detects_language(self, whisper, tone_wav, tmp_path):
        model = tmp_path / "ggml-base.bin"
        model.write_bytes(b"m")
        service(whisper, tmp_path, model=model).transcribe(str(tone_wav))
        (args,) = whisper.calls()
        assert args[args.index("-l") + 1] == "auto"

    def test_explicit_language_is_passed(self, whisper, tone_wav, tmp_path):
        model = tmp_path / "ggml-base.bin"
        model.write_bytes(b"m")
        service(whisper, tmp_path, model=model).transcribe(str(tone_wav), language="es")
        (args,) = whisper.calls()
        assert args[args.index("-l") + 1] == "es"

    def test_input_audio_is_converted_to_16khz_mono(self, whisper, tone_wav, tmp_path, monkeypatch):
        seen = {}
        original = AudioProcessor.export_audio
        def spy(self, audio, path, format="mp3"):
            seen.update(rate=audio.frame_rate, channels=audio.channels)
            return original(self, audio, path, format)
        monkeypatch.setattr(AudioProcessor, "export_audio", spy)
        service(whisper, tmp_path).transcribe(str(tone_wav))
        assert seen == {"rate": 16000, "channels": 1}

    def test_working_files_are_removed(self, whisper, tone_wav, tmp_path):
        service(whisper, tmp_path).transcribe(str(tone_wav))
        assert work_dirs(tmp_path) == []

    def test_working_files_are_removed_after_a_failure(self, whisper, tone_wav, tmp_path, monkeypatch):
        monkeypatch.setenv("FAKE_WHISPER_FAIL", "1")
        with pytest.raises(RuntimeError, match=r"Whisper.cpp failed \(exit code 3\)"):
            service(whisper, tmp_path).transcribe(str(tone_wav))
        assert work_dirs(tmp_path) == []

    def test_failure_message_does_not_include_the_command_or_paths(self, whisper, tone_wav, tmp_path, monkeypatch):
        monkeypatch.setenv("FAKE_WHISPER_FAIL", "1")
        with pytest.raises(RuntimeError) as error:
            service(whisper, tmp_path).transcribe(str(tone_wav))
        assert str(tmp_path) not in str(error.value)

    def test_missing_output_file_is_an_error(self, whisper, tone_wav, tmp_path, monkeypatch):
        monkeypatch.setenv("FAKE_WHISPER_NO_OUTPUT", "1")
        with pytest.raises(RuntimeError, match="no output"):
            service(whisper, tmp_path).transcribe(str(tone_wav))

    @pytest.mark.parametrize("seconds,expected", [(30, 600), (400, 600), (4000, 6000), (7200, 10800)])
    def test_the_timeout_grows_with_the_recording(self, whisper, tmp_path, monkeypatch, seconds, expected):
        import subprocess as sp
        seen = {}
        def fake_run(cmd, **kwargs):
            seen["timeout"] = kwargs["timeout"]
            raise sp.TimeoutExpired(cmd, kwargs["timeout"])
        monkeypatch.setattr("core.transcription_service.subprocess.run", fake_run)
        with pytest.raises(RuntimeError, match="timed out"):
            service(whisper, tmp_path)._transcribe_whisper_cpp(AudioSegment.silent(duration=1000), seconds, None)
        assert seen["timeout"] == expected

    def test_two_jobs_never_share_files(self, whisper, tone_wav, tmp_path):
        svc = service(whisper, tmp_path)
        svc.transcribe(str(tone_wav)); svc.transcribe(str(tone_wav))
        prefixes = {a[a.index("--output-file") + 1] for a in whisper.calls()}
        assert len(prefixes) == 2

    def test_missing_binary_or_model_is_reported_at_start(self, whisper, tmp_path):
        with pytest.raises(FileNotFoundError, match="binary not found"):
            TranscriptionService("whisper-cpp", whisper_cpp_path="/nope", whisper_model_path=str(whisper.model_path))
        with pytest.raises(FileNotFoundError, match="model file not found"):
            TranscriptionService("whisper-cpp", whisper_cpp_path=str(whisper.path), whisper_model_path="/nope")

    def test_unknown_backend_and_missing_key(self):
        with pytest.raises(ValueError, match="Unsupported backend"):
            TranscriptionService("carrier-pigeon")
        with pytest.raises(ValueError, match="API key"):
            TranscriptionService("openai")


class TestNoSpeech:
    def test_silence_never_reaches_whisper(self, whisper, silent_wav, tmp_path):
        with pytest.raises(NoSpeechError, match="No speech was detected"):
            service(whisper, tmp_path).transcribe(str(silent_wav))
        assert whisper.calls() == []

    @pytest.mark.parametrize("hallucination", [
        [[0, 3, " you"]],
        [[0, 3, " Thank you."]],
        [[0, 3, " (airplane engine roaring)"]],
        [[0, 3, " [BLANK_AUDIO]"], [3, 6, " [ Inaudible ]"]],
        [],
    ])
    def test_a_transcript_that_is_only_noise_is_rejected(self, whisper, tone_wav, tmp_path, monkeypatch, hallucination):
        monkeypatch.setenv("FAKE_WHISPER_SEGMENTS", json.dumps(hallucination))
        with pytest.raises(NoSpeechError):
            service(whisper, tmp_path).transcribe(str(tone_wav))

    def test_the_minimum_is_a_few_words(self, whisper, tone_wav, tmp_path, monkeypatch):
        monkeypatch.setenv("FAKE_WHISPER_SEGMENTS", json.dumps([[0, 3, " " + " ".join(["word"] * MIN_TRANSCRIPT_WORDS)]]))
        assert service(whisper, tmp_path).transcribe(str(tone_wav))["text"]

    def test_noise_is_not_cached(self, whisper, tone_wav, tmp_path, monkeypatch):
        monkeypatch.setenv("FAKE_WHISPER_SEGMENTS", json.dumps([[0, 3, " you"]]))
        svc = service(whisper, tmp_path, cache=True)
        with pytest.raises(NoSpeechError):
            svc.transcribe(str(tone_wav))
        monkeypatch.setenv("FAKE_WHISPER_SEGMENTS", json.dumps(SPEECH))
        assert svc.transcribe(str(tone_wav))["cached"] is False


class TestLanguage:
    @pytest.mark.parametrize("bad", ["--help", "english", "e", "EN", "en;rm", "en us", "../x"])
    def test_invalid_codes_are_refused(self, bad):
        with pytest.raises(ValueError, match="Invalid language"):
            TranscriptionService.validate_language(bad)

    @pytest.mark.parametrize("good,expected", [("en", "en"), ("es", "es"), ("auto", "auto"), ("yue", "yue"), (None, None), ("", None)])
    def test_valid_codes(self, good, expected):
        assert TranscriptionService.validate_language(good) == expected

    def test_an_english_only_model_refuses_other_languages(self, whisper, tone_wav, tmp_path):
        with pytest.raises(ValueError, match="only understands English"):
            service(whisper, tmp_path).transcribe(str(tone_wav), language="es")
        assert whisper.calls() == []

    def test_an_english_only_model_accepts_english_and_auto(self, whisper, tone_wav, tmp_path):
        service(whisper, tmp_path).transcribe(str(tone_wav), language="en")
        service(whisper, tmp_path).transcribe(str(tone_wav), language="auto")


class TestCaching:
    def test_second_run_is_served_from_the_cache(self, whisper, tone_wav, tmp_path):
        svc = service(whisper, tmp_path, cache=True)
        first = svc.transcribe(str(tone_wav))
        second = svc.transcribe(str(tone_wav))
        assert first["cached"] is False and second["cached"] is True
        assert second["segments"] == first["segments"]
        assert len(whisper.calls()) == 1

    def test_other_language_or_model_is_not_answered_from_the_cache(self, whisper, tone_wav, tmp_path):
        multilingual = tmp_path / "ggml-base.bin"
        multilingual.write_bytes(b"m")
        service(whisper, tmp_path, cache=True).transcribe(str(tone_wav))
        # same cache directory, different model: a fresh transcription
        other = service(whisper, tmp_path, cache=True, model=multilingual)
        assert other.transcribe(str(tone_wav))["cached"] is False
        assert other.transcribe(str(tone_wav), language="es")["cached"] is False
        assert other.transcribe(str(tone_wav), language="es")["cached"] is True
        assert len(whisper.calls()) == 3

    def test_use_cache_false_skips_it(self, whisper, tone_wav, tmp_path):
        svc = service(whisper, tmp_path, cache=True)
        svc.transcribe(str(tone_wav)); svc.transcribe(str(tone_wav), use_cache=False)
        assert len(whisper.calls()) == 2


class TestMergingChunks:
    def make(self, tmp_path, whisper):
        return service(whisper, tmp_path)

    def test_segments_are_shifted_and_overlap_duplicates_dropped(self, whisper, tmp_path):
        svc = self.make(tmp_path, whisper)
        chunk0 = {"language": "en", "segments": [{"start": 0, "end": 5, "text": "one"}, {"start": 590, "end": 600, "text": "end of first"}]}
        # the next chunk starts 5 s before the first ended: its first segment repeats "end of first"
        chunk1 = {"language": "en", "segments": [{"start": 0, "end": 4, "text": "end of first"}, {"start": 6, "end": 12, "text": "two"}]}
        merged = svc._merge_transcripts([chunk0, chunk1], 10, 5)
        assert [s["text"] for s in merged["segments"]] == ["one", "end of first", "two"]
        assert merged["segments"][2]["start"] == 6 + 595 and merged["segments"][2]["end"] == 12 + 595
        assert merged["text"] == "one\nend of first\ntwo"

    def test_text_only_chunks_skip_a_few_words_of_overlap(self, whisper, tmp_path):
        svc = self.make(tmp_path, whisper)
        merged = svc._merge_transcripts([{"text": "alpha beta gamma"}, {"text": " ".join(f"w{i}" for i in range(120))}], 1, 5)
        assert merged["text"].startswith("alpha beta gamma w")
        assert "w0 " not in merged["text"]

    def test_nothing_to_merge(self, whisper, tmp_path):
        assert self.make(tmp_path, whisper)._merge_transcripts([], 10, 5)["text"] == ""


@needs_ffmpeg
class TestChunkedTranscription:
    def test_long_audio_is_cut_transcribed_and_merged(self, whisper, tmp_path, monkeypatch):
        from pydub.generators import Sine
        audio = Sine(440).to_audio_segment(duration=150_000, volume=-6)          # 2.5 minutes
        path = tmp_path / "long.wav"
        audio.export(path, format="wav")
        monkeypatch.setenv("FAKE_WHISPER_SEGMENTS", json.dumps([[10, 20, " words spoken ten seconds into each chunk"]]))
        result = service(whisper, tmp_path).transcribe_chunked(str(path), chunk_duration_minutes=1, overlap_seconds=5)
        assert result["chunks_processed"] == 3
        assert len(whisper.calls()) == 3
        starts = [s["start"] for s in result["segments"]]
        assert starts == [10.0, 65.0, 120.0]      # 10 s into each chunk, chunks begin every 55 s (60 s minus 5 s overlap)
        assert work_dirs(tmp_path) == []

    def test_a_silent_chunk_is_skipped_not_fatal(self, whisper, tmp_path, monkeypatch):
        from pydub.generators import Sine
        audio = Sine(440).to_audio_segment(duration=60_000, volume=-6) + AudioSegment.silent(duration=60_000)
        path = tmp_path / "gap.wav"
        audio.export(path, format="wav")
        result = service(whisper, tmp_path).transcribe_chunked(str(path), chunk_duration_minutes=1, overlap_seconds=0)
        assert result["chunks_processed"] == 2
        assert len(whisper.calls()) == 1          # only the chunk with sound was transcribed

    def test_all_silent_is_no_speech(self, whisper, silent_wav, tmp_path):
        long_silence = tmp_path / "s.wav"
        AudioSegment.silent(duration=130_000).export(long_silence, format="wav")
        with pytest.raises(NoSpeechError):
            service(whisper, tmp_path).transcribe_chunked(str(long_silence), chunk_duration_minutes=1, overlap_seconds=0)

    def test_short_audio_is_transcribed_directly(self, whisper, tone_wav, tmp_path):
        result = service(whisper, tmp_path).transcribe_chunked(str(tone_wav), chunk_duration_minutes=10)
        assert "chunks_processed" not in result and len(whisper.calls()) == 1


class TestOpenAIBackend:
    def make(self, tmp_path, monkeypatch, **kw):
        monkeypatch.setattr("core.transcription_service.OpenAI", lambda api_key: object())
        return TranscriptionService("openai", api_key="sk-test", cache_manager=None, temp_dir=str(tmp_path / "temp"), **kw)

    def test_small_file_is_one_api_call(self, tone_wav, tmp_path, monkeypatch):
        svc = self.make(tmp_path, monkeypatch)
        calls = []
        monkeypatch.setattr(svc, "_transcribe_openai", lambda path, language: calls.append(path) or {"text": "hello there everyone", "language": "en"})
        assert svc.transcribe(str(tone_wav))["text"] == "hello there everyone"
        assert calls == [str(tone_wav)]

    def test_file_over_the_upload_limit_is_chunked(self, tone_wav, tmp_path, monkeypatch):
        svc = self.make(tmp_path, monkeypatch)
        monkeypatch.setattr("core.transcription_service.OPENAI_MAX_UPLOAD_BYTES", 10)   # the 3 s tone is bigger than this
        sizes = []
        def fake_api(path, language):
            sizes.append(Path(path).stat().st_size)
            return {"text": "part of the meeting here", "language": "en", "segments": [{"start": 0, "end": 1, "text": "part of the meeting here"}]}
        monkeypatch.setattr(svc, "_transcribe_openai", fake_api)
        monkeypatch.setattr(svc.audio_processor, "split_audio", lambda audio, minutes, overlap: [audio[:1500], audio[1500:]])
        result = svc.transcribe(str(tone_wav))
        assert len(sizes) == 2                              # two API calls instead of one oversized upload
        assert all(size < 100_000 for size in sizes)
        assert work_dirs(tmp_path) == []
