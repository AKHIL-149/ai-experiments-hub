"""
Sections of an audio file (src/utils/audio_sections.py): where an audio recording is cut when there is no
picture to find scenes in. Pure functions, no ffmpeg.
"""

import random
from types import SimpleNamespace as NS

import pytest

from src.utils.audio_sections import (
    MAX_SECTION, MIN_SECTION, PAUSE, SILENT_WINDOW, build_sections, sections_to_scenes,
)


def seg(start, end, text="words"):
    return NS(start=start, end=end, text=text)


def lines(count, length=4.0, gap=1.0, start=0.0):
    """count segments of `length` seconds with `gap` seconds between them"""
    out, t = [], start
    for _ in range(count):
        out.append(seg(t, t + length))
        t += length + gap
    return out


def assert_covers(sections, duration):
    assert sections, "no sections"
    assert sections[0][0] == 0.0 and sections[-1][1] == pytest.approx(duration)
    for (a_start, a_end), (b_start, _) in zip(sections, sections[1:]):
        assert a_end == pytest.approx(b_start)
    assert all(end > start for start, end in sections)


class TestNoSpeech:
    @pytest.mark.parametrize("duration,count", [(10, 1), (59, 1), (95, 2), (130, 2), (200, 3), (3600, 60)])
    def test_silence_or_music_is_cut_into_windows_of_about_a_minute(self, duration, count):
        sections = build_sections([], duration)
        assert len(sections) == count
        assert_covers(sections, duration)
        assert all(0.5 * SILENT_WINDOW <= end - start <= 1.5 * SILENT_WINDOW for start, end in sections) or count == 1

    def test_segments_without_words_count_as_no_speech(self):
        assert len(build_sections([seg(0, 5, "  "), seg(6, 9, "")], 130)) == 2

    @pytest.mark.parametrize("duration", [0, None, -5])
    def test_no_length_no_sections(self, duration):
        assert build_sections(lines(3), duration) == []


class TestPauses:
    def test_a_long_pause_after_enough_speech_starts_a_new_section(self):
        # 28 s of speech, a 6 s pause, then more speech
        segments = lines(5, length=5.0, gap=0.5) + [seg(34.0, 40.0), seg(40.5, 60.0)]
        sections = build_sections(segments, 80)
        assert segments[4].end == pytest.approx(27.0)
        assert sections[0][1] == pytest.approx(30.5)   # the middle of the pause between 27 s and 34 s
        assert len(sections) == 2

    def test_the_cut_is_in_the_middle_of_the_pause_so_no_sentence_is_split(self):
        segments = [seg(0, 12), seg(12.2, 24), seg(30, 40), seg(40.5, 50)]
        sections = build_sections(segments, 60)
        cut = sections[0][1]
        assert cut == pytest.approx((24 + 30) / 2)
        assert all(not (s.start < cut < s.end) for s in segments)

    def test_a_pause_too_early_does_not_cut(self):
        segments = [seg(0, 5), seg(9, 14), seg(14.5, 40), seg(40.2, 70)]   # a 4 s pause at 5 s: before MIN_SECTION
        sections = build_sections(segments, 90)
        assert all(end - start >= MIN_SECTION / 2 for start, end in sections)
        assert not any(abs(start - 7.0) < 0.01 for start, _ in sections)

    def test_short_gaps_are_not_pauses(self):
        sections = build_sections(lines(14, length=5.0, gap=PAUSE - 0.5), 14 * (6.5 - 0.5))
        assert all(end - start <= MAX_SECTION + 6 for start, end in sections)   # only the length limit cuts here
        assert len(sections) >= 1


class TestLengthLimit:
    def test_a_speaker_who_never_pauses_still_gets_sections(self):
        segments = lines(60, length=4.0, gap=0.2)      # ~252 s without a pause
        sections = build_sections(segments, 252)
        assert len(sections) >= 3
        assert all(end - start <= MAX_SECTION + 4.5 for start, end in sections)
        assert_covers(sections, 252)

    def test_a_single_endless_segment_is_one_section(self):
        assert build_sections([seg(0, 300)], 300) == [(0.0, 300.0)]

    def test_nothing_is_cut_below_the_minimum(self):
        segments = lines(3, length=4.0, gap=2.0)
        assert build_sections(segments, 18) == [(0.0, 18.0)]


class TestShape:
    def test_a_tiny_leftover_joins_the_section_before(self):
        segments = lines(5, length=5.0, gap=0.4) + [seg(34.0, 70.0), seg(70.3, 70.8)]
        sections = build_sections(segments, 72)
        assert sections[-1][1] == pytest.approx(72)
        assert all(end - start >= MIN_SECTION / 2 for start, end in sections)

    def test_a_short_last_section_joins_the_one_before_it(self):
        # a 3 s pause at 40 s would cut at 41.5 s, leaving 8.5 s: less than half the minimum, so no cut
        assert build_sections([seg(0, 40), seg(43, 49)], 50) == [(0.0, 50.0)]
        # the same pause with a long enough ending does cut
        assert build_sections([seg(0, 40), seg(43, 70)], 80) == [(0.0, 41.5), (41.5, 80.0)]

    def test_segments_in_any_order_give_the_same_sections(self):
        segments = lines(5, length=5.0, gap=0.5) + [seg(34.0, 40.0), seg(40.5, 60.0)]
        expected = build_sections(segments, 80)
        assert len(expected) == 2
        assert build_sections(list(reversed(segments)), 80) == expected
        shuffled = list(segments)
        random.Random(7).shuffle(shuffled)
        assert build_sections(shuffled, 80) == expected

    def test_unsorted_overlapping_and_zero_length_segments_do_not_break_it(self):
        segments = [seg(30, 40), seg(0, 12), seg(11, 25), seg(25, 25), seg(26, 26.5, ""), seg(50, 49)]
        sections = build_sections(segments, 60)
        assert_covers(sections, 60)

    @pytest.mark.parametrize("seed", range(25))
    def test_always_covers_the_whole_file_with_positive_sections(self, seed):
        rng = random.Random(seed)
        duration = rng.uniform(1, 3000)
        t, segments = 0.0, []
        while t < duration:
            length = rng.uniform(0.3, 15)
            segments.append(seg(t, min(t + length, duration)))
            t += length + rng.choice([0, 0.2, 0.8, 2, 6, 20])
        sections = build_sections(segments, duration)
        assert_covers(sections, duration)

    def test_a_segment_ending_after_the_file_is_still_covered(self):
        assert_covers(build_sections([seg(0, 50), seg(55, 120)], 100), 100)


class TestScenes:
    def test_scene_objects_for_the_rest_of_the_pipeline(self):
        scenes = sections_to_scenes([(0.0, 30.0), (30.0, 75.5)])
        assert [s.scene_id for s in scenes] == [1, 2]
        assert [(s.start_time, s.end_time, s.duration) for s in scenes] == [(0.0, 30.0, 30.0), (30.0, 75.5, 45.5)]
        assert all(s.scene_type.value == "unknown" and s.frame_count == 0 and s.metadata == {"kind": "audio_section"}
                   for s in scenes)

    def test_no_sections_no_scenes(self):
        assert sections_to_scenes([]) == []
