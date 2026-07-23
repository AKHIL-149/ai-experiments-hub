"""
CLIP frame embedder
Generates CLIP embeddings for video frames
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict
from dataclasses import dataclass
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.services.clip.clip_model import CLIPModel, CLIPConfig

logger = logging.getLogger(__name__)


@dataclass
class FrameEmbedding:
    """CLIP embedding for a video frame"""
    frame_path: Path
    embedding: np.ndarray
    frame_number: Optional[int] = None
    timestamp: Optional[float] = None
    metadata: Optional[Dict[str, any]] = None


@dataclass
class VideoEmbeddings:
    """CLIP embeddings for all frames in a video"""
    video_path: Optional[Path] = None
    frame_embeddings: List[FrameEmbedding] = None
    embedding_matrix: Optional[np.ndarray] = None  # Stacked embeddings for fast search
    total_frames: int = 0
    embedding_dim: int = 512
    model_name: str = "ViT-B/32"
    metadata: Optional[Dict[str, any]] = None

    def __post_init__(self):
        if self.frame_embeddings is None:
            self.frame_embeddings = []


class CLIPFrameEmbedder:
    """
    Generate CLIP embeddings for video frames
    Supports batch processing and caching
    """

    def __init__(
        self,
        clip_model: Optional[CLIPModel] = None,
        config: Optional[CLIPConfig] = None,
        cache_embeddings: bool = True,
        parallel_processing: bool = True,
        max_workers: int = 4
    ):
        """
        Initialize CLIP frame embedder

        Args:
            clip_model: Existing CLIP model instance
            config: CLIP configuration (if clip_model not provided)
            cache_embeddings: Cache embeddings to avoid recomputation
            parallel_processing: Process frames in parallel
            max_workers: Number of parallel workers
        """
        self.clip_model = clip_model or CLIPModel(config)
        self.cache_embeddings = cache_embeddings
        self.parallel_processing = parallel_processing
        self.max_workers = max_workers

        # Embedding cache
        self._embedding_cache: Dict[str, np.ndarray] = {}

    def embed_frame(
        self,
        frame_path: Path,
        frame_number: Optional[int] = None,
        timestamp: Optional[float] = None
    ) -> FrameEmbedding:
        """
        Generate CLIP embedding for a single frame

        Args:
            frame_path: Path to frame image
            frame_number: Frame number in video
            timestamp: Timestamp in video

        Returns:
            FrameEmbedding
        """
        # Check cache
        cache_key = str(frame_path)
        if self.cache_embeddings and cache_key in self._embedding_cache:
            logger.debug(f"Using cached embedding for {frame_path.name}")
            embedding = self._embedding_cache[cache_key]
        else:
            # Generate embedding
            embedding = self.clip_model.encode_image(frame_path)

            # Cache if enabled
            if self.cache_embeddings:
                self._embedding_cache[cache_key] = embedding

        return FrameEmbedding(
            frame_path=frame_path,
            embedding=embedding,
            frame_number=frame_number,
            timestamp=timestamp,
            metadata={'embedding_dim': len(embedding)}
        )

    def embed_frames(
        self,
        frame_paths: List[Path],
        frame_numbers: Optional[List[int]] = None,
        timestamps: Optional[List[float]] = None
    ) -> List[FrameEmbedding]:
        """
        Generate CLIP embeddings for multiple frames

        Args:
            frame_paths: List of frame paths
            frame_numbers: Optional frame numbers
            timestamps: Optional timestamps

        Returns:
            List of FrameEmbedding
        """
        if frame_numbers is None:
            frame_numbers = [None] * len(frame_paths)
        if timestamps is None:
            timestamps = [None] * len(frame_paths)

        logger.info(f"Generating CLIP embeddings for {len(frame_paths)} frames")

        if self.parallel_processing:
            return self._embed_frames_parallel(
                frame_paths, frame_numbers, timestamps
            )
        else:
            return self._embed_frames_sequential(
                frame_paths, frame_numbers, timestamps
            )

    def _embed_frames_sequential(
        self,
        frame_paths: List[Path],
        frame_numbers: List[Optional[int]],
        timestamps: List[Optional[float]]
    ) -> List[FrameEmbedding]:
        """Embed frames sequentially"""
        embeddings = []

        for frame_path, frame_num, ts in zip(frame_paths, frame_numbers, timestamps):
            try:
                embedding = self.embed_frame(frame_path, frame_num, ts)
                embeddings.append(embedding)
            except Exception as e:
                logger.error(f"Failed to embed {frame_path}: {e}")
                # Add empty embedding
                embeddings.append(FrameEmbedding(
                    frame_path=frame_path,
                    embedding=np.array([]),
                    frame_number=frame_num,
                    timestamp=ts,
                    metadata={'error': str(e)}
                ))

        return embeddings

    def _embed_frames_parallel(
        self,
        frame_paths: List[Path],
        frame_numbers: List[Optional[int]],
        timestamps: List[Optional[float]]
    ) -> List[FrameEmbedding]:
        """Embed frames in parallel"""
        results = [None] * len(frame_paths)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            for idx, (frame_path, frame_num, ts) in enumerate(
                zip(frame_paths, frame_numbers, timestamps)
            ):
                future = executor.submit(
                    self.embed_frame, frame_path, frame_num, ts
                )
                futures[future] = idx

            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.error(f"Frame embedding failed: {e}")
                    results[idx] = FrameEmbedding(
                        frame_path=frame_paths[idx],
                        embedding=np.array([]),
                        frame_number=frame_numbers[idx],
                        timestamp=timestamps[idx],
                        metadata={'error': str(e)}
                    )

        return results

    def embed_frames_batch(
        self,
        frame_paths: List[Path],
        frame_numbers: Optional[List[int]] = None,
        timestamps: Optional[List[float]] = None
    ) -> List[FrameEmbedding]:
        """
        Generate embeddings using CLIP's batch processing
        More efficient than parallel processing for large batches

        Args:
            frame_paths: List of frame paths
            frame_numbers: Optional frame numbers
            timestamps: Optional timestamps

        Returns:
            List of FrameEmbedding
        """
        if frame_numbers is None:
            frame_numbers = list(range(len(frame_paths)))
        if timestamps is None:
            timestamps = [None] * len(frame_paths)

        logger.info(f"Batch embedding {len(frame_paths)} frames with CLIP")

        # Check cache for existing embeddings
        uncached_indices = []
        uncached_paths = []
        embeddings_dict = {}

        for idx, frame_path in enumerate(frame_paths):
            cache_key = str(frame_path)
            if self.cache_embeddings and cache_key in self._embedding_cache:
                embeddings_dict[idx] = self._embedding_cache[cache_key]
            else:
                uncached_indices.append(idx)
                uncached_paths.append(frame_path)

        # Generate embeddings for uncached frames
        if uncached_paths:
            logger.info(f"Generating {len(uncached_paths)} new embeddings")
            embedding_matrix = self.clip_model.encode_images_batch(uncached_paths)

            # Cache and store
            for i, idx in enumerate(uncached_indices):
                embedding = embedding_matrix[i]
                embeddings_dict[idx] = embedding

                # Cache
                if self.cache_embeddings:
                    cache_key = str(uncached_paths[i])
                    self._embedding_cache[cache_key] = embedding

        # Create FrameEmbedding objects
        frame_embeddings = []
        for idx in range(len(frame_paths)):
            frame_embeddings.append(FrameEmbedding(
                frame_path=frame_paths[idx],
                embedding=embeddings_dict[idx],
                frame_number=frame_numbers[idx],
                timestamp=timestamps[idx],
                metadata={'embedding_dim': len(embeddings_dict[idx])}
            ))

        logger.info(f"Generated {len(frame_embeddings)} frame embeddings")

        return frame_embeddings

    def embed_video(
        self,
        video_path: Path,
        frame_paths: List[Path],
        fps: float = 30.0,
        use_batch: bool = True
    ) -> VideoEmbeddings:
        """
        Generate CLIP embeddings for all frames in a video

        Args:
            video_path: Path to video file
            frame_paths: List of extracted frame paths
            fps: Video frames per second
            use_batch: Use batch processing (recommended)

        Returns:
            VideoEmbeddings
        """
        logger.info(f"Embedding video: {video_path}")

        # Generate timestamps
        timestamps = [i / fps for i in range(len(frame_paths))]
        frame_numbers = list(range(len(frame_paths)))

        # Generate embeddings
        if use_batch:
            frame_embeddings = self.embed_frames_batch(
                frame_paths, frame_numbers, timestamps
            )
        else:
            frame_embeddings = self.embed_frames(
                frame_paths, frame_numbers, timestamps
            )

        # Create embedding matrix for fast search
        embedding_matrix = np.vstack([
            emb.embedding for emb in frame_embeddings
            if len(emb.embedding) > 0
        ])

        result = VideoEmbeddings(
            video_path=video_path,
            frame_embeddings=frame_embeddings,
            embedding_matrix=embedding_matrix,
            total_frames=len(frame_embeddings),
            embedding_dim=self.clip_model.get_embedding_dim(),
            model_name=self.clip_model.config.model_name,
            metadata={'fps': fps}
        )

        logger.info(
            f"Video embedding complete: {result.total_frames} frames, "
            f"{result.embedding_dim}-dim embeddings"
        )

        return result

    def get_embedding_matrix(
        self,
        frame_embeddings: List[FrameEmbedding]
    ) -> np.ndarray:
        """
        Get stacked embedding matrix from frame embeddings

        Args:
            frame_embeddings: List of FrameEmbedding

        Returns:
            Numpy array (n_frames x embedding_dim)
        """
        valid_embeddings = [
            emb.embedding for emb in frame_embeddings
            if len(emb.embedding) > 0
        ]

        if not valid_embeddings:
            return np.array([])

        return np.vstack(valid_embeddings)

    def clear_cache(self):
        """Clear embedding cache"""
        self._embedding_cache.clear()
        logger.info("Embedding cache cleared")

    def get_cache_size(self) -> int:
        """Get number of cached embeddings"""
        return len(self._embedding_cache)

    def get_cache_memory(self) -> float:
        """
        Get approximate cache memory usage in MB

        Returns:
            Memory usage in megabytes
        """
        total_bytes = sum(
            emb.nbytes for emb in self._embedding_cache.values()
        )
        return total_bytes / (1024 * 1024)

    def save_embeddings(
        self,
        video_embeddings: VideoEmbeddings,
        output_path: Path
    ):
        """
        Save video embeddings to disk

        Args:
            video_embeddings: VideoEmbeddings to save
            output_path: Output file path (.npz format)
        """
        # Prepare data
        data = {
            'embedding_matrix': video_embeddings.embedding_matrix,
            'frame_paths': [str(emb.frame_path) for emb in video_embeddings.frame_embeddings],
            'frame_numbers': [emb.frame_number for emb in video_embeddings.frame_embeddings],
            'timestamps': [emb.timestamp for emb in video_embeddings.frame_embeddings],
            'embedding_dim': video_embeddings.embedding_dim,
            'model_name': video_embeddings.model_name,
            'total_frames': video_embeddings.total_frames
        }

        # Save
        np.savez_compressed(output_path, **data)
        logger.info(f"Saved embeddings to {output_path}")

    def load_embeddings(
        self,
        embedding_path: Path,
        video_path: Optional[Path] = None
    ) -> VideoEmbeddings:
        """
        Load video embeddings from disk

        Args:
            embedding_path: Path to embeddings file (.npz)
            video_path: Optional video path

        Returns:
            VideoEmbeddings
        """
        # Load data
        data = np.load(embedding_path, allow_pickle=True)

        # Reconstruct frame embeddings
        frame_embeddings = []
        for i in range(len(data['frame_paths'])):
            frame_embeddings.append(FrameEmbedding(
                frame_path=Path(str(data['frame_paths'][i])),
                embedding=data['embedding_matrix'][i],
                frame_number=int(data['frame_numbers'][i]) if data['frame_numbers'][i] is not None else None,
                timestamp=float(data['timestamps'][i]) if data['timestamps'][i] is not None else None
            ))

        result = VideoEmbeddings(
            video_path=video_path,
            frame_embeddings=frame_embeddings,
            embedding_matrix=data['embedding_matrix'],
            total_frames=int(data['total_frames']),
            embedding_dim=int(data['embedding_dim']),
            model_name=str(data['model_name'])
        )

        logger.info(f"Loaded embeddings from {embedding_path}")

        return result


def embed_video_frames(
    frame_paths: List[Path],
    video_path: Optional[Path] = None,
    model_name: str = "ViT-B/32"
) -> VideoEmbeddings:
    """
    Convenience function to embed video frames

    Args:
        frame_paths: List of frame paths
        video_path: Optional video path
        model_name: CLIP model name

    Returns:
        VideoEmbeddings
    """
    config = CLIPConfig(model_name=model_name)
    embedder = CLIPFrameEmbedder(config=config)
    return embedder.embed_video(video_path or Path("unknown.mp4"), frame_paths)
