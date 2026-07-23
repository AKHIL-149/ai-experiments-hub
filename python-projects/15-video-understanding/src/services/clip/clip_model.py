"""
CLIP model integration
Contrastive Language-Image Pre-training for semantic search
"""

import logging
from pathlib import Path
from typing import List, Optional, Union, Tuple
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CLIPConfig:
    """Configuration for CLIP model"""
    model_name: str = "ViT-B/32"  # ViT-B/32, ViT-B/16, ViT-L/14
    device: str = "auto"  # auto, cuda, cpu
    batch_size: int = 32
    normalize_embeddings: bool = True
    cache_dir: Optional[Path] = None


class CLIPModel:
    """
    CLIP model for multi-modal embeddings

    Supports:
    - Text-to-image semantic search
    - Image-to-image similarity (via CLIP embeddings)
    - Zero-shot image classification
    - Joint vision-language embeddings
    """

    def __init__(self, config: Optional[CLIPConfig] = None):
        """
        Initialize CLIP model

        Args:
            config: CLIP configuration
        """
        self.config = config or CLIPConfig()
        self.model = None
        self.preprocess = None
        self.device = None
        self.tokenizer = None

        self._initialize_model()

    def _initialize_model(self):
        """Initialize CLIP model and preprocessing"""
        try:
            import torch
            import clip

            # Determine device
            if self.config.device == "auto":
                if torch.cuda.is_available():
                    self.device = torch.device("cuda")
                    logger.info("Using GPU for CLIP")
                else:
                    self.device = torch.device("cpu")
                    logger.info("Using CPU for CLIP")
            else:
                self.device = torch.device(self.config.device)

            # Load model
            logger.info(f"Loading CLIP model: {self.config.model_name}")

            if self.config.cache_dir:
                self.config.cache_dir.mkdir(parents=True, exist_ok=True)
                download_root = str(self.config.cache_dir)
            else:
                download_root = None

            self.model, self.preprocess = clip.load(
                self.config.model_name,
                device=self.device,
                download_root=download_root
            )

            self.model.eval()

            logger.info(f"CLIP model {self.config.model_name} loaded successfully")

        except ImportError:
            raise RuntimeError(
                "CLIP package required. Install with: pip install git+https://github.com/openai/CLIP.git"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to load CLIP model: {e}") from e

    def encode_image(
        self,
        image_path: Path,
        normalize: bool = True
    ) -> np.ndarray:
        """
        Encode image to CLIP embedding

        Args:
            image_path: Path to image file
            normalize: Normalize embedding to unit length

        Returns:
            Image embedding as numpy array

        Raises:
            ValueError: If image not found
            RuntimeError: If encoding fails
        """
        if not image_path.exists():
            raise ValueError(f"Image not found: {image_path}")

        try:
            import torch
            from PIL import Image

            # Load and preprocess image
            image = Image.open(image_path).convert('RGB')
            image_tensor = self.preprocess(image).unsqueeze(0).to(self.device)

            # Encode image
            with torch.no_grad():
                image_features = self.model.encode_image(image_tensor)

                if normalize or self.config.normalize_embeddings:
                    image_features = image_features / image_features.norm(dim=-1, keepdim=True)

            # Convert to numpy
            embedding = image_features.cpu().numpy().flatten()

            return embedding

        except Exception as e:
            raise RuntimeError(f"Image encoding failed: {e}") from e

    def encode_images_batch(
        self,
        image_paths: List[Path],
        normalize: bool = True
    ) -> np.ndarray:
        """
        Encode multiple images in batches

        Args:
            image_paths: List of image paths
            normalize: Normalize embeddings

        Returns:
            Array of embeddings (n_images x embedding_dim)
        """
        import torch
        from PIL import Image

        embeddings = []

        # Process in batches
        for i in range(0, len(image_paths), self.config.batch_size):
            batch_paths = image_paths[i:i + self.config.batch_size]

            # Load and preprocess batch
            batch_images = []
            for image_path in batch_paths:
                try:
                    image = Image.open(image_path).convert('RGB')
                    image_tensor = self.preprocess(image)
                    batch_images.append(image_tensor)
                except Exception as e:
                    logger.error(f"Failed to load {image_path}: {e}")
                    # Add zero vector for failed images
                    batch_images.append(torch.zeros_like(self.preprocess(
                        Image.new('RGB', (224, 224))
                    )))

            # Stack batch
            batch_tensor = torch.stack(batch_images).to(self.device)

            # Encode batch
            with torch.no_grad():
                batch_features = self.model.encode_image(batch_tensor)

                if normalize or self.config.normalize_embeddings:
                    batch_features = batch_features / batch_features.norm(dim=-1, keepdim=True)

            embeddings.append(batch_features.cpu().numpy())

        # Concatenate all batches
        all_embeddings = np.vstack(embeddings)

        logger.info(f"Encoded {len(image_paths)} images to CLIP embeddings")

        return all_embeddings

    def encode_text(
        self,
        text: Union[str, List[str]],
        normalize: bool = True
    ) -> np.ndarray:
        """
        Encode text to CLIP embedding

        Args:
            text: Text string or list of text strings
            normalize: Normalize embeddings

        Returns:
            Text embedding(s) as numpy array
        """
        try:
            import torch
            import clip

            # Convert single string to list
            if isinstance(text, str):
                text = [text]
                return_single = True
            else:
                return_single = False

            # Tokenize text
            text_tokens = clip.tokenize(text).to(self.device)

            # Encode text
            with torch.no_grad():
                text_features = self.model.encode_text(text_tokens)

                if normalize or self.config.normalize_embeddings:
                    text_features = text_features / text_features.norm(dim=-1, keepdim=True)

            # Convert to numpy
            embeddings = text_features.cpu().numpy()

            if return_single:
                return embeddings[0]
            else:
                return embeddings

        except Exception as e:
            raise RuntimeError(f"Text encoding failed: {e}") from e

    def compute_similarity(
        self,
        image_embedding: np.ndarray,
        text_embedding: np.ndarray
    ) -> float:
        """
        Compute cosine similarity between image and text embeddings

        Args:
            image_embedding: Image embedding
            text_embedding: Text embedding

        Returns:
            Similarity score (0-1)
        """
        # Ensure embeddings are normalized
        image_norm = image_embedding / (np.linalg.norm(image_embedding) + 1e-8)
        text_norm = text_embedding / (np.linalg.norm(text_embedding) + 1e-8)

        # Compute cosine similarity
        similarity = np.dot(image_norm, text_norm)

        return float(similarity)

    def search_images(
        self,
        query: str,
        image_embeddings: np.ndarray,
        top_k: int = 10
    ) -> List[Tuple[int, float]]:
        """
        Search images using text query

        Args:
            query: Text query
            image_embeddings: Array of image embeddings (n_images x dim)
            top_k: Number of results to return

        Returns:
            List of (index, similarity_score) tuples
        """
        # Encode query
        query_embedding = self.encode_text(query)

        # Compute similarities
        similarities = image_embeddings @ query_embedding

        # Get top-k indices
        top_indices = np.argsort(similarities)[::-1][:top_k]

        # Return indices and scores
        results = [(int(idx), float(similarities[idx])) for idx in top_indices]

        return results

    def classify_image(
        self,
        image_path: Path,
        class_labels: List[str]
    ) -> List[Tuple[str, float]]:
        """
        Zero-shot image classification using CLIP

        Args:
            image_path: Path to image
            class_labels: List of class labels

        Returns:
            List of (label, probability) tuples sorted by probability
        """
        import torch

        # Encode image
        image_embedding = self.encode_image(image_path, normalize=True)

        # Encode class labels as text
        text_prompts = [f"a photo of a {label}" for label in class_labels]
        text_embeddings = self.encode_text(text_prompts, normalize=True)

        # Compute similarities
        similarities = text_embeddings @ image_embedding

        # Convert to probabilities using softmax
        probs = torch.softmax(torch.tensor(similarities) * 100, dim=0).numpy()

        # Sort by probability
        results = [(class_labels[i], float(probs[i])) for i in range(len(class_labels))]
        results.sort(key=lambda x: x[1], reverse=True)

        return results

    def find_similar_images(
        self,
        query_embedding: np.ndarray,
        candidate_embeddings: np.ndarray,
        top_k: int = 10
    ) -> List[Tuple[int, float]]:
        """
        Find similar images using image embedding

        Args:
            query_embedding: Query image embedding
            candidate_embeddings: Array of candidate embeddings
            top_k: Number of results

        Returns:
            List of (index, similarity_score) tuples
        """
        # Compute similarities
        similarities = candidate_embeddings @ query_embedding

        # Get top-k
        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = [(int(idx), float(similarities[idx])) for idx in top_indices]

        return results

    def get_embedding_dim(self) -> int:
        """Get dimensionality of CLIP embeddings"""
        # Standard CLIP embedding dimensions
        dims = {
            "ViT-B/32": 512,
            "ViT-B/16": 512,
            "ViT-L/14": 768,
            "ViT-L/14@336px": 768,
            "RN50": 1024,
            "RN101": 512,
            "RN50x4": 640,
            "RN50x16": 768,
            "RN50x64": 1024
        }

        return dims.get(self.config.model_name, 512)

    def batch_search(
        self,
        queries: List[str],
        image_embeddings: np.ndarray,
        top_k: int = 10
    ) -> List[List[Tuple[int, float]]]:
        """
        Batch text-to-image search

        Args:
            queries: List of text queries
            image_embeddings: Array of image embeddings
            top_k: Number of results per query

        Returns:
            List of result lists, one per query
        """
        # Encode all queries
        query_embeddings = self.encode_text(queries)

        results = []

        for query_embedding in query_embeddings:
            # Compute similarities
            similarities = image_embeddings @ query_embedding

            # Get top-k
            top_indices = np.argsort(similarities)[::-1][:top_k]

            query_results = [(int(idx), float(similarities[idx])) for idx in top_indices]
            results.append(query_results)

        return results

    def compute_image_text_matrix(
        self,
        image_embeddings: np.ndarray,
        text_embeddings: np.ndarray
    ) -> np.ndarray:
        """
        Compute similarity matrix between images and texts

        Args:
            image_embeddings: Array of image embeddings (n_images x dim)
            text_embeddings: Array of text embeddings (n_texts x dim)

        Returns:
            Similarity matrix (n_images x n_texts)
        """
        # Matrix multiplication: (n_images x dim) @ (dim x n_texts)
        similarity_matrix = image_embeddings @ text_embeddings.T

        return similarity_matrix

    def describe_image(
        self,
        image_path: Path,
        candidate_descriptions: List[str]
    ) -> List[Tuple[str, float]]:
        """
        Find best matching descriptions for an image

        Args:
            image_path: Path to image
            candidate_descriptions: List of possible descriptions

        Returns:
            List of (description, similarity) tuples sorted by similarity
        """
        # Encode image
        image_embedding = self.encode_image(image_path)

        # Encode descriptions
        text_embeddings = self.encode_text(candidate_descriptions)

        # Compute similarities
        similarities = text_embeddings @ image_embedding

        # Sort by similarity
        results = [
            (candidate_descriptions[i], float(similarities[i]))
            for i in range(len(candidate_descriptions))
        ]
        results.sort(key=lambda x: x[1], reverse=True)

        return results


def create_clip_model(
    model_name: str = "ViT-B/32",
    device: str = "auto"
) -> CLIPModel:
    """
    Convenience function to create CLIP model

    Args:
        model_name: CLIP model variant
        device: Device to use (auto, cuda, cpu)

    Returns:
        CLIPModel instance
    """
    config = CLIPConfig(model_name=model_name, device=device)
    return CLIPModel(config)
