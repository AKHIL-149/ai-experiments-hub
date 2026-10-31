"""OCR processor for text extraction from images using Tesseract and vision models."""
import io
import os
import re
from typing import Dict, List, Optional, Tuple, Union
from pathlib import Path
from PIL import Image

from .image_processor import ImageProcessor

# Language codes are letters, digits and underscores joined by "+" ("eng", "chi_sim", "eng+fra")
_LANGUAGE_RE = re.compile(r'^[A-Za-z0-9_]+(\+[A-Za-z0-9_]+)*$')
# Text a vision model puts around a transcription ("Here is the text:" ...)
_VISION_PREAMBLE_RE = re.compile(
    r"^\s*(?:sure[,!.]?\s*)?(?:here\s+(?:is|are)|below\s+(?:is|are)|the\s+(?:extracted\s+)?text\s+(?:in|from)\s+the\s+image)\b[^\n]*:\s*$",
    re.IGNORECASE,
)


def clean_vision_text(text: str) -> str:
    """A vision model's transcription without its introduction or surrounding code fence."""
    text = (text or '').strip()
    lines = text.split('\n')
    if lines and _VISION_PREAMBLE_RE.match(lines[0]):
        lines = lines[1:]
    text = '\n'.join(lines).strip()
    fence = re.match(r'^```[A-Za-z]*\n(.*)\n```$', text, re.S)
    if fence:
        text = fence.group(1).strip()
    return text


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
            use_tesseract: Use Tesseract OCR (requires pytesseract and the tesseract program)
            vision_client: VisionClient instance for fallback/enhancement
            tesseract_config: Custom Tesseract configuration string
        """
        self.use_tesseract = use_tesseract
        self.vision_client = vision_client
        self.tesseract_config = tesseract_config or '--psm 3'  # Auto page segmentation
        self.images = ImageProcessor()
        self.tesseract_problem: Optional[str] = None       # why Tesseract cannot be used, if it cannot
        self._installed_languages: Optional[List[str]] = None

        # Lazy import of pytesseract
        self._pytesseract = None
        if use_tesseract:
            try:
                import pytesseract
                self._pytesseract = pytesseract
            except ImportError:
                self.tesseract_problem = "pytesseract is not installed (pip install pytesseract)"
                print(f"⚠️  Warning: {self.tesseract_problem}. Falling back to vision model.")
                self.use_tesseract = False

    # ------------------------------------------------------------------ helpers

    def _load(self, image: Union[str, bytes, Image.Image]) -> Image.Image:
        """The image, upright and in an ordinary colour mode"""
        if isinstance(image, str):
            return self.images.load_image(image)
        if isinstance(image, bytes):
            return self.images.open_bytes(image)
        return self.images.normalize(image)

    def installed_languages(self) -> List[str]:
        """Language data Tesseract has (cached); raises if the tesseract program is missing"""
        if self._installed_languages is None:
            try:
                langs = self._pytesseract.get_languages(config='')
            except Exception as error:
                if type(error).__name__ == 'TesseractNotFoundError':
                    raise RuntimeError("The tesseract program is not installed (macOS: brew install tesseract)")
                raise
            self._installed_languages = [l for l in langs if l != 'osd']
        return self._installed_languages

    def _check_language(self, language: str) -> None:
        """Refuse a language Tesseract cannot use, with the fix in the message"""
        if not _LANGUAGE_RE.match(language or ''):
            raise ValueError(f"'{language}' is not a Tesseract language code (examples: eng, fra, chi_sim, eng+fra)")
        installed = self.installed_languages()
        missing = [l for l in language.split('+') if l not in installed]
        if missing:
            raise ValueError(
                f"Tesseract has no language data for: {', '.join(missing)}. Installed: {', '.join(installed) or 'none'}. "
                f"Install more with: brew install tesseract-lang (macOS) or apt install tesseract-ocr-{missing[0]}"
            )

    def _for_tesseract(self, image: Image.Image) -> Image.Image:
        """Small images are enlarged: Tesseract reads text best at roughly 30+ pixel line height"""
        if image.mode not in ('RGB', 'L'):
            image = image.convert('RGB')
        if max(image.size) < 1000 and min(image.size) >= 1:
            factor = 2 if max(image.size) >= 500 else 3
            image = image.resize((image.width * factor, image.height * factor), Image.Resampling.LANCZOS)
        return image

    # ------------------------------------------------------------------ extraction

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
                - confidence: Confidence score (0-100). For the vision method this is a fixed
                  estimate (details['confidence_estimated']), since models report none.
                - method: 'tesseract' or 'vision'
                - language: Detected/used language
                - details: Additional metadata
        """
        img = self._load(image)

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

                # Empty output has confidence 0, so it always falls through to the vision model
                if tesseract_result['confidence'] >= confidence_threshold and tesseract_result['text']:
                    return tesseract_result

                # Store low-confidence result for potential fallback
                result = tesseract_result

            except Exception as e:
                print(f"⚠️  Tesseract OCR failed: {str(e)}")
                result['details']['tesseract_error'] = ' '.join(str(e).split())
        elif self.tesseract_problem:
            result['details']['tesseract_error'] = self.tesseract_problem

        # Fallback to vision model if enabled
        if fallback_to_vision and self.vision_client:
            try:
                vision_result = self._extract_with_vision(img, language)

                # Use vision result if Tesseract failed or had low confidence
                if result['method'] == 'none' or vision_result.get('confidence', 0) > result['confidence']:
                    for key in ('tesseract_error',):
                        if key in result['details']:
                            vision_result['details'][key] = result['details'][key]
                    return vision_result

            except Exception as e:
                print(f"⚠️  Vision model OCR failed: {str(e)}")
                result['details']['vision_error'] = ' '.join(str(e).split())

        return result

    def _extract_with_tesseract(
        self,
        image: Image.Image,
        language: str = 'eng'
    ) -> Dict[str, any]:
        """Extract text using Tesseract OCR (one pass over the image).

        Args:
            image: PIL Image
            language: Language code

        Returns:
            Dict with extraction results
        """
        self._check_language(language)
        prepared = self._for_tesseract(image)
        scale = prepared.width / image.width if image.width else 1

        data = self._pytesseract.image_to_data(
            prepared,
            lang=language,
            config=self.tesseract_config,
            output_type=self._pytesseract.Output.DICT,
            timeout=int(os.getenv('TESSERACT_TIMEOUT', '90'))
        )

        # Confidence is the mean over real words only. Tesseract also reports empty "words" with a
        # high score; counting them made a picture with no text come back as "95% sure: nothing".
        confidences = [
            float(data['conf'][i]) for i in range(len(data['text']))
            if str(data['text'][i]).strip() and float(data['conf'][i]) >= 0
        ]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        text = self._text_from_data(data)
        boxes = self._extract_bounding_boxes(data, scale)

        return {
            'text': text,
            'confidence': round(avg_confidence, 2),
            'method': 'tesseract',
            'language': language,
            'details': {
                'word_count': len(boxes),
                'bounding_boxes': boxes,
                'tesseract_version': str(self._pytesseract.get_tesseract_version())
            }
        }

    @staticmethod
    def _text_from_data(data: Dict) -> str:
        """Plain text rebuilt from Tesseract's word table: words on a line, lines in a paragraph, blank line between paragraphs"""
        lines: List[Tuple[Tuple[int, int], List[str]]] = []
        index: Dict[Tuple[int, int, int], int] = {}
        for i in range(len(data['text'])):
            word = str(data['text'][i]).strip()
            if not word or float(data['conf'][i]) < 0:
                continue
            key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
            if key not in index:
                index[key] = len(lines)
                lines.append(((key[0], key[1]), []))
            lines[index[key]][1].append(word)

        out: List[str] = []
        previous = None
        for paragraph, words in lines:
            if previous is not None and paragraph != previous:
                out.append('')
            out.append(' '.join(words))
            previous = paragraph
        return '\n'.join(out).strip()

    def _extract_bounding_boxes(self, data: Dict, scale: float = 1.0) -> List[Dict]:
        """Extract word-level bounding boxes from Tesseract data (in the original image's pixels).

        Args:
            data: Tesseract output dictionary
            scale: How much the image was enlarged before recognition

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
            if float(data['conf'][i]) < 0:
                continue

            boxes.append({
                'text': data['text'][i],
                'confidence': int(float(data['conf'][i])),
                'bbox': {
                    'x': round(data['left'][i] / scale),
                    'y': round(data['top'][i] / scale),
                    'width': round(data['width'][i] / scale),
                    'height': round(data['height'][i] / scale)
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
            'text': clean_vision_text(response),
            'confidence': 85.0,  # Vision models report no confidence: a fixed estimate, flagged below
            'method': 'vision',
            'language': language,
            'details': {
                'provider': self.vision_client.backend,
                'model': self.vision_client.model,
                'confidence_estimated': True
            }
        }

    # Scripts Tesseract's orientation detection reports, and the languages that use them
    _SCRIPT_HINTS = {
        'Latin': None, 'Han': 'Chinese or Japanese', 'Japanese': 'Japanese', 'Hangul': 'Korean', 'Korean': 'Korean',
        'Cyrillic': 'Russian or another Cyrillic language', 'Arabic': 'Arabic', 'Devanagari': 'Hindi',
        'Thai': 'Thai', 'Greek': 'Greek', 'Hebrew': 'Hebrew',
    }

    def detect_language(self, image: Union[str, bytes, Image.Image]) -> Dict[str, any]:
        """Detect language(s) in image text.

        With Tesseract this compares recognition quality across the *installed* languages and also
        reports the writing system (script) it sees, so a Japanese sign is not mistaken for English
        just because only English data is installed. A vision model is used when Tesseract is off
        or finds nothing.

        Args:
            image: Image (path, bytes, or PIL Image)

        Returns:
            Dict with detected languages and confidence
        """
        img = self._load(image)

        result = {
            'languages': [],
            'primary_language': None,
            'method': 'none'
        }

        # Try Tesseract language detection
        if self.use_tesseract and self._pytesseract:
            try:
                installed = self.installed_languages()
                result['installed_languages'] = installed
                prepared = self._for_tesseract(img)

                script = None
                try:
                    osd = self._pytesseract.image_to_osd(prepared, output_type=self._pytesseract.Output.DICT)
                    script = osd.get('script')
                    result['script'] = script
                    result['script_confidence'] = osd.get('script_conf')
                except Exception:
                    pass                          # OSD needs readable text; no script then

                common_langs = ['eng', 'fra', 'deu', 'spa', 'ita', 'por', 'rus', 'ara', 'chi_sim', 'jpn']
                candidates = [l for l in common_langs if l in installed] or installed[:3]

                lang_scores = {}
                for lang in candidates:
                    data = self._pytesseract.image_to_data(
                        prepared, lang=lang, output_type=self._pytesseract.Output.DICT,
                        timeout=int(os.getenv('TESSERACT_TIMEOUT', '90'))
                    )
                    confidences = [
                        float(c) for c, t in zip(data['conf'], data['text'])
                        if str(t).strip() and float(c) > 0
                    ]
                    if confidences:
                        lang_scores[lang] = round(sum(confidences) / len(confidences), 2)

                if lang_scores:
                    sorted_langs = sorted(lang_scores.items(), key=lambda x: x[1], reverse=True)
                    result['languages'] = [
                        {'code': lang, 'name': self._language_name(lang), 'confidence': score}
                        for lang, score in sorted_langs[:3]
                    ]
                    result['primary_language'] = sorted_langs[0][0]
                    result['method'] = 'tesseract'
                    if len(candidates) == 1:
                        result['note'] = (
                            f"Only {candidates[0]} is installed, so no other language could be compared. "
                            "Install more with: brew install tesseract-lang"
                        )

                hint = self._SCRIPT_HINTS.get(script)
                if hint and not any(l['code'] in ('chi_sim', 'chi_tra', 'jpn', 'kor', 'rus', 'ara', 'hin', 'tha')
                                    for l in result['languages'][:1]):
                    result['script_note'] = (
                        f"The text looks like {script} script ({hint}), which the installed language data may not read. "
                        "Install more with: brew install tesseract-lang"
                    )

            except Exception as e:
                result['error'] = f"Language detection failed: {' '.join(str(e).split())}"

        # Fallback to vision model
        if not result['primary_language'] and self.vision_client:
            try:
                prompt = """Identify the language(s) of any text in this image.

List the languages you detect, ordered by how much text appears in each language.
Format: "Language: [percentage]%"

If no text is visible, say "No text detected"."""

                response = self.vision_client.analyze(
                    prompt=prompt,
                    images=[img],
                    temperature=0.2,
                    max_tokens=200
                )

                result['languages'] = [{'description': response}]
                result['method'] = 'vision'
                result.pop('error', None)

            except Exception as e:
                result['error'] = f"Vision language detection failed: {' '.join(str(e).split())}"

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
