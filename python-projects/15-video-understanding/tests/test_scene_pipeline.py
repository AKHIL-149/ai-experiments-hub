"""
How the pipeline uses the scene and face detectors: which scene detector runs (and what happens when it
fails), and that every scene is typed from its motion, its speech and the faces in it.
"""

import logging
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.core.config import settings
from src.services.scene_detection.base import SceneType


class TestChoosingTheDetector:
    def run(self, monkeypatch, name="robust", robust=None, content=None):
        monkeypatch.setattr(settings, "scene_detector", name)
        monkeypatch.setattr(settings, "scene_threshold", 31.0)
        monkeypatch.setattr(settings, "min_scene_length", 2.5)
        robust = robust or Mock()
        content = content or Mock()
        from src.api.videos import _detect_scenes
        with patch("src.services.scene_detection.robust_detector.RobustSceneDetector", robust), \
             patch("src.services.scene_detection.content_detector.ContentBasedSceneDetector", content):
            result = _detect_scenes(Path("v.mp4"))
        return result, robust, content

    def test_the_robust_detector_is_the_default(self, monkeypatch):
        robust = Mock(return_value=Mock(detect_scenes=Mock(return_value=["robust scenes"])))
        result, robust, content = self.run(monkeypatch, "robust", robust=robust)
        assert result == ["robust scenes"]
        content.assert_not_called()

    def test_it_gets_the_threshold_and_minimum_length_from_the_settings(self, monkeypatch):
        robust = Mock(return_value=Mock(detect_scenes=Mock(return_value=[])))
        _, robust, _ = self.run(monkeypatch, "robust", robust=robust)
        config = robust.call_args[0][0]
        assert config.threshold == 31.0 and config.min_scene_length == 2.5

    def test_the_content_detector_can_be_chosen(self, monkeypatch):
        content = Mock(return_value=Mock(detect_scenes=Mock(return_value=["content scenes"])))
        result, robust, content = self.run(monkeypatch, "content", content=content)
        assert result == ["content scenes"]
        robust.assert_not_called()
        assert content.call_args[0][0].threshold == 31.0

    def test_when_the_robust_detector_fails_the_content_detector_runs_and_it_is_logged(self, monkeypatch, caplog):
        robust = Mock(return_value=Mock(detect_scenes=Mock(side_effect=RuntimeError("ffmpeg could not read the video"))))
        content = Mock(return_value=Mock(detect_scenes=Mock(return_value=["fallback"])))
        with caplog.at_level(logging.WARNING, logger="src.api.videos"):
            result, _, _ = self.run(monkeypatch, "robust", robust=robust, content=content)
        assert result == ["fallback"]
        assert any("robust scene detector failed" in r.getMessage() and "ffmpeg could not read" in r.getMessage()
                   for r in caplog.records)

    def test_when_both_fail_the_error_reaches_the_pipeline(self, monkeypatch):
        robust = Mock(return_value=Mock(detect_scenes=Mock(side_effect=RuntimeError("a"))))
        content = Mock(return_value=Mock(detect_scenes=Mock(side_effect=RuntimeError("b"))))
        with pytest.raises(RuntimeError, match="b"):
            self.run(monkeypatch, "robust", robust=robust, content=content)


def fake_scene(i, motion=None, start=None):
    start = float(i * 10) if start is None else start
    return NS(scene_id=i + 1, start_time=start, end_time=start + 10.0, keyframe_timestamp=start + 5.0,
              middle_timestamp=start + 5.0, scene_type=SceneType.UNKNOWN,
              metadata=None if motion is None else {"motion": motion})


def analyse(scenes, faces_per_scene, segments=(), actions=(), audio_energy=0.1):
    """_run_video_analysis with the models replaced; returns the scene results"""
    from src.api.videos import _run_video_analysis

    processor = Mock()
    processor.extract_frames.return_value = []
    detector = Mock()
    detector.detect_faces.side_effect = faces_per_scene if isinstance(faces_per_scene, Exception) else [
        NS(faces=[NS(bbox=(1, 2, 3, 4), confidence=0.9)] * n) for n in faces_per_scene]
    captioner = Mock()
    captioner.caption_image.return_value = NS(text="a caption")
    actions_service = Mock()
    actions_service.recognize_actions.return_value = NS(actions=list(actions))
    transcriber = Mock()
    transcriber.transcribe.return_value = NS(segments=list(segments), language="en", duration=60.0)
    extractor = Mock()
    extractor.extract_segment_features.return_value = NS(rms_energy=audio_energy / 10)
    kf_exists = patch("pathlib.Path.exists", return_value=True)

    with ExitStack() as stack:
        stack.enter_context(patch("src.core.video_processor.create_video_processor", return_value=processor))
        stack.enter_context(patch("src.api.videos._detect_scenes", return_value=scenes))
        stack.enter_context(patch("src.services.transcription_service.TranscriptionService", return_value=transcriber))
        stack.enter_context(patch("src.services.image_captioning.ImageCaptioningService.from_settings", return_value=captioner))
        objects = Mock()
        objects.detect_objects.return_value = NS(objects=[])
        stack.enter_context(patch("src.services.object_detection.ObjectDetectionService", return_value=objects))
        stack.enter_context(patch("src.services.face_detection.FaceDetectionService.from_settings", return_value=detector))
        ocr = Mock()
        ocr.extract_text.return_value = NS(text="")
        stack.enter_context(patch("src.services.ocr_service.OCRService", return_value=ocr))
        stack.enter_context(patch("src.services.action_recognition.ActionRecognitionService", return_value=actions_service))
        stack.enter_context(patch("src.services.audio_features.AudioFeatureExtractor", return_value=extractor))
        clip = Mock()
        clip.encode_image.return_value = None
        stack.enter_context(patch("src.api.videos._get_clip_model", return_value=clip))
        stack.enter_context(patch("src.api.videos.probe_media", return_value=NS(duration=60.0)))
        stack.enter_context(kf_exists)
        stack.enter_context(patch.object(settings, "diarization_use_auth_token", False))
        stack.enter_context(patch.object(settings, "frames_path", "/tmp/vu-test-frames"))
        stack.enter_context(patch.object(settings, "temp_path", "/tmp/vu-test-temp"))
        return _run_video_analysis("video.mp4", "vid-types")["scenes"]


