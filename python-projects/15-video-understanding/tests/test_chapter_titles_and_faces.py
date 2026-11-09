"""
Chapter titles and face boxes found wanting on real videos.

Chapters were titled with the first four words of the picture caption
("Chapter 1: a woman in a"); they now use what is said where the chapter starts.
The Haar face cascade reported one face as three boxes.
"""

import pytest

from src.services.face_detection import merge_overlapping_boxes
from src.services.summarization.chapter_generator import ChapterGenerator, Chapter, title_from_text


class TestTitleFromText:
    @pytest.mark.parametrize("text,expected", [
        ("Welcome to Trial Data Lab. Here is a simple question", "Welcome to Trial Data Lab"),
        ("a woman in a white jacket and black top", "A woman in a white jacket and black"),
        ("what is the difference between the two?", "What is the difference between the two"),
        ("The foundation of reliable clinical research.", "The foundation of reliable clinical research"),
    ])
    def test_first_sentence_capitalised(self, text, expected):
        assert title_from_text(text) == expected

    @pytest.mark.parametrize("text,expected", [
        ("a woman in a", "A woman"), ("we looked at the", "We looked"), ("data of the", "Data"),
    ])
    def test_never_ends_on_a_dangling_word(self, text, expected):
        assert title_from_text(text, max_words=8) == (expected if len(expected.split()) >= 2 else None)

    @pytest.mark.parametrize("text", [None, "", "   ", "one", "a the"])
    def test_too_little_to_make_a_title(self, text):
        assert title_from_text(text) is None

    def test_word_limit(self):
        assert len(title_from_text("one two three four five six seven eight nine ten", max_words=4).split()) <= 4


class TestChapterTitles:
    def generator(self):
        return ChapterGenerator()

    def scene(self, **kw):
        return {"scene_number": 1, "start_time": 0, "end_time": 10, "description": "a woman in a", **kw}

    def chapter(self):
        return Chapter(chapter_number=1, title="", description="", start_time=0, end_time=10, duration=10, scene_ids=[1])

    def test_speech_wins_over_the_caption(self):
        title = self.generator()._generate_chapter_title(self.chapter(), [self.scene(spoken_text="Welcome to Trial Data Lab. Here is a question")])
        assert title == "Chapter 1: Welcome to Trial Data Lab"

    def test_caption_is_the_fallback_when_nobody_speaks(self):
        title = self.generator()._generate_chapter_title(self.chapter(), [self.scene(spoken_text="", description="Slide titled Traceability with four boxes")])
        assert title == "Chapter 1: Slide titled Traceability with four boxes"

    def test_nothing_usable_gives_a_plain_title(self):
        title = self.generator()._generate_chapter_title(self.chapter(), [self.scene(spoken_text="", description="a")])
        assert title == "Chapter 1"


class TestFaceBoxes:
    def test_nested_duplicates_collapse_to_the_largest(self):
        assert merge_overlapping_boxes([(0, 0, 100, 100), (10, 10, 50, 50)]) == [(0, 0, 100, 100)]

    def test_the_real_cascade_output_for_one_woman(self):
        # (x, y, w, h) boxes reported for a single face on a real keyframe
        boxes = [(772, 149, 373, 373), (913, 569, 170, 170), (835, 571, 254, 254)]
        assert merge_overlapping_boxes(boxes) == [(772, 149, 373, 373), (835, 571, 254, 254)]

    def test_separate_faces_are_kept(self):
        assert len(merge_overlapping_boxes([(0, 0, 50, 50), (200, 0, 50, 50), (400, 0, 50, 50)])) == 3

    def test_touching_but_not_overlapping_boxes_are_kept(self):
        assert len(merge_overlapping_boxes([(0, 0, 50, 50), (50, 0, 50, 50)])) == 2

    def test_empty_and_zero_sized(self):
        assert merge_overlapping_boxes([]) == []
        assert merge_overlapping_boxes([(5, 5, 0, 0)]) == [(5, 5, 0, 0)]


class TestFaceDetectorUsesTheMerge:
    def test_one_face_reported_three_times_is_one_face_per_box(self, tmp_path):
        import numpy as np
        import cv2
        from src.services.face_detection import FaceDetectionService

        class Cascade:     # the boxes the real cascade returned for one woman
            def detectMultiScale(self, *a, **k):
                return np.array([(772, 149, 373, 373), (913, 569, 170, 170), (835, 571, 254, 254)])

        image = tmp_path / "frame.jpg"
        cv2.imwrite(str(image), np.zeros((1080, 1920, 3), dtype=np.uint8))
        service = FaceDetectionService(backend="opencv")
        service.detector = Cascade()
        result = service.detect_faces(image)
        assert result.num_faces == 2 and len(result.faces) == 2
        assert [f.bbox for f in result.faces] == [(772, 149, 373, 373), (835, 571, 254, 254)]
