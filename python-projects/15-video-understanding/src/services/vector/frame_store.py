"""
Frame vector store for CLIP embeddings
Efficient storage and retrieval of frame embeddings
"""

import logging
from typing import List, Optional, Dict, Union, Any
from pathlib import Path
from dataclasses import dataclass
import numpy as np

from src.core.vector_store import VideoVectorStore, SearchResult

logger = logging.getLogger(__name__)


@dataclass
class FrameSearchResult:
    """Result from frame search"""
    video_id: str
    frame_ids: List[str]
    frame_numbers: List[int]
    timestamps: List[float]
    frame_paths: List[str]
    similarities: List[float]
    metadatas: List[Dict[str, Any]]
    total_results: int


class FrameVectorStore:
    """
    Manage frame CLIP embeddings in vector store
    Optimized for fast frame retrieval and search
    """

    def __init__(self, persist_directory: Optional[Path] = None):
        """
        Initialize frame vector store

        Args:
            persist_directory: Directory for ChromaDB persistence
        """
        self.store = VideoVectorStore(persist_directory)
        self.store.initialize_collections()

        logger.info("Initialized FrameVectorStore")

    def add_video_frames(
        self,
        video_id: str,
        frame_embeddings: np.ndarray,
        frame_numbers: List[int],
        timestamps: List[float],
        frame_paths: Optional[List[str]] = None,
        scene_ids: Optional[List[int]] = None,
        descriptions: Optional[List[str]] = None,
        objects_detected: Optional[List[List[str]]] = None,
        batch_size: int = 100,
    ):
        """
        Add frame embeddings for a video

        Args:
            video_id: Unique video identifier
            frame_embeddings: Frame CLIP embeddings (n_frames x embedding_dim)
            frame_numbers: Frame numbers
            timestamps: Frame timestamps in seconds
            frame_paths: Optional paths to frame image files
            scene_ids: Optional scene IDs for each frame
            descriptions: Optional frame descriptions
            objects_detected: Optional lists of detected objects per frame
            batch_size: Batch size for insertion
        """
        n_frames = len(frame_embeddings)

        logger.info(f"Adding {n_frames} frames for video {video_id}")

        # Prepare metadata
        additional_metadata = []
        for i in range(n_frames):
            meta = {}

            if scene_ids and i < len(scene_ids):
                meta["scene_id"] = scene_ids[i]

            if descriptions and i < len(descriptions):
                meta["description"] = descriptions[i]

            if objects_detected and i < len(objects_detected):
                meta["objects"] = ",".join(objects_detected[i])
                meta["num_objects"] = len(objects_detected[i])

            additional_metadata.append(meta)

        # Add in batches
        for batch_start in range(0, n_frames, batch_size):
            batch_end = min(batch_start + batch_size, n_frames)

            batch_embeddings = frame_embeddings[batch_start:batch_end]
            batch_numbers = frame_numbers[batch_start:batch_end]
            batch_timestamps = timestamps[batch_start:batch_end]
            batch_paths = (
                frame_paths[batch_start:batch_end] if frame_paths else None
            )
            batch_metadata = additional_metadata[batch_start:batch_end]

            self.store.add_frame_embeddings(
                video_id=video_id,
                frame_embeddings=batch_embeddings,
                frame_numbers=batch_numbers,
                timestamps=batch_timestamps,
                frame_paths=batch_paths,
                additional_metadata=batch_metadata,
            )

            logger.debug(
                f"Added batch {batch_start}-{batch_end} ({batch_end - batch_start} frames)"
            )

        logger.info(f"Successfully added {n_frames} frames for video {video_id}")

    def search_frames(
        self,
        query_embedding: np.ndarray,
        n_results: int = 10,
        video_id: Optional[str] = None,
        time_range: Optional[tuple] = None,
        scene_id: Optional[int] = None,
        min_objects: Optional[int] = None,
    ) -> FrameSearchResult:
        """
        Search for similar frames

        Args:
            query_embedding: Query CLIP embedding
            n_results: Number of results to return
            video_id: Filter by specific video
            time_range: Filter by time range (start, end) in seconds
            scene_id: Filter by scene ID
            min_objects: Minimum number of detected objects

        Returns:
            FrameSearchResult with matched frames
        """
        # Build metadata filter
        where = {}
        if video_id:
            where["video_id"] = video_id
        if scene_id is not None:
            where["scene_id"] = scene_id
        if min_objects is not None:
            where["num_objects"] = {"$gte": min_objects}

        # Search using store
        results = self.store.search_frames(
            query_embedding=query_embedding,
            n_results=n_results,
            video_id=video_id,
            time_range=time_range,
        )

        # Parse results
        frame_ids = results.ids
        metadatas = results.metadatas
        similarities = [1 - dist for dist in results.distances]  # Convert distance to similarity

        # Extract fields
        video_ids = [m.get("video_id", "") for m in metadatas]
        frame_numbers = [m.get("frame_number", 0) for m in metadatas]
        timestamps = [m.get("timestamp", 0.0) for m in metadatas]
        frame_paths = [m.get("frame_path", "") for m in metadatas]

        # Use first video_id if not filtered
        result_video_id = video_id or (video_ids[0] if video_ids else "")

        return FrameSearchResult(
            video_id=result_video_id,
            frame_ids=frame_ids,
            frame_numbers=frame_numbers,
            timestamps=timestamps,
            frame_paths=frame_paths,
            similarities=similarities,
            metadatas=metadatas,
            total_results=len(frame_ids),
        )

    def search_frames_by_text(
        self,
        text_query: str,
        text_embedder,
        n_results: int = 10,
        **kwargs,
    ) -> FrameSearchResult:
        """
        Search frames using text query

        Args:
            text_query: Natural language query
            text_embedder: CLIPTextEmbedder instance
            n_results: Number of results
            **kwargs: Additional search filters

        Returns:
            FrameSearchResult
        """
        # Generate text embedding
        query_embedding = text_embedder.embed_text(text_query).embedding

        # Search with embedding
        return self.search_frames(
            query_embedding=query_embedding,
            n_results=n_results,
            **kwargs,
        )

    def get_frames_in_range(
        self,
        video_id: str,
        start_time: float,
        end_time: float,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Get all frames in a time range

        Args:
            video_id: Video identifier
            start_time: Start time in seconds
            end_time: End time in seconds
            limit: Maximum number of frames

        Returns:
            Dictionary with frame data
        """
        where = {
            "video_id": video_id,
            "timestamp": {"$gte": start_time, "$lte": end_time},
        }

        self.store.collection = self.store.frames_collection
        results = self.store.get_embeddings(where=where, limit=limit)

        return results

    def get_frames_for_scene(
        self,
        video_id: str,
        scene_id: int,
    ) -> Dict[str, Any]:
        """
        Get all frames for a specific scene

        Args:
            video_id: Video identifier
            scene_id: Scene identifier

        Returns:
            Dictionary with frame data
        """
        where = {
            "video_id": video_id,
            "scene_id": scene_id,
        }

        self.store.collection = self.store.frames_collection
        results = self.store.get_embeddings(where=where)

        return results

    def get_keyframes(
        self,
        video_id: str,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Get keyframes for a video

        Args:
            video_id: Video identifier
            limit: Maximum number of keyframes

        Returns:
            Dictionary with keyframe data
        """
        # Assuming keyframes have is_keyframe metadata
        where = {
            "video_id": video_id,
            "is_keyframe": True,
        }

        self.store.collection = self.store.frames_collection
        results = self.store.get_embeddings(where=where, limit=limit)

        return results

    def find_similar_frames(
        self,
        video_id: str,
        frame_number: int,
        n_results: int = 10,
        same_video_only: bool = True,
    ) -> FrameSearchResult:
        """
        Find frames similar to a given frame

        Args:
            video_id: Video containing source frame
            frame_number: Frame number to match
            n_results: Number of similar frames to return
            same_video_only: Only search within same video

        Returns:
            FrameSearchResult with similar frames
        """
        # Get the source frame embedding
        frame_id = f"{video_id}_frame_{frame_number}"

        self.store.collection = self.store.frames_collection
        frame_data = self.store.get_embeddings(ids=[frame_id])

        if not frame_data["embeddings"]:
            raise ValueError(f"Frame {frame_id} not found")

        source_embedding = np.array(frame_data["embeddings"][0])

        # Search for similar frames
        filter_video_id = video_id if same_video_only else None

        return self.search_frames(
            query_embedding=source_embedding,
            n_results=n_results + 1,  # +1 to account for source frame
            video_id=filter_video_id,
        )

    def get_frame_embedding(
        self,
        video_id: str,
        frame_number: int,
    ) -> Optional[np.ndarray]:
        """
        Get embedding for a specific frame

        Args:
            video_id: Video identifier
            frame_number: Frame number

        Returns:
            Frame embedding or None
        """
        frame_id = f"{video_id}_frame_{frame_number}"

        self.store.collection = self.store.frames_collection
        frame_data = self.store.get_embeddings(ids=[frame_id])

        if frame_data["embeddings"]:
            return np.array(frame_data["embeddings"][0])

        return None

    def update_frame_metadata(
        self,
        video_id: str,
        frame_number: int,
        metadata: Dict[str, Any],
    ):
        """
        Update metadata for a frame

        Args:
            video_id: Video identifier
            frame_number: Frame number
            metadata: New metadata to add/update
        """
        frame_id = f"{video_id}_frame_{frame_number}"

        # Get existing metadata
        self.store.collection = self.store.frames_collection
        frame_data = self.store.get_embeddings(ids=[frame_id])

        if not frame_data["metadatas"]:
            raise ValueError(f"Frame {frame_id} not found")

        # Update metadata
        existing_meta = frame_data["metadatas"][0]
        existing_meta.update(metadata)

        # Save updated metadata
        self.store.update_metadata(ids=[frame_id], metadatas=[existing_meta])

        logger.info(f"Updated metadata for frame {frame_id}")

    def delete_video_frames(self, video_id: str):
        """
        Delete all frames for a video

        Args:
            video_id: Video identifier
        """
        where = {"video_id": video_id}

        self.store.collection = self.store.frames_collection
        self.store.delete_embeddings(where=where)

        logger.info(f"Deleted all frames for video {video_id}")

    def count_video_frames(self, video_id: str) -> int:
        """
        Count frames for a video

        Args:
            video_id: Video identifier

        Returns:
            Number of frames
        """
        self.store.collection = self.store.frames_collection
        frames = self.store.get_embeddings(
            where={"video_id": video_id},
            include=[],  # Don't include data, just count
        )

        return len(frames["ids"])

    def get_frame_statistics(self, video_id: str) -> Dict[str, Any]:
        """
        Get statistics about frames for a video

        Args:
            video_id: Video identifier

        Returns:
            Dictionary with statistics
        """
        self.store.collection = self.store.frames_collection
        frames = self.store.get_embeddings(
            where={"video_id": video_id},
            include=["metadatas"],
        )

        if not frames["metadatas"]:
            return {"count": 0}

        timestamps = [m.get("timestamp", 0.0) for m in frames["metadatas"]]
        scene_ids = [
            m.get("scene_id") for m in frames["metadatas"]
            if m.get("scene_id") is not None
        ]

        stats = {
            "count": len(frames["ids"]),
            "min_timestamp": min(timestamps) if timestamps else 0,
            "max_timestamp": max(timestamps) if timestamps else 0,
            "unique_scenes": len(set(scene_ids)) if scene_ids else 0,
        }

        # Object detection stats
        object_counts = [
            m.get("num_objects", 0) for m in frames["metadatas"]
        ]
        if object_counts:
            stats["avg_objects_per_frame"] = sum(object_counts) / len(object_counts)
            stats["max_objects_per_frame"] = max(object_counts)

        return stats

    def batch_search(
        self,
        query_embeddings: np.ndarray,
        n_results: int = 10,
        **kwargs,
    ) -> List[FrameSearchResult]:
        """
        Search with multiple query embeddings

        Args:
            query_embeddings: Multiple query embeddings (n_queries x embedding_dim)
            n_results: Results per query
            **kwargs: Additional search filters

        Returns:
            List of FrameSearchResult
        """
        results = []

        for query_emb in query_embeddings:
            result = self.search_frames(
                query_embedding=query_emb,
                n_results=n_results,
                **kwargs,
            )
            results.append(result)

        return results

    def export_frame_index(
        self,
        video_id: str,
        output_path: Path,
    ):
        """
        Export frame embeddings and metadata

        Args:
            video_id: Video identifier
            output_path: Path to save export
        """
        import pickle

        self.store.collection = self.store.frames_collection
        frames = self.store.get_embeddings(
            where={"video_id": video_id},
            include=["embeddings", "metadatas"],
        )

        export_data = {
            "video_id": video_id,
            "embeddings": np.array(frames["embeddings"]),
            "metadatas": frames["metadatas"],
            "frame_ids": frames["ids"],
        }

        with open(output_path, "wb") as f:
            pickle.dump(export_data, f)

        logger.info(f"Exported {len(frames['ids'])} frames to {output_path}")

    def import_frame_index(
        self,
        input_path: Path,
        overwrite: bool = False,
    ):
        """
        Import frame embeddings and metadata

        Args:
            input_path: Path to import from
            overwrite: Overwrite existing frames
        """
        import pickle

        with open(input_path, "rb") as f:
            import_data = pickle.load(f)

        video_id = import_data["video_id"]
        embeddings = import_data["embeddings"]
        metadatas = import_data["metadatas"]

        # Extract fields from metadata
        frame_numbers = [m["frame_number"] for m in metadatas]
        timestamps = [m["timestamp"] for m in metadatas]
        frame_paths = [m.get("frame_path") for m in metadatas]

        # Add frames
        if overwrite:
            self.delete_video_frames(video_id)

        self.add_video_frames(
            video_id=video_id,
            frame_embeddings=embeddings,
            frame_numbers=frame_numbers,
            timestamps=timestamps,
            frame_paths=frame_paths,
        )

        logger.info(f"Imported {len(embeddings)} frames from {input_path}")


def add_frames_to_vector_store(
    video_id: str,
    frame_embeddings: np.ndarray,
    frame_numbers: List[int],
    timestamps: List[float],
    persist_directory: Optional[Path] = None,
    **kwargs,
) -> FrameVectorStore:
    """
    Convenience function to add frames to vector store

    Args:
        video_id: Video identifier
        frame_embeddings: Frame embeddings
        frame_numbers: Frame numbers
        timestamps: Timestamps
        persist_directory: ChromaDB directory
        **kwargs: Additional metadata

    Returns:
        FrameVectorStore instance
    """
    store = FrameVectorStore(persist_directory)

    store.add_video_frames(
        video_id=video_id,
        frame_embeddings=frame_embeddings,
        frame_numbers=frame_numbers,
        timestamps=timestamps,
        **kwargs,
    )

    return store
