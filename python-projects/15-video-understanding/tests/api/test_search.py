"""
Tests for video search API endpoints
"""

import pytest
from contextlib import contextmanager
from unittest.mock import Mock, MagicMock, patch
import numpy as np


def _mock_get_db(mock_session):
    """Build a get_db() replacement usable as `with get_db() as db: ...`"""
    @contextmanager
    def _get_db():
        yield mock_session
    return _get_db


def _mock_db_session(video_rows=None, frame_rows=None):
    """MagicMock DB session whose .query(Model) dispatches by model name,
    matching the pattern used across tests/api/test_videos.py."""
    session = MagicMock()

    def query_side_effect(model):
        name = getattr(model, "__name__", "")
        q = MagicMock()
        if name == "Video":
            q.filter.return_value.all.return_value = video_rows or []
        elif name == "Frame":
            q.filter.return_value.all.return_value = frame_rows or []
        else:
            q.filter.return_value.all.return_value = []
        return q

    session.query.side_effect = query_side_effect
    return session


class TestFrameSearchThreshold:
    """Regression tests for the CLIP min_similarity default"""

    def test_default_min_similarity_is_realistic_for_clip_cross_modal_scores(self):
        """Real CLIP text<->image cosine similarity against genuinely
        processed video frames tops out around 0.29 for a correct match
        (checked directly: a "whiteboard" query against a frame captioned
        "a man is writing on a blackboard" scored ~0.286) and a
        deliberately nonsensical query still scored ~0.22. A same-modality
        threshold like 0.6 (copied from the sentence-transformer text
        search convention) is unreachable here and silently zeroed out
        every real result regardless of query - confirmed live."""
        from src.api.search import FrameSearchRequest

        default_min_similarity = FrameSearchRequest.model_fields["min_similarity"].default
        assert default_min_similarity <= 0.3

    @pytest.mark.asyncio
    async def test_realistic_clip_scores_are_not_filtered_out_by_default(self):
        """End-to-end regression: with the *default* request (no explicit
        min_similarity override), a hit scored at a realistic CLIP
        cross-modal similarity must survive the threshold filter and be
        returned - this is exactly the case that was silently broken."""
        from src.api.search import search_frames, FrameSearchRequest
        from src.core.vector_store import SearchResult

        realistic_similarity = 0.24  # matches the real "person" query score
        distance = 1.0 - realistic_similarity

        mock_hits = SearchResult(
            ids=["frame_1"],
            distances=[distance],
            metadatas=[{
                "video_id": "video-abc",
                "frame_number": 10,
                "timestamp": 5.0,
                "frame_path": "storage/frames/video-abc/keyframes/scene_001.jpg",
                "scene_id": 1,
                "description": "a man standing in front of a whiteboard",
                "frame_db_id": None,
            }],
        )

        mock_video = Mock(external_id="video-abc", title="Test Video")
        mock_db = _mock_db_session(video_rows=[mock_video])

        mock_clip_model = Mock()
        mock_clip_model.encode_text.return_value = np.zeros(512)

        mock_store = Mock()
        mock_store.search_frames.return_value = mock_hits

        with patch("src.core.database.get_db", _mock_get_db(mock_db)), \
             patch("src.api.videos._get_clip_model", return_value=mock_clip_model), \
             patch("src.core.vector_store.VideoVectorStore", return_value=mock_store):

            response = await search_frames(FrameSearchRequest(query="whiteboard"))

        assert response.total_results == 1
        assert response.results[0].similarity_score == pytest.approx(realistic_similarity, abs=1e-4)

    @pytest.mark.asyncio
    async def test_min_similarity_still_filters_when_explicitly_raised(self):
        """The threshold isn't removed, just recalibrated - an explicit,
        higher min_similarity should still filter results out."""
        from src.api.search import search_frames, FrameSearchRequest
        from src.core.vector_store import SearchResult

        mock_hits = SearchResult(
            ids=["frame_1"],
            distances=[1.0 - 0.24],
            metadatas=[{
                "video_id": "video-abc",
                "frame_number": 10,
                "timestamp": 5.0,
                "frame_path": "storage/frames/video-abc/keyframes/scene_001.jpg",
                "scene_id": 1,
                "description": "a man standing in front of a whiteboard",
                "frame_db_id": None,
            }],
        )

        mock_db = _mock_db_session()
        mock_clip_model = Mock()
        mock_clip_model.encode_text.return_value = np.zeros(512)
        mock_store = Mock()
        mock_store.search_frames.return_value = mock_hits

        with patch("src.core.database.get_db", _mock_get_db(mock_db)), \
             patch("src.api.videos._get_clip_model", return_value=mock_clip_model), \
             patch("src.core.vector_store.VideoVectorStore", return_value=mock_store):

            response = await search_frames(FrameSearchRequest(query="whiteboard", min_similarity=0.9))

        assert response.total_results == 0
