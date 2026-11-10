"""
Scene detection that sees what PySceneDetect's ContentDetector does not.

ContentDetector compares each frame with the one before it and calls a scene change when the difference is large.
Measured on videos with known cuts (see tests/test_scene_boundaries.py) that finds a hard cut between very different
shots, and misses: slide changes (a new layout on the same background is a small difference), dissolves and fades
(each step is small, only the total is large), and it reports a one-frame white flash as a cut.

This detector looks at the video in two ways, on a small grayscale copy of every tenth of a second:

* Cuts: a frame that differs a lot from the one before it while its neighbours do not (a spike). A spike that is
  undone a moment later (a camera flash, a glitch) is not a cut.
* Gradual changes (dissolves, fades, wipes): the picture half a second before differs from the picture half a second
  after, by clearly more than that same kind of difference is anywhere nearby (so a camera pan or a zoom, which
  keeps changing, is not one), and the difference is a bump, not a level.

The decision rules work on the numbers alone (find_boundaries), so they can be tested without a video; the class
reads the numbers from ffmpeg and turns boundaries into scenes. A fade through black is reported as FADE, other
gradual changes as DISSOLVE.
"""

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np

from src.services.scene_detection.base import (
    Scene, SceneBoundary, SceneDetector, SceneDetectorConfig, SceneType, TransitionType,
)

logger = logging.getLogger(__name__)

SAMPLE_FPS = 10        # frames looked at per second
THUMB_W, THUMB_H = 32, 18
WINDOW = 5             # frames each side for the gradual comparison (0.5 s)

# Cuts
CUT_MIN = 0.02         # smallest frame-to-frame change (0..1 of full brightness range) that can be a cut
CUT_BIG = 0.08         # a change this big can only be a cut ...
CUT_SPIKE = 1.5        # ... if it is at least this many times the biggest change in the three frames either side
CUT_SPIKE_SMALL = 3.0  # a smaller change must stand out this much (a slide changing, but not a hand moving)
FLASH_RETURN = 0.35    # a change that is mostly undone within 0.3 s (the picture comes back) is a flash

# Gradual changes
GRADUAL_MIN = 0.06     # smallest before/after difference that can be a dissolve
GRADUAL_RATIO = 2.2    # ... and this many times the usual before/after difference nearby
GRADUAL_BUMP = 0.5     # the difference must drop back by this fraction on both sides: a bump, not a level
FADE_DIP = 0.35        # brightness drops below this fraction of the darker side: a fade through black


@dataclass
class Boundary:
    time: float          # seconds from the start (the middle of a gradual change)
    kind: str            # "cut" | "dissolve" | "fade"
    strength: float      # 0..1 how sure (the size of the change)


def frame_changes(thumbs: np.ndarray) -> np.ndarray:
    """changes[i] = how much frame i differs from frame i-1 (0 for the first)"""
    changes = np.zeros(len(thumbs))
    if len(thumbs) > 1:
        changes[1:] = np.abs(thumbs[1:] - thumbs[:-1]).mean(axis=(1, 2))
    return changes


def window_changes(thumbs: np.ndarray, window: int = WINDOW) -> np.ndarray:
    """
    span[i] = how much the picture around frame i-window differs from the picture around frame i+window (0 near
    the ends). "Around" is the middle of five neighbouring frames, so a camera flash of a frame or two cannot make
    a difference that is not there.
    """
    n = len(thumbs)
    span = np.zeros(n)
    if n > 2 * window + 4:
        # steady[j] is the median of frames j..j+4 (frame j+2): one or two odd frames in a row cannot change it
        steady = np.median(np.stack([thumbs[k:n - 4 + k] for k in range(5)]), axis=0)
        left = steady[:n - 2 * window - 4]
        right = steady[2 * window:]
        span[window + 2:n - window - 2] = np.abs(left - right).mean(axis=(1, 2))
    return span


def _local(values: np.ndarray, i: int, radius: int, exclude: int = 0) -> np.ndarray:
    lo, hi = max(0, i - radius), min(len(values), i + radius + 1)
    part = np.concatenate([values[lo:max(lo, i - exclude)], values[min(hi, i + exclude + 1):hi]])
    return part if len(part) else values[lo:hi]


