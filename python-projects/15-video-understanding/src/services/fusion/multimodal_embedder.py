"""
Multi-modal embedder for unified cross-modal embeddings
Combine visual, text, and audio embeddings with weighted fusion strategies
"""

import logging
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np

logger = logging.getLogger(__name__)


class FusionStrategy(str, Enum):
    """Embedding fusion strategies"""
    WEIGHTED_SUM = "weighted_sum"  # Weighted linear combination
    CONCATENATION = "concatenation"  # Concatenate embeddings
    ATTENTION = "attention"  # Attention-based fusion
    MAX_POOLING = "max_pooling"  # Element-wise max
    AVERAGE_POOLING = "average_pooling"  # Element-wise average
    LEARNED = "learned"  # Learned projection (requires training)


@dataclass
class ModalityEmbedding:
    """Embedding from a single modality"""
    modality: str  # visual, text, audio
    embedding: np.ndarray
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MultiModalEmbedding:
    """Fused multi-modal embedding"""
    fused_embedding: np.ndarray
    fusion_strategy: FusionStrategy
    modality_weights: Dict[str, float]
    source_embeddings: List[ModalityEmbedding] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EmbeddingFusionConfig:
    """Configuration for embedding fusion"""
    strategy: FusionStrategy = FusionStrategy.WEIGHTED_SUM
    normalize_inputs: bool = True
    normalize_output: bool = True

    # Weights for different modalities
    visual_weight: float = 0.5
    text_weight: float = 0.3
    audio_weight: float = 0.2

    # Dimension handling
    target_dimension: Optional[int] = None  # None = use first embedding's dimension
    dimension_reduction: str = "truncate"  # truncate, pad, project

    # Concatenation settings
    concat_normalize_per_modality: bool = True

    # Attention settings
    attention_temperature: float = 1.0


