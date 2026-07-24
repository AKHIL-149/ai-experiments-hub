"""
Multi-modal vector retriever
Unified search across frames, transcripts, and scenes
"""

import logging
from typing import List, Optional, Dict, Union, Any
from pathlib import Path
from dataclasses import dataclass, field
import numpy as np

from src.services.vector.frame_store import FrameVectorStore, FrameSearchResult
from src.services.vector.transcript_store import (
    TranscriptVectorStore,
    TranscriptSearchResult,
)
from src.services.vector.scene_store import SceneVectorStore, SceneSearchResult

logger = logging.getLogger(__name__)


@dataclass
class MultiModalResult:
    """Unified result from multi-modal search"""
    video_id: str
    result_type: str  # 'frame', 'transcript', 'scene', 'combined'
    items: List[Dict[str, Any]]
    scores: List[float]
    total_results: int
    search_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RankedResult:
    """Result with fusion ranking"""
    item_id: str
    item_type: str  # 'frame', 'transcript', 'scene'
    score: float
    timestamp: Optional[float] = None
    time_range: Optional[tuple] = None
    content: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class MultiModalVectorRetriever:
    """
    Unified retrieval across multiple vector stores
    Supports hybrid search and result fusion
    """

    def __init__(self, persist_directory: Optional[Path] = None):
        """
        Initialize multi-modal retriever

        Args:
            persist_directory: Directory for ChromaDB persistence
        """
        self.persist_directory = persist_directory

        # Initialize stores
        self.frame_store = FrameVectorStore(persist_directory)
        self.transcript_store = TranscriptVectorStore(persist_directory)
        self.scene_store = SceneVectorStore(persist_directory)

        logger.info("Initialized MultiModalVectorRetriever")

    def search_all_modalities(
        self,
        query_embedding: np.ndarray,
        n_results_per_modality: int = 10,
        video_id: Optional[str] = None,
        modalities: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Search across all modalities

        Args:
            query_embedding: Query embedding
            n_results_per_modality: Results per modality
            video_id: Filter by video
            modalities: Specific modalities to search (default: all)

        Returns:
            Dictionary with results from each modality
        """
        if modalities is None:
            modalities = ["frames", "transcripts", "scenes"]

        results = {}

        # Search frames
        if "frames" in modalities:
            try:
                frame_results = self.frame_store.search_frames(
                    query_embedding=query_embedding,
                    n_results=n_results_per_modality,
                    video_id=video_id,
                )
                results["frames"] = frame_results
            except Exception as e:
                logger.warning(f"Frame search failed: {e}")
                results["frames"] = None

        # Search transcripts
        if "transcripts" in modalities:
            try:
                transcript_results = self.transcript_store.search_transcripts(
                    query_embedding=query_embedding,
                    n_results=n_results_per_modality,
                    video_id=video_id,
                )
                results["transcripts"] = transcript_results
            except Exception as e:
                logger.warning(f"Transcript search failed: {e}")
                results["transcripts"] = None

        # Search scenes
        if "scenes" in modalities:
            try:
                scene_results = self.scene_store.search_scenes(
                    query_embedding=query_embedding,
                    n_results=n_results_per_modality,
                    video_id=video_id,
                )
                results["scenes"] = scene_results
            except Exception as e:
                logger.warning(f"Scene search failed: {e}")
                results["scenes"] = None

        return results

    def hybrid_search(
        self,
        visual_embedding: Optional[np.ndarray] = None,
        text_embedding: Optional[np.ndarray] = None,
        n_results: int = 20,
        video_id: Optional[str] = None,
        weights: Optional[Dict[str, float]] = None,
        fusion_method: str = "rrf",  # reciprocal rank fusion or weighted
    ) -> MultiModalResult:
        """
        Hybrid search combining visual and text embeddings

        Args:
            visual_embedding: Visual query embedding (for frames/scenes)
            text_embedding: Text query embedding (for transcripts/scenes)
            n_results: Total results to return
            video_id: Filter by video
            weights: Weights for different modalities
            fusion_method: Method for fusing results (rrf, weighted, borda)

        Returns:
            MultiModalResult with fused results
        """
        if weights is None:
            weights = {
                "frames": 0.4,
                "transcripts": 0.3,
                "scenes": 0.3,
            }

        all_results = []

        # Search with visual embedding
        if visual_embedding is not None:
            # Search frames
            try:
                frame_results = self.frame_store.search_frames(
                    query_embedding=visual_embedding,
                    n_results=n_results * 2,  # Get more for fusion
                    video_id=video_id,
                )

                # Convert to ranked results
                for i, (fid, score, timestamp, meta) in enumerate(
                    zip(
                        frame_results.frame_ids,
                        frame_results.similarities,
                        frame_results.timestamps,
                        frame_results.metadatas,
                    )
                ):
                    all_results.append(
                        RankedResult(
                            item_id=fid,
                            item_type="frame",
                            score=score * weights["frames"],
                            timestamp=timestamp,
                            metadata=meta,
                        )
                    )
            except Exception as e:
                logger.warning(f"Visual frame search failed: {e}")

        # Search with text embedding
        if text_embedding is not None:
            # Search transcripts
            try:
                transcript_results = self.transcript_store.search_transcripts(
                    query_embedding=text_embedding,
                    n_results=n_results * 2,
                    video_id=video_id,
                )

                for i, (sid, score, text, start, end, meta) in enumerate(
                    zip(
                        transcript_results.segment_ids,
                        transcript_results.similarities,
                        transcript_results.texts,
                        transcript_results.start_times,
                        transcript_results.end_times,
                        transcript_results.metadatas,
                    )
                ):
                    all_results.append(
                        RankedResult(
                            item_id=sid,
                            item_type="transcript",
                            score=score * weights["transcripts"],
                            time_range=(start, end),
                            content=text,
                            metadata=meta,
                        )
                    )
            except Exception as e:
                logger.warning(f"Text transcript search failed: {e}")

        # Search scenes with combined embedding
        if visual_embedding is not None or text_embedding is not None:
            # Combine embeddings if both available
            if visual_embedding is not None and text_embedding is not None:
                scene_embedding = (
                    0.6 * visual_embedding + 0.4 * text_embedding
                )
                scene_embedding = scene_embedding / (
                    np.linalg.norm(scene_embedding) + 1e-8
                )
            elif visual_embedding is not None:
                scene_embedding = visual_embedding
            else:
                scene_embedding = text_embedding

            try:
                scene_results = self.scene_store.search_scenes(
                    query_embedding=scene_embedding,
                    n_results=n_results * 2,
                    video_id=video_id,
                )

                for i, (scid, score, start, end, desc, meta) in enumerate(
                    zip(
                        scene_results.scene_ids,
                        scene_results.similarities,
                        scene_results.start_times,
                        scene_results.end_times,
                        scene_results.descriptions,
                        scene_results.metadatas,
                    )
                ):
                    all_results.append(
                        RankedResult(
                            item_id=scid,
                            item_type="scene",
                            score=score * weights["scenes"],
                            time_range=(start, end),
                            content=desc,
                            metadata=meta,
                        )
                    )
            except Exception as e:
                logger.warning(f"Scene search failed: {e}")

        # Fuse results
        fused_results = self._fuse_results(
            all_results, n_results, method=fusion_method
        )

        # Convert to MultiModalResult
        items = []
        scores = []

        for result in fused_results:
            item = {
                "item_id": result.item_id,
                "item_type": result.item_type,
                "score": result.score,
                "timestamp": result.timestamp,
                "time_range": result.time_range,
                "content": result.content,
                "metadata": result.metadata,
            }
            items.append(item)
            scores.append(result.score)

        return MultiModalResult(
            video_id=video_id or "all",
            result_type="combined",
            items=items,
            scores=scores,
            total_results=len(items),
            search_metadata={
                "fusion_method": fusion_method,
                "weights": weights,
            },
        )

    def _fuse_results(
        self,
        results: List[RankedResult],
        top_k: int,
        method: str = "rrf",
    ) -> List[RankedResult]:
        """
        Fuse results from multiple sources

        Args:
            results: List of ranked results
            top_k: Number of top results
            method: Fusion method (rrf, weighted, borda)

        Returns:
            Fused and re-ranked results
        """
        if method == "weighted":
            # Simple weighted score fusion
            results.sort(key=lambda x: x.score, reverse=True)
            return results[:top_k]

        elif method == "rrf":
            # Reciprocal Rank Fusion
            k = 60  # RRF constant

            # Group by item type
            type_groups = {}
            for result in results:
                if result.item_type not in type_groups:
                    type_groups[result.item_type] = []
                type_groups[result.item_type].append(result)

            # Sort each group by score
            for item_type in type_groups:
                type_groups[item_type].sort(key=lambda x: x.score, reverse=True)

            # Compute RRF scores
            rrf_scores = {}
            for item_type, group in type_groups.items():
                for rank, result in enumerate(group):
                    if result.item_id not in rrf_scores:
                        rrf_scores[result.item_id] = {
                            "score": 0,
                            "result": result,
                        }

                    rrf_scores[result.item_id]["score"] += 1 / (k + rank + 1)

            # Sort by RRF score
            sorted_items = sorted(
                rrf_scores.values(),
                key=lambda x: x["score"],
                reverse=True,
            )

            # Extract results
            fused = []
            for item in sorted_items[:top_k]:
                result = item["result"]
                result.score = item["score"]  # Update with RRF score
                fused.append(result)

            return fused

        elif method == "borda":
            # Borda count fusion
            # Group by type and rank
            type_groups = {}
            for result in results:
                if result.item_type not in type_groups:
                    type_groups[result.item_type] = []
                type_groups[result.item_type].append(result)

            # Sort each group
            for item_type in type_groups:
                type_groups[item_type].sort(key=lambda x: x.score, reverse=True)

            # Compute Borda scores
            borda_scores = {}
            for item_type, group in type_groups.items():
                n = len(group)
                for rank, result in enumerate(group):
                    if result.item_id not in borda_scores:
                        borda_scores[result.item_id] = {
                            "score": 0,
                            "result": result,
                        }

                    # Borda count: n - rank
                    borda_scores[result.item_id]["score"] += (n - rank)

            # Sort by Borda score
            sorted_items = sorted(
                borda_scores.values(),
                key=lambda x: x["score"],
                reverse=True,
            )

            fused = []
            for item in sorted_items[:top_k]:
                result = item["result"]
                result.score = item["score"]
                fused.append(result)

            return fused

        else:
            raise ValueError(f"Unknown fusion method: {method}")

    def temporal_search(
        self,
        query_embedding: np.ndarray,
        video_id: str,
        time_window: float = 5.0,
        n_results: int = 10,
    ) -> MultiModalResult:
        """
        Search within temporal context

        Args:
            query_embedding: Query embedding
            video_id: Video identifier
            time_window: Time window in seconds
            n_results: Number of results

        Returns:
            MultiModalResult with temporally grouped results
        """
        # Search all modalities
        all_results_dict = self.search_all_modalities(
            query_embedding=query_embedding,
            n_results_per_modality=n_results * 2,
            video_id=video_id,
        )

        # Extract timestamps/time ranges
        all_results = []

        # Frames
        if all_results_dict.get("frames"):
            frame_res = all_results_dict["frames"]
            for i, (fid, score, ts, meta) in enumerate(
                zip(
                    frame_res.frame_ids,
                    frame_res.similarities,
                    frame_res.timestamps,
                    frame_res.metadatas,
                )
            ):
                all_results.append(
                    RankedResult(
                        item_id=fid,
                        item_type="frame",
                        score=score,
                        timestamp=ts,
                        metadata=meta,
                    )
                )

        # Transcripts
        if all_results_dict.get("transcripts"):
            trans_res = all_results_dict["transcripts"]
            for i, (sid, score, text, start, end, meta) in enumerate(
                zip(
                    trans_res.segment_ids,
                    trans_res.similarities,
                    trans_res.texts,
                    trans_res.start_times,
                    trans_res.end_times,
                    trans_res.metadatas,
                )
            ):
                all_results.append(
                    RankedResult(
                        item_id=sid,
                        item_type="transcript",
                        score=score,
                        time_range=(start, end),
                        content=text,
                        metadata=meta,
                    )
                )

        # Scenes
        if all_results_dict.get("scenes"):
            scene_res = all_results_dict["scenes"]
            for i, (scid, score, start, end, desc, meta) in enumerate(
                zip(
                    scene_res.scene_ids,
                    scene_res.similarities,
                    scene_res.start_times,
                    scene_res.end_times,
                    scene_res.descriptions,
                    scene_res.metadatas,
                )
            ):
                all_results.append(
                    RankedResult(
                        item_id=scid,
                        item_type="scene",
                        score=score,
                        time_range=(start, end),
                        content=desc,
                        metadata=meta,
                    )
                )

        # Group by temporal proximity
        temporal_groups = self._group_temporal_results(
            all_results, time_window
        )

        # Take top groups by best score
        temporal_groups.sort(
            key=lambda g: max(r.score for r in g),
            reverse=True,
        )

        # Flatten top groups
        top_results = []
        for group in temporal_groups[:n_results]:
            top_results.extend(group)

        # Convert to result items
        items = []
        scores = []

        for result in top_results:
            item = {
                "item_id": result.item_id,
                "item_type": result.item_type,
                "score": result.score,
                "timestamp": result.timestamp,
                "time_range": result.time_range,
                "content": result.content,
                "metadata": result.metadata,
            }
            items.append(item)
            scores.append(result.score)

        return MultiModalResult(
            video_id=video_id,
            result_type="temporal",
            items=items,
            scores=scores,
            total_results=len(items),
            search_metadata={"time_window": time_window},
        )

    def _group_temporal_results(
        self,
        results: List[RankedResult],
        time_window: float,
    ) -> List[List[RankedResult]]:
        """
        Group results by temporal proximity

        Args:
            results: List of results with timestamps
            time_window: Time window for grouping

        Returns:
            List of result groups
        """
        # Extract representative timestamps
        timestamped_results = []
        for result in results:
            if result.timestamp is not None:
                ts = result.timestamp
            elif result.time_range is not None:
                ts = (result.time_range[0] + result.time_range[1]) / 2
            else:
                continue

            timestamped_results.append((ts, result))

        # Sort by timestamp
        timestamped_results.sort(key=lambda x: x[0])

        # Group by proximity
        groups = []
        current_group = []
        current_start = None

        for ts, result in timestamped_results:
            if current_start is None:
                current_start = ts
                current_group = [result]
            elif ts - current_start <= time_window:
                current_group.append(result)
            else:
                groups.append(current_group)
                current_start = ts
                current_group = [result]

        # Add last group
        if current_group:
            groups.append(current_group)

        return groups

    def get_comprehensive_context(
        self,
        video_id: str,
        timestamp: float,
        context_window: float = 10.0,
    ) -> Dict[str, Any]:
        """
        Get comprehensive multi-modal context around a timestamp

        Args:
            video_id: Video identifier
            timestamp: Target timestamp
            context_window: Time window around timestamp

        Returns:
            Dictionary with all context
        """
        start_time = max(0, timestamp - context_window / 2)
        end_time = timestamp + context_window / 2

        context = {
            "video_id": video_id,
            "timestamp": timestamp,
            "context_window": (start_time, end_time),
        }

        # Get frames
        try:
            frames = self.frame_store.get_frames_in_range(
                video_id=video_id,
                start_time=start_time,
                end_time=end_time,
            )
            context["frames"] = frames
        except Exception as e:
            logger.warning(f"Failed to get frames: {e}")

        # Get transcripts
        try:
            transcripts = self.transcript_store.get_transcript_in_range(
                video_id=video_id,
                start_time=start_time,
                end_time=end_time,
            )
            context["transcripts"] = transcripts
        except Exception as e:
            logger.warning(f"Failed to get transcripts: {e}")

        # Get scenes
        try:
            scenes = self.scene_store.get_scenes_in_range(
                video_id=video_id,
                start_time=start_time,
                end_time=end_time,
            )
            context["scenes"] = scenes
        except Exception as e:
            logger.warning(f"Failed to get scenes: {e}")

        return context

    def delete_all_video_data(self, video_id: str):
        """
        Delete all embeddings for a video across all stores

        Args:
            video_id: Video identifier
        """
        self.frame_store.delete_video_frames(video_id)
        self.transcript_store.delete_video_transcript(video_id)
        self.scene_store.delete_video_scenes(video_id)

        logger.info(f"Deleted all data for video {video_id}")

    def get_video_statistics(self, video_id: str) -> Dict[str, Any]:
        """
        Get statistics across all stores for a video

        Args:
            video_id: Video identifier

        Returns:
            Comprehensive statistics
        """
        stats = {
            "video_id": video_id,
            "frames": self.frame_store.get_frame_statistics(video_id),
            "transcripts": self.transcript_store.get_transcript_statistics(video_id),
            "scenes": self.scene_store.get_scene_statistics(video_id),
        }

        return stats
