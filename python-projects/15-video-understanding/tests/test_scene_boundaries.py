"""
Where scenes change (src/services/scene_detection/robust_detector.py).

PySceneDetect's ContentDetector, which the platform used alone, was measured against videos with known cuts:
it found hard cuts between very different shots and missed slide changes (a new layout on the same
background), dissolves and fades, and it reported a one-frame white flash as a cut. On the same videos made from
real footage the replacement found every boundary with no false ones.

Two layers of tests: the decision rules on small made-up pictures (exact, fast), and the whole detector on short
ffmpeg-made videos with known boundaries.
"""

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from src.services.scene_detection.base import SceneDetectorConfig, TransitionType
from src.services.scene_detection.robust_detector import (
    RobustSceneDetector, find_boundaries, frame_changes, read_thumbnails, window_changes,
)

FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
needs_ffmpeg = pytest.mark.skipif(not Path(FFMPEG).exists(), reason="ffmpeg not installed")
FPS = 10


# ---------------------------------------------------------------------------
# Made-up pictures (frames x 18 x 32, brightness 0..1)
# ---------------------------------------------------------------------------

def texture(seed):
    return np.random.default_rng(seed).uniform(0.15, 0.85, (18, 32)).astype(np.float32)


def still(n, seed=1, noise=0.001):
    """A picture that does not move (a slide, a screen) with a little compression noise"""
    rng = np.random.default_rng(seed + 100)
    return np.clip(texture(seed)[None] + rng.normal(0, noise, (n, 18, 32)), 0, 1).astype(np.float32)


def lively(n, seed=1, step=0.03):
    """A picture that is always moving (people, a camera): every frame differs a little from the last"""
    rng = np.random.default_rng(seed + 200)
    walk = texture(seed)[None] + np.cumsum(rng.normal(0, step * 0.35, (n, 18, 32)), axis=0)
    drift = np.sin(np.arange(n))[:, None, None] * step * 0.7
    return np.clip(walk + drift, 0, 1).astype(np.float32)


def join(*parts):
    return np.concatenate(parts)


def brightness(thumbs):
    return thumbs.mean(axis=(1, 2))


def times(found):
    return [round(b.time, 2) for b in found]


def kinds(found):
    return [b.kind for b in found]


class TestCuts:
    def test_a_cut_in_a_still_picture(self):
        found = find_boundaries(join(still(50, 1), still(50, 2)))
        assert kinds(found) == ["cut"] and times(found) == [4.95]

    def test_a_cut_in_lively_footage(self):
        found = find_boundaries(join(lively(60, 1), lively(60, 2)))
        assert kinds(found) == ["cut"] and abs(found[0].time - 5.95) < 0.11

    def test_several_cuts_in_order(self):
        found = find_boundaries(join(still(30, 1), still(40, 2), still(30, 3), still(40, 4)))
        assert times(found) == [2.95, 6.95, 9.95]

    def test_the_time_is_between_the_last_old_and_the_first_new_frame(self):
        found = find_boundaries(join(still(40, 1), still(40, 2)), fps=10)
        assert found[0].time == pytest.approx(3.95)
        found = find_boundaries(join(still(40, 1), still(40, 2)), fps=20, min_scene_length=1.0)
        assert found[0].time == pytest.approx(1.975)

    def test_a_new_slide_in_a_still_picture_is_a_cut_even_when_little_changes(self):
        base = still(60, 1)
        after = base.copy()
        after[30:, 2:6, 4:14] = 0.0            # a dark box appears on about 7% of the picture
        found = find_boundaries(after)
        assert kinds(found) == ["cut"] and abs(found[0].time - 2.95) < 0.11

    def test_the_same_small_change_in_lively_footage_is_not_a_cut(self):
        """A hand moving or a head turning changes a little of the picture; that is not a new scene"""
        footage = lively(80, 3, step=0.03)
        footage[40:, 2:6, 4:14] -= 0.5
        footage = np.clip(footage, 0, 1)
        assert find_boundaries(footage) == []

    def test_noise_alone_is_not_a_cut(self):
        assert find_boundaries(still(200, 1, noise=0.004)) == []
        assert find_boundaries(lively(200, 1)) == []

    def test_a_flash_is_not_a_cut(self):
        """One white frame and the picture is back: PySceneDetect called this a cut"""
        footage = still(80, 1)
        footage[40] = 1.0
        assert find_boundaries(footage) == []

    def test_a_flash_lasting_two_frames_is_not_a_cut_either(self):
        footage = still(80, 1)
        footage[40:42] = 1.0
        assert find_boundaries(footage) == []

    def test_a_change_that_stays_after_a_flash_still_counts(self):
        footage = join(still(40, 1), still(40, 2))
        footage[40] = 1.0                      # a flash right at the cut
        assert len(find_boundaries(footage)) == 1

    def test_two_cuts_closer_than_a_scene_may_be_become_one(self):
        footage = join(still(40, 1), still(4, 2), still(40, 3))     # the middle picture lasts 0.4 s
        assert len(find_boundaries(footage, min_scene_length=1.0)) == 1
        assert len(find_boundaries(footage, min_scene_length=0.2)) == 2

    def test_boundaries_too_near_the_ends_are_not_reported(self):
        assert find_boundaries(join(still(3, 1), still(80, 2)), min_scene_length=1.0) == []
        assert find_boundaries(join(still(80, 1), still(3, 2)), min_scene_length=1.0) == []

    def test_a_changing_picture_is_one_scene_when_nothing_cuts(self):
        assert find_boundaries(still(120, 5)) == []

    @pytest.mark.parametrize("n", [0, 1, 2])
    def test_too_few_frames_to_decide(self, n):
        assert find_boundaries(still(n, 1)) == []


