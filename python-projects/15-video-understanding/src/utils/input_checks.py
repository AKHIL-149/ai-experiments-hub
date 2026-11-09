"""
Checks on what users hand to the API: files, URLs and tool error messages.

Kept free of FastAPI and the database so each rule can be tested on its own.
"""

import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 2000

VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov", ".mkv", ".webm")
AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma")
ALLOWED_EXTENSIONS = VIDEO_EXTENSIONS + AUDIO_EXTENSIONS


class InvalidMedia(ValueError):
    """The file is not a video the pipeline can process (the message says why)"""


@dataclass
class MediaInfo:
    duration: float
    width: Optional[int]
    height: Optional[int]
    has_audio: bool
    kind: str = "video"   # "audio" when there is no moving picture: podcasts, music, voice memos, audio-only .mp4

    @property
    def has_video(self) -> bool:
        return self.kind == "video"


def _ffprobe() -> str:
    return shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"


def probe_media(path: str, timeout: float = 30.0) -> MediaInfo:
    """
    Ask ffprobe what the file really is. A name ending in .mp4 proves nothing:
    text files and empty files get that far, and so do audio-only files, which are now accepted as audio
    (kind == "audio"). Cover art in an .mp3 is not a video: ffprobe lists it as a video stream with the
    attached_pic flag, and it is ignored here.

    Raises InvalidMedia with a one-line reason a user can act on.
    """
    try:
        result = subprocess.run(
            [_ffprobe(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise InvalidMedia("The file took too long to read and looks damaged")
    except FileNotFoundError:
        raise RuntimeError("ffprobe is not installed (brew install ffmpeg)")

    try:
        data = json.loads(result.stdout or "{}")
    except ValueError:
        data = {}
    if result.returncode != 0 or not data.get("streams"):
        raise InvalidMedia("The file is not a valid video or audio file (it is empty, damaged or something else)")

    streams = data["streams"]
    video = next(
        (s for s in streams
         if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")),
        None,
    )
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None and audio is None:
        raise InvalidMedia("The file has no video or audio stream")
    main = video or audio

    try:
        duration = float(data.get("format", {}).get("duration") or main.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration <= 0:
        raise InvalidMedia("The file has no length (it is empty or damaged)")

    return MediaInfo(
        duration=duration,
        width=video.get("width") if video else None,
        height=video.get("height") if video else None,
        has_audio=audio is not None,
        kind="video" if video else "audio",
    )


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

_TOOL_PREFIX = re.compile(r"^\s*\[[^\]]*@\s*0x[0-9a-fA-F]+\]\s*")
_PATH = re.compile(r"(?<![\w/])(?:[A-Za-z]:)?(?:\.{0,2}/)?(?:[\w.\-]+/)+([\w.\-%]+\.\w{1,5})")

_KNOWN = (
    ("moov atom not found", "The file is not a valid video (it may be damaged, cut short or not a video)"),
    ("invalid data found when processing input", "The file is not a valid video (it may be damaged or not a video)"),
    ("does not contain any stream", "The file has no video stream"),
    ("no such file or directory", "The video file is missing on the server"),
)


def short_error(message: object, limit: int = 300) -> str:
    """
    Turn a tool failure into one readable line.

    ffmpeg and friends answer with several lines of "[in#0 @ 0x13a...]" noise,
    the server's own file paths and memory addresses; none of that helps the
    person looking at a failed video.
    """
    text = str(message or "").strip()
    lowered = text.lower()
    for needle, friendly in _KNOWN:
        if needle in lowered:
            stage = re.match(r"^([A-Z][A-Za-z ]{2,30} failed):", text)
            return f"{stage.group(1)}: {friendly}" if stage else friendly

    lines = [_TOOL_PREFIX.sub("", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    line = lines[0] if lines else "Processing failed"
    line = _PATH.sub(r"\1", line)
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------

_YOUTUBE_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
    "youtu.be", "www.youtu.be", "youtube-nocookie.com", "www.youtube-nocookie.com",
}


def is_youtube_url(url: str) -> bool:
    """True only when the *host* is YouTube ('evil.example/?youtube.com' is not)"""
    try:
        parsed = urlparse((url or "").strip())
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and (parsed.hostname or "").lower() in _YOUTUBE_HOSTS


def check_public_http_url(url: str) -> str:
    """
    Accept only http(s) URLs that lead to the public internet.

    The server fetches these addresses itself, so 127.0.0.1 (Ollama, databases,
    this API), 192.168.x.x, and 169.254.169.254 (cloud credentials) must be
    refused. Every address the name resolves to has to be public.

    Returns the cleaned URL, raises ValueError with a one-line reason.
    Limits: a public host can still redirect somewhere internal or change its
    DNS answer after this check; run the server without access to internal
    networks if that matters.
    """
    cleaned = (url or "").strip()
    try:
        parsed = urlparse(cleaned)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        raise ValueError("Invalid streaming URL")
    if parsed.scheme not in ("http", "https") or not host:
        raise ValueError("Invalid streaming URL (must be HTTP/HTTPS)")
    if parsed.username or parsed.password:
        raise ValueError("Streaming URLs with a user name or password are not accepted")

    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, port or 443, proto=socket.IPPROTO_TCP)}
    except socket.gaierror:
        raise ValueError("The streaming URL's host could not be found")
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%")[0])
        mapped = getattr(ip, "ipv4_mapped", None)
        if not (mapped or ip).is_global:
            raise ValueError("Streaming URLs must point to the public internet, not to this computer or a private network")
    return cleaned


# ---------------------------------------------------------------------------
# Text fields
# ---------------------------------------------------------------------------

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_title(title: Optional[str], filename: Optional[str]) -> str:
    """
    A title from the user, else from the file name without any directory part
    ('../../tmp/x.mp4' is titled 'x'), without control characters, capped.
    """
    text = _CONTROL.sub("", title or "").strip()
    if not text and filename:
        text = os.path.splitext(os.path.basename(filename.replace("\\", "/")))[0]
        text = _CONTROL.sub("", text).strip()
    return (text or "Untitled video")[:MAX_TITLE_LENGTH]


def clean_description(description: Optional[str]) -> Optional[str]:
    text = _CONTROL.sub("", description or "").strip()
    return text[:MAX_DESCRIPTION_LENGTH] or None


# ---------------------------------------------------------------------------
# Model output
# ---------------------------------------------------------------------------

_PREAMBLE = re.compile(
    r"^\s*(?:here(?:'s| is| are)|sure|certainly|of course|okay|ok|below is|this is)\b[^\n]{0,150}:\s*$",
    re.IGNORECASE,
)


def clean_llm_text(text: Optional[str]) -> str:
    """
    Drop the chatty first line a model adds ('Here is a summary of the video
    in 2-3 paragraphs:'). It is not part of the answer and it was being saved
    and shown as the first line of every summary.
    """
    cleaned = (text or "").strip()
    lines = cleaned.split("\n", 1)
    if len(lines) == 2 and _PREAMBLE.match(lines[0]):
        cleaned = lines[1].strip()
    return cleaned


def fit_segments_to_duration(segments, duration: float):
    """
    Keep transcript segments inside the video. Whisper can invent a segment
    that starts after the audio ends or runs far past it (a lone "to" from
    0 s to 21.5 s on a 5.7 s video), which then shows up on the timeline
    and in search as speech that does not exist.

    segments need .start, .end and .text. Returns a new list.
    """
    if not duration or duration <= 0:
        return list(segments)
    kept = []
    for seg in segments:
        if not (seg.text or "").strip() or seg.start >= duration - 0.05:
            continue
        if seg.end > duration:
            seg.end = duration
        kept.append(seg)
    return kept
