"""
Transcript vector store for text embeddings
Semantic search over video transcripts
"""

import logging
from typing import List, Optional, Dict, Union, Any
from pathlib import Path
from dataclasses import dataclass
import numpy as np

from src.core.vector_store import VideoVectorStore, SearchResult

logger = logging.getLogger(__name__)


@dataclass
class TranscriptSearchResult:
    """Result from transcript search"""
    video_id: str
    segment_ids: List[str]
    texts: List[str]
    start_times: List[float]
    end_times: List[float]
    speakers: List[Optional[str]]
    similarities: List[float]
    metadatas: List[Dict[str, Any]]
    total_results: int


class TranscriptVectorStore:
    """
    Manage transcript text embeddings in vector store
    Supports semantic search over spoken content
    """

    def __init__(self, persist_directory: Optional[Path] = None):
        """
        Initialize transcript vector store

        Args:
            persist_directory: Directory for ChromaDB persistence
        """
        self.store = VideoVectorStore(persist_directory)
        self.store.initialize_collections()

        logger.info("Initialized TranscriptVectorStore")

    def add_video_transcript(
        self,
        video_id: str,
        transcript_embeddings: np.ndarray,
        segment_ids: List[str],
        texts: List[str],
        start_times: List[float],
        end_times: List[float],
        speakers: Optional[List[str]] = None,
        scene_ids: Optional[List[int]] = None,
        confidences: Optional[List[float]] = None,
        languages: Optional[List[str]] = None,
        batch_size: int = 100,
    ):
        """
        Add transcript embeddings for a video

        Args:
            video_id: Unique video identifier
            transcript_embeddings: Text embeddings (n_segments x embedding_dim)
            segment_ids: Segment identifiers
            texts: Transcript texts
            start_times: Segment start times in seconds
            end_times: Segment end times in seconds
            speakers: Optional speaker IDs
            scene_ids: Optional scene IDs
            confidences: Optional transcription confidences
            languages: Optional language codes
            batch_size: Batch size for insertion
        """
        n_segments = len(transcript_embeddings)

        logger.info(f"Adding {n_segments} transcript segments for video {video_id}")

        # Prepare timestamps as tuples
        timestamps = list(zip(start_times, end_times))

        # Prepare metadata
        additional_metadata = []
        for i in range(n_segments):
            meta = {}

            if scene_ids and i < len(scene_ids):
                meta["scene_id"] = scene_ids[i]

            if confidences and i < len(confidences):
                meta["confidence"] = confidences[i]

            if languages and i < len(languages):
                meta["language"] = languages[i]

            # Add text length
            if texts and i < len(texts):
                meta["text_length"] = len(texts[i])
                meta["word_count"] = len(texts[i].split())

            additional_metadata.append(meta)

        # Add in batches
        for batch_start in range(0, n_segments, batch_size):
            batch_end = min(batch_start + batch_size, n_segments)

            batch_embeddings = transcript_embeddings[batch_start:batch_end]
            batch_segment_ids = segment_ids[batch_start:batch_end]
            batch_texts = texts[batch_start:batch_end]
            batch_timestamps = timestamps[batch_start:batch_end]
            batch_speakers = (
                speakers[batch_start:batch_end] if speakers else None
            )
            batch_metadata = additional_metadata[batch_start:batch_end]

            self.store.add_transcript_embeddings(
                video_id=video_id,
                transcript_embeddings=batch_embeddings,
                segment_ids=batch_segment_ids,
                texts=batch_texts,
                timestamps=batch_timestamps,
                speakers=batch_speakers,
                additional_metadata=batch_metadata,
            )

            logger.debug(
                f"Added batch {batch_start}-{batch_end} ({batch_end - batch_start} segments)"
            )

        logger.info(
            f"Successfully added {n_segments} transcript segments for video {video_id}"
        )

    def search_transcripts(
        self,
        query_embedding: np.ndarray,
        n_results: int = 10,
        video_id: Optional[str] = None,
        speaker: Optional[str] = None,
        time_range: Optional[tuple] = None,
        scene_id: Optional[int] = None,
        min_confidence: Optional[float] = None,
        language: Optional[str] = None,
    ) -> TranscriptSearchResult:
        """
        Search for similar transcript segments

        Args:
            query_embedding: Query text embedding
            n_results: Number of results to return
            video_id: Filter by specific video
            speaker: Filter by speaker
            time_range: Filter by time range (start, end)
            scene_id: Filter by scene ID
            min_confidence: Minimum transcription confidence
            language: Filter by language

        Returns:
            TranscriptSearchResult with matched segments
        """
        # Build metadata filter
        where = {}
        if video_id:
            where["video_id"] = video_id
        if speaker:
            where["speaker"] = speaker
        if scene_id is not None:
            where["scene_id"] = scene_id
        if min_confidence is not None:
            where["confidence"] = {"$gte": min_confidence}
        if language:
            where["language"] = language

        # Handle time range filtering
        if time_range:
            where["start_time"] = {"$gte": time_range[0]}
            where["end_time"] = {"$lte": time_range[1]}

        # Search using store
        results = self.store.search_transcripts(
            query_embedding=query_embedding,
            n_results=n_results,
            video_id=video_id,
            speaker=speaker,
        )

        # Parse results
        segment_ids = [m.get("segment_id", "") for m in results.metadatas]
        texts = results.documents or []
        start_times = [m.get("start_time", 0.0) for m in results.metadatas]
        end_times = [m.get("end_time", 0.0) for m in results.metadatas]
        speakers = [m.get("speaker") for m in results.metadatas]
        similarities = [1 - dist for dist in results.distances]

        # Get video_id from results
        video_ids = [m.get("video_id", "") for m in results.metadatas]
        result_video_id = video_id or (video_ids[0] if video_ids else "")

        return TranscriptSearchResult(
            video_id=result_video_id,
            segment_ids=segment_ids,
            texts=texts,
            start_times=start_times,
            end_times=end_times,
            speakers=speakers,
            similarities=similarities,
            metadatas=results.metadatas,
            total_results=len(segment_ids),
        )

    def search_transcripts_by_text(
        self,
        text_query: str,
        text_embedder,
        n_results: int = 10,
        **kwargs,
    ) -> TranscriptSearchResult:
        """
        Search transcripts using text query

        Args:
            text_query: Natural language query
            text_embedder: Text embedding model
            n_results: Number of results
            **kwargs: Additional search filters

        Returns:
            TranscriptSearchResult
        """
        # Generate text embedding
        query_embedding = text_embedder.embed_text(text_query).embedding

        # Search with embedding
        return self.search_transcripts(
            query_embedding=query_embedding,
            n_results=n_results,
            **kwargs,
        )

    def get_transcript_in_range(
        self,
        video_id: str,
        start_time: float,
        end_time: float,
    ) -> Dict[str, Any]:
        """
        Get transcript segments in a time range

        Args:
            video_id: Video identifier
            start_time: Start time in seconds
            end_time: End time in seconds

        Returns:
            Dictionary with transcript data
        """
        where = {
            "video_id": video_id,
            "start_time": {"$gte": start_time},
            "end_time": {"$lte": end_time},
        }

        self.store.collection = self.store.transcripts_collection
        results = self.store.get_embeddings(where=where)

        return results

    def get_speaker_segments(
        self,
        video_id: str,
        speaker: str,
    ) -> Dict[str, Any]:
        """
        Get all segments for a specific speaker

        Args:
            video_id: Video identifier
            speaker: Speaker identifier

        Returns:
            Dictionary with speaker segments
        """
        where = {
            "video_id": video_id,
            "speaker": speaker,
        }

        self.store.collection = self.store.transcripts_collection
        results = self.store.get_embeddings(where=where)

        return results

    def get_full_transcript(
        self,
        video_id: str,
        sort_by_time: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Get complete transcript for a video

        Args:
            video_id: Video identifier
            sort_by_time: Sort segments by start time

        Returns:
            List of transcript segments
        """
        where = {"video_id": video_id}

        self.store.collection = self.store.transcripts_collection
        results = self.store.get_embeddings(where=where)

        # Combine into segments
        segments = []
        for i, text in enumerate(results.get("documents", [])):
            meta = results["metadatas"][i] if i < len(results["metadatas"]) else {}

            segment = {
                "text": text,
                "start_time": meta.get("start_time", 0.0),
                "end_time": meta.get("end_time", 0.0),
                "speaker": meta.get("speaker"),
                "confidence": meta.get("confidence"),
                "segment_id": meta.get("segment_id"),
            }
            segments.append(segment)

        # Sort by time if requested
        if sort_by_time:
            segments.sort(key=lambda x: x["start_time"])

        return segments

    def search_by_keywords(
        self,
        video_id: str,
        keywords: List[str],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Search for segments containing keywords

        Args:
            video_id: Video identifier
            keywords: List of keywords to search

        Returns:
            Dictionary mapping keywords to matching segments
        """
        results = {}

        # Get all transcripts for video
        transcripts = self.get_full_transcript(video_id)

        # Search for each keyword
        for keyword in keywords:
            matches = []
            keyword_lower = keyword.lower()

            for segment in transcripts:
                if keyword_lower in segment["text"].lower():
                    matches.append(segment)

            if matches:
                results[keyword] = matches

        return results

    def get_speaker_statistics(
        self,
        video_id: str,
    ) -> Dict[str, Any]:
        """
        Get statistics about speakers in a video

        Args:
            video_id: Video identifier

        Returns:
            Dictionary with speaker stats
        """
        where = {"video_id": video_id}

        self.store.collection = self.store.transcripts_collection
        results = self.store.get_embeddings(where=where, include=["metadatas"])

        # Analyze speakers
        speaker_stats = {}

        for meta in results["metadatas"]:
            speaker = meta.get("speaker", "unknown")

            if speaker not in speaker_stats:
                speaker_stats[speaker] = {
                    "segment_count": 0,
                    "total_duration": 0.0,
                    "word_count": 0,
                }

            speaker_stats[speaker]["segment_count"] += 1

            duration = meta.get("end_time", 0) - meta.get("start_time", 0)
            speaker_stats[speaker]["total_duration"] += duration

            word_count = meta.get("word_count", 0)
            speaker_stats[speaker]["word_count"] += word_count

        return speaker_stats

    def find_similar_segments(
        self,
        video_id: str,
        segment_id: str,
        n_results: int = 10,
        same_video_only: bool = True,
    ) -> TranscriptSearchResult:
        """
        Find segments semantically similar to a given segment

        Args:
            video_id: Video containing source segment
            segment_id: Segment ID to match
            n_results: Number of similar segments
            same_video_only: Only search within same video

        Returns:
            TranscriptSearchResult with similar segments
        """
        # Get source segment embedding
        full_id = f"{video_id}_transcript_{segment_id}"

        self.store.collection = self.store.transcripts_collection
        segment_data = self.store.get_embeddings(ids=[full_id])

        if not segment_data["embeddings"]:
            raise ValueError(f"Segment {full_id} not found")

        source_embedding = np.array(segment_data["embeddings"][0])

        # Search for similar segments
        filter_video_id = video_id if same_video_only else None

        return self.search_transcripts(
            query_embedding=source_embedding,
            n_results=n_results + 1,  # +1 for source segment
            video_id=filter_video_id,
        )

    def update_segment_metadata(
        self,
        video_id: str,
        segment_id: str,
        metadata: Dict[str, Any],
    ):
        """
        Update metadata for a transcript segment

        Args:
            video_id: Video identifier
            segment_id: Segment identifier
            metadata: New metadata to add/update
        """
        full_id = f"{video_id}_transcript_{segment_id}"

        # Get existing metadata
        self.store.collection = self.store.transcripts_collection
        segment_data = self.store.get_embeddings(ids=[full_id])

        if not segment_data["metadatas"]:
            raise ValueError(f"Segment {full_id} not found")

        # Update metadata
        existing_meta = segment_data["metadatas"][0]
        existing_meta.update(metadata)

        # Save
        self.store.update_metadata(ids=[full_id], metadatas=[existing_meta])

        logger.info(f"Updated metadata for segment {full_id}")

    def delete_video_transcript(self, video_id: str):
        """
        Delete all transcript segments for a video

        Args:
            video_id: Video identifier
        """
        where = {"video_id": video_id}

        self.store.collection = self.store.transcripts_collection
        self.store.delete_embeddings(where=where)

        logger.info(f"Deleted transcript for video {video_id}")

    def count_video_segments(self, video_id: str) -> int:
        """
        Count transcript segments for a video

        Args:
            video_id: Video identifier

        Returns:
            Number of segments
        """
        self.store.collection = self.store.transcripts_collection
        segments = self.store.get_embeddings(
            where={"video_id": video_id},
            include=[],
        )

        return len(segments["ids"])

    def get_transcript_statistics(self, video_id: str) -> Dict[str, Any]:
        """
        Get statistics about transcript for a video

        Args:
            video_id: Video identifier

        Returns:
            Dictionary with statistics
        """
        self.store.collection = self.store.transcripts_collection
        segments = self.store.get_embeddings(
            where={"video_id": video_id},
            include=["metadatas", "documents"],
        )

        if not segments["metadatas"]:
            return {"count": 0}

        start_times = [m.get("start_time", 0.0) for m in segments["metadatas"]]
        end_times = [m.get("end_time", 0.0) for m in segments["metadatas"]]
        word_counts = [m.get("word_count", 0) for m in segments["metadatas"]]
        speakers = [
            m.get("speaker") for m in segments["metadatas"]
            if m.get("speaker") is not None
        ]

        stats = {
            "count": len(segments["ids"]),
            "min_start_time": min(start_times) if start_times else 0,
            "max_end_time": max(end_times) if end_times else 0,
            "total_duration": max(end_times) - min(start_times) if start_times else 0,
            "unique_speakers": len(set(speakers)) if speakers else 0,
            "total_words": sum(word_counts) if word_counts else 0,
        }

        # Confidence stats
        confidences = [
            m.get("confidence") for m in segments["metadatas"]
            if m.get("confidence") is not None
        ]
        if confidences:
            stats["avg_confidence"] = sum(confidences) / len(confidences)
            stats["min_confidence"] = min(confidences)

        return stats

    def export_transcript_index(
        self,
        video_id: str,
        output_path: Path,
    ):
        """
        Export transcript embeddings and metadata

        Args:
            video_id: Video identifier
            output_path: Path to save export
        """
        import pickle

        self.store.collection = self.store.transcripts_collection
        segments = self.store.get_embeddings(
            where={"video_id": video_id},
            include=["embeddings", "metadatas", "documents"],
        )

        export_data = {
            "video_id": video_id,
            "embeddings": np.array(segments["embeddings"]),
            "metadatas": segments["metadatas"],
            "texts": segments["documents"],
            "segment_ids": segments["ids"],
        }

        with open(output_path, "wb") as f:
            pickle.dump(export_data, f)

        logger.info(f"Exported {len(segments['ids'])} segments to {output_path}")

    def import_transcript_index(
        self,
        input_path: Path,
        overwrite: bool = False,
    ):
        """
        Import transcript embeddings and metadata

        Args:
            input_path: Path to import from
            overwrite: Overwrite existing transcript
        """
        import pickle

        with open(input_path, "rb") as f:
            import_data = pickle.load(f)

        video_id = import_data["video_id"]
        embeddings = import_data["embeddings"]
        metadatas = import_data["metadatas"]
        texts = import_data["texts"]

        # Extract fields
        segment_ids = [m["segment_id"] for m in metadatas]
        start_times = [m["start_time"] for m in metadatas]
        end_times = [m["end_time"] for m in metadatas]
        speakers = [m.get("speaker") for m in metadatas]

        # Add transcript
        if overwrite:
            self.delete_video_transcript(video_id)

        self.add_video_transcript(
            video_id=video_id,
            transcript_embeddings=embeddings,
            segment_ids=segment_ids,
            texts=texts,
            start_times=start_times,
            end_times=end_times,
            speakers=speakers,
        )

        logger.info(f"Imported {len(embeddings)} segments from {input_path}")


def add_transcript_to_vector_store(
    video_id: str,
    transcript_embeddings: np.ndarray,
    segment_ids: List[str],
    texts: List[str],
    start_times: List[float],
    end_times: List[float],
    persist_directory: Optional[Path] = None,
    **kwargs,
) -> TranscriptVectorStore:
    """
    Convenience function to add transcript to vector store

    Args:
        video_id: Video identifier
        transcript_embeddings: Text embeddings
        segment_ids: Segment IDs
        texts: Transcript texts
        start_times: Start times
        end_times: End times
        persist_directory: ChromaDB directory
        **kwargs: Additional metadata

    Returns:
        TranscriptVectorStore instance
    """
    store = TranscriptVectorStore(persist_directory)

    store.add_video_transcript(
        video_id=video_id,
        transcript_embeddings=transcript_embeddings,
        segment_ids=segment_ids,
        texts=texts,
        start_times=start_times,
        end_times=end_times,
        **kwargs,
    )

    return store
