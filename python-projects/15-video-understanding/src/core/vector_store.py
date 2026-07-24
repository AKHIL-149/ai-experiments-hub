"""
ChromaDB vector store integration
Manages vector storage and retrieval for video embeddings
"""

import logging
from typing import List, Optional, Dict, Union, Any
from pathlib import Path
import numpy as np
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class VectorStoreConfig:
    """Configuration for vector store"""
    persist_directory: Path = field(default_factory=lambda: Path("./chroma_data"))
    collection_name: str = "default"
    distance_metric: str = "cosine"  # cosine, l2, ip
    embedding_dimension: Optional[int] = None


@dataclass
class SearchResult:
    """Result from vector search"""
    ids: List[str]
    distances: List[float]
    metadatas: List[Dict[str, Any]]
    documents: Optional[List[str]] = None
    embeddings: Optional[List[np.ndarray]] = None


class VectorStore:
    """
    ChromaDB vector store for embedding storage and retrieval
    Supports multiple collections for different embedding types
    """

    def __init__(self, config: Optional[VectorStoreConfig] = None):
        """
        Initialize vector store

        Args:
            config: Vector store configuration
        """
        self.config = config or VectorStoreConfig()
        self.client = None
        self.collection = None

        self._initialize_client()

    def _initialize_client(self):
        """Initialize ChromaDB client"""
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError:
            raise RuntimeError(
                "ChromaDB required. Install with: pip install chromadb"
            )

        # Create persistent client
        self.client = chromadb.PersistentClient(
            path=str(self.config.persist_directory),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            )
        )

        logger.info(f"Initialized ChromaDB client at {self.config.persist_directory}")

    def create_collection(
        self,
        name: str,
        metadata: Optional[Dict[str, Any]] = None,
        get_or_create: bool = True,
    ):
        """
        Create or get a collection

        Args:
            name: Collection name
            metadata: Collection metadata
            get_or_create: Get existing collection if it exists

        Returns:
            Collection object
        """
        # Distance metric mapping
        distance_map = {
            "cosine": "cosine",
            "l2": "l2",
            "ip": "ip",  # inner product
        }

        distance_fn = distance_map.get(
            self.config.distance_metric, "cosine"
        )

        if get_or_create:
            self.collection = self.client.get_or_create_collection(
                name=name,
                metadata=metadata or {"distance_metric": distance_fn},
            )
            logger.info(f"Got or created collection: {name}")
        else:
            self.collection = self.client.create_collection(
                name=name,
                metadata=metadata or {"distance_metric": distance_fn},
            )
            logger.info(f"Created collection: {name}")

        return self.collection

    def get_collection(self, name: str):
        """
        Get existing collection

        Args:
            name: Collection name

        Returns:
            Collection object
        """
        self.collection = self.client.get_collection(name=name)
        logger.info(f"Retrieved collection: {name}")
        return self.collection

    def list_collections(self) -> List[str]:
        """
        List all collections

        Returns:
            List of collection names
        """
        collections = self.client.list_collections()
        return [col.name for col in collections]

    def delete_collection(self, name: str):
        """
        Delete a collection

        Args:
            name: Collection name
        """
        self.client.delete_collection(name=name)
        logger.info(f"Deleted collection: {name}")

    def add_embeddings(
        self,
        embeddings: Union[List[np.ndarray], np.ndarray],
        ids: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        documents: Optional[List[str]] = None,
    ):
        """
        Add embeddings to collection

        Args:
            embeddings: Embedding vectors
            ids: Unique IDs for embeddings
            metadatas: Optional metadata for each embedding
            documents: Optional document text for each embedding
        """
        if self.collection is None:
            raise RuntimeError("No collection selected. Call create_collection() first.")

        # Convert numpy arrays to lists for ChromaDB
        if isinstance(embeddings, np.ndarray):
            embeddings_list = embeddings.tolist()
        else:
            embeddings_list = [
                emb.tolist() if isinstance(emb, np.ndarray) else emb
                for emb in embeddings
            ]

        self.collection.add(
            embeddings=embeddings_list,
            ids=ids,
            metadatas=metadatas,
            documents=documents,
        )

        logger.info(f"Added {len(ids)} embeddings to collection")

    def upsert_embeddings(
        self,
        embeddings: Union[List[np.ndarray], np.ndarray],
        ids: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        documents: Optional[List[str]] = None,
    ):
        """
        Update or insert embeddings

        Args:
            embeddings: Embedding vectors
            ids: Unique IDs for embeddings
            metadatas: Optional metadata
            documents: Optional documents
        """
        if self.collection is None:
            raise RuntimeError("No collection selected.")

        # Convert numpy arrays
        if isinstance(embeddings, np.ndarray):
            embeddings_list = embeddings.tolist()
        else:
            embeddings_list = [
                emb.tolist() if isinstance(emb, np.ndarray) else emb
                for emb in embeddings
            ]

        self.collection.upsert(
            embeddings=embeddings_list,
            ids=ids,
            metadatas=metadatas,
            documents=documents,
        )

        logger.info(f"Upserted {len(ids)} embeddings")

    def query(
        self,
        query_embedding: Optional[np.ndarray] = None,
        query_text: Optional[str] = None,
        n_results: int = 10,
        where: Optional[Dict[str, Any]] = None,
        where_document: Optional[Dict[str, Any]] = None,
        include: Optional[List[str]] = None,
    ) -> SearchResult:
        """
        Query collection for similar embeddings

        Args:
            query_embedding: Query embedding vector
            query_text: Query text (if using embedding function)
            n_results: Number of results to return
            where: Metadata filter
            where_document: Document filter
            include: Fields to include in results

        Returns:
            SearchResult object
        """
        if self.collection is None:
            raise RuntimeError("No collection selected.")

        # Prepare query
        query_embeddings = None
        query_texts = None

        if query_embedding is not None:
            if isinstance(query_embedding, np.ndarray):
                query_embeddings = [query_embedding.tolist()]
            else:
                query_embeddings = [query_embedding]

        if query_text is not None:
            query_texts = [query_text]

        # Default includes
        if include is None:
            include = ["metadatas", "distances", "documents"]

        # Query collection
        results = self.collection.query(
            query_embeddings=query_embeddings,
            query_texts=query_texts,
            n_results=n_results,
            where=where,
            where_document=where_document,
            include=include,
        )

        # Convert to SearchResult
        return SearchResult(
            ids=results["ids"][0] if results["ids"] else [],
            distances=results["distances"][0] if results["distances"] else [],
            metadatas=results["metadatas"][0] if results["metadatas"] else [],
            documents=results.get("documents", [[]])[0],
            embeddings=results.get("embeddings", None),
        )

    def get_embeddings(
        self,
        ids: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        include: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Get embeddings by ID or filter

        Args:
            ids: Specific IDs to retrieve
            where: Metadata filter
            limit: Maximum number to retrieve
            include: Fields to include

        Returns:
            Dictionary with embeddings and metadata
        """
        if self.collection is None:
            raise RuntimeError("No collection selected.")

        if include is None:
            include = ["metadatas", "embeddings", "documents"]

        results = self.collection.get(
            ids=ids,
            where=where,
            limit=limit,
            include=include,
        )

        return results

    def delete_embeddings(
        self,
        ids: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None,
    ):
        """
        Delete embeddings from collection

        Args:
            ids: Specific IDs to delete
            where: Metadata filter for deletion
        """
        if self.collection is None:
            raise RuntimeError("No collection selected.")

        self.collection.delete(
            ids=ids,
            where=where,
        )

        logger.info(f"Deleted embeddings from collection")

    def update_metadata(
        self,
        ids: List[str],
        metadatas: List[Dict[str, Any]],
    ):
        """
        Update metadata for existing embeddings

        Args:
            ids: IDs to update
            metadatas: New metadata
        """
        if self.collection is None:
            raise RuntimeError("No collection selected.")

        self.collection.update(
            ids=ids,
            metadatas=metadatas,
        )

        logger.info(f"Updated metadata for {len(ids)} embeddings")

    def count(self) -> int:
        """
        Get number of embeddings in collection

        Returns:
            Count of embeddings
        """
        if self.collection is None:
            raise RuntimeError("No collection selected.")

        return self.collection.count()

    def peek(self, limit: int = 10) -> Dict[str, Any]:
        """
        Peek at first N items in collection

        Args:
            limit: Number of items to peek

        Returns:
            Dictionary with items
        """
        if self.collection is None:
            raise RuntimeError("No collection selected.")

        return self.collection.peek(limit=limit)

    def reset(self):
        """Reset the entire database (dangerous!)"""
        self.client.reset()
        logger.warning("Database reset - all collections deleted")

    def get_collection_info(self) -> Dict[str, Any]:
        """
        Get information about current collection

        Returns:
            Dictionary with collection info
        """
        if self.collection is None:
            raise RuntimeError("No collection selected.")

        return {
            "name": self.collection.name,
            "count": self.collection.count(),
            "metadata": self.collection.metadata,
        }


class VideoVectorStore(VectorStore):
    """
    Specialized vector store for video embeddings
    Manages multiple collections: frames, transcripts, scenes
    """

    def __init__(self, persist_directory: Optional[Path] = None):
        """
        Initialize video vector store

        Args:
            persist_directory: Directory for persistent storage
        """
        config = VectorStoreConfig(
            persist_directory=persist_directory or Path("./chroma_data"),
            distance_metric="cosine",
        )
        super().__init__(config)

        # Collection references
        self.frames_collection = None
        self.transcripts_collection = None
        self.scenes_collection = None

    def initialize_collections(self):
        """Initialize all video-related collections"""
        # Frames collection
        self.frames_collection = self.client.get_or_create_collection(
            name="video_frames",
            metadata={
                "description": "CLIP embeddings for video frames",
                "distance_metric": "cosine",
            }
        )

        # Transcripts collection
        self.transcripts_collection = self.client.get_or_create_collection(
            name="video_transcripts",
            metadata={
                "description": "Text embeddings for transcript segments",
                "distance_metric": "cosine",
            }
        )

        # Scenes collection
        self.scenes_collection = self.client.get_or_create_collection(
            name="video_scenes",
            metadata={
                "description": "Multi-modal embeddings for video scenes",
                "distance_metric": "cosine",
            }
        )

        logger.info("Initialized all video collections")

        return {
            "frames": self.frames_collection,
            "transcripts": self.transcripts_collection,
            "scenes": self.scenes_collection,
        }

    def add_frame_embeddings(
        self,
        video_id: str,
        frame_embeddings: np.ndarray,
        frame_numbers: List[int],
        timestamps: List[float],
        frame_paths: Optional[List[str]] = None,
        additional_metadata: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Add frame embeddings to frames collection

        Args:
            video_id: Video identifier
            frame_embeddings: Frame CLIP embeddings
            frame_numbers: Frame numbers
            timestamps: Frame timestamps
            frame_paths: Optional frame file paths
            additional_metadata: Additional metadata per frame
        """
        if self.frames_collection is None:
            self.initialize_collections()

        # Create IDs
        ids = [f"{video_id}_frame_{num}" for num in frame_numbers]

        # Create metadata
        metadatas = []
        for i, (num, ts) in enumerate(zip(frame_numbers, timestamps)):
            meta = {
                "video_id": video_id,
                "frame_number": num,
                "timestamp": ts,
                "type": "frame",
            }

            if frame_paths:
                meta["frame_path"] = frame_paths[i]

            if additional_metadata and i < len(additional_metadata):
                meta.update(additional_metadata[i])

            metadatas.append(meta)

        # Add to collection
        self.collection = self.frames_collection
        self.add_embeddings(frame_embeddings, ids, metadatas)

        logger.info(
            f"Added {len(frame_embeddings)} frame embeddings for video {video_id}"
        )

    def add_transcript_embeddings(
        self,
        video_id: str,
        transcript_embeddings: np.ndarray,
        segment_ids: List[str],
        texts: List[str],
        timestamps: List[tuple],  # (start, end) tuples
        speakers: Optional[List[str]] = None,
        additional_metadata: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Add transcript embeddings to transcripts collection

        Args:
            video_id: Video identifier
            transcript_embeddings: Text embeddings
            segment_ids: Segment identifiers
            texts: Transcript texts
            timestamps: Segment timestamps (start, end)
            speakers: Optional speaker IDs
            additional_metadata: Additional metadata
        """
        if self.transcripts_collection is None:
            self.initialize_collections()

        # Create IDs
        ids = [f"{video_id}_transcript_{seg_id}" for seg_id in segment_ids]

        # Create metadata
        metadatas = []
        for i, (seg_id, ts) in enumerate(zip(segment_ids, timestamps)):
            meta = {
                "video_id": video_id,
                "segment_id": seg_id,
                "start_time": ts[0],
                "end_time": ts[1],
                "type": "transcript",
            }

            if speakers and i < len(speakers):
                meta["speaker"] = speakers[i]

            if additional_metadata and i < len(additional_metadata):
                meta.update(additional_metadata[i])

            metadatas.append(meta)

        # Add to collection
        self.collection = self.transcripts_collection
        self.add_embeddings(transcript_embeddings, ids, metadatas, documents=texts)

        logger.info(
            f"Added {len(transcript_embeddings)} transcript embeddings for video {video_id}"
        )

    def add_scene_embeddings(
        self,
        video_id: str,
        scene_embeddings: np.ndarray,
        scene_numbers: List[int],
        scene_timestamps: List[tuple],  # (start, end)
        scene_descriptions: Optional[List[str]] = None,
        additional_metadata: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Add scene embeddings to scenes collection

        Args:
            video_id: Video identifier
            scene_embeddings: Scene embeddings
            scene_numbers: Scene numbers
            scene_timestamps: Scene timestamps
            scene_descriptions: Optional scene descriptions
            additional_metadata: Additional metadata
        """
        if self.scenes_collection is None:
            self.initialize_collections()

        # Create IDs
        ids = [f"{video_id}_scene_{num}" for num in scene_numbers]

        # Create metadata
        metadatas = []
        for i, (num, ts) in enumerate(zip(scene_numbers, scene_timestamps)):
            meta = {
                "video_id": video_id,
                "scene_number": num,
                "start_time": ts[0],
                "end_time": ts[1],
                "duration": ts[1] - ts[0],
                "type": "scene",
            }

            if additional_metadata and i < len(additional_metadata):
                meta.update(additional_metadata[i])

            metadatas.append(meta)

        # Add to collection
        self.collection = self.scenes_collection
        documents = scene_descriptions if scene_descriptions else None
        self.add_embeddings(scene_embeddings, ids, metadatas, documents=documents)

        logger.info(
            f"Added {len(scene_embeddings)} scene embeddings for video {video_id}"
        )

    def search_frames(
        self,
        query_embedding: np.ndarray,
        n_results: int = 10,
        video_id: Optional[str] = None,
        time_range: Optional[tuple] = None,
    ) -> SearchResult:
        """
        Search for similar frames

        Args:
            query_embedding: Query embedding
            n_results: Number of results
            video_id: Filter by video ID
            time_range: Filter by time range (start, end)

        Returns:
            SearchResult
        """
        if self.frames_collection is None:
            self.initialize_collections()

        self.collection = self.frames_collection

        # Build metadata filter
        where = {}
        if video_id:
            where["video_id"] = video_id

        if time_range:
            where["timestamp"] = {"$gte": time_range[0], "$lte": time_range[1]}

        return self.query(
            query_embedding=query_embedding,
            n_results=n_results,
            where=where if where else None,
        )

    def search_transcripts(
        self,
        query_embedding: np.ndarray,
        n_results: int = 10,
        video_id: Optional[str] = None,
        speaker: Optional[str] = None,
    ) -> SearchResult:
        """
        Search for similar transcript segments

        Args:
            query_embedding: Query embedding
            n_results: Number of results
            video_id: Filter by video ID
            speaker: Filter by speaker

        Returns:
            SearchResult
        """
        if self.transcripts_collection is None:
            self.initialize_collections()

        self.collection = self.transcripts_collection

        # Build metadata filter
        where = {}
        if video_id:
            where["video_id"] = video_id
        if speaker:
            where["speaker"] = speaker

        return self.query(
            query_embedding=query_embedding,
            n_results=n_results,
            where=where if where else None,
        )

    def search_scenes(
        self,
        query_embedding: np.ndarray,
        n_results: int = 10,
        video_id: Optional[str] = None,
        min_duration: Optional[float] = None,
    ) -> SearchResult:
        """
        Search for similar scenes

        Args:
            query_embedding: Query embedding
            n_results: Number of results
            video_id: Filter by video ID
            min_duration: Minimum scene duration

        Returns:
            SearchResult
        """
        if self.scenes_collection is None:
            self.initialize_collections()

        self.collection = self.scenes_collection

        # Build metadata filter
        where = {}
        if video_id:
            where["video_id"] = video_id
        if min_duration:
            where["duration"] = {"$gte": min_duration}

        return self.query(
            query_embedding=query_embedding,
            n_results=n_results,
            where=where if where else None,
        )

    def get_video_embeddings(self, video_id: str) -> Dict[str, Any]:
        """
        Get all embeddings for a video

        Args:
            video_id: Video identifier

        Returns:
            Dictionary with all embedding types
        """
        result = {}

        # Get frames
        if self.frames_collection:
            self.collection = self.frames_collection
            frames = self.get_embeddings(where={"video_id": video_id})
            result["frames"] = frames

        # Get transcripts
        if self.transcripts_collection:
            self.collection = self.transcripts_collection
            transcripts = self.get_embeddings(where={"video_id": video_id})
            result["transcripts"] = transcripts

        # Get scenes
        if self.scenes_collection:
            self.collection = self.scenes_collection
            scenes = self.get_embeddings(where={"video_id": video_id})
            result["scenes"] = scenes

        return result

    def delete_video_embeddings(self, video_id: str):
        """
        Delete all embeddings for a video

        Args:
            video_id: Video identifier
        """
        where = {"video_id": video_id}

        if self.frames_collection:
            self.collection = self.frames_collection
            self.delete_embeddings(where=where)

        if self.transcripts_collection:
            self.collection = self.transcripts_collection
            self.delete_embeddings(where=where)

        if self.scenes_collection:
            self.collection = self.scenes_collection
            self.delete_embeddings(where=where)

        logger.info(f"Deleted all embeddings for video {video_id}")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics for all collections

        Returns:
            Dictionary with stats
        """
        stats = {}

        if self.frames_collection:
            stats["frames_count"] = self.frames_collection.count()

        if self.transcripts_collection:
            stats["transcripts_count"] = self.transcripts_collection.count()

        if self.scenes_collection:
            stats["scenes_count"] = self.scenes_collection.count()

        stats["total_count"] = sum(stats.values())

        return stats