class TestGradualChanges:
    @staticmethod
    def dissolve(a, b, steps):
        mix = [(1 - k) * a + k * b for k in np.linspace(0, 1, steps + 2)[1:-1]]
        return np.array(mix, dtype=np.float32)

    def test_a_dissolve_between_stills_is_found_at_its_middle(self):
        a, b = texture(1), texture(2)
        footage = join(np.repeat(a[None], 50, 0), self.dissolve(a, b, 10), np.repeat(b[None], 50, 0))
        found = find_boundaries(footage)
        assert kinds(found) == ["dissolve"] and abs(found[0].time - 5.5) < 0.31

    def test_a_dissolve_between_slides_is_found(self):
        """The change in each step is tiny; only the total is large"""
        a = texture(1)
        b = a.copy()
        b[4:12, 6:26] = 0.1
        footage = join(np.repeat(a[None], 50, 0), self.dissolve(a, b, 10), np.repeat(b[None], 50, 0))
        found = find_boundaries(footage)
        assert kinds(found) == ["dissolve"] and abs(found[0].time - 5.5) < 0.31

    def test_a_fade_through_black_is_called_a_fade(self):
        a, b, black = texture(1), texture(2), np.zeros((18, 32), np.float32)
        footage = join(np.repeat(a[None], 50, 0), self.dissolve(a, black, 4), np.repeat(black[None], 2, 0),
                       self.dissolve(black, b, 4), np.repeat(b[None], 50, 0))
        found = find_boundaries(footage, brightness(footage))
        assert kinds(found) == ["fade"] and abs(found[0].time - 5.5) < 0.5

    def test_without_brightness_a_gradual_change_is_a_dissolve(self):
        a, b, black = texture(1), texture(2), np.zeros((18, 32), np.float32)
        footage = join(np.repeat(a[None], 50, 0), self.dissolve(a, black, 4), np.repeat(black[None], 2, 0),
                       self.dissolve(black, b, 4), np.repeat(b[None], 50, 0))
        assert kinds(find_boundaries(footage)) == ["dissolve"]

    def test_a_dissolve_is_one_boundary_not_a_run_of_cuts(self):
        a, b = texture(1), texture(2)
        footage = join(np.repeat(a[None], 50, 0), self.dissolve(a, b, 12), np.repeat(b[None], 50, 0))
        assert len(find_boundaries(footage)) == 1

    def test_a_slow_continuous_change_is_not_a_scene_change(self):
        """A pan or a zoom keeps changing the picture; there is no before and after"""
        a, b = texture(1), texture(2)
        morph = np.array([(1 - k) * a + k * b for k in np.linspace(0, 1, 160)], dtype=np.float32)
        assert find_boundaries(morph) == []

    def test_a_single_odd_frame_cannot_make_a_dissolve(self):
        footage = still(100, 1)
        footage[50] = texture(9)               # one frame of something else
        assert find_boundaries(footage) == []

    def test_a_cut_is_not_also_reported_as_a_dissolve(self):
        found = find_boundaries(join(still(50, 1), still(50, 2)))
        assert kinds(found) == ["cut"]

    def test_strength_is_between_zero_and_one(self):
        a, b = texture(1), texture(2)
        footage = join(np.repeat(a[None], 50, 0), self.dissolve(a, b, 10), np.repeat(b[None], 50, 0), still(40, 3))
        for boundary in find_boundaries(footage):
            assert 0.0 < boundary.strength <= 1.0


