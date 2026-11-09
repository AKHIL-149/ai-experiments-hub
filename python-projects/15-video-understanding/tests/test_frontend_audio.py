"""
The page and audio files: a music-note icon instead of a film strip, no picture for sound clips, an
upload form that offers audio and a YouTube "audio only" choice (run in node against a stub DOM; the
static page is read as text).
"""

import re
from pathlib import Path

import pytest

from src.utils.input_checks import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS
from tests.test_frontend_auth import run

INDEX = Path(__file__).resolve().parents[1] / "frontend" / "index.html"


def video(**fields):
    base = {"video_id": "v1", "title": "T", "duration_seconds": 5, "processing_status": "completed", "error_message": None,
            "job_id": None, "job_status": None, "queue_position": None, "media_type": "video"}
    return {**base, **fields}


def listing(videos):
    page = run(["app.js"], [["/api/videos", 200, {"videos": videos, "total": len(videos)}]], "await loadVideos();")
    return page["byId"]["videos-list"]["innerHTML"]


class TestIcons:
    def test_audio_gets_a_note_and_video_a_film_strip(self):
        html = listing([video(video_id="a", title="Podcast", media_type="audio"), video(video_id="b", title="Clip")])
        cards = html.split('<div class="video-card"')[1:]
        assert "fa-music" in cards[0] and "fa-film" not in cards[0]
        assert "fa-film" in cards[1] and "fa-music" not in cards[1]

    def test_an_old_response_without_a_type_is_a_video(self):
        v = video()
        del v["media_type"]
        assert "fa-film" in listing([v])

    def test_the_helper(self):
        page = run(["app.js"], [], "document.getElementById('o').textContent = [mediaIconClass({media_type:'audio'}),"
                                   "mediaIconClass({media_type:'video'}), mediaIconClass({})].join(',');")
        assert page["byId"]["o"]["textContent"] == "fa-music,fa-film,fa-film"


class TestClipCards:
    def card(self, **fields):
        clip = {"clip_id": "c1", "title": "Bit", "start_time": 1, "end_time": 5, "status": "completed", "format": "mp4",
                "resolution": "original", "file_size": 1000, **fields}
        page = run(["app.js"], [], "document.getElementById('o').innerHTML = renderClipCard(" + __import__("json").dumps(clip) + ");")
        return page["byId"]["o"]["innerHTML"]

    def test_a_sound_clip_shows_a_note_not_a_picture_that_does_not_exist(self):
        html = self.card(format="mp3")
        assert "fa-music" in html and "<img" not in html and "/thumbnail" not in html

    def test_a_video_clip_still_shows_its_thumbnail(self):
        html = self.card(format="mp4")
        assert "/api/clips/c1/thumbnail" in html and "fa-music" not in html

    def test_a_clip_still_being_made_says_so(self):
        assert "processing..." in self.card(format="mp3", status="processing")
        assert "failed" in self.card(format="mp3", status="failed")


class TestDetails:
    @pytest.mark.parametrize("media,label", [("audio", "Audio"), ("video", "Video")])
    def test_the_details_say_what_it_is(self, media, label):
        page = run(["app.js"], [["/api/videos/v1", 200, video(media_type=media)]], "await showVideoDetails('v1');")
        assert f"<strong>Type:</strong> {label}" in page["byId"]["video-details"]["innerHTML"]


class TestUploadForm:
    html = INDEX.read_text()

    def test_the_file_picker_offers_audio(self):
        accept = re.search(r'id="file-input" accept="([^"]+)"', self.html).group(1)
        assert "audio/*" in accept and "video/*" in accept

    def test_the_page_names_every_format_the_server_accepts(self):
        hint = re.search(r'class="upload-hint">([^<]+)<', self.html).group(1)
        for ext in VIDEO_EXTENSIONS + AUDIO_EXTENSIONS:
            assert ext.lstrip(".") in hint, ext
        for ext in re.findall(r"\b[a-z0-9]{3,4}\b", hint):
            if ext in ("video", "audio"):
                continue
            assert "." + ext in VIDEO_EXTENSIONS + AUDIO_EXTENSIONS, f"{ext} is offered but the server refuses it"

    def test_youtube_can_be_downloaded_as_audio_only(self):
        assert '<option value="audio">Audio only (mp3)</option>' in self.html
