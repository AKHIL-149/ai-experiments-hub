"""
Scene vector store for multi-modal embeddings
Aggregate visual and audio context for scene-level search
"""

import logging
from typing import List, Optional, Dict, Union, Any
from pathlib import Path
from dataclasses import dataclass
import numpy as np

from src.core.vector_store import VideoVectorStore, SearchResult

logger = logging.getLogger(__name__)


@dataclass
class SceneSearchResult:
    """Result from scene search"""
    video_id: str
    scene_ids: List[str]
    scene_numbers: List[int]
    start_times: List[float]
    end_times: List[float]
    durations: List[float]
    descriptions: List[Optional[str]]
    similarities: List[float]
    metadatas: List[Dict[str, Any]]
    total_results: int


class SceneVectorStore:
    """
    Manage scene-level multi-modal embeddings
    Combines visual, audio, and textual information
    """

    def __init__(self, persist_directory: Optional[Path] = None):
        """
        Initialize scene vector store

        Args:
            persist_directory: Directory for ChromaDB persistence
        """
        self.store = VideoVectorStore(persist_directory)
        self.store.initialize_collections()

        logger.info("Initialized SceneVectorStore")

    def add_video_scenes(
        self,
        video_id: str,
        scene_embeddings: np.ndarray,
        scene_numbers: List[int],
        start_times: List[float],
        end_times: List[float],
        descriptions: Optional[List[str]] = None,
        scene_types: Optional[List[str]] = None,
        transition_types: Optional[List[str]] = None,
        avg_frame_embeddings: Optional[np.ndarray] = None,
        transcript_summaries: Optional[List[str]] = None,
        num_frames: Optional[List[int]] = None,
        num_speakers: Optional[List[int]] = None,
        objects_present: Optional[List[List[str]]] = None,
        batch_size: int = 50,
    ):
        """
        Add scene embeddings for a video

        Args:
            video_id: Unique video identifier
            scene_embeddings: Scene embeddings (n_scenes x embedding_dim)
            scene_numbers: Scene numbers
            start_times: Scene start times in seconds
            end_times: Scene end times in seconds
            descriptions: Optional scene descriptions
            scene_types: Optional scene types (static, motion, dialogue, action)
            transition_types: Optional transition types (cut, fade, dissolve)
            avg_frame_embeddings: Optional average frame embeddings per scene
            transcript_summaries: Optional transcript summaries per scene
            num_frames: Optional number of frames per scene
            num_speakers: Optional number of speakers per scene
            objects_present: Optional objects detected in scene
            batch_size: Batch size for insertion
        """
        n_scenes = len(scene_embeddings)

        logger.info(f"Adding {n_scenes} scenes for video {video_id}")

        # Prepare timestamps as tuples
        scene_timestamps = list(zip(start_times, end_times))

        # Prepare metadata
        additional_metadata = []
        for i in range(n_scenes):
            meta = {}

            # Basic metrics
            duration = end_times[i] - start_times[i]
            meta["duration"] = duration

            if scene_types and i < len(scene_types):
                meta["scene_type"] = scene_types[i]

            if transition_types and i < len(transition_types):
                meta["transition_type"] = transition_types[i]

            if num_frames and i < len(num_frames):
                meta["num_frames"] = num_frames[i]

            if num_speakers and i < len(num_speakers):
                meta["num_speakers"] = num_speakers[i]

            if objects_present and i < len(objects_present):
                meta["objects"] = ",".join(objects_present[i])
                meta["num_objects"] = len(objects_present[i])

            if transcript_summaries and i < len(transcript_summaries):
                meta["transcript_summary"] = transcript_summaries[i]

            additional_metadata.append(meta)

        # Add in batches
        for batch_start in range(0, n_scenes, batch_size):
            batch_end = min(batch_start + batch_size, n_scenes)

            batch_embeddings = scene_embeddings[batch_start:batch_end]
            batch_numbers = scene_numbers[batch_start:batch_end]
            batch_timestamps = scene_timestamps[batch_start:batch_end]
            batch_descriptions = (
                descriptions[batch_start:batch_end] if descriptions else None
            )
            batch_metadata = additional_metadata[batch_start:batch_end]

            self.store.add_scene_embeddings(
                video_id=video_id,
                scene_embeddings=batch_embeddings,
                scene_numbers=batch_numbers,
                scene_timestamps=batch_timestamps,
                scene_descriptions=batch_descriptions,
                additional_metadata=batch_metadata,
            )

            logger.debug(
                f"Added batch {batch_start}-{batch_end} ({batch_end - batch_start} scenes)"
            )

        logger.info(f"Successfully added {n_scenes} scenes for video {video_id}")

    def create_aggregated_scene_embedding(
        self,
        frame_embeddings: np.ndarray,
        transcript_embedding: Optional[np.ndarray] = None,
        weights: Optional[Dict[str, float]] = None,
    ) -> np.ndarray:
        """
        Create aggregated scene embedding from frames and transcript

        Args:
            frame_embeddings: Frame embeddings for the scene (n_frames x dim)
            transcript_embedding: Transcript embedding for the scene
            weights: Optional weights for different modalities

        Returns:
            Aggregated scene embedding
        """
        # Default weights
        if weights is None:
            weights = {"visual": 0.6, "text": 0.4}

        # Aggregate frame embeddings (mean pooling)
        visual_embedding = np.mean(frame_embeddings, axis=0)

        # Normalize
        visual_embedding = visual_embedding / (np.linalg.norm(visual_embedding) + 1e-8)

        # Combine with transcript if available
        if transcript_embedding is not None:
            # Normalize transcript embedding
            transcript_embedding = transcript_embedding / (
                np.linalg.norm(transcript_embedding) + 1e-8
            )

            # Weighted combination
            scene_embedding = (
                weights["visual"] * visual_embedding +
                weights["text"] * transcript_embedding
            )
        else:
            scene_embedding = visual_embedding

        # Final normalization
        scene_embedding = scene_embedding / (np.linalg.norm(scene_embedding) + 1e-8)

        return scene_embedding

    def search_scenes(
        self,
        query_embedding: np.ndarray,
        n_results: int = 10,
        video_id: Optional[str] = None,
        min_duration: Optional[float] = None,
        max_duration: Optional[float] = None,
        scene_type: Optional[str] = None,
        has_speakers: Optional[bool] = None,
        min_frames: Optional[int] = None,
    ) -> SceneSearchResult:
        """
        Search for similar scenes

        Args:
            query_embedding: Query embedding
            n_results: Number of results to return
            video_id: Filter by specific video
            min_duration: Minimum scene duration
            max_duration: Maximum scene duration
            scene_type: Filter by scene type
            has_speakers: Filter scenes with/without speakers
            min_frames: Minimum number of frames

        Returns:
            SceneSearchResult with matched scenes
        """
        # Build metadata filter
        where = {}
        if video_id:
            where["video_id"] = video_id
        if scene_type:
            where["scene_type"] = scene_type
        if min_duration:
            where["duration"] = {"$gte": min_duration}
        if max_duration:
            if "duration" in where:
                where["duration"]["$lte"] = max_duration
            else:
                where["duration"] = {"$lte": max_duration}
        if has_speakers is not None:
            if has_speakers:
                where["num_speakers"] = {"$gt": 0}
            else:
                where["num_speakers"] = 0
        if min_frames:
            where["num_frames"] = {"$gte": min_frames}

        # Search using store
        results = self.store.search_scenes(
            query_embedding=query_embedding,
            n_results=n_results,
            video_id=video_id,
            min_duration=min_duration,
        )

        # Parse results
        scene_ids = results.ids
        metadatas = results.metadatas
        descriptions = results.documents or [None] * len(scene_ids)
        similarities = [1 - dist for dist in results.distances]

        # Extract fields
        video_ids = [m.get("video_id", "") for m in metadatas]
        scene_numbers = [m.get("scene_number", 0) for m in metadatas]
        start_times = [m.get("start_time", 0.0) for m in metadatas]
        end_times = [m.get("end_time", 0.0) for m in metadatas]
        durations = [m.get("duration", 0.0) for m in metadatas]

        # Get video_id
        result_video_id = video_id or (video_ids[0] if video_ids else "")

        return SceneSearchResult(
            video_id=result_video_id,
            scene_ids=scene_ids,
            scene_numbers=scene_numbers,
            start_times=start_times,
            end_times=end_times,
            durations=durations,
            descriptions=descriptions,
            similarities=similarities,
            metadatas=metadatas,
            total_results=len(scene_ids),
        )

    def search_scenes_by_text(
        self,
        text_query: str,
        text_embedder,
        n_results: int = 10,
        **kwargs,
    ) -> SceneSearchResult:
        """
        Search scenes using text query

        Args:
            text_query: Natural language query
            text_embedder: Text embedding model
            n_results: Number of results
            **kwargs: Additional search filters

        Returns:
            SceneSearchResult
        """
        # Generate text embedding
        query_embedding = text_embedder.embed_text(text_query).embedding

        # Search with embedding
        return self.search_scenes(
            query_embedding=query_embedding,
            n_results=n_results,
            **kwargs,
        )

    def get_scene_by_number(
        self,
        video_id: str,
        scene_number: int,
    ) -> Dict[str, Any]:
        """
        Get a specific scene by number

        Args:
            video_id: Video identifier
            scene_number: Scene number

        Returns:
            Scene data
        """
        where = {
            "video_id": video_id,
            "scene_number": scene_number,
        }

        self.store.collection = self.store.scenes_collection
        results = self.store.get_embeddings(where=where)

        return results

    def get_scenes_in_range(
        self,
        video_id: str,
        start_time: float,
        end_time: float,
    ) -> Dict[str, Any]:
        """
        Get scenes overlapping a time range

        Args:
            video_id: Video identifier
            start_time: Start time in seconds
            end_time: End time in seconds

        Returns:
            Scene data
        """
        where = {
            "video_id": video_id,
            "start_time": {"$lte": end_time},
            "end_time": {"$gte": start_time},
        }

        self.store.collection = self.store.scenes_collection
        results = self.store.get_embeddings(where=where)

        return results

    def get_scenes_by_type(
        self,
        video_id: str,
        scene_type: str,
    ) -> Dict[str, Any]:
        """
        Get all scenes of a specific type

        Args:
            video_id: Video identifier
            scene_type: Scene type (static, motion, dialogue, action)

        Returns:
            Scene data
        """
        where = {
            "video_id": video_id,
            "scene_type": scene_type,
        }

        self.store.collection = self.store.scenes_collection
        results = self.store.get_embeddings(where=where)

        return results

    def find_similar_scenes(
        self,
        video_id: str,
        scene_number: int,
        n_results: int = 10,
        same_video_only: bool = True,
    ) -> SceneSearchResult:
        """
        Find scenes similar to a given scene

        Args:
            video_id: Video containing source scene
            scene_number: Scene number to match
            n_results: Number of similar scenes
            same_video_only: Only search within same video

        Returns:
            SceneSearchResult with similar scenes
        """
        # Get source scene embedding
        scene_id = f"{video_id}_scene_{scene_number}"

        self.store.collection = self.store.scenes_collection
        scene_data = self.store.get_embeddings(ids=[scene_id])

        if not scene_data["embeddings"]:
            raise ValueError(f"Scene {scene_id} not found")

        source_embedding = np.array(scene_data["embeddings"][0])

        # Search for similar scenes
        filter_video_id = video_id if same_video_only else None

        return self.search_scenes(
            query_embedding=source_embedding,
            n_results=n_results + 1,  # +1 for source scene
            video_id=filter_video_id,
        )

    def get_longest_scenes(
        self,
        video_id: str,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Get longest scenes in a video

        Args:
            video_id: Video identifier
            top_k: Number of scenes to return

        Returns:
            List of scenes sorted by duration
        """
        where = {"video_id": video_id}

        self.store.collection = self.store.scenes_collection
        results = self.store.get_embeddings(where=where, include=["metadatas"])

        # Sort by duration
        scenes_with_duration = []
        for i, meta in enumerate(results["metadatas"]):
            scenes_with_duration.append({
                "scene_number": meta.get("scene_number"),
                "start_time": meta.get("start_time"),
                "end_time": meta.get("end_time"),
                "duration": meta.get("duration", 0.0),
                "scene_type": meta.get("scene_type"),
            })

        scenes_with_duration.sort(key=lambda x: x["duration"], reverse=True)

        return scenes_with_duration[:top_k]

    def update_scene_metadata(
        self,
        video_id: str,
        scene_number: int,
        metadata: Dict[str, Any],
    ):
        """
        Update metadata for a scene

        Args:
            video_id: Video identifier
            scene_number: Scene number
            metadata: New metadata to add/update
        """
        scene_id = f"{video_id}_scene_{scene_number}"

        # Get existing metadata
        self.store.collection = self.store.scenes_collection
        scene_data = self.store.get_embeddings(ids=[scene_id])

        if not scene_data["metadatas"]:
            raise ValueError(f"Scene {scene_id} not found")

        # Update metadata
        existing_meta = scene_data["metadatas"][0]
        existing_meta.update(metadata)

        # Save
        self.store.update_metadata(ids=[scene_id], metadatas=[existing_meta])

        logger.info(f"Updated metadata for scene {scene_id}")

    def delete_video_scenes(self, video_id: str):
        """
        Delete all scenes for a video

        Args:
            video_id: Video identifier
        """
        where = {"video_id": video_id}

        self.store.collection = self.store.scenes_collection
        self.store.delete_embeddings(where=where)

        logger.info(f"Deleted scenes for video {video_id}")

    def count_video_scenes(self, video_id: str) -> int:
        """
        Count scenes for a video

        Args:
            video_id: Video identifier

        Returns:
            Number of scenes
        """
        self.store.collection = self.store.scenes_collection
        scenes = self.store.get_embeddings(
            where={"video_id": video_id},
            include=[],
        )

        return len(scenes["ids"])

    def get_scene_statistics(self, video_id: str) -> Dict[str, Any]:
        """
        Get statistics about scenes for a video

        Args:
            video_id: Video identifier

        Returns:
            Dictionary with statistics
        """
        self.store.collection = self.store.scenes_collection
        scenes = self.store.get_embeddings(
            where={"video_id": video_id},
            include=["metadatas"],
        )

        if not scenes["metadatas"]:
            return {"count": 0}

        durations = [m.get("duration", 0.0) for m in scenes["metadatas"]]
        scene_types = [m.get("scene_type") for m in scenes["metadatas"]]
        num_frames = [m.get("num_frames", 0) for m in scenes["metadatas"]]
        num_speakers = [m.get("num_speakers", 0) for m in scenes["metadatas"]]

        stats = {
            "count": len(scenes["ids"]),
            "total_duration": sum(durations),
            "avg_duration": sum(durations) / len(durations) if durations else 0,
            "min_duration": min(durations) if durations else 0,
            "max_duration": max(durations) if durations else 0,
        }

        # Scene type distribution
        if scene_types:
            type_counts = {}
            for st in scene_types:
                if st:
                    type_counts[st] = type_counts.get(st, 0) + 1
            stats["scene_type_distribution"] = type_counts

        # Frame statistics
        if num_frames:
            stats["avg_frames_per_scene"] = sum(num_frames) / len(num_frames)

        # Speaker statistics
        if num_speakers:
            stats["scenes_with_speakers"] = sum(1 for n in num_speakers if n > 0)

        return stats

    def export_scene_index(
        self,
        video_id: str,
        output_path: Path,
    ):
        """
        Export scene embeddings and metadata

        Args:
            video_id: Video identifier
            output_path: Path to save export
        """
        import pickle

        self.store.collection = self.store.scenes_collection
        scenes = self.store.get_embeddings(
            where={"video_id": video_id},
            include=["embeddings", "metadatas", "documents"],
        )

        export_data = {
            "video_id": video_id,
            "embeddings": np.array(scenes["embeddings"]),
            "metadatas": scenes["metadatas"],
            "descriptions": scenes["documents"],
            "scene_ids": scenes["ids"],
        }

        with open(output_path, "wb") as f:
            pickle.dump(export_data, f)

        logger.info(f"Exported {len(scenes['ids'])} scenes to {output_path}")

    def import_scene_index(
        self,
        input_path: Path,
        overwrite: bool = False,
    ):
        """
        Import scene embeddings and metadata

        Args:
            input_path: Path to import from
            overwrite: Overwrite existing scenes
        """
        import pickle

        with open(input_path, "rb") as f:
            import_data = pickle.load(f)

        video_id = import_data["video_id"]
        embeddings = import_data["embeddings"]
        metadatas = import_data["metadatas"]
        descriptions = import_data.get("descriptions")

        # Extract fields
        scene_numbers = [m["scene_number"] for m in metadatas]
        start_times = [m["start_time"] for m in metadatas]
        end_times = [m["end_time"] for m in metadatas]

        # Add scenes
        if overwrite:
            self.delete_video_scenes(video_id)

        self.add_video_scenes(
            video_id=video_id,
            scene_embeddings=embeddings,
            scene_numbers=scene_numbers,
            start_times=start_times,
            end_times=end_times,
            descriptions=descriptions,
        )

        logger.info(f"Imported {len(embeddings)} scenes from {input_path}")


def add_scenes_to_vector_store(
    video_id: str,
    scene_embeddings: np.ndarray,
    scene_numbers: List[int],
    start_times: List[float],
    end_times: List[float],
    persist_directory: Optional[Path] = None,
    **kwargs,
) -> SceneVectorStore:
    """
    Convenience function to add scenes to vector store

    Args:
        video_id: Video identifier
        scene_embeddings: Scene embeddings
        scene_numbers: Scene numbers
        start_times: Start times
        end_times: End times
        persist_directory: ChromaDB directory
        **kwargs: Additional metadata

    Returns:
        SceneVectorStore instance
    """
    store = SceneVectorStore(persist_directory)

    store.add_video_scenes(
        video_id=video_id,
        scene_embeddings=scene_embeddings,
        scene_numbers=scene_numbers,
        start_times=start_times,
        end_times=end_times,
        **kwargs,
    )

    return store