def find_boundaries(
    thumbs: np.ndarray,
    brightness: Optional[np.ndarray] = None,
    fps: float = SAMPLE_FPS,
    min_scene_length: float = 1.0,
) -> List[Boundary]:
    """
    Decide where scenes change from small grayscale pictures (frames x height x width, values 0..1), one per
    1/fps seconds. `brightness` (mean brightness per frame, 0..1) tells a fade through black from other gradual
    changes. Returns boundaries in time order, at least min_scene_length apart.
    """
    n = len(thumbs)
    if n < 3:
        return []
    changes = frame_changes(thumbs)
    span = window_changes(thumbs)
    radius = int(3 * fps)
    found: List[Boundary] = []

    # --- cuts: isolated spikes in the frame-to-frame change
    for i in range(1, n):
        c = changes[i]
        if c < CUT_MIN:
            continue
        near = np.concatenate([changes[max(1, i - 3):i], changes[i + 1:min(n, i + 4)]])
        # A big change only has to stand out a little (a cut in lively footage, where the picture always moves);
        # a small one has to stand out clearly (a new slide in a still picture, and not a gesture in a lively one)
        needed = CUT_SPIKE if c >= CUT_BIG else CUT_SPIKE_SMALL
        if len(near) and c < needed * max(float(near.max()), 1e-4):
            continue                                   # not a spike: a plateau of changes, which is a gradual change
        if c < changes[max(0, i - 2):i + 3].max():
            continue                                   # a neighbour is bigger: that one is the cut
        # flash / glitch: the picture from before comes back within a few frames, either right after this change
        # (it was a one-frame flash) or after a short interruption that this change ends
        back = [np.abs(thumbs[i - 1] - thumbs[i + k]).mean() for k in (1, 2) if i + k < n]
        back += [np.abs(thumbs[i - 1 - m] - thumbs[i + k]).mean() for m in (1, 2, 3) for k in (0, 1) if i - 1 - m >= 0 and i + k < n]
        if back and min(back) < FLASH_RETURN * c:
            continue
        kind = "cut"
        if brightness is not None and brightness[i - 1] > 0.05 and brightness[i] < FADE_DIP * brightness[i - 1]:
            kind = "fade"   # the picture went dark in one step: the way into a fade through black (time stays at the step)
        found.append(Boundary(time=(i - 0.5) / fps, kind=kind, strength=float(min(1.0, c * 4))))

    # --- gradual changes: a bump in the before/after difference
    candidates = []
    for i in range(WINDOW, n - WINDOW):
        s = span[i]
        if s < GRADUAL_MIN or s < span[max(0, i - 3):i + 4].max():
            continue
        candidates.append(i)
    # a plateau has equal neighbours: keep the middle one
    merged: List[int] = []
    for i in candidates:
        if merged and i - merged[-1] <= 3:
            merged[-1] = (merged[-1] + i) // 2 if abs(span[merged[-1]] - span[i]) < 1e-6 else (
                merged[-1] if span[merged[-1]] >= span[i] else i)
        else:
            merged.append(i)
    for i in merged:
        s = span[i]
        usual = float(np.percentile(_local(span, i, int(6 * fps), exclude=WINDOW + 2), 30))
        if s < GRADUAL_RATIO * usual + 0.02:
            continue                                   # no bigger than the difference found everywhere here
        far = 2 * WINDOW + 3
        before = span[i - far] if i - far >= 0 else 0.0
        after = span[i + far] if i + far < n else 0.0
        if max(before, after) > (1 - GRADUAL_BUMP) * s:
            continue                                   # the difference stays high around it: a pan or a zoom
        t = i / fps
        if any(abs(b.time - t) <= 0.9 for b in found):
            continue                                   # that is the shadow of a cut or fade already found
        kind = "dissolve"
        if brightness is not None:
            lo, hi = max(0, i - WINDOW), min(n, i + WINDOW + 1)
            dip = float(brightness[lo:hi].min())
            sides = min(float(brightness[max(0, i - 2 * WINDOW):lo + 1].mean()),
                        float(brightness[hi - 1:min(n, i + 2 * WINDOW + 1)].mean())) if hi - 1 < n else 1.0
            if sides > 0.05 and dip < FADE_DIP * sides:
                kind = "fade"
        found.append(Boundary(time=t, kind=kind, strength=float(min(1.0, s * 2))))

    # --- tidy: in order, not closer together than a scene may be (the stronger one stays)
    found.sort(key=lambda b: b.time)
    kept: List[Boundary] = []
    for b in found:
        if kept and b.time - kept[-1].time < min_scene_length:
            if b.strength > kept[-1].strength:
                kept[-1] = b
            continue
        kept.append(b)
    return [b for b in kept if min_scene_length / 2 <= b.time <= (n - 1) / fps - min_scene_length / 2]


# ---------------------------------------------------------------------------
# Reading the numbers from a video
# ---------------------------------------------------------------------------

def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"


