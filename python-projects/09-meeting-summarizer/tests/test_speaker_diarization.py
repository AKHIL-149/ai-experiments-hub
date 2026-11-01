import pytest

from utils.speaker_diarization import SpeakerDiarization


@pytest.fixture
def d():
    return SpeakerDiarization.__new__(SpeakerDiarization)       # no model: only the logic is tested


TURNS = [
    {"start": 0, "end": 5, "speaker": "Speaker 1", "duration": 5},
    {"start": 5, "end": 12, "speaker": "Speaker 2", "duration": 7},
    {"start": 20, "end": 25, "speaker": "Speaker 1", "duration": 5},
]


def seg(a, b, text="words here"):
    return {"start": a, "end": b, "text": text}


class TestAssignSegments:
    def speakers(self, d, *segments, turns=TURNS):
        return [r["speaker"] for r in d.assign_segments_to_speakers(list(segments), turns)]

    def test_segment_inside_a_turn(self, d):
        assert self.speakers(d, seg(0, 4), seg(6, 10), seg(21, 24)) == ["Speaker 1", "Speaker 2", "Speaker 1"]

    def test_a_segment_across_two_turns_goes_to_the_one_it_overlaps_more(self, d):
        assert self.speakers(d, seg(4, 9)) == ["Speaker 2"]          # 1 s of Speaker 1, 4 s of Speaker 2
        assert self.speakers(d, seg(1, 6)) == ["Speaker 1"]          # 4 s vs 1 s

    def test_a_gap_goes_to_the_nearest_turn(self, d):
        assert self.speakers(d, seg(14, 16)) == ["Speaker 2"]
        assert self.speakers(d, seg(18, 19)) == ["Speaker 1"]

    def test_before_and_after_everything(self, d):
        assert self.speakers(d, seg(-3, -1), seg(40, 41)) == ["Speaker 1", "Speaker 1"]

    def test_several_turns_of_one_speaker_add_up(self, d):
        turns = [{"start": 0, "end": 2, "speaker": "A"}, {"start": 2, "end": 3, "speaker": "B"}, {"start": 3, "end": 5, "speaker": "A"}]
        assert self.speakers(d, seg(0, 5), turns=turns) == ["A"]

    def test_unsorted_turns_are_handled(self, d):
        assert self.speakers(d, seg(6, 10), turns=list(reversed(TURNS))) == ["Speaker 2"]

    def test_empty_text_is_skipped_and_the_rest_kept_in_order(self, d):
        out = d.assign_segments_to_speakers([seg(0, 1, "  "), seg(1, 2, " hello "), seg(6, 7, "there")], TURNS)
        assert [(r["speaker"], r["text"]) for r in out] == [("Speaker 1", "hello"), ("Speaker 2", "there")]
        assert out[0]["start"] == 1 and out[0]["end"] == 2

    def test_no_turns_at_all(self, d):
        assert self.speakers(d, seg(0, 1), turns=[]) == ["Speaker 1"]

    def test_no_segments(self, d):
        assert d.assign_segments_to_speakers([], TURNS) == []

    def test_timing_is_real_not_evenly_spread(self, d):
        # the old method gave every line the same-sized window; here the times are the transcriber's
        out = d.assign_segments_to_speakers([seg(0, 1), seg(1, 9), seg(9, 10)], TURNS)
        assert [round(r["end"] - r["start"]) for r in out] == [1, 8, 1]


class TestOtherHelpers:
    def test_relabelling_numbers_speakers_by_first_appearance(self, d):
        out = d._relabel_speakers([
            {"start": 5, "end": 6, "speaker": "SPEAKER_01"}, {"start": 0, "end": 1, "speaker": "SPEAKER_00"}, {"start": 7, "end": 8, "speaker": "SPEAKER_01"},
        ])
        assert [s["speaker"] for s in out] == ["Speaker 2", "Speaker 1", "Speaker 2"]

    def test_statistics(self, d):
        stats = d.get_speaker_statistics(TURNS)
        assert stats["total_speakers"] == 2 and stats["total_duration"] == 17
        assert stats["speakers"]["Speaker 2"]["percentage"] == pytest.approx(7 / 17 * 100)
        assert stats["speakers"]["Speaker 1"]["num_segments"] == 2
        assert d.get_speaker_statistics([]) == {}

    def test_even_spread_fallback_exists_but_is_only_a_guess(self, d):
        out = d.assign_transcript_to_speakers("One. Two. Three. Four.", TURNS)
        assert len({round(r["end"] - r["start"], 3) for r in out}) == 1        # every line the same length

    def test_format_groups_consecutive_lines(self, d):
        text = d.format_speaker_transcript([{"speaker": "A", "text": "one"}, {"speaker": "A", "text": "two"}, {"speaker": "B", "text": "three"}])
        assert text.count("A:") == 1 and text.count("B:") == 1

    def test_diarize_returns_relabelled_turns_and_records_failures(self, d, tmp_path):
        audio = tmp_path / "a.wav"; audio.write_bytes(b"x")

        class Output:
            def serialize(self_inner):
                return {"diarization": [{"start": 0, "end": 2, "speaker": "SPEAKER_07"}, {"start": 2, "end": 3, "speaker": "SPEAKER_03"}]}

        d.is_available, d.last_error = True, None
        d.pipeline = lambda path, **kw: Output()
        out = d.diarize(str(audio))
        assert [t["speaker"] for t in out] == ["Speaker 1", "Speaker 2"] and out[0]["duration"] == 2

        def broken(path, **kw):
            raise RuntimeError("model blew up")
        d.pipeline = broken
        assert d.diarize(str(audio)) is None and d.last_error == "model blew up"

    def test_unavailable_diarizer(self, d, tmp_path):
        d.is_available = False
        assert d.diarize(str(tmp_path / "x.wav")) is None