def seg(start, end):
    return NS(start=start, end=end, text="words", confidence=1.0, language="en", speaker=None)


class TestSceneTyping:
    def test_a_slide_is_static(self):
        out = analyse([fake_scene(0, motion=0.0)], [0])
        assert out[0]["scene"].scene_type == SceneType.STATIC

    def test_a_person_talking_is_dialogue(self):
        out = analyse([fake_scene(0, motion=0.01)], [1], segments=[seg(0, 9)])
        assert out[0]["scene"].scene_type == SceneType.DIALOGUE

    def test_the_same_motion_without_a_face_is_not_dialogue(self):
        out = analyse([fake_scene(0, motion=0.01)], [0], segments=[seg(0, 9)])
        assert out[0]["scene"].scene_type == SceneType.MOTION

    def test_the_same_scene_without_speech_is_not_dialogue(self):
        out = analyse([fake_scene(0, motion=0.01)], [1], segments=[])
        assert out[0]["scene"].scene_type == SceneType.MOTION

    def test_speech_is_measured_inside_each_scene(self):
        scenes = [fake_scene(0, motion=0.01), fake_scene(1, motion=0.01)]
        out = analyse(scenes, [1, 1], segments=[seg(0, 9)])    # speech only in the first
        assert [o["scene"].scene_type for o in out] == [SceneType.DIALOGUE, SceneType.MOTION]

    def test_fast_footage_is_action(self):
        out = analyse([fake_scene(0, motion=0.05)], [1])
        assert out[0]["scene"].scene_type == SceneType.ACTION

    def test_each_scene_gets_its_own_type(self):
        scenes = [fake_scene(0, motion=0.0), fake_scene(1, motion=0.05), fake_scene(2, motion=0.025)]
        out = analyse(scenes, [0, 1, 0])
        assert [o["scene"].scene_type for o in out] == [SceneType.STATIC, SceneType.ACTION, SceneType.MOTION]

    def test_the_loudness_of_the_scene_decides_between_motion_and_action_for_fast_speech(self):
        loud = analyse([fake_scene(0, motion=0.05)], [1], segments=[seg(0, 9)], audio_energy=0.8)
        quiet = analyse([fake_scene(0, motion=0.05)], [1], segments=[seg(0, 9)], audio_energy=0.1)
        assert loud[0]["scene"].scene_type == SceneType.ACTION and quiet[0]["scene"].scene_type == SceneType.MOTION

    def test_without_a_motion_measurement_the_action_recognition_is_used(self):
        """The content detector does not measure motion: scenes it makes fall back to the action recognition"""
        busy = NS(start_time=0.0, end_time=10.0, action="running")
        out = analyse([fake_scene(0)], [0], actions=[busy])
        assert out[0]["scene"].scene_type == SceneType.ACTION
        out = analyse([fake_scene(0)], [0], actions=[])
        assert out[0]["scene"].scene_type == SceneType.STATIC

    def test_the_faces_found_are_stored_with_the_scene(self):
        out = analyse([fake_scene(0, motion=0.01)], [2])
        assert out[0]["faces"] == [{"bbox": (1, 2, 3, 4), "confidence": 0.9}] * 2

    def test_a_scene_whose_face_detection_fails_is_still_typed(self):
        out = analyse([fake_scene(0, motion=0.0)], RuntimeError("boom"))
        assert out[0]["scene"].scene_type == SceneType.STATIC and out[0]["faces"] == []


class TestFaceDetectorFromSettings:
    def test_the_pipeline_asks_the_settings_for_its_face_detector(self):
        import inspect
        from src.api import videos
        source = inspect.getsource(videos._run_video_analysis)
        assert "FaceDetectionService.from_settings()" in source and 'backend="opencv"' not in source
