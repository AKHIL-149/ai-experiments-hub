"""
Embedding indexer for fast vector retrieval
Uses FAISS for efficient nearest neighbor search
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Tuple, Union
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class IndexConfig:
    """Configuration for embedding index"""
    index_type: str = "flat"  # flat, ivf, hnsw
    metric: str = "cosine"  # cosine, l2, ip (inner product)
    n_clusters: int = 100  # For IVF index
    n_probe: int = 10  # Number of clusters to search
    use_gpu: bool = False
    normalize: bool = True  # Normalize embeddings for cosine similarity


@dataclass
class SearchResult:
    """Search result from index"""
    indices: np.ndarray  # Indices of nearest neighbors
    distances: np.ndarray  # Distances to nearest neighbors
    similarities: Optional[np.ndarray] = None  # Similarity scores (if applicable)
    metadata: Optional[Dict[str, any]] = None


class EmbeddingIndexer:
    """
    Fast vector indexing and retrieval using FAISS
    Supports multiple index types and metrics
    """

    def __init__(self, config: Optional[IndexConfig] = None):
        """
        Initialize embedding indexer

        Args:
            config: Index configuration
        """
        self.config = config or IndexConfig()
        self.index = None
        self.embedding_dim = None
        self.n_embeddings = 0
        self.metadata_store: List[Dict] = []

    def build_index(
        self,
        embeddings: np.ndarray,
        metadata: Optional[List[Dict]] = None
    ):
        """
        Build index from embeddings

        Args:
            embeddings: Embedding matrix (n x dim)
            metadata: Optional metadata for each embedding

        Raises:
            RuntimeError: If index building fails
        """
        try:
            import faiss
        except ImportError:
            raise RuntimeError(
                "FAISS required. Install with: pip install faiss-cpu (or faiss-gpu)"
            )

        self.embedding_dim = embeddings.shape[1]
        self.n_embeddings = len(embeddings)

        logger.info(
            f"Building {self.config.index_type} index for {self.n_embeddings} "
            f"embeddings of dimension {self.embedding_dim}"
        )

        # Normalize embeddings if needed
        if self.config.normalize:
            embeddings = embeddings / (
                np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-8
            )

        # Build index based on type
        if self.config.index_type == "flat":
            self.index = self._build_flat_index(embeddings)
        elif self.config.index_type == "ivf":
            self.index = self._build_ivf_index(embeddings)
        elif self.config.index_type == "hnsw":
            self.index = self._build_hnsw_index(embeddings)
        else:
            raise ValueError(f"Unknown index type: {self.config.index_type}")

        # Store metadata
        if metadata:
            self.metadata_store = metadata
        else:
            self.metadata_store = [{'index': i} for i in range(len(embeddings))]

        logger.info(f"Index built successfully with {self.index.ntotal} vectors")

    def _build_flat_index(self, embeddings: np.ndarray):
        """Build flat (exact) index"""
        import faiss

        if self.config.metric == "cosine":
            # For cosine similarity with normalized vectors, use inner product
            index = faiss.IndexFlatIP(self.embedding_dim)
        elif self.config.metric == "l2":
            index = faiss.IndexFlatL2(self.embedding_dim)
        elif self.config.metric == "ip":
            index = faiss.IndexFlatIP(self.embedding_dim)
        else:
            raise ValueError(f"Unknown metric: {self.config.metric}")

        index.add(embeddings.astype(np.float32))

        return index

    def _build_ivf_index(self, embeddings: np.ndarray):
        """Build IVF (inverted file) index for faster search"""
        import faiss

        # Create quantizer
        if self.config.metric == "cosine" or self.config.metric == "ip":
            quantizer = faiss.IndexFlatIP(self.embedding_dim)
            index = faiss.IndexIVFFlat(
                quantizer, self.embedding_dim, self.config.n_clusters
            )
        elif self.config.metric == "l2":
            quantizer = faiss.IndexFlatL2(self.embedding_dim)
            index = faiss.IndexIVFFlat(
                quantizer, self.embedding_dim, self.config.n_clusters
            )
        else:
            raise ValueError(f"Unknown metric: {self.config.metric}")

        # Train index
        logger.info(f"Training IVF index with {self.config.n_clusters} clusters")
        index.train(embeddings.astype(np.float32))

        # Add vectors
        index.add(embeddings.astype(np.float32))

        # Set number of clusters to probe
        index.nprobe = self.config.n_probe

        return index

    def _build_hnsw_index(self, embeddings: np.ndarray):
        """Build HNSW (Hierarchical Navigable Small World) index"""
        import faiss

        # HNSW parameters
        M = 32  # Number of connections per layer
        ef_construction = 40  # Size of dynamic candidate list

        if self.config.metric == "cosine" or self.config.metric == "ip":
            index = faiss.IndexHNSWFlat(self.embedding_dim, M)
        elif self.config.metric == "l2":
            index = faiss.IndexHNSWFlat(self.embedding_dim, M)
        else:
            raise ValueError(f"Unknown metric: {self.config.metric}")

        index.hnsw.efConstruction = ef_construction

        # Add vectors
        index.add(embeddings.astype(np.float32))

        return index

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 10
    ) -> SearchResult:
        """
        Search for nearest neighbors

        Args:
            query_embedding: Query embedding (1D array)
            top_k: Number of results to return

        Returns:
            SearchResult with indices and distances
        """
        if self.index is None:
            raise RuntimeError("Index not built. Call build_index() first.")

        # Ensure query is 2D
        if query_embedding.ndim == 1:
            query_embedding = query_embedding.reshape(1, -1)

        # Normalize if needed
        if self.config.normalize:
            query_embedding = query_embedding / (
                np.linalg.norm(query_embedding, axis=1, keepdims=True) + 1e-8
            )

        # Search
        distances, indices = self.index.search(
            query_embedding.astype(np.float32), top_k
        )

        # Convert distances to similarities for cosine/IP
        similarities = None
        if self.config.metric in ["cosine", "ip"]:
            similarities = distances  # FAISS returns similarities for IP
        elif self.config.metric == "l2":
            # Convert L2 distance to similarity
            similarities = 1 / (1 + distances)

        return SearchResult(
            indices=indices[0],
            distances=distances[0],
            similarities=similarities[0] if similarities is not None else None,
            metadata={
                'top_k': top_k,
                'metric': self.config.metric,
                'index_type': self.config.index_type
            }
        )

    def batch_search(
        self,
        query_embeddings: np.ndarray,
        top_k: int = 10
    ) -> List[SearchResult]:
        """
        Search with multiple queries

        Args:
            query_embeddings: Query embeddings (n x dim)
            top_k: Number of results per query

        Returns:
            List of SearchResult
        """
        if self.index is None:
            raise RuntimeError("Index not built. Call build_index() first.")

        # Normalize if needed
        if self.config.normalize:
            query_embeddings = query_embeddings / (
                np.linalg.norm(query_embeddings, axis=1, keepdims=True) + 1e-8
            )

        # Search
        distances, indices = self.index.search(
            query_embeddings.astype(np.float32), top_k
        )

        # Convert to SearchResult objects
        results = []
        for i in range(len(query_embeddings)):
            similarities = None
            if self.config.metric in ["cosine", "ip"]:
                similarities = distances[i]
            elif self.config.metric == "l2":
                similarities = 1 / (1 + distances[i])

            results.append(SearchResult(
                indices=indices[i],
                distances=distances[i],
                similarities=similarities,
                metadata={'top_k': top_k}
            ))

        return results

    def add_embeddings(
        self,
        embeddings: np.ndarray,
        metadata: Optional[List[Dict]] = None
    ):
        """
        Add new embeddings to existing index

        Args:
            embeddings: New embeddings to add
            metadata: Optional metadata for new embeddings
        """
        if self.index is None:
            raise RuntimeError("Index not built. Call build_index() first.")

        # Normalize if needed
        if self.config.normalize:
            embeddings = embeddings / (
                np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-8
            )

        # Add to index
        self.index.add(embeddings.astype(np.float32))

        # Update metadata
        if metadata:
            self.metadata_store.extend(metadata)
        else:
            start_idx = self.n_embeddings
            self.metadata_store.extend([
                {'index': start_idx + i} for i in range(len(embeddings))
            ])

        self.n_embeddings += len(embeddings)

        logger.info(f"Added {len(embeddings)} embeddings. Total: {self.n_embeddings}")

    def get_metadata(self, indices: np.ndarray) -> List[Dict]:
        """
        Get metadata for given indices

        Args:
            indices: Array of indices

        Returns:
            List of metadata dictionaries
        """
        return [self.metadata_store[i] for i in indices]

    def save_index(self, index_path: Path, metadata_path: Optional[Path] = None):
        """
        Save index to disk

        Args:
            index_path: Path to save index
            metadata_path: Optional path to save metadata
        """
        if self.index is None:
            raise RuntimeError("Index not built. Call build_index() first.")

        import faiss
        import pickle

        # Save FAISS index
        faiss.write_index(self.index, str(index_path))
        logger.info(f"Saved index to {index_path}")

        # Save metadata
        if metadata_path is None:
            metadata_path = index_path.parent / f"{index_path.stem}_metadata.pkl"

        with open(metadata_path, 'wb') as f:
            pickle.dump({
                'metadata_store': self.metadata_store,
                'embedding_dim': self.embedding_dim,
                'n_embeddings': self.n_embeddings,
                'config': self.config
            }, f)

        logger.info(f"Saved metadata to {metadata_path}")

    def load_index(self, index_path: Path, metadata_path: Optional[Path] = None):
        """
        Load index from disk

        Args:
            index_path: Path to index file
            metadata_path: Optional path to metadata file
        """
        import faiss
        import pickle

        # Load FAISS index
        self.index = faiss.read_index(str(index_path))
        logger.info(f"Loaded index from {index_path}")

        # Load metadata
        if metadata_path is None:
            metadata_path = index_path.parent / f"{index_path.stem}_metadata.pkl"

        if metadata_path.exists():
            with open(metadata_path, 'rb') as f:
                data = pickle.load(f)
                self.metadata_store = data['metadata_store']
                self.embedding_dim = data['embedding_dim']
                self.n_embeddings = data['n_embeddings']
                self.config = data.get('config', self.config)

            logger.info(f"Loaded metadata from {metadata_path}")
        else:
            logger.warning(f"Metadata file not found: {metadata_path}")

    def get_stats(self) -> Dict[str, any]:
        """
        Get index statistics

        Returns:
            Dictionary of statistics
        """
        stats = {
            'n_embeddings': self.n_embeddings,
            'embedding_dim': self.embedding_dim,
            'index_type': self.config.index_type,
            'metric': self.config.metric,
            'normalize': self.config.normalize
        }

        if self.index:
            stats['index_size'] = self.index.ntotal

        return stats


def create_frame_index(
    embeddings: np.ndarray,
    frame_paths: List[Path],
    timestamps: Optional[List[float]] = None,
    index_type: str = "flat"
) -> EmbeddingIndexer:
    """
    Convenience function to create frame index

    Args:
        embeddings: Frame embeddings
        frame_paths: Frame file paths
        timestamps: Optional timestamps
        index_type: Index type (flat, ivf, hnsw)

    Returns:
        EmbeddingIndexer
    """
    # Create metadata
    metadata = []
    for i, path in enumerate(frame_paths):
        meta = {
            'index': i,
            'frame_path': str(path),
        }
        if timestamps:
            meta['timestamp'] = timestamps[i]
        metadata.append(meta)

    # Build index
    config = IndexConfig(index_type=index_type, metric="cosine")
    indexer = EmbeddingIndexer(config)
    indexer.build_index(embeddings, metadata)

    return indexer