class TestSignals:
    def test_frame_changes(self):
        footage = join(still(3, 1), still(3, 2))
        changes = frame_changes(footage)
        assert len(changes) == 6 and changes[0] == 0.0 and changes[3] > 0.1
        assert np.all(changes[[1, 2, 4, 5]] < 0.01)

    def test_window_changes_ignore_a_single_odd_frame(self):
        footage = still(40, 1)
        footage[20] = 1.0
        assert window_changes(footage).max() < 0.01

    def test_window_changes_see_a_lasting_change(self):
        footage = join(still(30, 1), still(30, 2))
        assert window_changes(footage).max() > 0.2

    def test_short_input(self):
        assert frame_changes(still(1, 1)).tolist() == [0.0]
        assert not window_changes(still(5, 1)).any()


# ---------------------------------------------------------------------------
# Real (ffmpeg-made) videos with known boundaries
# ---------------------------------------------------------------------------

W, H, R = 160, 90, 25


def slide(i, secs):
    layouts = [
        [(10, 10, 140, 13, "black"), (10, 35, 100, 6, "gray"), (10, 47, 120, 6, "gray")],
        [(10, 10, 100, 13, "black"), (10, 35, 60, 30, "blue"), (80, 35, 60, 30, "gray")],
        [(20, 10, 120, 13, "black"), (20, 35, 120, 6, "gray"), (20, 47, 120, 6, "gray"), (20, 59, 120, 6, "gray")],
        [(10, 10, 140, 13, "black"), (10, 35, 40, 40, "gray"), (60, 35, 40, 40, "gray"), (110, 35, 40, 40, "gray")],
    ]
    boxes = layouts[i % len(layouts)]
    drawing = ",".join(f"drawbox=x={x}:y={y}:w={w}:h={h}:color={c}:t=fill" for x, y, w, h, c in boxes)
    return f"color=c=white:s={W}x{H}:r={R},{drawing}"


