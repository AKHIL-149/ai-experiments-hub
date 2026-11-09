"""
Sections of an audio file.

A video is cut into scenes by looking at the picture. Audio has no picture, so its "scenes" are sections
found in the speech: a new section starts at a pause once the current one is long enough, and a section never
grows past a maximum, so a speaker who does not pause still gets sections. Everything that works from scenes
(summary, chapters, highlights, the timeline) then works on audio unchanged.

Kept free of the database and ffmpeg so the rules can be tested on their own.
"""

from typing import List, Sequence, Tuple

from src.services.scene_detection.base import Scene, SceneType, TransitionType

MIN_SECTION = 20.0     # seconds: a pause does not start a new section before this
MAX_SECTION = 90.0     # seconds: a section is cut at a segment boundary before it passes this
PAUSE = 1.5            # seconds of silence between two segments that counts as a pause
SILENT_WINDOW = 60.0   # seconds: audio with no speech (music, silence) is cut into windows of about this length


def build_sections(
    segments: Sequence,
    duration: float,
    min_len: float = MIN_SECTION,
    max_len: float = MAX_SECTION,
    pause: float = PAUSE,
    silent_window: float = SILENT_WINDOW,
) -> List[Tuple[float, float]]:
    """
    Cut 0..duration into contiguous (start, end) sections from transcript segments (objects with .start,
    .end and .text). Boundaries are placed in the middle of a pause, so no sentence is split. The sections
    always cover the whole file, each has a positive length, and the last one is not a tiny leftover.
    """
    if not duration or duration <= 0:
        return []

    spoken = sorted(
        (s for s in segments if (getattr(s, "text", "") or "").strip() and s.end > s.start),
        key=lambda s: s.start,
    )
    if not spoken:
        count = max(1, round(duration / silent_window))
        return [(duration * i / count, duration * (i + 1) / count) for i in range(count)]

    cuts: List[float] = []
    section_start = 0.0
    for current, following in zip(spoken, spoken[1:]):
        gap = following.start - current.end
        cut = (current.end + following.start) / 2 if gap > 0 else current.end
        length = cut - section_start
        paused = gap >= pause and length >= min_len
        too_long = following.end - section_start > max_len and length >= min_len / 2
        if (paused or too_long) and 0 < cut < duration and cut > section_start:
            cuts.append(cut)
            section_start = cut

    bounds = [0.0] + cuts + [duration]
    if len(bounds) > 2 and bounds[-1] - bounds[-2] < min_len / 2:
        del bounds[-2]   # a tiny leftover joins the section before it
    return [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1) if bounds[i + 1] > bounds[i]]


def sections_to_scenes(sections: Sequence[Tuple[float, float]]) -> List[Scene]:
    """Scene objects (1-based ids) for sections, so the code that handles scenes can handle audio"""
    return [
        Scene(
            scene_id=i + 1, start_time=start, end_time=end, duration=end - start,
            start_frame=0, end_frame=0, frame_count=0,
            scene_type=SceneType.UNKNOWN, transition_type=TransitionType.CUT,
            metadata={"kind": "audio_section"},
        )
        for i, (start, end) in enumerate(sections)
    ]
