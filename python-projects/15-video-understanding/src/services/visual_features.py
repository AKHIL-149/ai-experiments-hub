"""
Visual feature extraction service
Extracts deep learning features from images for similarity and clustering
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VisualFeatures:
    """Visual features extracted from an image"""
    image_path: Path
    features: np.ndarray
    model: str
    feature_dim: int
    metadata: Optional[Dict[str, any]] = None


@dataclass
class SimilarityResult:
    """Similarity comparison result"""
    image1_path: Path
    image2_path: Path
    similarity: float
    distance: float
    metric: str
    metadata: Optional[Dict[str, any]] = None


class VisualFeatureExtractor:
    """
    Extract visual features from images using deep learning models
    Supports ResNet, VGG, EfficientNet, and other CNN backbones
    """

    def __init__(
        self,
        model_name: str = "resnet50",
        use_gpu: bool = True,
        feature_layer: str = "avg_pool"
    ):
        """
        Initialize visual feature extractor

        Args:
            model_name: Model to use (resnet50, resnet101, vgg16, vgg19, efficientnet_b0)
            use_gpu: Use GPU if available
            feature_layer: Layer to extract features from
        """
        self.model_name = model_name
        self.use_gpu = use_gpu
        self.feature_layer = feature_layer
        self.model = None
        self.preprocess = None
        self.device = None

    def extract_features(
        self,
        image_path: Path,
        normalize: bool = True
    ) -> VisualFeatures:
        """
        Extract visual features from image

        Args:
            image_path: Path to image file
            normalize: Normalize features to unit length

        Returns:
            VisualFeatures

        Raises:
            ValueError: If image not found
            RuntimeError: If feature extraction fails
        """
        if not image_path.exists():
            raise ValueError(f"Image not found: {image_path}")

        logger.info(f"Extracting visual features from {image_path}")

        try:
            # Load model if not loaded
            if self.model is None:
                self._load_model()

            # Load and preprocess image
            image = self._load_image(image_path)
            image_tensor = self.preprocess(image).unsqueeze(0)

            if self.device:
                image_tensor = image_tensor.to(self.device)

            # Extract features
            import torch
            with torch.no_grad():
                features = self.model(image_tensor)

            # Convert to numpy
            features_np = features.cpu().numpy().flatten()

            # Normalize if requested
            if normalize:
                features_np = features_np / (np.linalg.norm(features_np) + 1e-8)

            result = VisualFeatures(
                image_path=image_path,
                features=features_np,
                model=self.model_name,
                feature_dim=len(features_np),
                metadata={'normalized': normalize}
            )

            logger.info(
                f"Extracted {len(features_np)}-dim features from {image_path.name}"
            )

            return result

        except Exception as e:
            raise RuntimeError(f"Feature extraction failed: {e}") from e

    def extract_batch(
        self,
        image_paths: List[Path],
        normalize: bool = True
    ) -> List[VisualFeatures]:
        """
        Extract features from multiple images

        Args:
            image_paths: List of image paths
            normalize: Normalize features

        Returns:
            List of VisualFeatures
        """
        logger.info(f"Extracting features from {len(image_paths)} images")

        results = []
        for image_path in image_paths:
            try:
                result = self.extract_features(image_path, normalize)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to extract features from {image_path}: {e}")
                # Add empty result
                results.append(VisualFeatures(
                    image_path=image_path,
                    features=np.array([]),
                    model=self.model_name,
                    feature_dim=0,
                    metadata={'error': str(e)}
                ))

        return results

    def _load_model(self):
        """Load feature extraction model"""
        try:
            import torch
            import torchvision.models as models
            from torchvision import transforms

            # Setup device
            if self.use_gpu and torch.cuda.is_available():
                self.device = torch.device('cuda')
                logger.info("Using GPU for feature extraction")
            else:
                self.device = torch.device('cpu')
                logger.info("Using CPU for feature extraction")

            # Load model
            logger.info(f"Loading {self.model_name} model...")

            if self.model_name == "resnet50":
                base_model = models.resnet50(pretrained=True)
                # Remove final classification layer
                self.model = torch.nn.Sequential(*list(base_model.children())[:-1])
            elif self.model_name == "resnet101":
                base_model = models.resnet101(pretrained=True)
                self.model = torch.nn.Sequential(*list(base_model.children())[:-1])
            elif self.model_name == "vgg16":
                base_model = models.vgg16(pretrained=True)
                self.model = base_model.features
            elif self.model_name == "vgg19":
                base_model = models.vgg19(pretrained=True)
                self.model = base_model.features
            elif self.model_name == "efficientnet_b0":
                base_model = models.efficientnet_b0(pretrained=True)
                self.model = torch.nn.Sequential(*list(base_model.children())[:-1])
            else:
                # Default to ResNet50
                logger.warning(f"Unknown model {self.model_name}, using resnet50")
                base_model = models.resnet50(pretrained=True)
                self.model = torch.nn.Sequential(*list(base_model.children())[:-1])

            self.model.eval()
            self.model.to(self.device)

            # Setup preprocessing
            self.preprocess = transforms.Compose([
                transforms.Resize(256),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225]
                )
            ])

            logger.info(f"Model {self.model_name} loaded successfully")

        except ImportError:
            raise RuntimeError(
                "PyTorch and torchvision required. Install with: pip install torch torchvision"
            )

    def _load_image(self, image_path: Path):
        """Load image using PIL"""
        from PIL import Image

        image = Image.open(image_path).convert('RGB')
        return image

    def compute_similarity(
        self,
        features1: VisualFeatures,
        features2: VisualFeatures,
        metric: str = "cosine"
    ) -> SimilarityResult:
        """
        Compute similarity between two feature vectors

        Args:
            features1: First image features
            features2: Second image features
            metric: Similarity metric (cosine, euclidean, dot)

        Returns:
            SimilarityResult
        """
        if len(features1.features) == 0 or len(features2.features) == 0:
            raise ValueError("Cannot compute similarity with empty features")

        if metric == "cosine":
            # Cosine similarity
            similarity = np.dot(features1.features, features2.features)
            distance = 1 - similarity
        elif metric == "euclidean":
            # Euclidean distance
            distance = np.linalg.norm(features1.features - features2.features)
            similarity = 1 / (1 + distance)
        elif metric == "dot":
            # Dot product
            similarity = np.dot(features1.features, features2.features)
            distance = -similarity
        else:
            raise ValueError(f"Unknown metric: {metric}")

        return SimilarityResult(
            image1_path=features1.image_path,
            image2_path=features2.image_path,
            similarity=float(similarity),
            distance=float(distance),
            metric=metric
        )

    def find_similar(
        self,
        query_features: VisualFeatures,
        candidate_features: List[VisualFeatures],
        top_k: int = 10,
        metric: str = "cosine"
    ) -> List[Tuple[VisualFeatures, float]]:
        """
        Find most similar images to query

        Args:
            query_features: Query image features
            candidate_features: List of candidate features
            top_k: Number of results to return
            metric: Similarity metric

        Returns:
            List of (VisualFeatures, similarity_score) tuples
        """
        similarities = []

        for candidate in candidate_features:
            try:
                result = self.compute_similarity(
                    query_features,
                    candidate,
                    metric
                )
                similarities.append((candidate, result.similarity))
            except Exception as e:
                logger.error(
                    f"Failed to compute similarity with {candidate.image_path}: {e}"
                )

        # Sort by similarity (descending)
        similarities.sort(key=lambda x: x[1], reverse=True)

        # Return top-k
        return similarities[:top_k]

    def cluster_features(
        self,
        features_list: List[VisualFeatures],
        n_clusters: int = 5,
        method: str = "kmeans"
    ) -> Dict[int, List[VisualFeatures]]:
        """
        Cluster images based on visual features

        Args:
            features_list: List of image features
            n_clusters: Number of clusters
            method: Clustering method (kmeans, hierarchical)

        Returns:
            Dictionary mapping cluster_id to list of VisualFeatures
        """
        if len(features_list) == 0:
            return {}

        # Stack feature vectors
        feature_matrix = np.vstack([f.features for f in features_list])

        if method == "kmeans":
            from sklearn.cluster import KMeans

            clusterer = KMeans(n_clusters=n_clusters, random_state=42)
            labels = clusterer.fit_predict(feature_matrix)

        elif method == "hierarchical":
            from sklearn.cluster import AgglomerativeClustering

            clusterer = AgglomerativeClustering(n_clusters=n_clusters)
            labels = clusterer.fit_predict(feature_matrix)

        else:
            raise ValueError(f"Unknown clustering method: {method}")

        # Group by cluster
        clusters = {}
        for idx, label in enumerate(labels):
            label = int(label)
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(features_list[idx])

        logger.info(f"Clustered {len(features_list)} images into {n_clusters} clusters")

        return clusters

    def compute_pairwise_similarities(
        self,
        features_list: List[VisualFeatures],
        metric: str = "cosine"
    ) -> np.ndarray:
        """
        Compute pairwise similarity matrix

        Args:
            features_list: List of image features
            metric: Similarity metric

        Returns:
            NxN similarity matrix
        """
        n = len(features_list)
        similarity_matrix = np.zeros((n, n))

        for i in range(n):
            for j in range(i, n):
                if i == j:
                    similarity_matrix[i, j] = 1.0
                else:
                    result = self.compute_similarity(
                        features_list[i],
                        features_list[j],
                        metric
                    )
                    similarity_matrix[i, j] = result.similarity
                    similarity_matrix[j, i] = result.similarity

        return similarity_matrix

    def reduce_dimensions(
        self,
        features_list: List[VisualFeatures],
        n_components: int = 2,
        method: str = "pca"
    ) -> np.ndarray:
        """
        Reduce feature dimensions for visualization

        Args:
            features_list: List of image features
            n_components: Target number of dimensions
            method: Reduction method (pca, tsne, umap)

        Returns:
            Reduced feature matrix (n_images x n_components)
        """
        feature_matrix = np.vstack([f.features for f in features_list])

        if method == "pca":
            from sklearn.decomposition import PCA

            reducer = PCA(n_components=n_components)
            reduced = reducer.fit_transform(feature_matrix)

        elif method == "tsne":
            from sklearn.manifold import TSNE

            reducer = TSNE(n_components=n_components, random_state=42)
            reduced = reducer.fit_transform(feature_matrix)

        elif method == "umap":
            try:
                import umap
                reducer = umap.UMAP(n_components=n_components, random_state=42)
                reduced = reducer.fit_transform(feature_matrix)
            except ImportError:
                logger.warning("UMAP not available, falling back to PCA")
                from sklearn.decomposition import PCA
                reducer = PCA(n_components=n_components)
                reduced = reducer.fit_transform(feature_matrix)

        else:
            raise ValueError(f"Unknown reduction method: {method}")

        logger.info(
            f"Reduced {feature_matrix.shape[1]}-dim features to {n_components}-dim using {method}"
        )

        return reduced


def extract_visual_features(
    image_path: Path,
    model_name: str = "resnet50",
    normalize: bool = True
) -> VisualFeatures:
    """
    Convenience function to extract visual features from image

    Args:
        image_path: Path to image file
        model_name: Model to use
        normalize: Normalize features

    Returns:
        VisualFeatures
    """
    extractor = VisualFeatureExtractor(model_name=model_name)
    return extractor.extract_features(image_path, normalize)


def extract_features_batch(
    image_paths: List[Path],
    model_name: str = "resnet50"
) -> List[VisualFeatures]:
    """
    Convenience function to extract features from multiple images

    Args:
        image_paths: List of image paths
        model_name: Model to use

    Returns:
        List of VisualFeatures
    """
    extractor = VisualFeatureExtractor(model_name=model_name)
    return extractor.extract_batch(image_paths)
