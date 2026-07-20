"""
Frame hashing utilities for detecting duplicate and similar frames
Uses perceptual hashing (pHash) to identify visually similar frames
"""

import hashlib
import logging
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Set
from dataclasses import dataclass
from PIL import Image
import imagehash

logger = logging.getLogger(__name__)


@dataclass
class FrameHash:
    """Hash information for a frame"""
    frame_path: Path
    md5_hash: str  # Exact duplicate detection
    perceptual_hash: str  # Similar frame detection
    dhash: str  # Difference hash
    average_hash: str  # Average hash
    timestamp: Optional[float] = None
    frame_number: Optional[int] = None


class HashAlgorithm:
    """Available hashing algorithms"""
    MD5 = "md5"  # Exact duplicate detection
    PHASH = "phash"  # Perceptual hash (robust to minor changes)
    DHASH = "dhash"  # Difference hash (faster, less precise)
    AVERAGE = "average"  # Average hash (fastest, least precise)


class FrameHasher:
    """
    Compute and compare hashes for video frames to detect duplicates and similar frames
    """

    def __init__(self, hash_size: int = 8):
        """
        Initialize frame hasher

        Args:
            hash_size: Size of perceptual hash (default 8 = 64-bit hash)
                      Larger sizes are more precise but slower
        """
        self.hash_size = hash_size

    def compute_hash(
        self,
        frame_path: Path,
        algorithms: Optional[List[str]] = None,
        timestamp: Optional[float] = None,
        frame_number: Optional[int] = None
    ) -> FrameHash:
        """
        Compute multiple hashes for a frame

        Args:
            frame_path: Path to frame image
            algorithms: List of algorithms to use (default: all)
            timestamp: Optional frame timestamp
            frame_number: Optional frame number

        Returns:
            FrameHash object with computed hashes

        Raises:
            ValueError: If frame file not found
            RuntimeError: If hash computation fails
        """
        if not frame_path.exists():
            raise ValueError(f"Frame file not found: {frame_path}")

        if algorithms is None:
            algorithms = [
                HashAlgorithm.MD5,
                HashAlgorithm.PHASH,
                HashAlgorithm.DHASH,
                HashAlgorithm.AVERAGE
            ]

        try:
            # Load image
            image = Image.open(frame_path)

            # Compute hashes
            md5_hash = ""
            phash = ""
            dhash = ""
            avg_hash = ""

            if HashAlgorithm.MD5 in algorithms:
                md5_hash = self._compute_md5(frame_path)

            if HashAlgorithm.PHASH in algorithms:
                phash = str(imagehash.phash(image, hash_size=self.hash_size))

            if HashAlgorithm.DHASH in algorithms:
                dhash = str(imagehash.dhash(image, hash_size=self.hash_size))

            if HashAlgorithm.AVERAGE in algorithms:
                avg_hash = str(imagehash.average_hash(image, hash_size=self.hash_size))

            return FrameHash(
                frame_path=frame_path,
                md5_hash=md5_hash,
                perceptual_hash=phash,
                dhash=dhash,
                average_hash=avg_hash,
                timestamp=timestamp,
                frame_number=frame_number
            )

        except Exception as e:
            raise RuntimeError(f"Failed to compute hash for {frame_path}: {e}") from e

    def compute_hashes_batch(
        self,
        frame_paths: List[Path],
        algorithms: Optional[List[str]] = None
    ) -> List[FrameHash]:
        """
        Compute hashes for multiple frames

        Args:
            frame_paths: List of frame paths
            algorithms: List of algorithms to use

        Returns:
            List of FrameHash objects
        """
        hashes = []

        for idx, frame_path in enumerate(frame_paths, start=1):
            try:
                frame_hash = self.compute_hash(
                    frame_path=frame_path,
                    algorithms=algorithms,
                    frame_number=idx
                )
                hashes.append(frame_hash)

            except Exception as e:
                logger.error(f"Failed to hash {frame_path}: {e}")
                continue

        logger.info(f"Computed hashes for {len(hashes)}/{len(frame_paths)} frames")
        return hashes

    @staticmethod
    def _compute_md5(file_path: Path) -> str:
        """Compute MD5 hash of file"""
        md5 = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                md5.update(chunk)
        return md5.hexdigest()

    def find_duplicates(
        self,
        frame_hashes: List[FrameHash],
        algorithm: str = HashAlgorithm.MD5
    ) -> Dict[str, List[FrameHash]]:
        """
        Find exact duplicate frames

        Args:
            frame_hashes: List of FrameHash objects
            algorithm: Hash algorithm to use for comparison

        Returns:
            Dictionary mapping hash to list of duplicate frames
        """
        duplicates: Dict[str, List[FrameHash]] = {}

        for frame_hash in frame_hashes:
            # Get the hash value based on algorithm
            if algorithm == HashAlgorithm.MD5:
                hash_value = frame_hash.md5_hash
            elif algorithm == HashAlgorithm.PHASH:
                hash_value = frame_hash.perceptual_hash
            elif algorithm == HashAlgorithm.DHASH:
                hash_value = frame_hash.dhash
            elif algorithm == HashAlgorithm.AVERAGE:
                hash_value = frame_hash.average_hash
            else:
                raise ValueError(f"Unknown algorithm: {algorithm}")

            if not hash_value:
                continue

            if hash_value not in duplicates:
                duplicates[hash_value] = []

            duplicates[hash_value].append(frame_hash)

        # Filter to only keep groups with duplicates
        duplicates = {k: v for k, v in duplicates.items() if len(v) > 1}

        logger.info(
            f"Found {len(duplicates)} groups of duplicates "
            f"({sum(len(v) for v in duplicates.values())} total frames)"
        )

        return duplicates

    def find_similar_frames(
        self,
        frame_hashes: List[FrameHash],
        threshold: int = 10,
        algorithm: str = HashAlgorithm.PHASH
    ) -> List[Tuple[FrameHash, FrameHash, int]]:
        """
        Find similar (but not identical) frames

        Args:
            frame_hashes: List of FrameHash objects
            threshold: Hamming distance threshold (lower = more similar)
            algorithm: Hash algorithm to use

        Returns:
            List of (frame1, frame2, distance) tuples for similar pairs
        """
        similar_pairs = []

        # Compare all pairs
        for i, hash1 in enumerate(frame_hashes):
            for hash2 in frame_hashes[i + 1:]:
                # Get hash values
                if algorithm == HashAlgorithm.PHASH:
                    h1 = imagehash.hex_to_hash(hash1.perceptual_hash)
                    h2 = imagehash.hex_to_hash(hash2.perceptual_hash)
                elif algorithm == HashAlgorithm.DHASH:
                    h1 = imagehash.hex_to_hash(hash1.dhash)
                    h2 = imagehash.hex_to_hash(hash2.dhash)
                elif algorithm == HashAlgorithm.AVERAGE:
                    h1 = imagehash.hex_to_hash(hash1.average_hash)
                    h2 = imagehash.hex_to_hash(hash2.average_hash)
                else:
                    raise ValueError(f"Unsupported algorithm for similarity: {algorithm}")

                # Compute Hamming distance
                distance = h1 - h2

                if distance <= threshold:
                    similar_pairs.append((hash1, hash2, distance))

        logger.info(f"Found {len(similar_pairs)} similar frame pairs (threshold={threshold})")
        return similar_pairs

    def deduplicate_frames(
        self,
        frame_hashes: List[FrameHash],
        exact_only: bool = False,
        similarity_threshold: int = 5
    ) -> Tuple[List[FrameHash], List[FrameHash]]:
        """
        Remove duplicate and similar frames, keeping only unique ones

        Args:
            frame_hashes: List of FrameHash objects
            exact_only: Only remove exact duplicates (ignore similar frames)
            similarity_threshold: Hamming distance threshold for similarity

        Returns:
            Tuple of (unique_frames, removed_frames)
        """
        if not frame_hashes:
            return [], []

        unique_frames = []
        removed_frames = []
        seen_hashes: Set[str] = set()

        # First pass: remove exact duplicates
        for frame_hash in frame_hashes:
            hash_key = frame_hash.md5_hash

            if hash_key in seen_hashes:
                removed_frames.append(frame_hash)
                logger.debug(f"Removing exact duplicate: {frame_hash.frame_path}")
            else:
                unique_frames.append(frame_hash)
                seen_hashes.add(hash_key)

        # Second pass: remove similar frames if requested
        if not exact_only and len(unique_frames) > 1:
            final_unique = []
            seen_phashes: Set[str] = set()

            for frame_hash in unique_frames:
                # Check if similar to any already kept frame
                is_similar = False

                for kept_phash in seen_phashes:
                    h1 = imagehash.hex_to_hash(frame_hash.perceptual_hash)
                    h2 = imagehash.hex_to_hash(kept_phash)
                    distance = h1 - h2

                    if distance <= similarity_threshold:
                        is_similar = True
                        break

                if is_similar:
                    removed_frames.append(frame_hash)
                    logger.debug(f"Removing similar frame: {frame_hash.frame_path}")
                else:
                    final_unique.append(frame_hash)
                    seen_phashes.add(frame_hash.perceptual_hash)

            unique_frames = final_unique

        logger.info(
            f"Deduplicated frames: {len(unique_frames)} unique, "
            f"{len(removed_frames)} removed"
        )

        return unique_frames, removed_frames

    def compare_frames(
        self,
        frame1_path: Path,
        frame2_path: Path,
        algorithm: str = HashAlgorithm.PHASH
    ) -> int:
        """
        Compare two frames and return similarity score

        Args:
            frame1_path: Path to first frame
            frame2_path: Path to second frame
            algorithm: Hash algorithm to use

        Returns:
            Hamming distance (0 = identical, higher = more different)
        """
        hash1 = self.compute_hash(frame1_path, algorithms=[algorithm])
        hash2 = self.compute_hash(frame2_path, algorithms=[algorithm])

        if algorithm == HashAlgorithm.MD5:
            # MD5 is binary (same or different)
            return 0 if hash1.md5_hash == hash2.md5_hash else 1

        elif algorithm == HashAlgorithm.PHASH:
            h1 = imagehash.hex_to_hash(hash1.perceptual_hash)
            h2 = imagehash.hex_to_hash(hash2.perceptual_hash)

        elif algorithm == HashAlgorithm.DHASH:
            h1 = imagehash.hex_to_hash(hash1.dhash)
            h2 = imagehash.hex_to_hash(hash2.dhash)

        elif algorithm == HashAlgorithm.AVERAGE:
            h1 = imagehash.hex_to_hash(hash1.average_hash)
            h2 = imagehash.hex_to_hash(hash2.average_hash)

        else:
            raise ValueError(f"Unknown algorithm: {algorithm}")

        return h1 - h2


def compute_frame_hash(frame_path: Path) -> FrameHash:
    """
    Convenience function to compute all hashes for a frame

    Args:
        frame_path: Path to frame image

    Returns:
        FrameHash object
    """
    hasher = FrameHasher()
    return hasher.compute_hash(frame_path)


def deduplicate_frame_list(
    frame_paths: List[Path],
    exact_only: bool = False,
    similarity_threshold: int = 5
) -> Tuple[List[Path], List[Path]]:
    """
    Convenience function to deduplicate a list of frames

    Args:
        frame_paths: List of frame paths
        exact_only: Only remove exact duplicates
        similarity_threshold: Hamming distance threshold

    Returns:
        Tuple of (unique_paths, removed_paths)
    """
    hasher = FrameHasher()

    # Compute hashes
    frame_hashes = hasher.compute_hashes_batch(frame_paths)

    # Deduplicate
    unique, removed = hasher.deduplicate_frames(
        frame_hashes,
        exact_only=exact_only,
        similarity_threshold=similarity_threshold
    )

    # Extract paths
    unique_paths = [fh.frame_path for fh in unique]
    removed_paths = [fh.frame_path for fh in removed]

    return unique_paths, removed_paths
