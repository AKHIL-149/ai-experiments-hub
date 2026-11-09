"""
Checks on what users hand to the API: files, URLs, titles, tool errors and
model text (src/utils/input_checks.py).

Found by uploading real files: a text file, an empty file and 3 KB of random
bytes named .mp4 were all accepted as videos, a stream URL could point at this
computer, and a failed video showed a multi-line ffmpeg dump.
"""

import shutil
import subprocess
from types import SimpleNamespace as NS

import pytest

from src.utils.input_checks import (
    InvalidMedia, probe_media, short_error, is_youtube_url, check_public_http_url,
    clean_title, clean_description, clean_llm_text, fit_segments_to_duration,
    MAX_TITLE_LENGTH, MAX_DESCRIPTION_LENGTH,
)

FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg") and not shutil.which(FFMPEG), reason="ffmpeg not installed")


def make_media(path, *args):
    subprocess.run([FFMPEG, "-v", "error", "-y", *args, str(path)], check=True, capture_output=True)
    return str(path)


# ---------------------------------------------------------------------------
# probe_media
# ---------------------------------------------------------------------------

@needs_ffmpeg
class TestProbeMedia:
    def test_real_video(self, tmp_path):
        path = make_media(tmp_path / "v.mp4", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=2", "-f", "lavfi",
                          "-i", "sine=d=2", "-shortest", "-pix_fmt", "yuv420p")
        info = probe_media(path)
        assert 1.5 < info.duration < 2.5
        assert (info.width, info.height) == (320, 240)
        assert info.has_audio is True

    def test_silent_video_is_fine(self, tmp_path):
        path = make_media(tmp_path / "v.mp4", "-f", "lavfi", "-i", "color=c=red:s=160x120:d=1", "-pix_fmt", "yuv420p")
        assert probe_media(path).has_audio is False

    def test_audio_only_mp4_is_refused(self, tmp_path):
        path = make_media(tmp_path / "a.mp4", "-f", "lavfi", "-i", "sine=d=2", "-vn")
        with pytest.raises(InvalidMedia, match="no video stream"):
            probe_media(path)

    @pytest.mark.parametrize("name,content", [
        ("text.mp4", b"this is not a video"),
        ("empty.mp4", b""),
        ("random.mp4", bytes(range(256)) * 12),
    ])
    def test_files_that_only_have_the_extension_are_refused(self, tmp_path, name, content):
        path = tmp_path / name
        path.write_bytes(content)
        with pytest.raises(InvalidMedia, match="not a valid video"):
            probe_media(str(path))

    def test_missing_file_is_refused(self, tmp_path):
        with pytest.raises(InvalidMedia):
            probe_media(str(tmp_path / "nope.mp4"))

    def test_messages_are_one_line_without_paths(self, tmp_path):
        path = tmp_path / "x.mp4"
        path.write_bytes(b"junk")
        with pytest.raises(InvalidMedia) as info:
            probe_media(str(path))
        assert "\n" not in str(info.value) and str(tmp_path) not in str(info.value)


# ---------------------------------------------------------------------------
# short_error
# ---------------------------------------------------------------------------

class TestShortError:
    FFMPEG_DUMP = (
        "Frame extraction failed: [in#0 @ 0x132104300] moov atom not found\n"
        "[in#0 @ 0x132104080] Error opening input: Invalid data found when processing input\n"
        "Error opening input file uploads/videos/ca4d84f3.mp4.\n"
        "Error opening input files: Invalid data found when processing input"
    )

    def test_ffmpeg_dump_becomes_one_readable_line(self):
        out = short_error(self.FFMPEG_DUMP)
        assert out == "Frame extraction failed: The file is not a valid video (it may be damaged, cut short or not a video)"
        assert "0x" not in out and "uploads/" not in out and "\n" not in out

    def test_no_stream_error(self):
        assert "no video stream" in short_error("[out#0/image2 @ 0x140f04ac0] Output file does not contain any stream")

    def test_unknown_error_keeps_first_line_without_noise_or_paths(self):
        out = short_error("[x#0 @ 0xdeadbeef] Something odd at /Users/me/secret/dir/clip.mp4\nsecond line")
        assert out == "Something odd at clip.mp4"

    def test_long_message_is_cut(self):
        out = short_error("x" * 1000, limit=50)
        assert len(out) <= 50 and out.endswith("…")

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_empty_gets_a_default(self, value):
        assert short_error(value) == "Processing failed"

    def test_exceptions_are_accepted(self):
        assert short_error(RuntimeError("plain failure")) == "plain failure"


# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------

class TestYouTubeUrl:
    @pytest.mark.parametrize("url", [
        "https://www.youtube.com/watch?v=abc", "http://youtube.com/watch?v=abc", "https://youtu.be/abc",
        "https://m.youtube.com/watch?v=abc", "https://music.youtube.com/watch?v=abc", " https://youtu.be/abc ",
    ])
    def test_real_youtube_hosts(self, url):
        assert is_youtube_url(url)

    @pytest.mark.parametrize("url", [
        "https://evil.example/?youtube.com", "https://evil.example/youtu.be/abc",
        "https://youtube.com.evil.example/watch?v=abc", "https://notyoutube.com/watch",
        "http://localhost:8000/x?u=youtu.be", "file:///etc/youtube.com", "ftp://youtube.com/x",
        "javascript:alert('youtube.com')", "youtube.com", "", "not a url",
    ])
    def test_everything_else(self, url):
        assert not is_youtube_url(url)


