"""
OCR (Optical Character Recognition) service
Extracts text from images using OCR engines
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TextRegion:
    """A region of detected text in an image"""
    text: str
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float
    metadata: Optional[Dict[str, any]] = None


@dataclass
class OCRResult:
    """OCR result for an image"""
    image_path: Path
    text: str
    regions: List[TextRegion]
    language: str
    confidence: float
    model: str
    metadata: Optional[Dict[str, any]] = None


class OCRService:
    """
    Extract text from images using OCR
    Supports Tesseract, EasyOCR, and cloud APIs
    """

    def __init__(
        self,
        engine: str = "tesseract",
        language: str = "eng"
    ):
        """
        Initialize OCR service

        Args:
            engine: OCR engine (tesseract, easyocr, paddleocr)
            language: Language code (eng, chi_sim, etc.)
        """
        self.engine = engine
        self.language = language
        self.reader = None

    def extract_text(
        self,
        image_path: Path,
        detect_regions: bool = True
    ) -> OCRResult:
        """
        Extract text from image

        Args:
            image_path: Path to image file
            detect_regions: Detect individual text regions

        Returns:
            OCRResult

        Raises:
            ValueError: If image not found
            RuntimeError: If OCR fails
        """
        if not image_path.exists():
            raise ValueError(f"Image not found: {image_path}")

        logger.info(f"Extracting text from {image_path}")

        try:
            if self.engine == "tesseract":
                result = self._ocr_tesseract(image_path, detect_regions)
            elif self.engine == "easyocr":
                result = self._ocr_easyocr(image_path)
            else:
                result = self._ocr_tesseract(image_path, detect_regions)

            logger.info(
                f"Extracted {len(result.text)} characters from {image_path.name}"
            )

            return result

        except Exception as e:
            raise RuntimeError(f"OCR failed: {e}") from e

    def extract_batch(
        self,
        image_paths: List[Path]
    ) -> List[OCRResult]:
        """
        Extract text from multiple images

        Args:
            image_paths: List of image paths

        Returns:
            List of OCRResult
        """
        logger.info(f"Extracting text from {len(image_paths)} images")

        results = []
        for image_path in image_paths:
            try:
                result = self.extract_text(image_path)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to extract text from {image_path}: {e}")
                results.append(OCRResult(
                    image_path=image_path,
                    text="",
                    regions=[],
                    language=self.language,
                    confidence=0.0,
                    model=self.engine,
                    metadata={'error': str(e)}
                ))

        return results

    def _ocr_tesseract(
        self,
        image_path: Path,
        detect_regions: bool
    ) -> OCRResult:
        """Extract text using Tesseract OCR"""
        try:
            import pytesseract
            from PIL import Image

            # Open image
            image = Image.open(image_path)

            # Extract text
            text = pytesseract.image_to_string(image, lang=self.language)

            # Extract regions if requested
            regions = []
            avg_confidence = 0.0

            if detect_regions:
                data = pytesseract.image_to_data(
                    image,
                    lang=self.language,
                    output_type=pytesseract.Output.DICT
                )

                n_boxes = len(data['text'])
                confidences = []

                for i in range(n_boxes):
                    text_str = data['text'][i].strip()
                    if text_str:
                        conf = int(data['conf'][i])
                        if conf > 0:
                            region = TextRegion(
                                text=text_str,
                                bbox=(
                                    data['left'][i],
                                    data['top'][i],
                                    data['left'][i] + data['width'][i],
                                    data['top'][i] + data['height'][i]
                                ),
                                confidence=conf / 100.0
                            )
                            regions.append(region)
                            confidences.append(conf)

                if confidences:
                    avg_confidence = sum(confidences) / len(confidences) / 100.0
                else:
                    avg_confidence = 0.0
            else:
                avg_confidence = 0.9  # Default confidence

            return OCRResult(
                image_path=image_path,
                text=text.strip(),
                regions=regions,
                language=self.language,
                confidence=avg_confidence,
                model="tesseract",
                metadata={'num_regions': len(regions)}
            )

        except ImportError:
            raise RuntimeError(
                "pytesseract required. Install with: pip install pytesseract"
            )
        except Exception as e:
            raise RuntimeError(f"Tesseract OCR failed: {e}") from e

    def _ocr_easyocr(self, image_path: Path) -> OCRResult:
        """Extract text using EasyOCR"""
        try:
            import easyocr

            # Load reader if not loaded
            if self.reader is None:
                logger.info(f"Loading EasyOCR model for {self.language}...")
                # Map common language codes
                lang_code = self.language if self.language != 'eng' else 'en'
                self.reader = easyocr.Reader([lang_code])
                logger.info("EasyOCR model loaded")

            # Read text
            results = self.reader.readtext(str(image_path))

            # Parse results
            regions = []
            all_text = []
            confidences = []

            for (bbox, text, conf) in results:
                # Convert bbox to x1, y1, x2, y2
                x_coords = [point[0] for point in bbox]
                y_coords = [point[1] for point in bbox]

                region = TextRegion(
                    text=text,
                    bbox=(
                        int(min(x_coords)),
                        int(min(y_coords)),
                        int(max(x_coords)),
                        int(max(y_coords))
                    ),
                    confidence=conf
                )
                regions.append(region)
                all_text.append(text)
                confidences.append(conf)

            full_text = ' '.join(all_text)
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

            return OCRResult(
                image_path=image_path,
                text=full_text,
                regions=regions,
                language=self.language,
                confidence=avg_confidence,
                model="easyocr",
                metadata={'num_regions': len(regions)}
            )

        except ImportError:
            raise RuntimeError("easyocr required. Install with: pip install easyocr")
        except Exception as e:
            raise RuntimeError(f"EasyOCR failed: {e}") from e

    def has_text(
        self,
        result: OCRResult,
        min_confidence: float = 0.5,
        min_chars: int = 3
    ) -> bool:
        """
        Check if image contains text

        Args:
            result: OCRResult
            min_confidence: Minimum confidence threshold
            min_chars: Minimum number of characters

        Returns:
            True if text is detected
        """
        if result.confidence < min_confidence:
            return False

        if len(result.text) < min_chars:
            return False

        return True

    def filter_by_confidence(
        self,
        result: OCRResult,
        min_confidence: float
    ) -> OCRResult:
        """
        Filter text regions by confidence

        Args:
            result: OCRResult
            min_confidence: Minimum confidence

        Returns:
            Filtered OCRResult
        """
        filtered_regions = [
            region for region in result.regions
            if region.confidence >= min_confidence
        ]

        filtered_text = ' '.join(region.text for region in filtered_regions)

        return OCRResult(
            image_path=result.image_path,
            text=filtered_text,
            regions=filtered_regions,
            language=result.language,
            confidence=result.confidence,
            model=result.model,
            metadata={'original_regions': len(result.regions)}
        )

    def find_frames_with_text(
        self,
        frame_paths: List[Path],
        min_confidence: float = 0.5
    ) -> List[Path]:
        """
        Find frames containing text

        Args:
            frame_paths: List of frame paths
            min_confidence: Minimum confidence

        Returns:
            List of frame paths with text
        """
        results = self.extract_batch(frame_paths)

        frames_with_text = [
            result.image_path
            for result in results
            if self.has_text(result, min_confidence)
        ]

        return frames_with_text

    def visualize_regions(
        self,
        result: OCRResult,
        output_path: Optional[Path] = None
    ) -> Optional[Path]:
        """
        Draw bounding boxes around text regions

        Args:
            result: OCRResult
            output_path: Optional output path

        Returns:
            Path to annotated image
        """
        try:
            import cv2

            # Read image
            image = cv2.imread(str(result.image_path))

            # Draw each region
            for region in result.regions:
                x1, y1, x2, y2 = region.bbox

                # Draw box
                cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)

                # Draw text
                label = f"{region.text} ({region.confidence:.2f})"
                cv2.putText(
                    image,
                    label,
                    (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 0),
                    1
                )

            # Save or display
            if output_path:
                cv2.imwrite(str(output_path), image)
                logger.info(f"Annotated image saved to {output_path}")
                return output_path
            else:
                cv2.imshow('OCR Regions', image)
                cv2.waitKey(0)
                cv2.destroyAllWindows()
                return None

        except Exception as e:
            logger.error(f"Visualization failed: {e}")
            return None


def extract_text_from_image(
    image_path: Path,
    engine: str = "tesseract",
    language: str = "eng"
) -> OCRResult:
    """
    Convenience function to extract text from image

    Args:
        image_path: Path to image file
        engine: OCR engine
        language: Language code

    Returns:
        OCRResult
    """
    service = OCRService(engine=engine, language=language)
    return service.extract_text(image_path)


def extract_text_from_frames(
    frame_paths: List[Path],
    engine: str = "tesseract"
) -> List[OCRResult]:
    """
    Convenience function to extract text from multiple frames

    Args:
        frame_paths: List of frame paths
        engine: OCR engine

    Returns:
        List of OCRResult
    """
    service = OCRService(engine=engine)
    return service.extract_batch(frame_paths)