def make_video(path, sources, lengths, mode, flash=None):
    """mode cut | fade | fadeblack; returns the true boundary times (the middle of a transition)"""
    transition = 0.0 if mode == "cut" else 1.0
    command = [FFMPEG, "-v", "error", "-y"]
    for source, length in zip(sources, lengths):
        command += ["-f", "lavfi", "-t", str(length + transition), "-i", source]
    n = len(sources)
    prepare = ";".join(f"[{i}:v]format=yuv420p,setsar=1,fps={R}[n{i}]" for i in range(n)) + ";"
    truth = []
    if mode == "cut":
        graph = prepare + "".join(f"[n{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[out]"
        at = 0.0
        for length in lengths[:-1]:
            at += length
            truth.append(at)
    else:
        parts, previous, at = [], "[n0]", lengths[0]
        for i in range(1, n):
            out = f"[v{i}]" if i < n - 1 else "[out]"
            parts.append(f"{previous}[n{i}]xfade=transition={mode}:duration=1:offset={at}{out}")
            truth.append(at + 0.5)
            previous, at = out, at + lengths[i]
        graph = prepare + ";".join(parts)
    final = "[out]"
    if flash:
        graph += f";[out]{flash}[final]"
        final = "[final]"
    command += ["-filter_complex", graph, "-map", final, "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "20", str(path)]
    subprocess.run(command, check=True, capture_output=True)
    return truth


def shot(name):
    return f"{name}=s={W}x{H}:r={R}"


def detect(path, **config):
    scenes = RobustSceneDetector(SceneDetectorConfig(min_scene_length=1.0, **config)).detect_scenes(Path(path))
    return scenes


def starts(scenes):
    return [s.start_time for s in scenes][1:]


def matches(found, truth, tolerance=0.7):
    return len(found) == len(truth) and all(abs(f - t) <= tolerance for f, t in zip(found, truth))


@needs_ffmpeg
class TestRealVideos:
    def test_cuts_between_different_shots(self, tmp_path):
        truth = make_video(tmp_path / "a.mp4", [shot(n) for n in ("testsrc2", "smptebars", "rgbtestsrc", "yuvtestsrc")],
                           [4, 5, 4, 5], "cut")
        assert matches(starts(detect(tmp_path / "a.mp4")), truth, 0.2)

    def test_slide_changes(self, tmp_path):
        """The case ContentDetector missed: the same white background, a different layout"""
        truth = make_video(tmp_path / "s.mp4", [slide(i, 0) for i in range(4)], [4, 5, 4, 5], "cut")
        assert matches(starts(detect(tmp_path / "s.mp4")), truth, 0.2)

    def test_slide_dissolves(self, tmp_path):
        truth = make_video(tmp_path / "d.mp4", [slide(i, 0) for i in range(4)], [4, 5, 4, 5], "fade")
        assert matches(starts(detect(tmp_path / "d.mp4")), truth, 0.7)

    def test_a_fade_through_black(self, tmp_path):
        truth = make_video(tmp_path / "f.mp4", [shot(n) for n in ("testsrc2", "smptebars", "rgbtestsrc")], [4, 5, 4], "fadeblack")
        scenes = detect(tmp_path / "f.mp4")
        assert matches(starts(scenes), truth, 0.9)
        assert all(s.transition_type == TransitionType.FADE for s in scenes[1:])

    def test_a_flash_is_not_a_scene(self, tmp_path):
        flash = "drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='between(t,5,5.08)'"
        make_video(tmp_path / "x.mp4", [shot("testsrc2")], [12], "cut", flash=flash)
        assert len(detect(tmp_path / "x.mp4")) == 1

    def test_continuous_motion_is_one_scene(self, tmp_path):
        make_video(tmp_path / "m.mp4", [shot("testsrc2")], [12], "cut")
        scenes = detect(tmp_path / "m.mp4")
        assert len(scenes) == 1 and scenes[0].metadata["motion"] > 0

    def test_scenes_cover_the_whole_video_in_order(self, tmp_path):
        make_video(tmp_path / "a.mp4", [shot(n) for n in ("testsrc2", "smptebars", "rgbtestsrc")], [4, 5, 4], "cut")
        scenes = detect(tmp_path / "a.mp4")
        assert scenes[0].start_time == 0.0 and scenes[-1].end_time == pytest.approx(13.0, abs=0.2)
        for first, second in zip(scenes, scenes[1:]):
            assert first.end_time == second.start_time
        assert [s.scene_id for s in scenes] == [1, 2, 3]
        assert all(s.duration == pytest.approx(s.end_time - s.start_time) for s in scenes)

    def test_the_keyframe_is_inside_its_scene_and_not_at_its_edge(self, tmp_path):
        make_video(tmp_path / "a.mp4", [shot(n) for n in ("testsrc2", "smptebars", "rgbtestsrc")], [4, 5, 4], "cut")
        for scene in detect(tmp_path / "a.mp4"):
            assert scene.start_time + 0.2 * scene.duration <= scene.keyframe_timestamp <= scene.end_time - 0.15 * scene.duration

    def test_each_scene_says_how_it_began(self, tmp_path):
        make_video(tmp_path / "a.mp4", [slide(i, 0) for i in range(3)], [4, 5, 4], "fade")
        scenes = detect(tmp_path / "a.mp4")
        assert [s.metadata["entered_by"] for s in scenes] == ["start", "dissolve", "dissolve"]
        assert [s.transition_type for s in scenes] == [TransitionType.CUT, TransitionType.DISSOLVE, TransitionType.DISSOLVE]
        assert all(0 < s.confidence <= 1 for s in scenes)

    def test_motion_tells_a_still_picture_from_a_moving_one(self, tmp_path):
        make_video(tmp_path / "s.mp4", [slide(0, 0)], [8], "cut")
        make_video(tmp_path / "m.mp4", [shot("testsrc2")], [8], "cut")
        still_scene, moving_scene = detect(tmp_path / "s.mp4")[0], detect(tmp_path / "m.mp4")[0]
        assert still_scene.metadata["motion"] < 0.003 and still_scene.metadata["still_ratio"] > 0.9
        assert moving_scene.metadata["motion"] > 0.01

    def test_a_video_with_no_cuts_is_one_scene(self, tmp_path):
        make_video(tmp_path / "s.mp4", [slide(0, 0)], [6], "cut")
        scenes = detect(tmp_path / "s.mp4")
        assert len(scenes) == 1 and scenes[0].start_time == 0.0

    def test_long_scenes_can_be_split(self, tmp_path):
        make_video(tmp_path / "s.mp4", [slide(0, 0)], [12], "cut")
        scenes = RobustSceneDetector(SceneDetectorConfig(min_scene_length=1.0, max_scene_length=5.0)).detect_scenes(
            tmp_path / "s.mp4")
        assert len(scenes) >= 2 and all(s.duration <= 5.5 for s in scenes)

    def test_boundaries_view(self, tmp_path):
        make_video(tmp_path / "a.mp4", [shot(n) for n in ("testsrc2", "smptebars")], [4, 5], "cut")
        found = RobustSceneDetector().detect_boundaries(tmp_path / "a.mp4")
        assert len(found) == 2 and found[1].start_time == pytest.approx(4.0, abs=0.2)

    def test_part_of_a_video(self, tmp_path):
        make_video(tmp_path / "a.mp4", [shot(n) for n in ("testsrc2", "smptebars", "rgbtestsrc")], [4, 5, 4], "cut")
        scenes = RobustSceneDetector().detect_scenes(tmp_path / "a.mp4", start_time=3.0, end_time=10.0)
        assert scenes[0].start_time == 3.0 and starts(scenes)[0] == pytest.approx(4.0, abs=0.3)

    def test_a_missing_file(self, tmp_path):
        with pytest.raises(ValueError):
            RobustSceneDetector().detect_scenes(tmp_path / "nope.mp4")

    def test_a_file_that_is_not_a_video(self, tmp_path):
        bad = tmp_path / "bad.mp4"
        bad.write_bytes(b"not a video at all")
        with pytest.raises(RuntimeError):
            RobustSceneDetector().detect_scenes(bad)


@needs_ffmpeg
class TestReadingThumbnails:
    def test_ten_pictures_a_second_with_their_brightness(self, tmp_path):
        make_video(tmp_path / "a.mp4", [shot("testsrc2")], [5], "cut")
        thumbs, light = read_thumbnails(tmp_path / "a.mp4", fps=10)
        assert thumbs.shape[1:] == (18, 32) and 48 <= len(thumbs) <= 51 and len(light) == len(thumbs)
        assert 0.0 <= thumbs.min() and thumbs.max() <= 1.0 and 0.1 < light.mean() < 0.9

    def test_a_different_rate(self, tmp_path):
        make_video(tmp_path / "a.mp4", [shot("testsrc2")], [4], "cut")
        assert 19 <= len(read_thumbnails(tmp_path / "a.mp4", fps=5)[0]) <= 21

    def test_a_video_that_does_not_end_on_a_whole_read(self, tmp_path):
        """The reader takes frames in blocks; a length that is not a multiple of a block must lose nothing"""
        for seconds in (3, 7, 13):
            make_video(tmp_path / "a.mp4", [shot("testsrc2")], [seconds], "cut")
            count = len(read_thumbnails(tmp_path / "a.mp4", fps=10)[0])
            assert abs(count - seconds * 10) <= 1, seconds

    def test_a_black_video_is_dark(self, tmp_path):
        subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-t", "2", "-i", f"color=c=black:s={W}x{H}:r={R}",
                        "-pix_fmt", "yuv420p", str(tmp_path / "b.mp4")], check=True)
        thumbs, light = read_thumbnails(tmp_path / "b.mp4")
        assert light.max() < 0.1
