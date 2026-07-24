"""
Semantic similarity calculator for CLIP embeddings
Compute and analyze similarities between images and texts
"""

import logging
from typing import List, Optional, Dict, Tuple, Union
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SimilarityMatrix:
    """Pairwise similarity matrix"""
    matrix: np.ndarray
    row_labels: Optional[List[str]] = None
    col_labels: Optional[List[str]] = None
    metric: str = "cosine"
    metadata: Optional[Dict[str, any]] = None


@dataclass
class SimilarityPair:
    """Similarity between two items"""
    item1: str
    item2: str
    similarity: float
    distance: float
    metric: str
    metadata: Optional[Dict[str, any]] = None


class SemanticSimilarityCalculator:
    """
    Calculate semantic similarities using CLIP embeddings
    Supports multiple similarity metrics and analysis functions
    """

    def __init__(self, default_metric: str = "cosine"):
        """
        Initialize similarity calculator

        Args:
            default_metric: Default similarity metric (cosine, euclidean, dot)
        """
        self.default_metric = default_metric

    def cosine_similarity(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray
    ) -> float:
        """
        Compute cosine similarity between two embeddings

        Args:
            embedding1: First embedding
            embedding2: Second embedding

        Returns:
            Cosine similarity (0-1)
        """
        # Normalize embeddings
        norm1 = embedding1 / (np.linalg.norm(embedding1) + 1e-8)
        norm2 = embedding2 / (np.linalg.norm(embedding2) + 1e-8)

        # Compute dot product
        similarity = np.dot(norm1, norm2)

        return float(similarity)

    def euclidean_distance(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray
    ) -> float:
        """
        Compute Euclidean distance between embeddings

        Args:
            embedding1: First embedding
            embedding2: Second embedding

        Returns:
            Euclidean distance
        """
        distance = np.linalg.norm(embedding1 - embedding2)
        return float(distance)

    def dot_product_similarity(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray
    ) -> float:
        """
        Compute dot product similarity

        Args:
            embedding1: First embedding
            embedding2: Second embedding

        Returns:
            Dot product
        """
        similarity = np.dot(embedding1, embedding2)
        return float(similarity)

    def compute_similarity(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray,
        metric: Optional[str] = None
    ) -> SimilarityPair:
        """
        Compute similarity between two embeddings

        Args:
            embedding1: First embedding
            embedding2: Second embedding
            metric: Similarity metric (cosine, euclidean, dot)

        Returns:
            SimilarityPair
        """
        metric = metric or self.default_metric

        if metric == "cosine":
            similarity = self.cosine_similarity(embedding1, embedding2)
            distance = 1 - similarity
        elif metric == "euclidean":
            distance = self.euclidean_distance(embedding1, embedding2)
            similarity = 1 / (1 + distance)
        elif metric == "dot":
            similarity = self.dot_product_similarity(embedding1, embedding2)
            distance = -similarity
        else:
            raise ValueError(f"Unknown metric: {metric}")

        return SimilarityPair(
            item1="embedding1",
            item2="embedding2",
            similarity=similarity,
            distance=distance,
            metric=metric
        )

    def pairwise_similarity(
        self,
        embeddings1: np.ndarray,
        embeddings2: Optional[np.ndarray] = None,
        metric: Optional[str] = None,
        labels1: Optional[List[str]] = None,
        labels2: Optional[List[str]] = None
    ) -> SimilarityMatrix:
        """
        Compute pairwise similarity matrix

        Args:
            embeddings1: First set of embeddings (n x dim)
            embeddings2: Second set of embeddings (m x dim), or None for self-similarity
            metric: Similarity metric
            labels1: Labels for first set
            labels2: Labels for second set

        Returns:
            SimilarityMatrix (n x m)
        """
        metric = metric or self.default_metric

        if embeddings2 is None:
            embeddings2 = embeddings1
            labels2 = labels1

        # Normalize for cosine similarity
        if metric == "cosine":
            norm1 = embeddings1 / (np.linalg.norm(embeddings1, axis=1, keepdims=True) + 1e-8)
            norm2 = embeddings2 / (np.linalg.norm(embeddings2, axis=1, keepdims=True) + 1e-8)
            similarity_matrix = norm1 @ norm2.T

        elif metric == "euclidean":
            # Compute pairwise Euclidean distances
            # Using the formula: ||a-b||^2 = ||a||^2 + ||b||^2 - 2*a*b
            sq_norms1 = np.sum(embeddings1**2, axis=1, keepdims=True)
            sq_norms2 = np.sum(embeddings2**2, axis=1, keepdims=True)
            distances = np.sqrt(
                sq_norms1 + sq_norms2.T - 2 * embeddings1 @ embeddings2.T
            )
            similarity_matrix = 1 / (1 + distances)

        elif metric == "dot":
            similarity_matrix = embeddings1 @ embeddings2.T

        else:
            raise ValueError(f"Unknown metric: {metric}")

        return SimilarityMatrix(
            matrix=similarity_matrix,
            row_labels=labels1,
            col_labels=labels2,
            metric=metric,
            metadata={
                'shape': similarity_matrix.shape,
                'n_rows': len(embeddings1),
                'n_cols': len(embeddings2)
            }
        )

    def find_most_similar(
        self,
        query_embedding: np.ndarray,
        candidate_embeddings: np.ndarray,
        top_k: int = 10,
        metric: Optional[str] = None,
        labels: Optional[List[str]] = None
    ) -> List[Tuple[int, float]]:
        """
        Find most similar candidates to query

        Args:
            query_embedding: Query embedding (1D array)
            candidate_embeddings: Candidate embeddings (n x dim)
            top_k: Number of results
            metric: Similarity metric
            labels: Optional labels for candidates

        Returns:
            List of (index, similarity) tuples
        """
        metric = metric or self.default_metric

        # Compute similarities
        if metric == "cosine":
            query_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-8)
            cand_norm = candidate_embeddings / (
                np.linalg.norm(candidate_embeddings, axis=1, keepdims=True) + 1e-8
            )
            similarities = cand_norm @ query_norm

        elif metric == "euclidean":
            distances = np.linalg.norm(
                candidate_embeddings - query_embedding, axis=1
            )
            similarities = 1 / (1 + distances)

        elif metric == "dot":
            similarities = candidate_embeddings @ query_embedding

        else:
            raise ValueError(f"Unknown metric: {metric}")

        # Get top-k indices
        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = [(int(idx), float(similarities[idx])) for idx in top_indices]

        return results

    def find_nearest_neighbors(
        self,
        embeddings: np.ndarray,
        k: int = 5,
        metric: Optional[str] = None,
        exclude_self: bool = True
    ) -> List[List[Tuple[int, float]]]:
        """
        Find k-nearest neighbors for each embedding

        Args:
            embeddings: Embedding matrix (n x dim)
            k: Number of neighbors
            metric: Similarity metric
            exclude_self: Exclude self from neighbors

        Returns:
            List of neighbor lists, one per embedding
        """
        # Compute pairwise similarities
        sim_matrix = self.pairwise_similarity(embeddings, metric=metric)

        neighbors_list = []

        for i in range(len(embeddings)):
            similarities = sim_matrix.matrix[i]

            # Get top-k indices
            if exclude_self:
                # Set self-similarity to -inf
                similarities[i] = -np.inf

            top_indices = np.argsort(similarities)[::-1][:k]
            neighbors = [(int(idx), float(similarities[idx])) for idx in top_indices]

            neighbors_list.append(neighbors)

        return neighbors_list

    def compute_average_similarity(
        self,
        embeddings: np.ndarray,
        metric: Optional[str] = None
    ) -> float:
        """
        Compute average pairwise similarity

        Args:
            embeddings: Embedding matrix
            metric: Similarity metric

        Returns:
            Average similarity
        """
        sim_matrix = self.pairwise_similarity(embeddings, metric=metric)

        # Get upper triangle (excluding diagonal)
        n = len(embeddings)
        upper_triangle = sim_matrix.matrix[np.triu_indices(n, k=1)]

        avg_similarity = np.mean(upper_triangle)

        return float(avg_similarity)

    def find_outliers(
        self,
        embeddings: np.ndarray,
        threshold: Optional[float] = None,
        metric: Optional[str] = None
    ) -> List[int]:
        """
        Find outlier embeddings with low average similarity

        Args:
            embeddings: Embedding matrix
            threshold: Similarity threshold (auto-computed if None)
            metric: Similarity metric

        Returns:
            List of outlier indices
        """
        # Compute pairwise similarities
        sim_matrix = self.pairwise_similarity(embeddings, metric=metric)

        # Compute average similarity for each embedding
        avg_similarities = np.mean(sim_matrix.matrix, axis=1)

        # Auto-compute threshold if not provided
        if threshold is None:
            mean_sim = np.mean(avg_similarities)
            std_sim = np.std(avg_similarities)
            threshold = mean_sim - 2 * std_sim

        # Find outliers
        outlier_indices = np.where(avg_similarities < threshold)[0]

        return outlier_indices.tolist()

    def cluster_by_similarity(
        self,
        embeddings: np.ndarray,
        n_clusters: int = 5,
        method: str = "kmeans",
        metric: Optional[str] = None
    ) -> np.ndarray:
        """
        Cluster embeddings by similarity

        Args:
            embeddings: Embedding matrix
            n_clusters: Number of clusters
            method: Clustering method (kmeans, hierarchical)
            metric: Distance metric

        Returns:
            Cluster labels
        """
        if method == "kmeans":
            from sklearn.cluster import KMeans
            clusterer = KMeans(n_clusters=n_clusters, random_state=42)
            labels = clusterer.fit_predict(embeddings)

        elif method == "hierarchical":
            from sklearn.cluster import AgglomerativeClustering
            clusterer = AgglomerativeClustering(n_clusters=n_clusters)
            labels = clusterer.fit_predict(embeddings)

        else:
            raise ValueError(f"Unknown clustering method: {method}")

        return labels

    def compute_diversity_score(
        self,
        embeddings: np.ndarray,
        metric: Optional[str] = None
    ) -> float:
        """
        Compute diversity score (inverse of average similarity)

        Args:
            embeddings: Embedding matrix
            metric: Similarity metric

        Returns:
            Diversity score (0-1, higher = more diverse)
        """
        avg_sim = self.compute_average_similarity(embeddings, metric)

        # Diversity is inverse of similarity
        diversity = 1 - avg_sim

        return float(diversity)

    def rank_by_relevance(
        self,
        query_embedding: np.ndarray,
        candidate_embeddings: np.ndarray,
        labels: Optional[List[str]] = None,
        metric: Optional[str] = None
    ) -> List[Dict[str, any]]:
        """
        Rank candidates by relevance to query

        Args:
            query_embedding: Query embedding
            candidate_embeddings: Candidate embeddings
            labels: Optional labels
            metric: Similarity metric

        Returns:
            List of ranked items with scores
        """
        # Find all similarities
        results = self.find_most_similar(
            query_embedding,
            candidate_embeddings,
            top_k=len(candidate_embeddings),
            metric=metric
        )

        # Create ranked list
        ranked = []
        for rank, (idx, similarity) in enumerate(results):
            item = {
                'rank': rank + 1,
                'index': idx,
                'similarity': similarity
            }

            if labels:
                item['label'] = labels[idx]

            ranked.append(item)

        return ranked

    def compute_similarity_statistics(
        self,
        embeddings: np.ndarray,
        metric: Optional[str] = None
    ) -> Dict[str, float]:
        """
        Compute similarity statistics

        Args:
            embeddings: Embedding matrix
            metric: Similarity metric

        Returns:
            Dictionary of statistics
        """
        # Compute pairwise similarities
        sim_matrix = self.pairwise_similarity(embeddings, metric=metric)

        # Get upper triangle (excluding diagonal)
        n = len(embeddings)
        upper_triangle = sim_matrix.matrix[np.triu_indices(n, k=1)]

        stats = {
            'mean': float(np.mean(upper_triangle)),
            'std': float(np.std(upper_triangle)),
            'min': float(np.min(upper_triangle)),
            'max': float(np.max(upper_triangle)),
            'median': float(np.median(upper_triangle)),
            'q25': float(np.percentile(upper_triangle, 25)),
            'q75': float(np.percentile(upper_triangle, 75))
        }

        return stats


def compute_clip_similarity(
    embedding1: np.ndarray,
    embedding2: np.ndarray,
    metric: str = "cosine"
) -> float:
    """
    Convenience function to compute CLIP similarity

    Args:
        embedding1: First embedding
        embedding2: Second embedding
        metric: Similarity metric

    Returns:
        Similarity score
    """
    calculator = SemanticSimilarityCalculator(default_metric=metric)
    result = calculator.compute_similarity(embedding1, embedding2, metric)
    return result.similarity