def read_thumbnails(
    video_path: Path,
    fps: float = SAMPLE_FPS,
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Grayscale pictures of the video, `fps` per second, as a (frames, 18, 32) array of 0..1 plus the mean
    brightness of each. ffmpeg decodes and shrinks (about 50x faster than real time, and the same decoder that
    the rest of the pipeline uses), and the frames are reduced as they arrive, so memory stays small.
    """
    width, height = THUMB_W * 5, THUMB_H * 5
    cmd = [_ffmpeg(), "-v", "error"]
    if start_time:
        cmd += ["-ss", str(start_time)]
    cmd += ["-i", str(video_path)]
    if end_time is not None:
        cmd += ["-t", str(end_time - (start_time or 0.0))]
    cmd += ["-vf", f"fps={fps},scale={width}:{height}:flags=area,format=gray", "-f", "rawvideo", "-"]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    size = width * height
    thumbs: List[np.ndarray] = []
    try:
        while True:
            chunk = process.stdout.read(size * 64)
            if not chunk:
                break
            usable = len(chunk) - len(chunk) % size
            if usable:
                frames = np.frombuffer(chunk[:usable], np.uint8).reshape(-1, height, width).astype(np.float32)
                thumbs.append(frames.reshape(-1, THUMB_H, 5, THUMB_W, 5).mean(axis=(2, 4)) / 255.0)
            rest = chunk[usable:]
            while len(rest) < size:  # a frame split across two reads
                more = process.stdout.read(size - len(rest))
                if not more:
                    break
                rest += more
            if len(rest) == size:
                frame = np.frombuffer(rest, np.uint8).reshape(1, height, width).astype(np.float32)
                thumbs.append(frame.reshape(1, THUMB_H, 5, THUMB_W, 5).mean(axis=(2, 4)) / 255.0)
    finally:
        process.stdout.close()
        error = process.stderr.read().decode(errors="replace")
        process.stderr.close()
        process.wait()
    if process.returncode not in (0, None) and not thumbs:
        raise RuntimeError(f"ffmpeg could not read the video: {error.strip()[-200:]}")
    if not thumbs:
        return np.zeros((0, THUMB_H, THUMB_W), np.float32), np.zeros(0)
    stacked = np.concatenate(thumbs)
    return stacked, stacked.mean(axis=(1, 2))


class RobustSceneDetector(SceneDetector):
    """Cuts, dissolves, fades and slide changes, without false cuts on flashes (see the module notes)"""

    def __init__(self, config: Optional[SceneDetectorConfig] = None, fps: float = SAMPLE_FPS):
        super().__init__(config)
        self.fps = fps

    def detect_scenes(
        self,
        video_path: Path,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> List[Scene]:
        if not video_path.exists():
            raise ValueError(f"Video not found: {video_path}")
        thumbs, brightness = read_thumbnails(video_path, self.fps, start_time, end_time)
        if len(thumbs) == 0:
            raise RuntimeError("The video has no frames to look at")
        offset = start_time or 0.0
        length = len(thumbs) / self.fps
        boundaries = find_boundaries(thumbs, brightness, self.fps, self.config.min_scene_length)

        changes = frame_changes(thumbs)
        edges = [offset] + [offset + b.time for b in boundaries] + [offset + length]
        kinds = [None] + [b for b in boundaries]
        scenes: List[Scene] = []
        for index in range(len(edges) - 1):
            start, end = edges[index], edges[index + 1]
            first = int(round((start - offset) * self.fps))
            last = max(first + 1, int(round((end - offset) * self.fps)))
            entering = kinds[index]
            keyframe = self._keyframe(thumbs[first:last], first) / self.fps + offset
            scenes.append(Scene(
                scene_id=index + 1, start_time=start, end_time=end, duration=end - start,
                start_frame=first, end_frame=last, frame_count=last - first,
                scene_type=SceneType.UNKNOWN,
                transition_type={
                    None: TransitionType.CUT, "cut": TransitionType.CUT,
                    "dissolve": TransitionType.DISSOLVE, "fade": TransitionType.FADE,
                }[entering.kind if entering else None],
                confidence=entering.strength if entering else 1.0,
                keyframe_timestamp=keyframe,
                metadata={"detector": "robust", "fps": self.fps,
                          "entered_by": entering.kind if entering else "start",
                          **self._motion(changes, first, last)},
            ))
        if self.config.max_scene_length:
            scenes = self.split_long_scenes(scenes)
        for number, scene in enumerate(scenes, start=1):
            scene.scene_id = number
        return scenes

    @staticmethod
    def _motion(changes: np.ndarray, first: int, last: int) -> dict:
        """How much the picture moves inside a scene (the frames at its edges belong to the transitions)"""
        inside = changes[first + 2:last - 1]
        if len(inside) == 0:
            inside = changes[first:last]
        if len(inside) == 0:
            return {}
        return {"motion": round(float(inside.mean()), 5), "still_ratio": round(float((inside < 0.004).mean()), 3)}

    @staticmethod
    def _keyframe(thumbs: np.ndarray, first_index: int) -> float:
        """
        The frame (as a sampled index) that stands for a scene: the one closest to the scene's typical picture,
        looked for in its middle part so it is not a half-dissolved frame at the edge.
        """
        n = len(thumbs)
        if n <= 2:
            return first_index + n / 2
        lo, hi = (int(n * 0.2), max(int(n * 0.2) + 1, int(n * 0.8))) if n >= 6 else (0, n)
        middle = thumbs[lo:hi]
        typical = np.median(middle, axis=0)
        distance = np.abs(middle - typical).mean(axis=(1, 2))
        return first_index + lo + int(np.argmin(distance)) + 0.5

    def detect_boundaries(
        self,
        video_path: Path,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> List[SceneBoundary]:
        return [
            SceneBoundary(
                start_time=s.start_time, end_time=s.end_time, start_frame=s.start_frame, end_frame=s.end_frame,
                confidence=s.confidence, transition_type=s.transition_type, scene_type=s.scene_type,
                metadata=s.metadata,
            )
            for s in self.detect_scenes(video_path, start_time, end_time)
        ]
