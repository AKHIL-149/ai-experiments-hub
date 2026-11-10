"""
What kind of scene is it: still, a person talking, movement, or high-energy action.

Until now every scene was stored as "unknown". The rules below use three things the pipeline already knows about a
scene: how much the picture moves, how much of it is speech, and whether a face is in it. The motion numbers are
the mean frame-to-frame change measured by the scene detector at ten frames a second; on real videos that is
about 0.000 for slides and screen recordings, 0.003-0.017 for a person talking to a camera, 0.02-0.05 for a
fast-cut music video.

Pure functions, so the rules can be tested without a video.
"""

from typing import Optional, Sequence

from src.services.scene_detection.base import SceneType

STILL = 0.003        # below this the picture does not move: slides, a screen, a still photo
LIVELY = 0.008       # above this a person or things in the picture are really moving
FAST = 0.02          # above this the picture itself is changing fast (camera or subject)
ENERGETIC = 0.035    # above this it is high-energy
SPEECH = 0.4         # this share of the scene being speech makes it a talking scene


def speech_ratio(segments: Sequence, start: float, end: float) -> float:
    """The share of [start, end] that has speech in it (segments need .start, .end and .text)"""
    length = end - start
    if length <= 0:
        return 0.0
    covered, last = 0.0, start
    for seg in sorted((s for s in segments if (getattr(s, "text", "") or "").strip()), key=lambda s: s.start):
        a, b = max(seg.start, start, last), min(seg.end, end)
        if b > a:
            covered += b - a
            last = b
    return min(1.0, covered / length)


def classify_scene(
    motion: Optional[float],
    speech: float = 0.0,
    faces: int = 0,
    audio_energy: float = 0.0,
) -> SceneType:
    """
    STATIC: nothing moves (a slide, a screen), even with narration over it.
    DIALOGUE: a face on screen and speech, with the modest movement of a person talking.
    ACTION: fast, high-energy movement (and, when there is speech, loud audio).
    MOTION: movement that is neither of those.
    UNKNOWN: no motion measurement.
    """
    if motion is None:
        return SceneType.UNKNOWN
    if motion < STILL:
        return SceneType.STATIC
    talking = speech >= SPEECH and faces >= 1
    if motion >= ENERGETIC:
        return SceneType.MOTION if (speech >= SPEECH and audio_energy < 0.3) else SceneType.ACTION
    if talking and motion < FAST:
        return SceneType.DIALOGUE
    if motion >= LIVELY:
        return SceneType.MOTION
    return SceneType.STATIC
