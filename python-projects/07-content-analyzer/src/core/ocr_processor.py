"""OCR processor for text extraction from images using Tesseract and vision models."""
import os
from typing import Dict, List, Optional, Tuple, Union
from pathlib import Path
from PIL import Image
import io


class OCRProcessor:
    """OCR text extraction with Tesseract and vision model fallback."""

    def __init__(
        self,
        use_tesseract: bool = True,
        vision_client=None,
        tesseract_config: Optional[str] = None
    ):
        """Initialize OCR processor.

        Args:
            use_tesseract: Use Tesseract OCR (requires pytesseract)
            vision_client: VisionClient instance for fallback/enhancement
            tesseract_config: Custom Tesseract configuration string
        """
        self.use_tesseract = use_tesseract
        self.vision_client = vision_client
        self.tesseract_config = tesseract_config or '--psm 3'  # Auto page segmentation

        # Lazy import of pytesseract
        self._pytesseract = None
        if use_tesseract:
            try:
                import pytesseract
                self._pytesseract = pytesseract
            except ImportError:
                print("⚠️  Warning: pytesseract not installed. Falling back to vision model.")
                self.use_tesseract = False

    def extract_text(
        self,
        image: Union[str, bytes, Image.Image],
        language: str = 'eng',
        fallback_to_vision: bool = True,
        confidence_threshold: float = 60.0
    ) -> Dict[str, any]:
        """Extract text from image with OCR.

        Args:
            image: Image (path, bytes, or PIL Image)
            language: Language code (e.g., 'eng', 'fra', 'spa')
            fallback_to_vision: Use vision model if Tesseract fails/low confidence
            confidence_threshold: Minimum confidence to accept Tesseract result

        Returns:
            Dict with:
                - text: Extracted text
                - confidence: Confidence score (0-100)
                - method: 'tesseract' or 'vision'
                - language: Detected/used language
                - details: Additional metadata
        """
        # Load image if needed
        if isinstance(image, str):
            img = Image.open(image)
        elif isinstance(image, bytes):
            img = Image.open(io.BytesIO(image))
        else:
            img = image

        result = {
            'text': '',
            'confidence': 0.0,
            'method': 'none',
            'language': language,
            'details': {}
        }

        # Try Tesseract first
        if self.use_tesseract and self._pytesseract:
            try:
                tesseract_result = self._extract_with_tesseract(img, language)

                # Check if result meets confidence threshold
                if tesseract_result['confidence'] >= confidence_threshold:
                    return tesseract_result

                # Store low-confidence result for potential fallback
                result = tesseract_result

            except Exception as e:
                print(f"⚠️  Tesseract OCR failed: {str(e)}")
                result['details']['tesseract_error'] = str(e)

        # Fallback to vision model if enabled
        if fallback_to_vision and self.vision_client:
            try:
                vision_result = self._extract_with_vision(image, language)

                # Use vision result if Tesseract failed or had low confidence
                if result['method'] == 'none' or vision_result.get('confidence', 0) > result['confidence']:
                    return vision_result

            except Exception as e:
                print(f"⚠️  Vision model OCR failed: {str(e)}")
                result['details']['vision_error'] = str(e)

        return result

    def _extract_with_tesseract(
        self,
        image: Image.Image,
        language: str = 'eng'
    ) -> Dict[str, any]:
        """Extract text using Tesseract OCR.

        Args:
            image: PIL Image
            language: Language code

        Returns:
            Dict with extraction results
        """
        # Extract text with confidence data
        data = self._pytesseract.image_to_data(
            image,
            lang=language,
            config=self.tesseract_config,
            output_type=self._pytesseract.Output.DICT
        )

        # Extract plain text
        text = self._pytesseract.image_to_string(
            image,
            lang=language,
            config=self.tesseract_config
        ).strip()

        # Calculate average confidence (filter out -1 values)
        confidences = [int(conf) for conf in data['conf'] if int(conf) != -1]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        # Extract word-level bounding boxes
        boxes = self._extract_bounding_boxes(data)

        return {
            'text': text,
            'confidence': round(avg_confidence, 2),
            'method': 'tesseract',
            'language': language,
            'details': {
                'word_count': len([w for w in data['text'] if w.strip()]),
                'bounding_boxes': boxes,
                'tesseract_version': self._pytesseract.get_tesseract_version()
            }
        }

    def _extract_bounding_boxes(self, data: Dict) -> List[Dict]:
        """Extract word-level bounding boxes from Tesseract data.

        Args:
            data: Tesseract output dictionary

        Returns:
            List of bounding boxes with text and coordinates
        """
        boxes = []
        n_boxes = len(data['text'])

        for i in range(n_boxes):
            # Skip empty text
            if not data['text'][i].strip():
                continue

            # Skip low confidence
            if int(data['conf'][i]) < 0:
                continue

            boxes.append({
                'text': data['text'][i],
                'confidence': int(data['conf'][i]),
                'bbox': {
                    'x': data['left'][i],
                    'y': data['top'][i],
                    'width': data['width'][i],
                    'height': data['height'][i]
                }
            })

        return boxes

    def _extract_with_vision(
        self,
        image: Union[str, bytes, Image.Image],
        language: str = 'eng'
    ) -> Dict[str, any]:
        """Extract text using vision model.

        Args:
            image: Image (path, bytes, or PIL Image)
            language: Language hint

        Returns:
            Dict with extraction results
        """
        if not self.vision_client:
            raise ValueError("Vision client not provided")

        # Build OCR-specific prompt
        prompt = f"""Extract all text from this image.

Instructions:
1. Transcribe ALL visible text exactly as it appears
2. Preserve formatting, line breaks, and structure
3. If text is in multiple languages, identify them
4. Note any text that's unclear or partially visible
5. Include text orientation if not horizontal

Language hint: {self._language_name(language)}

Return the extracted text with high accuracy."""

        # Prepare image for vision client
        image_list = [image]

        # Use lower temperature for factual OCR
        response = self.vision_client.analyze(
            prompt=prompt,
            images=image_list,
            temperature=0.1,  # Very deterministic for OCR
            max_tokens=2000
        )

        return {
            'text': response.strip(),
            'confidence': 85.0,  # Vision models don't provide confidence, use estimate
            'method': 'vision',
            'language': language,
            'details': {
                'provider': self.vision_client.backend,
                'model': self.vision_client.model
            }
        }

    def detect_language(self, image: Union[str, bytes, Image.Image]) -> Dict[str, any]:
        """Detect language(s) in image text.

        Args:
            image: Image (path, bytes, or PIL Image)

        Returns:
            Dict with detected languages and confidence
        """
        # Load image if needed
        if isinstance(image, str):
            img = Image.open(image)
        elif isinstance(image, bytes):
            img = Image.open(io.BytesIO(image))
        else:
            img = image

        result = {
            'languages': [],
            'primary_language': None,
            'method': 'none'
        }

        # Try Tesseract language detection
        if self.use_tesseract and self._pytesseract:
            try:
                # Try common languages
                common_langs = ['eng', 'fra', 'deu', 'spa', 'ita', 'por', 'rus', 'ara', 'chi_sim', 'jpn']

                lang_scores = {}
                for lang in common_langs:
                    try:
                        data = self._pytesseract.image_to_data(
                            img,
                            lang=lang,
                            output_type=self._pytesseract.Output.DICT
                        )
                        confidences = [int(c) for c in data['conf'] if int(c) > 0]
                        if confidences:
                            lang_scores[lang] = sum(confidences) / len(confidences)
                    except:
                        continue

                # Sort by confidence
                if lang_scores:
                    sorted_langs = sorted(lang_scores.items(), key=lambda x: x[1], reverse=True)
                    result['languages'] = [
                        {'code': lang, 'name': self._language_name(lang), 'confidence': score}
                        for lang, score in sorted_langs[:3]
                    ]
                    result['primary_language'] = sorted_langs[0][0]
                    result['method'] = 'tesseract'

            except Exception as e:
                result['error'] = f"Language detection failed: {str(e)}"

        # Fallback to vision model
        if not result['primary_language'] and self.vision_client:
            try:
                prompt = """Identify the language(s) of any text in this image.

List the languages you detect, ordered by how much text appears in each language.
Format: "Language: [percentage]%"

If no text is visible, say "No text detected"."""

                response = self.vision_client.analyze(
                    prompt=prompt,
                    images=[image],
                    temperature=0.2,
                    max_tokens=200
                )

                result['languages'] = [{'description': response}]
                result['method'] = 'vision'

            except Exception as e:
                result['error'] = f"Vision language detection failed: {str(e)}"

        return result

    def _language_name(self, code: str) -> str:
        """Convert language code to full name.

        Args:
            code: ISO 639-2/3 language code

        Returns:
            Full language name
        """
        lang_map = {
            'eng': 'English',
            'fra': 'French',
            'deu': 'German',
            'spa': 'Spanish',
            'ita': 'Italian',
            'por': 'Portuguese',
            'rus': 'Russian',
            'ara': 'Arabic',
            'chi_sim': 'Chinese (Simplified)',
            'chi_tra': 'Chinese (Traditional)',
            'jpn': 'Japanese',
            'kor': 'Korean',
            'hin': 'Hindi',
            'tha': 'Thai',
            'vie': 'Vietnamese'
        }
        return lang_map.get(code, code.upper())

    def extract_structured_data(
        self,
        image: Union[str, bytes, Image.Image],
        data_type: str = 'auto'
    ) -> Dict[str, any]:
        """Extract structured data from documents.

        Args:
            image: Image (path, bytes, or PIL Image)
            data_type: Type of document ('form', 'receipt', 'invoice', 'table', 'auto')

        Returns:
            Dict with structured data extraction
        """
        if not self.vision_client:
            raise ValueError("Vision client required for structured data extraction")

        # Build specialized prompts based on document type
        prompts = {
            'form': """Extract all form fields and their values from this image.

Return as a structured list:
Field Name: Value

Include all visible fields, checkboxes, and selections.""",

            'receipt': """Extract receipt information:

1. Merchant name and location
2. Date and time
3. All items with prices
4. Subtotal, tax, and total
5. Payment method

Format clearly with labels.""",

            'invoice': """Extract invoice details:

1. Invoice number and date
2. Vendor and customer information
3. Line items with descriptions, quantities, and prices
4. Subtotal, tax, total, and amount due
5. Payment terms

Format as structured data.""",

            'table': """Extract all data from the table in this image.

Preserve:
1. Column headers
2. Row data
3. Structure and alignment

Return as formatted text table or describe the table structure.""",

            'auto': """Analyze this document and extract all structured information.

Identify:
1. Document type
2. Key fields and values
3. Important dates, numbers, and names
4. Any tabular data

Return organized, structured information."""
        }

        prompt = prompts.get(data_type, prompts['auto'])

        response = self.vision_client.analyze(
            prompt=prompt,
            images=[image],
            temperature=0.1,  # Very deterministic for data extraction
            max_tokens=2000
        )

        return {
            'data_type': data_type,
            'extracted_data': response,
            'method': 'vision',
            'provider': self.vision_client.backend
        }
