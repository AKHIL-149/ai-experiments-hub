import subprocess

import pytest

from utils.video_processor import VideoProcessor, VideoError
from tests.helpers import needs_ffmpeg


def make_video(path, audio=True):
    cmd = ["ffmpeg", "-loglevel", "error", "-y"]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=2"]
    cmd += ["-f", "lavfi", "-i", "testsrc=size=160x120:rate=5", "-t", "2", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(cmd, check=True)
    return path


@pytest.fixture
def processor(tmp_path):
    return VideoProcessor(temp_dir=str(tmp_path / "temp"))


def test_video_detection(processor):
    for name in ("a.mp4", "A.MOV", "x.mkv", "y.webm"):
        assert processor.is_video_file(name)
    for name in ("a.mp3", "a.wav", "a.txt", "mp4"):
        assert not processor.is_video_file(name)


def test_missing_file_and_unsupported_format(processor, tmp_path):
    with pytest.raises(FileNotFoundError):
        processor.extract_audio(str(tmp_path / "nope.mp4"))
    other = tmp_path / "a.txt"; other.write_text("x")
    with pytest.raises(ValueError, match="Unsupported video format"):
        processor.extract_audio(str(other))


@needs_ffmpeg
class TestWithFfmpeg:
    def test_audio_is_extracted(self, processor, tmp_path):
        out = processor.extract_audio(str(make_video(tmp_path / "talk.mp4")))
        assert out.endswith("talk_audio.mp3")
        assert (tmp_path / "temp" / "talk_audio.mp3").stat().st_size > 0

    def test_a_video_without_sound_says_so(self, processor, tmp_path):
        silent = make_video(tmp_path / "mute.mp4", audio=False)
        with pytest.raises(VideoError) as error:
            processor.extract_audio(str(silent))
        assert str(error.value) == "This video has no audio track, so there is nothing to transcribe."

    def test_a_damaged_video_gives_one_readable_line(self, processor, tmp_path):
        bad = tmp_path / "bad.mp4"
        bad.write_bytes(b"this is not a video" * 100)
        with pytest.raises(VideoError) as error:
            processor.extract_audio(str(bad))
        message = str(error.value)
        assert "\n" not in message and "configuration:" not in message and "ffmpeg version" not in message
        assert not (tmp_path / "temp" / "bad_audio.mp3").exists()

    def test_video_info(self, processor, tmp_path):
        info = processor.get_video_info(str(make_video(tmp_path / "talk.mp4")))
        assert info["has_video"] and info["has_audio"] and info["duration_seconds"] == pytest.approx(2, abs=0.5)
        assert processor.get_video_info(str(make_video(tmp_path / "mute.mp4", audio=False)))["has_audio"] is False

    def test_old_temp_files_are_cleaned_up(self, processor):
        import os, time
        old = processor.temp_dir / "old_audio.mp3"; new = processor.temp_dir / "new_audio.mp3"
        old.write_bytes(b"x"); new.write_bytes(b"x")
        os.utime(old, (time.time() - 3 * 86400,) * 2)
        processor.cleanup_temp_files(max_age_hours=24)
        assert not old.exists() and new.exists()


def test_missing_ffmpeg_is_reported(processor, tmp_path, monkeypatch):
    video = tmp_path / "v.mp4"; video.write_bytes(b"x")
    monkeypatch.setattr(processor, "_check_ffmpeg", lambda: False)
    with pytest.raises(VideoError, match="ffmpeg is not installed"):
        processor.extract_audio(str(video))
