"""Image comparison functionality using vision AI."""
from typing import Dict, List, Optional, Any
from PIL import Image
import hashlib
from pathlib import Path


class ImageComparator:
    """Compare images using vision AI and structural analysis."""

    def __init__(self, vision_client=None):
        """Initialize image comparator.

        Args:
            vision_client: VisionClient instance for AI-powered comparison
        """
        self.vision_client = vision_client

    def compare_images(
        self,
        image1: Image.Image,
        image2: Image.Image,
        mode: str = 'content',
        temperature: float = 0.3,
        max_tokens: int = 1000
    ) -> Dict[str, Any]:
        """Compare two images and identify similarities/differences.

        Args:
            image1: First image
            image2: Second image
            mode: Comparison mode ('content', 'visual', 'detailed')
            temperature: Sampling temperature (lower = more factual)
            max_tokens: Maximum tokens in response

        Returns:
            Dictionary with comparison results
        """
        # Get basic structural comparison
        structural = self._structural_comparison(image1, image2)

        # If vision client available, do AI comparison
        ai_comparison = None
        if self.vision_client:
            ai_comparison = self._ai_comparison(
                image1, image2, mode, temperature, max_tokens
            )

        return {
            'structural': structural,
            'ai_analysis': ai_comparison,
            'mode': mode,
            'identical': structural['identical'],
            'similar_dimensions': structural['same_dimensions'],
            'similarity_score': self._calculate_similarity_score(structural, ai_comparison)
        }

    def _structural_comparison(
        self,
        image1: Image.Image,
        image2: Image.Image
    ) -> Dict[str, Any]:
        """Perform structural comparison of images.

        Args:
            image1: First image
            image2: Second image

        Returns:
            Dictionary with structural comparison results
        """
        # Get image properties
        size1 = image1.size
        size2 = image2.size
        format1 = image1.format or 'Unknown'
        format2 = image2.format or 'Unknown'
        mode1 = image1.mode
        mode2 = image2.mode

        # Calculate pixel hash for exact comparison
        hash1 = self._calculate_image_hash(image1)
        hash2 = self._calculate_image_hash(image2)

        identical = (hash1 == hash2)
        same_dimensions = (size1 == size2)
        same_aspect_ratio = self._compare_aspect_ratio(size1, size2)

        return {
            'image1': {
                'dimensions': f"{size1[0]}x{size1[1]}",
                'format': format1,
                'mode': mode1,
                'hash': hash1[:16]  # First 16 chars for display
            },
            'image2': {
                'dimensions': f"{size2[0]}x{size2[1]}",
                'format': format2,
                'mode': mode2,
                'hash': hash2[:16]
            },
            'identical': identical,
            'same_dimensions': same_dimensions,
            'same_aspect_ratio': same_aspect_ratio,
            'dimension_diff': {
                'width_diff': abs(size1[0] - size2[0]),
                'height_diff': abs(size1[1] - size2[1]),
                'width_ratio': size1[0] / size2[0] if size2[0] > 0 else 0,
                'height_ratio': size1[1] / size2[1] if size2[1] > 0 else 0
            }
        }

    def _ai_comparison(
        self,
        image1: Image.Image,
        image2: Image.Image,
        mode: str,
        temperature: float,
        max_tokens: int
    ) -> Dict[str, Any]:
        """Use AI to compare images semantically.

        Args:
            image1: First image
            image2: Second image
            mode: Comparison mode
            temperature: Sampling temperature
            max_tokens: Maximum tokens

        Returns:
            Dictionary with AI comparison results
        """
        # Select prompt based on mode
        prompts = {
            'content': (
                "Compare these two images in detail. Identify:\n"
                "1. What is the same between them?\n"
                "2. What is different between them?\n"
                "3. Are they showing the same subject/scene?\n"
                "4. Rate their similarity from 0-100%\n"
                "Be specific and factual."
            ),
            'visual': (
                "Compare the visual appearance of these two images:\n"
                "1. Color scheme differences\n"
                "2. Composition and layout\n"
                "3. Lighting and exposure\n"
                "4. Visual style and aesthetic\n"
                "5. Overall similarity rating (0-100%)"
            ),
            'detailed': (
                "Provide a comprehensive comparison of these two images:\n"
                "1. Subject matter (same/different?)\n"
                "2. Content differences (what changed?)\n"
                "3. Visual differences (colors, lighting, composition)\n"
                "4. Context differences (setting, time, mood)\n"
                "5. Technical differences (quality, resolution, clarity)\n"
                "6. Similarity score (0-100%) with explanation\n"
                "Be thorough and analytical."
            )
        }

        prompt = prompts.get(mode, prompts['content'])
        backend = self.vision_client.backend if self.vision_client else None

        try:
            descriptions = None
            if backend == 'ollama':
                # LLaVA can't reliably keep two images apart in one prompt - confirmed
                # live: for a beach footprint and a galaxy it answered "both images show
                # a night sky with a galaxy and a footprint" and scored them 62-76%.
                # Describe each image on its own (single-image input is what it handles
                # well), then compare the two descriptions as plain text.
                descriptions = [
                    self._describe_single(image1, temperature),
                    self._describe_single(image2, temperature),
                ]
                result = self.vision_client.analyze(
                    prompt=self._text_comparison_prompt(prompt, descriptions),
                    images=[],
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                strategy = 'describe_then_compare'
            else:
                result = self.vision_client.analyze(
                    prompt=prompt,
                    images=[image1, image2],
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                strategy = 'joint'

            # Try to extract similarity score from response
            similarity = self._extract_similarity_score(result)

            return {
                'analysis': result,
                'extracted_similarity': similarity,
                'descriptions': descriptions,
                'strategy': strategy,
                'method': 'vision_ai',
                'provider': backend
            }
        except Exception as e:
            return {
                'error': str(e),
                'method': 'vision_ai',
                'analysis': None
            }

    def _describe_single(self, image: Image.Image, temperature: float) -> str:
        """Structured description of one image (temperature is ignored on purpose)."""
        # Fixed format, generic terms, temperature 0: two independent free-form
        # descriptions of the same scene differed in specificity ("the Brooklyn
        # Bridge" vs "a large suspension bridge") and the comparison step then
        # treated that as two different places. Comparable descriptions first.
        return self.vision_client.analyze(
            prompt=(
                "Describe this image in exactly this format, using short generic terms. "
                "Do not name specific landmarks, places, people or brands, and do not "
                "speculate about anything you cannot see.\n"
                "Subject: <main subject, a few words>\n"
                "Setting: <where it is>\n"
                "Time and lighting: <time of day, light quality>\n"
                "Main colors: <2-4 colors>\n"
                "Notable objects: <up to 5 things>"
            ),
            images=[image],
            temperature=0.0,
            max_tokens=200
        ).strip()

    @staticmethod
    def _text_comparison_prompt(mode_prompt: str, descriptions: List[str]) -> str:
        """Turn a two-image comparison prompt into one over two text descriptions."""
        task = mode_prompt.replace("these two images", "Image 1 and Image 2")
        return (
            "You are comparing two images you cannot see. Below is a factual "
            "description of each.\n\n"
            f"Image 1: {descriptions[0]}\n\n"
            f"Image 2: {descriptions[1]}\n\n"
            f"{task}\n\n"
            "Rules: base your answer ONLY on the two descriptions and do not invent "
            "details. A detail that appears in only one description (for example a "
            "landmark name or an object the other description doesn't mention) is NOT "
            "a difference - only count things the descriptions actually contradict. If "
            "everything they say is consistent with the same scene, treat them as the "
            "same scene and rate similarity 80-100%. If they describe clearly different "
            "subjects or settings, say so plainly and rate low. End with a final line "
            "of the form 'Similarity rating: NN%'."
        )

    def _calculate_image_hash(self, image: Image.Image) -> str:
        """Calculate hash of image for exact comparison.

        Args:
            image: Image to hash

        Returns:
            Hash string
        """
        # Convert to bytes and hash
        img_bytes = image.tobytes()
        return hashlib.sha256(img_bytes).hexdigest()

    def _compare_aspect_ratio(
        self,
        size1: tuple,
        size2: tuple,
        tolerance: float = 0.05
    ) -> bool:
        """Compare aspect ratios of two images.

        Args:
            size1: First image size (width, height)
            size2: Second image size (width, height)
            tolerance: Tolerance for aspect ratio comparison

        Returns:
            True if aspect ratios are similar
        """
        if size1[1] == 0 or size2[1] == 0:
            return False

        ratio1 = size1[0] / size1[1]
        ratio2 = size2[0] / size2[1]

        return abs(ratio1 - ratio2) <= tolerance

    def _extract_similarity_score(self, text: str) -> Optional[int]:
        """Try to extract similarity percentage from AI response.

        Args:
            text: AI response text

        Returns:
            Similarity score (0-100) or None
        """
        import re

        # Prefer the explicit final rating line. Models often give a range
        # ("Similarity rating: 80-100%"); take its midpoint rather than the
        # upper bound the generic "(\d+)%" pattern below would pick.
        rating = re.findall(
            r'similarity\s*(?:rating|score)?\s*:?\s*(\d{1,3})(?:\s*-\s*(\d{1,3}))?\s*%',
            text.lower()
        )
        if rating:
            lo, hi = rating[-1]
            score = (int(lo) + int(hi)) // 2 if hi else int(lo)
            if 0 <= score <= 100:
                return score

        # Look for patterns like "80%", "similarity: 75", "score: 90%", etc.
        patterns = [
            r'(\d+)%',
            r'similarity[:\s]+(\d+)',
            r'score[:\s]+(\d+)',
            r'rating[:\s]+(\d+)'
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text.lower())
            if matches:
                # Get the first match that's in valid range
                for match in matches:
                    score = int(match)
                    if 0 <= score <= 100:
                        return score

        return None

    def _calculate_similarity_score(
        self,
        structural: Dict[str, Any],
        ai_comparison: Optional[Dict[str, Any]]
    ) -> int:
        """Calculate overall similarity score.

        Args:
            structural: Structural comparison results
            ai_comparison: AI comparison results

        Returns:
            Similarity score (0-100)
        """
        # If images are identical, return 100
        if structural['identical']:
            return 100

        # Start with structural similarity
        score = 0

        # Same dimensions adds 20 points
        if structural['same_dimensions']:
            score += 20
        # Similar aspect ratio adds 10 points
        elif structural['same_aspect_ratio']:
            score += 10

        # If AI comparison available and has similarity score, use it (weighted)
        # `is not None`, not truthiness: an AI rating of 0% is a real answer
        if ai_comparison and ai_comparison.get('extracted_similarity') is not None:
            ai_score = ai_comparison['extracted_similarity']
            # Weighted average: 30% structural, 70% AI
            score = int(score * 0.3 + ai_score * 0.7)

        return min(100, max(0, score))

    def find_duplicates(
        self,
        images: List[Image.Image],
        threshold: int = 95
    ) -> List[List[int]]:
        """Find duplicate or near-duplicate images in a collection.

        Args:
            images: List of images to compare
            threshold: Similarity threshold for duplicates (0-100)

        Returns:
            List of groups of duplicate image indices
        """
        if not images:
            return []

        # Calculate hashes for all images
        hashes = [self._calculate_image_hash(img) for img in images]

        # Find exact duplicates by hash
        duplicates = []
        processed = set()

        for i, hash1 in enumerate(hashes):
            if i in processed:
                continue

            group = [i]
            for j, hash2 in enumerate(hashes[i+1:], start=i+1):
                if hash1 == hash2:
                    group.append(j)
                    processed.add(j)

            if len(group) > 1:
                duplicates.append(group)
                processed.add(i)

        return duplicates
