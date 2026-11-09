"""
Context given to the model when answering a question (src/utils/qa_context.py).

Found by asking a real video "What is the foundation of reliable clinical
research?": retrieval returned the line "the foundation of reliable clinical
research." but not the line before it ("Accurate, complete, traceable data
creates stronger evidence. That is"), so the answer named the wrong thing.
"""

from src.utils.qa_context import build_context

SEGMENTS = {
    "v1": [
        (0.0, 6.0, "Welcome to Trial Data Lab."),
        (6.0, 13.0, "Every data point begins somewhere."),
        (13.0, 20.0, "Good data management catches the problem early."),
        (20.0, 26.0, "Accurate, complete, traceable data creates stronger evidence. That is"),
        (26.0, 30.0, "the foundation of reliable clinical research."),
    ],
    "v2": [(0.0, 5.0, "Other video one."), (5.0, 9.0, "Other video two.")],
}
TITLES = {"v1": "Lab", "v2": "Other"}


def hit(video, ts, text, kind="transcript"):
    return {"source_type": kind, "video_id": video, "timestamp": ts, "content": text}


def test_a_hit_is_widened_with_the_line_before_and_after():
    out = build_context([hit("v1", 26.0, "the foundation of reliable clinical research.")], SEGMENTS, TITLES)
    assert "Accurate, complete, traceable data creates stronger evidence. That is the foundation of reliable clinical research." in out
    assert out.startswith("[Lab @ 20s-30s]:")


def test_neighbouring_hits_become_one_passage():
    out = build_context([hit("v1", 13.0, "x"), hit("v1", 20.0, "y")], SEGMENTS, TITLES)
    assert out.count("[Lab") == 1
    assert "Every data point" in out and "the foundation" in out.replace("That is\n", "") or "That is" in out


def test_passages_are_read_in_time_order_not_relevance_order():
    out = build_context([hit("v1", 26.0, "late"), hit("v1", 0.0, "early")], SEGMENTS, TITLES, neighbours=0)
    assert out.index("Welcome") < out.index("foundation")


def test_videos_are_kept_apart():
    out = build_context([hit("v2", 0.0, "a"), hit("v1", 0.0, "b")], SEGMENTS, TITLES, neighbours=0)
    assert out.index("[Lab") < out.index("[Other")


def test_no_neighbours_gives_just_the_hit():
    out = build_context([hit("v1", 13.0, "x")], SEGMENTS, TITLES, neighbours=0)
    assert out == "[Lab @ 13s-20s]: Good data management catches the problem early."


def test_edges_of_the_transcript_do_not_fail():
    assert "Welcome" in build_context([hit("v1", 0.0, "x")], SEGMENTS, TITLES)
    assert "research." in build_context([hit("v1", 26.0, "x")], SEGMENTS, TITLES)


def test_a_hit_no_longer_in_the_database_is_used_as_retrieved():
    out = build_context([hit("v1", 99.0, "text from the index")], SEGMENTS, TITLES)
    assert "text from the index" in out


def test_scene_descriptions_are_included_and_labelled():
    out = build_context([hit("v1", 30.0, "A slide titled TRACEABILITY", kind="scene")], SEGMENTS, TITLES)
    assert out == "[Lab scene @ 30s]: A slide titled TRACEABILITY"


def test_empty_scene_captions_are_skipped():
    assert build_context([hit("v1", 30.0, "   ", kind="scene")], SEGMENTS, TITLES) == ""


def test_unknown_title_and_video():
    out = build_context([hit("ghost", 1.0, "text")], {}, {})
    assert out == "[video @ 1s]: text"


def test_context_is_capped_but_never_empty():
    big = {"v": [(float(i), float(i + 1), "word " * 200) for i in range(30)]}
    out = build_context([hit("v", float(i), "x") for i in range(0, 30, 4)], big, {}, neighbours=0, max_chars=2500)
    assert 0 < len(out) < 3500
    tiny = build_context([hit("v", 0.0, "x")], big, {}, neighbours=0, max_chars=10)
    assert tiny  # the first passage is always kept


def test_no_sources():
    assert build_context([], SEGMENTS, TITLES) == ""
