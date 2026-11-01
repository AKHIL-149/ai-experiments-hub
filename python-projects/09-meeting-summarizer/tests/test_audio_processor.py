import pytest
from pydub import AudioSegment

from core.audio_processor import AudioProcessor, AudioError
from tests.helpers import needs_ffmpeg


def minutes(n):
    return AudioSegment.silent(duration=int(n * 60 * 1000), frame_rate=8000)


class TestSplitAudio:
    def test_short_audio_is_one_chunk(self):
        assert len(AudioProcessor().split_audio(minutes(5), 10, 5)) == 1

    def test_long_audio_terminates(self):
        # Used to loop forever: the last chunk reached the end, stepping back by the
        # overlap started another one, and so on.
        chunks = AudioProcessor().split_audio(minutes(25), 10, 5)
        assert len(chunks) == 3

    def test_chunks_cover_all_the_audio_with_the_requested_overlap(self):
        audio = minutes(25)
        chunks = AudioProcessor().split_audio(audio, 10, 5)
        assert len(chunks[0]) == 10 * 60 * 1000
        # each later chunk starts 5 s before the previous one ended
        step = 10 * 60 - 5
        assert len(chunks[1]) == 10 * 60 * 1000
        assert len(chunks[2]) == len(audio) - 2 * step * 1000

    @pytest.mark.parametrize("duration,chunk,overlap", [
        (10.5, 10, 0), (20, 10, 5), (30, 10, 590), (31, 1, 30), (12, 10, 600), (10.0001, 10, 5),
    ])
    def test_always_terminates_and_reaches_the_end(self, duration, chunk, overlap):
        audio = minutes(duration)
        chunks = AudioProcessor().split_audio(audio, chunk, overlap)
        assert 1 <= len(chunks) <= 200
        # the last chunk ends at the end of the audio
        step_ms = chunk * 60 * 1000 - min(overlap * 1000, chunk * 60 * 1000 // 2)
        covered_end = step_ms * (len(chunks) - 1) + len(chunks[-1])
        assert covered_end == len(audio)

    def test_overlap_as_long_as_the_chunk_is_clamped_to_half(self):
        # 3 minutes in 1-minute chunks with a "120 s" overlap: steps of 30 s, not of 1 ms
        chunks = AudioProcessor().split_audio(minutes(3), 1, 120)
        assert len(chunks) == 5


class TestSilence:
    def test_silence_is_silent(self):
        assert AudioProcessor.is_silent(AudioSegment.silent(duration=2000)) is True

    def test_empty_audio_is_silent(self):
        assert AudioProcessor.is_silent(AudioSegment.empty()) is True

    def test_a_tone_is_not_silent(self):
        from pydub.generators import Sine
        assert AudioProcessor.is_silent(Sine(440).to_audio_segment(duration=1000, volume=-10)) is False

    def test_very_quiet_sound_counts_as_silence(self):
        from pydub.generators import Sine
        assert AudioProcessor.is_silent(Sine(440).to_audio_segment(duration=1000, volume=-70)) is True

    def test_threshold_is_adjustable(self):
        from pydub.generators import Sine
        quiet = Sine(440).to_audio_segment(duration=1000, volume=-40)
        assert AudioProcessor.is_silent(quiet) is False
        assert AudioProcessor.is_silent(quiet, threshold_dbfs=-30) is True


@needs_ffmpeg
class TestLoadingAndValidation:
    def test_unreadable_file_gives_one_readable_line(self, tmp_path):
        bad = tmp_path / "fake.mp3"
        bad.write_bytes(b"this is not audio at all")
        with pytest.raises(AudioError) as error:
            AudioProcessor().load_audio(str(bad))
        message = str(error.value)
        assert message == "This file could not be read as MP3 audio. It may be empty, damaged, or not really MP3."
        assert "ffmpeg" not in message and "\n" not in message

    def test_empty_file(self, tmp_path):
        empty = tmp_path / "empty.wav"
        empty.write_bytes(b"")
        result = AudioProcessor().validate_audio(str(empty))
        assert result["valid"] is False
        assert result["errors"] == ["This file could not be read as WAV audio. It may be empty, damaged, or not really WAV."]

    def test_valid_file(self, tone_wav):
        result = AudioProcessor().validate_audio(str(tone_wav))
        assert result["valid"] is True and result["errors"] == []
        assert result["format"] == "wav"

    def test_missing_file(self, tmp_path):
        result = AudioProcessor().validate_audio(str(tmp_path / "nope.mp3"))
        assert result["valid"] is False and "not found" in result["errors"][0].lower()
        with pytest.raises(FileNotFoundError):
            AudioProcessor().load_audio(str(tmp_path / "nope.mp3"))

    def test_unsupported_extension(self, tmp_path):
        other = tmp_path / "notes.txt"
        other.write_text("hello")
        with pytest.raises(ValueError, match="Unsupported audio format"):
            AudioProcessor().load_audio(str(other))
        assert AudioProcessor().validate_audio(str(other))["valid"] is False

    def test_size_limit(self, tone_wav):
        result = AudioProcessor(max_size_mb=0).validate_audio(str(tone_wav))
        assert result["valid"] is False
        assert "exceeds maximum" in result["errors"][0]

    def test_very_short_audio_warns(self, tmp_path):
        short = tmp_path / "short.wav"
        AudioSegment.silent(duration=300).export(short, format="wav")
        assert AudioProcessor().validate_audio(str(short))["warnings"]

    def test_metadata(self, tone_wav):
        meta = AudioProcessor().get_metadata(str(tone_wav))
        assert meta["duration_seconds"] == 3.0
        assert meta["format"] == "wav" and meta["channels"] >= 1

    def test_metadata_of_a_bad_file_reports_an_error_instead_of_raising(self, tmp_path):
        bad = tmp_path / "bad.mp3"
        bad.write_bytes(b"x")
        assert AudioProcessor().get_metadata(str(bad))["duration_seconds"] == 0

    def test_file_hash_changes_with_content(self, tmp_path):
        a, b = tmp_path / "a.bin", tmp_path / "b.bin"
        a.write_bytes(b"one"); b.write_bytes(b"two")
        ap = AudioProcessor()
        assert ap.get_file_hash(str(a)) != ap.get_file_hash(str(b))
        assert ap.get_file_hash(str(a)) == ap.get_file_hash(str(a))

    def test_export_creates_parent_directories(self, tmp_path):
        out = tmp_path / "deep" / "er" / "x.wav"
        AudioProcessor().export_audio(AudioSegment.silent(duration=100), str(out), "wav")
        assert out.exists()