class TestPublicHttpUrl:
    @pytest.mark.parametrize("url", [
        "http://127.0.0.1:11434/api/tags", "http://localhost/x", "http://[::1]:8000/health",
        "http://169.254.169.254/latest/meta-data/", "http://10.0.0.5/v.mp4", "http://192.168.1.1/v.mp4",
        "http://172.16.0.1/v.mp4", "http://0.0.0.0/", "http://2130706433/", "http://0x7f000001/",
        "http://[::ffff:127.0.0.1]/", "http://100.64.0.1/",
    ])
    def test_internal_addresses_are_refused(self, url):
        with pytest.raises(ValueError, match="public internet"):
            check_public_http_url(url)

    @pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/x", "rtsp://1.2.3.4/x", "gopher://x", "", "   ", "example.com"])
    def test_other_schemes_are_refused(self, url):
        with pytest.raises(ValueError, match="HTTP/HTTPS"):
            check_public_http_url(url)

    def test_credentials_in_the_url_are_refused(self):
        with pytest.raises(ValueError, match="user name"):
            check_public_http_url("http://user:pw@8.8.8.8/v.mp4")

    def test_public_address_passes_and_is_returned_trimmed(self):
        assert check_public_http_url("  https://8.8.8.8/video.m3u8 ") == "https://8.8.8.8/video.m3u8"

    def test_a_name_is_checked_by_what_it_resolves_to(self, monkeypatch):
        import socket
        monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 80))])
        with pytest.raises(ValueError, match="public internet"):
            check_public_http_url("http://innocent.example/v.mp4")

    def test_every_resolved_address_must_be_public(self, monkeypatch):
        import socket
        monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [
            (2, 1, 6, "", ("8.8.8.8", 80)), (2, 1, 6, "", ("10.0.0.1", 80))])
        with pytest.raises(ValueError, match="public internet"):
            check_public_http_url("http://mixed.example/v.mp4")

    def test_unknown_host(self, monkeypatch):
        import socket

        def boom(*a, **k):
            raise socket.gaierror(8, "nodename nor servname provided")
        monkeypatch.setattr(socket, "getaddrinfo", boom)
        with pytest.raises(ValueError, match="could not be found"):
            check_public_http_url("http://no-such-host.invalid/v.mp4")


# ---------------------------------------------------------------------------
# Text fields
# ---------------------------------------------------------------------------

class TestTitles:
    def test_title_wins(self):
        assert clean_title("  My video  ", "file.mp4") == "My video"

    @pytest.mark.parametrize("filename,expected", [
        ("holiday.mp4", "holiday"), ("../../../tmp/pwn.mp4", "pwn"), ("C:\\Users\\me\\clip.mov", "clip"),
        ("a/b/c.final.webm", "c.final"),
    ])
    def test_file_name_without_directories(self, filename, expected):
        assert clean_title(None, filename) == expected
        assert clean_title("   ", filename) == expected

    def test_control_characters_are_removed(self):
        assert clean_title("a\x00b\x07c\nd", None) == "abc\nd"

    def test_length_is_capped(self):
        assert len(clean_title("x" * 5000, None)) == MAX_TITLE_LENGTH

    def test_nothing_at_all(self):
        assert clean_title(None, None) == "Untitled video"

    def test_html_is_kept_as_text_not_stripped(self):
        # escaping is the page's job (see test_frontend_escaping.py); the API must not mangle it
        assert clean_title("<b>x</b>", None) == "<b>x</b>"

    def test_description(self):
        assert clean_description(None) is None
        assert clean_description("   ") is None
        assert len(clean_description("y" * 9000)) == MAX_DESCRIPTION_LENGTH


# ---------------------------------------------------------------------------
# Model text
# ---------------------------------------------------------------------------

class TestCleanLlmText:
    def test_preamble_line_is_dropped(self):
        assert clean_llm_text("Here is a summary of the video in 2-3 paragraphs:\n\nThe video begins.") == "The video begins."

    @pytest.mark.parametrize("opener", ["Here's a summary:", "Sure! Here is the summary:", "Certainly, below is what you asked for:", "Okay, here are the key points:"])
    def test_common_openers(self, opener):
        assert clean_llm_text(f"{opener}\nBody text") == "Body text"

    @pytest.mark.parametrize("text", [
        "The video begins:\nand then", "Here is why it matters.\nBecause", "Summary: it works", "Just one line",
        "Here is the plan", "",
    ])
    def test_real_content_is_untouched(self, text):
        assert clean_llm_text(text) == text.strip()

    def test_only_the_first_line_is_considered(self):
        text = "Intro.\nHere is a list:\nitem"
        assert clean_llm_text(text) == text

    def test_none(self):
        assert clean_llm_text(None) == ""


# ---------------------------------------------------------------------------
# Transcript segments
# ---------------------------------------------------------------------------

class TestFitSegments:
    def segs(self):
        return [NS(start=0, end=21.54, text="to"), NS(start=5.9, end=7, text="late"),
                NS(start=1, end=2, text="  "), NS(start=3, end=5.7, text="ok")]

    def test_segments_are_kept_inside_the_video(self):
        out = fit_segments_to_duration(self.segs(), 5.7)
        assert [(s.start, s.end, s.text) for s in out] == [(0, 5.7, "to"), (3, 5.7, "ok")]

    def test_unknown_duration_changes_nothing(self):
        assert len(fit_segments_to_duration(self.segs(), 0)) == 4
        assert len(fit_segments_to_duration(self.segs(), None)) == 4

    def test_segment_starting_at_the_very_end_is_dropped(self):
        assert fit_segments_to_duration([NS(start=10.0, end=10.4, text="x")], 10.0) == []