class MultiModalEmbedder:
    """
    Generate unified embeddings from multiple modalities
    Supports various fusion strategies and weighting schemes
    """

    def __init__(
        self,
        config: Optional[EmbeddingFusionConfig] = None,
    ):
        """
        Initialize multi-modal embedder

        Args:
            config: Fusion configuration
        """
        self.config = config or EmbeddingFusionConfig()

        logger.info(
            f"Initialized MultiModalEmbedder "
            f"(strategy={self.config.strategy.value})"
        )

    def fuse_embeddings(
        self,
        visual_embedding: Optional[np.ndarray] = None,
        text_embedding: Optional[np.ndarray] = None,
        audio_embedding: Optional[np.ndarray] = None,
        visual_confidence: float = 1.0,
        text_confidence: float = 1.0,
        audio_confidence: float = 1.0,
        custom_weights: Optional[Dict[str, float]] = None,
    ) -> MultiModalEmbedding:
        """
        Fuse embeddings from multiple modalities

        Args:
            visual_embedding: Visual embedding
            text_embedding: Text embedding
            audio_embedding: Audio embedding
            visual_confidence: Confidence for visual modality
            text_confidence: Confidence for text modality
            audio_confidence: Confidence for audio modality
            custom_weights: Custom weights (overrides config)

        Returns:
            MultiModalEmbedding
        """
        # Collect available embeddings
        modality_embeddings = []

        if visual_embedding is not None:
            modality_embeddings.append(ModalityEmbedding(
                modality="visual",
                embedding=visual_embedding,
                confidence=visual_confidence,
            ))

        if text_embedding is not None:
            modality_embeddings.append(ModalityEmbedding(
                modality="text",
                embedding=text_embedding,
                confidence=text_confidence,
            ))

        if audio_embedding is not None:
            modality_embeddings.append(ModalityEmbedding(
                modality="audio",
                embedding=audio_embedding,
                confidence=audio_confidence,
            ))

        if not modality_embeddings:
            raise ValueError("At least one embedding must be provided")

        # Determine weights
        if custom_weights:
            weights = custom_weights
        else:
            weights = {
                "visual": self.config.visual_weight,
                "text": self.config.text_weight,
                "audio": self.config.audio_weight,
            }

        # Adjust weights by confidence
        adjusted_weights = {}
        for mod_emb in modality_embeddings:
            mod = mod_emb.modality
            adjusted_weights[mod] = weights.get(mod, 0.0) * mod_emb.confidence

        # Normalize weights
        total_weight = sum(adjusted_weights.values())
        if total_weight > 0:
            adjusted_weights = {k: v / total_weight for k, v in adjusted_weights.items()}

        # Fuse embeddings using strategy
        if self.config.strategy == FusionStrategy.WEIGHTED_SUM:
            fused = self._weighted_sum_fusion(modality_embeddings, adjusted_weights)
        elif self.config.strategy == FusionStrategy.CONCATENATION:
            fused = self._concatenation_fusion(modality_embeddings)
        elif self.config.strategy == FusionStrategy.ATTENTION:
            fused = self._attention_fusion(modality_embeddings, adjusted_weights)
        elif self.config.strategy == FusionStrategy.MAX_POOLING:
            fused = self._max_pooling_fusion(modality_embeddings)
        elif self.config.strategy == FusionStrategy.AVERAGE_POOLING:
            fused = self._average_pooling_fusion(modality_embeddings)
        else:
            raise ValueError(f"Unsupported fusion strategy: {self.config.strategy}")

        return MultiModalEmbedding(
            fused_embedding=fused,
            fusion_strategy=self.config.strategy,
            modality_weights=adjusted_weights,
            source_embeddings=modality_embeddings,
            metadata={
                "num_modalities": len(modality_embeddings),
                "dimension": len(fused),
            },
        )

    def _weighted_sum_fusion(
        self,
        embeddings: List[ModalityEmbedding],
        weights: Dict[str, float],
    ) -> np.ndarray:
        """
        Weighted sum fusion strategy

        Args:
            embeddings: List of modality embeddings
            weights: Modality weights

        Returns:
            Fused embedding
        """
        # Normalize input embeddings if requested
        normalized_embeddings = []
        for emb in embeddings:
            emb_array = emb.embedding.copy()
            if self.config.normalize_inputs:
                emb_array = emb_array / (np.linalg.norm(emb_array) + 1e-8)
            normalized_embeddings.append((emb.modality, emb_array))

        # Determine target dimension
        target_dim = self._get_target_dimension([e for _, e in normalized_embeddings])

        # Align dimensions
        aligned_embeddings = []
        for modality, emb in normalized_embeddings:
            aligned = self._align_dimension(emb, target_dim)
            aligned_embeddings.append((modality, aligned))

        # Weighted sum
        fused = np.zeros(target_dim, dtype=np.float32)
        for modality, emb in aligned_embeddings:
            weight = weights.get(modality, 0.0)
            fused += weight * emb

        # Normalize output if requested
        if self.config.normalize_output:
            fused = fused / (np.linalg.norm(fused) + 1e-8)

        return fused

    def _concatenation_fusion(
        self,
        embeddings: List[ModalityEmbedding],
    ) -> np.ndarray:
        """
        Concatenation fusion strategy

        Args:
            embeddings: List of modality embeddings

        Returns:
            Fused embedding
        """
        parts = []

        for emb in embeddings:
            emb_array = emb.embedding.copy()

            # Normalize per modality if requested
            if self.config.concat_normalize_per_modality:
                emb_array = emb_array / (np.linalg.norm(emb_array) + 1e-8)

            parts.append(emb_array)

        # Concatenate
        fused = np.concatenate(parts)

        # Normalize output if requested
        if self.config.normalize_output:
            fused = fused / (np.linalg.norm(fused) + 1e-8)

        return fused

    def _attention_fusion(
        self,
        embeddings: List[ModalityEmbedding],
        weights: Dict[str, float],
    ) -> np.ndarray:
        """
        Attention-based fusion strategy

        Args:
            embeddings: List of modality embeddings
            weights: Base modality weights

        Returns:
            Fused embedding
        """
        # Normalize embeddings
        normalized_embeddings = []
        for emb in embeddings:
            emb_array = emb.embedding.copy()
            if self.config.normalize_inputs:
                emb_array = emb_array / (np.linalg.norm(emb_array) + 1e-8)
            normalized_embeddings.append((emb.modality, emb_array))

        # Determine target dimension
        target_dim = self._get_target_dimension([e for _, e in normalized_embeddings])

        # Align dimensions
        aligned_embeddings = []
        for modality, emb in normalized_embeddings:
            aligned = self._align_dimension(emb, target_dim)
            aligned_embeddings.append((modality, aligned))

        # Calculate attention scores
        # Use dot product similarity with average embedding as query
        avg_embedding = np.mean([emb for _, emb in aligned_embeddings], axis=0)
        avg_embedding = avg_embedding / (np.linalg.norm(avg_embedding) + 1e-8)

        attention_scores = []
        for modality, emb in aligned_embeddings:
            # Similarity score
            score = np.dot(avg_embedding, emb)
            # Scale by base weight
            score *= weights.get(modality, 1.0)
            attention_scores.append(score)

        # Softmax with temperature
        attention_scores = np.array(attention_scores) / self.config.attention_temperature
        attention_weights = np.exp(attention_scores) / np.sum(np.exp(attention_scores))

        # Weighted combination using attention weights
        fused = np.zeros(target_dim, dtype=np.float32)
        for (modality, emb), att_weight in zip(aligned_embeddings, attention_weights):
            fused += att_weight * emb

        # Normalize output if requested
        if self.config.normalize_output:
            fused = fused / (np.linalg.norm(fused) + 1e-8)

        return fused

    def _max_pooling_fusion(
        self,
        embeddings: List[ModalityEmbedding],
    ) -> np.ndarray:
        """
        Max pooling fusion strategy

        Args:
            embeddings: List of modality embeddings

        Returns:
            Fused embedding
        """
        # Normalize embeddings
        normalized_embeddings = []
        for emb in embeddings:
            emb_array = emb.embedding.copy()
            if self.config.normalize_inputs:
                emb_array = emb_array / (np.linalg.norm(emb_array) + 1e-8)
            normalized_embeddings.append(emb_array)

        # Determine target dimension
        target_dim = self._get_target_dimension(normalized_embeddings)

        # Align dimensions
        aligned_embeddings = [
            self._align_dimension(emb, target_dim)
            for emb in normalized_embeddings
        ]

        # Stack and take max
        stacked = np.stack(aligned_embeddings, axis=0)
        fused = np.max(stacked, axis=0)

        # Normalize output if requested
        if self.config.normalize_output:
            fused = fused / (np.linalg.norm(fused) + 1e-8)

        return fused

    def _average_pooling_fusion(
        self,
        embeddings: List[ModalityEmbedding],
    ) -> np.ndarray:
        """
        Average pooling fusion strategy

        Args:
            embeddings: List of modality embeddings

        Returns:
            Fused embedding
        """
        # Normalize embeddings
        normalized_embeddings = []
        for emb in embeddings:
            emb_array = emb.embedding.copy()
            if self.config.normalize_inputs:
                emb_array = emb_array / (np.linalg.norm(emb_array) + 1e-8)
            normalized_embeddings.append(emb_array)

        # Determine target dimension
        target_dim = self._get_target_dimension(normalized_embeddings)

        # Align dimensions
        aligned_embeddings = [
            self._align_dimension(emb, target_dim)
            for emb in normalized_embeddings
        ]

        # Stack and take mean
        stacked = np.stack(aligned_embeddings, axis=0)
        fused = np.mean(stacked, axis=0)

        # Normalize output if requested
        if self.config.normalize_output:
            fused = fused / (np.linalg.norm(fused) + 1e-8)

        return fused

    def _get_target_dimension(self, embeddings: List[np.ndarray]) -> int:
        """
        Determine target dimension for fusion

        Args:
            embeddings: List of embeddings

        Returns:
            Target dimension
        """
        if self.config.target_dimension is not None:
            return self.config.target_dimension

        # Use first embedding's dimension
        return embeddings[0].shape[0]

    def _align_dimension(
        self,
        embedding: np.ndarray,
        target_dim: int,
    ) -> np.ndarray:
        """
        Align embedding to target dimension

        Args:
            embedding: Input embedding
            target_dim: Target dimension

        Returns:
            Aligned embedding
        """
        current_dim = embedding.shape[0]

        if current_dim == target_dim:
            return embedding

        if self.config.dimension_reduction == "truncate":
            if current_dim > target_dim:
                return embedding[:target_dim]
            else:
                # Pad with zeros
                return np.pad(embedding, (0, target_dim - current_dim))

        elif self.config.dimension_reduction == "pad":
            if current_dim < target_dim:
                return np.pad(embedding, (0, target_dim - current_dim))
            else:
                return embedding[:target_dim]

        elif self.config.dimension_reduction == "project":
            # Simple linear projection (random projection)
            # In practice, would use learned projection
            projection_matrix = np.random.randn(current_dim, target_dim).astype(np.float32)
            projection_matrix /= np.sqrt(current_dim)
            projected = embedding @ projection_matrix
            return projected

        else:
            raise ValueError(f"Unknown dimension reduction: {self.config.dimension_reduction}")

    def fuse_batch(
        self,
        visual_embeddings: Optional[List[np.ndarray]] = None,
        text_embeddings: Optional[List[np.ndarray]] = None,
        audio_embeddings: Optional[List[np.ndarray]] = None,
        custom_weights: Optional[Dict[str, float]] = None,
    ) -> List[MultiModalEmbedding]:
        """
        Fuse multiple sets of embeddings in batch

        Args:
            visual_embeddings: List of visual embeddings
            text_embeddings: List of text embeddings
            audio_embeddings: List of audio embeddings
            custom_weights: Custom weights

        Returns:
            List of fused embeddings
        """
        # Determine batch size
        batch_size = 0
        if visual_embeddings:
            batch_size = len(visual_embeddings)
        elif text_embeddings:
            batch_size = len(text_embeddings)
        elif audio_embeddings:
            batch_size = len(audio_embeddings)

        if batch_size == 0:
            return []

        # Pad lists to same length
        visual_embeddings = visual_embeddings or [None] * batch_size
        text_embeddings = text_embeddings or [None] * batch_size
        audio_embeddings = audio_embeddings or [None] * batch_size

        # Ensure same length
        max_len = max(len(visual_embeddings), len(text_embeddings), len(audio_embeddings))
        visual_embeddings += [None] * (max_len - len(visual_embeddings))
        text_embeddings += [None] * (max_len - len(text_embeddings))
        audio_embeddings += [None] * (max_len - len(audio_embeddings))

        # Fuse each set
        fused_embeddings = []
        for vis, txt, aud in zip(visual_embeddings, text_embeddings, audio_embeddings):
            if vis is None and txt is None and aud is None:
                continue

            fused = self.fuse_embeddings(
                visual_embedding=vis,
                text_embedding=txt,
                audio_embedding=aud,
                custom_weights=custom_weights,
            )
            fused_embeddings.append(fused)

        return fused_embeddings

    def compute_similarity(
        self,
        embedding1: MultiModalEmbedding,
        embedding2: MultiModalEmbedding,
        metric: str = "cosine",
    ) -> float:
        """
        Compute similarity between two multi-modal embeddings

        Args:
            embedding1: First embedding
            embedding2: Second embedding
            metric: Similarity metric (cosine, euclidean, dot)

        Returns:
            Similarity score
        """
        emb1 = embedding1.fused_embedding
        emb2 = embedding2.fused_embedding

        if metric == "cosine":
            similarity = np.dot(emb1, emb2) / (
                np.linalg.norm(emb1) * np.linalg.norm(emb2) + 1e-8
            )
            return float(similarity)

        elif metric == "euclidean":
            distance = np.linalg.norm(emb1 - emb2)
            # Convert to similarity (inverse distance)
            similarity = 1.0 / (1.0 + distance)
            return float(similarity)

        elif metric == "dot":
            return float(np.dot(emb1, emb2))

        else:
            raise ValueError(f"Unknown metric: {metric}")

    def get_modality_contributions(
        self,
        fused_embedding: MultiModalEmbedding,
    ) -> Dict[str, float]:
        """
        Get contribution of each modality to fused embedding

        Args:
            fused_embedding: Fused embedding

        Returns:
            Dict of modality -> contribution score
        """
        contributions = {}

        for source_emb in fused_embedding.source_embeddings:
            modality = source_emb.modality

            # Weight from fusion
            weight = fused_embedding.modality_weights.get(modality, 0.0)

            # Confidence
            confidence = source_emb.confidence

            # Combined contribution
            contributions[modality] = weight * confidence

        return contributions


def fuse_multimodal_embeddings(
    visual_embedding: Optional[np.ndarray] = None,
    text_embedding: Optional[np.ndarray] = None,
    audio_embedding: Optional[np.ndarray] = None,
    strategy: FusionStrategy = FusionStrategy.WEIGHTED_SUM,
    weights: Optional[Dict[str, float]] = None,
) -> MultiModalEmbedding:
    """
    Convenience function to fuse multi-modal embeddings

    Args:
        visual_embedding: Visual embedding
        text_embedding: Text embedding
        audio_embedding: Audio embedding
        strategy: Fusion strategy
        weights: Custom weights

    Returns:
        MultiModalEmbedding
    """
    config = EmbeddingFusionConfig(strategy=strategy)
    embedder = MultiModalEmbedder(config=config)

    return embedder.fuse_embeddings(
        visual_embedding=visual_embedding,
        text_embedding=text_embedding,
        audio_embedding=audio_embedding,
        custom_weights=weights,
    )
