"""
What kind of scene it is (src/services/scene_detection/scene_typing.py). Every scene used to be stored as
"unknown". The motion numbers in these tests are the ones measured on real videos: 0.000 for slides, 0.003-0.017
for a person talking to a camera, 0.02-0.05 for a fast-cut music video.
"""

from types import SimpleNamespace as NS

import pytest

from src.services.scene_detection.base import SceneType
from src.services.scene_detection.scene_typing import (
    ENERGETIC, FAST, LIVELY, SPEECH, STILL, classify_scene, speech_ratio,
)


def seg(start, end, text="words"):
    return NS(start=start, end=end, text=text)


class TestClassify:
    @pytest.mark.parametrize("motion,speech,faces,energy,expected", [
        (0.0, 0.0, 0, 0.0, SceneType.STATIC),              # a slide
        (0.0, 1.0, 0, 0.1, SceneType.STATIC),              # a slide with narration over it
        (0.0, 1.0, 1, 0.1, SceneType.STATIC),              # a still photo of a person, with speech
        (0.0013, 0.0, 0, 0.0, SceneType.STATIC),           # a screen recording
        (0.008, 0.9, 1, 0.2, SceneType.DIALOGUE),          # a person talking to the camera
        (0.017, 0.9, 2, 0.2, SceneType.DIALOGUE),          # two people talking
        (0.017, 0.0, 1, 0.2, SceneType.MOTION),            # a person moving, silent
        (0.012, 0.9, 0, 0.2, SceneType.MOTION),            # speech over moving things, no face
        (0.004, 0.0, 0, 0.0, SceneType.STATIC),            # barely moving, nobody speaking
        (0.03, 0.0, 0, 0.5, SceneType.MOTION),             # lively footage
        (0.03, 0.9, 1, 0.5, SceneType.MOTION),             # too lively for a conversation
        (0.045, 0.0, 1, 0.5, SceneType.ACTION),            # fast cutting music video
        (0.045, 0.9, 1, 0.6, SceneType.ACTION),            # fast and loud
        (0.045, 0.9, 1, 0.1, SceneType.MOTION),            # fast but quiet speech: not action
    ])
    def test_the_type(self, motion, speech, faces, energy, expected):
        assert classify_scene(motion, speech, faces, energy) == expected

    def test_without_a_motion_measurement_it_is_unknown(self):
        assert classify_scene(None, 1.0, 1, 1.0) == SceneType.UNKNOWN

    def test_the_boundaries_between_types(self):
        assert classify_scene(STILL - 1e-6) == SceneType.STATIC
        assert classify_scene(STILL, 0.0, 0) == SceneType.STATIC             # still below LIVELY and no one talking
        assert classify_scene(LIVELY, 0.0, 0) == SceneType.MOTION
        assert classify_scene(LIVELY - 1e-6, 0.0, 0) == SceneType.STATIC
        assert classify_scene(FAST - 1e-6, SPEECH, 1) == SceneType.DIALOGUE
        assert classify_scene(FAST, SPEECH, 1) == SceneType.MOTION
        assert classify_scene(ENERGETIC - 1e-6, 0.0, 0, 1.0) == SceneType.MOTION
        assert classify_scene(ENERGETIC, 0.0, 0, 1.0) == SceneType.ACTION

    def test_speech_needs_to_be_a_good_part_of_the_scene(self):
        assert classify_scene(0.01, SPEECH - 0.01, 1) == SceneType.MOTION
        assert classify_scene(0.01, SPEECH, 1) == SceneType.DIALOGUE

    def test_a_dialogue_needs_a_face(self):
        assert classify_scene(0.01, 1.0, 0) == SceneType.MOTION
        assert classify_scene(0.01, 1.0, 1) == SceneType.DIALOGUE

    def test_the_audio_only_matters_for_fast_scenes_with_speech(self):
        assert classify_scene(0.05, 1.0, 0, 0.29) == SceneType.MOTION
        assert classify_scene(0.05, 1.0, 0, 0.3) == SceneType.ACTION
        assert classify_scene(0.05, 0.0, 0, 0.0) == SceneType.ACTION


class TestSpeechRatio:
    def test_no_speech(self):
        assert speech_ratio([], 0, 10) == 0.0

    def test_all_speech(self):
        assert speech_ratio([seg(0, 10)], 0, 10) == 1.0

    def test_part_of_the_scene(self):
        assert speech_ratio([seg(2, 5)], 0, 10) == pytest.approx(0.3)

    def test_only_the_part_inside_the_scene_counts(self):
        assert speech_ratio([seg(-5, 3), seg(8, 20)], 0, 10) == pytest.approx(0.5)

    def test_overlapping_segments_are_not_counted_twice(self):
        assert speech_ratio([seg(0, 6), seg(4, 8)], 0, 10) == pytest.approx(0.8)

    def test_segments_out_of_order(self):
        assert speech_ratio([seg(6, 8), seg(0, 2)], 0, 10) == pytest.approx(0.4)

    def test_segments_without_words_are_silence(self):
        assert speech_ratio([seg(0, 10, "  "), seg(0, 10, "")], 0, 10) == 0.0

    def test_segments_outside_the_scene(self):
        assert speech_ratio([seg(20, 30)], 0, 10) == 0.0

    @pytest.mark.parametrize("start,end", [(5, 5), (7, 3)])
    def test_an_empty_scene(self, start, end):
        assert speech_ratio([seg(0, 10)], start, end) == 0.0

    def test_never_more_than_all(self):
        assert speech_ratio([seg(0, 10), seg(0, 10), seg(0, 10)], 0, 10) == 1.0
