"""
A video with no cuts is one scene, not an error.

Found with a real 5.8 s phone video: PySceneDetect lists only the cuts, so a
continuous shot came back empty and the detector divided by zero
("Scene detection failed: division by zero"), failing the whole pipeline.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from src.services.scene_detection.base import SceneDetectorConfig
from src.services.scene_detection.content_detector import ContentBasedSceneDetector

FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
pytestmark = pytest.mark.skipif(not Path(FFMPEG).exists(), reason="ffmpeg not installed")

try:
    import scenedetect  # noqa: F401
except ImportError:      # pragma: no cover
    pytestmark = pytest.mark.skip(reason="scenedetect not installed")


def make(path, *inputs):
    args = [FFMPEG, "-v", "error", "-y"]
    for source in inputs:
        args += ["-f", "lavfi", "-i", source]
    subprocess.run(args + ["-pix_fmt", "yuv420p", "-r", "25", str(path)], check=True, capture_output=True)
    return path


def detect(path, **config):
    detector = ContentBasedSceneDetector(SceneDetectorConfig(threshold=27.0, min_scene_length=config.pop("min_scene_length", 1.0), **config))
    return detector.detect_scenes(Path(path))


def test_continuous_shot_is_one_scene_covering_the_video(tmp_path):
    scenes = detect(make(tmp_path / "still.mp4", "color=c=blue:s=320x240:d=5"))
    assert len(scenes) == 1
    scene = scenes[0]
    assert scene.scene_id == 1 and scene.start_time == 0
    assert scene.end_time == pytest.approx(5.0, abs=0.1)
    assert scene.duration == pytest.approx(5.0, abs=0.1)
    assert scene.frame_count == pytest.approx(125, abs=3)
    assert scene.keyframe_timestamp == pytest.approx(2.5, abs=0.1)


def test_clip_shorter_than_the_minimum_scene_length_still_gets_a_scene(tmp_path):
    scenes = detect(make(tmp_path / "tiny.mp4", "color=c=red:s=160x120:d=0.6"), min_scene_length=2.0)
    assert len(scenes) == 1


def test_real_cuts_are_still_found(tmp_path):
    scenes_path = tmp_path / "cuts.mp4"
    subprocess.run([
        FFMPEG, "-v", "error", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=320x240:d=3:r=25",
        "-f", "lavfi", "-i", "color=c=white:s=320x240:d=3:r=25",
        "-filter_complex", "[0][1]concat=n=2:v=1:a=0,format=yuv420p", str(scenes_path),
    ], check=True, capture_output=True)
    scenes = detect(scenes_path)
    assert len(scenes) == 2
    assert scenes[0].end_time == pytest.approx(3.0, abs=0.1)
    assert scenes[1].start_time == pytest.approx(3.0, abs=0.1)
    assert [s.scene_id for s in scenes] == [1, 2]


def test_adaptive_mode_survives_a_video_without_cuts(tmp_path):
    detector = ContentBasedSceneDetector(SceneDetectorConfig(threshold=27.0, min_scene_length=1.0))
    assert isinstance(detector.detect_with_adaptive_threshold(make(tmp_path / "s.mp4", "color=c=green:s=160x120:d=4")), list)
