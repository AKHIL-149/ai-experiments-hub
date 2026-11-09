"""
The context a model gets when answering a question about a video.

Retrieval returns the few transcript lines that best match the question. Each
is a fragment of a spoken sentence, and the answer is often in the line before
or after it ("Accurate, complete, traceable data creates stronger evidence.
[next line] That is the foundation of reliable clinical research."). So every
hit is widened with its neighbours and the result is read in time order.
"""

from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

Segment = Tuple[float, float, str]  # start, end, text


def _runs(indexes: Sequence[int]) -> List[List[int]]:
    runs: List[List[int]] = []
    for i in indexes:
        if runs and i == runs[-1][-1] + 1:
            runs[-1].append(i)
        else:
            runs.append([i])
    return runs


def build_context(
    sources: Sequence[dict],
    segments_by_video: Dict[str, List[Segment]],
    titles: Optional[Dict[str, str]] = None,
    neighbours: int = 1,
    max_chars: int = 6000,
) -> str:
    """
    sources: retrieved hits with source_type, video_id, timestamp, content
    segments_by_video: every transcript segment of those videos, sorted by start
    """
    titles = titles or {}
    blocks = []  # (video_id, start, end, label, text)

    picked: Dict[str, set] = defaultdict(set)
    for hit in sources:
        if hit["source_type"] != "transcript":
            continue
        video = hit["video_id"]
        segments = segments_by_video.get(video, [])
        index = next(
            (i for i, seg in enumerate(segments) if abs(seg[0] - hit["timestamp"]) < 0.05), None
        )
        if index is None:   # not in the database any more: use the hit as retrieved
            blocks.append((video, hit["timestamp"], hit["timestamp"], "", hit["content"]))
        else:
            picked[video].update(range(max(0, index - neighbours), min(len(segments), index + neighbours + 1)))

    for video, indexes in picked.items():
        segments = segments_by_video[video]
        for run in _runs(sorted(indexes)):
            text = " ".join(segments[i][2].strip() for i in run)
            blocks.append((video, segments[run[0]][0], segments[run[-1]][1], "", text))

    for hit in sources:
        if hit["source_type"] == "scene" and (hit.get("content") or "").strip():
            blocks.append((hit["video_id"], hit["timestamp"], hit["timestamp"], "scene ", hit["content"]))

    blocks.sort(key=lambda b: (b[0] or "", b[1]))

    lines, used = [], 0
    for video, start, end, kind, text in blocks:
        name = titles.get(video, "video")
        where = f"{start:.0f}s" if end <= start else f"{start:.0f}s-{end:.0f}s"
        line = f"[{name} {kind}@ {where}]: {text}"
        if used + len(line) > max_chars and lines:
            break
        lines.append(line)
        used += len(line)
    return "\n\n".join(lines)
