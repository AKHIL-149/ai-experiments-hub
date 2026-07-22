"""
Language detection service
Detects language from audio or text transcripts
"""

import logging
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LanguageDetection:
    """Language detection result"""
    language: str
    language_name: str
    confidence: float
    alternative_languages: Optional[List[Tuple[str, float]]] = None


class LanguageDetector:
    """
    Detect language from audio or text
    Supports both audio-based and text-based detection
    """

    # Common language codes and names
    LANGUAGE_NAMES = {
        'en': 'English',
        'es': 'Spanish',
        'fr': 'French',
        'de': 'German',
        'it': 'Italian',
        'pt': 'Portuguese',
        'ru': 'Russian',
        'ja': 'Japanese',
        'zh': 'Chinese',
        'ko': 'Korean',
        'ar': 'Arabic',
        'hi': 'Hindi',
        'nl': 'Dutch',
        'pl': 'Polish',
        'tr': 'Turkish',
        'vi': 'Vietnamese',
        'th': 'Thai',
        'sv': 'Swedish',
        'da': 'Danish',
        'no': 'Norwegian',
        'fi': 'Finnish',
        'cs': 'Czech',
        'hu': 'Hungarian',
        'ro': 'Romanian',
        'el': 'Greek',
        'he': 'Hebrew',
        'id': 'Indonesian',
        'uk': 'Ukrainian',
    }

    def __init__(self):
        """Initialize language detector"""
        pass

    def detect_from_audio(
        self,
        audio_path: Path,
        sample_duration: float = 30.0
    ) -> LanguageDetection:
        """
        Detect language from audio file

        Args:
            audio_path: Path to audio file
            sample_duration: Duration of audio sample to analyze

        Returns:
            LanguageDetection result

        Raises:
            ValueError: If audio file not found
            RuntimeError: If detection fails
        """
        if not audio_path.exists():
            raise ValueError(f"Audio file not found: {audio_path}")

        logger.info(f"Detecting language from audio: {audio_path}")

        # Use Whisper for language detection
        # Whisper has built-in language detection capabilities
        try:
            import whisper

            # Load small model for language detection
            model = whisper.load_model("base")

            # Load audio
            audio = whisper.load_audio(str(audio_path))

            # Trim to sample duration
            if sample_duration:
                max_samples = int(sample_duration * 16000)  # Whisper uses 16kHz
                audio = audio[:max_samples]

            # Pad or trim to 30 seconds
            audio = whisper.pad_or_trim(audio)

            # Make log-Mel spectrogram
            mel = whisper.log_mel_spectrogram(audio).to(model.device)

            # Detect language
            _, probs = model.detect_language(mel)

            # Get top language
            language_code = max(probs, key=probs.get)
            confidence = probs[language_code]

            # Get alternative languages (top 3)
            sorted_langs = sorted(probs.items(), key=lambda x: x[1], reverse=True)
            alternatives = [(code, prob) for code, prob in sorted_langs[1:4]]

            result = LanguageDetection(
                language=language_code,
                language_name=self.LANGUAGE_NAMES.get(language_code, language_code),
                confidence=confidence,
                alternative_languages=alternatives
            )

            logger.info(
                f"Language detected: {result.language_name} "
                f"({result.language}, confidence={result.confidence:.2f})"
            )

            return result

        except ImportError:
            logger.warning("Whisper not available, using fallback method")
            return self._detect_from_audio_fallback(audio_path)

        except Exception as e:
            raise RuntimeError(f"Language detection from audio failed: {e}") from e

    def detect_from_text(
        self,
        text: str
    ) -> LanguageDetection:
        """
        Detect language from text

        Args:
            text: Text to analyze

        Returns:
            LanguageDetection result
        """
        logger.info(f"Detecting language from text ({len(text)} chars)")

        try:
            from langdetect import detect_langs

            # Detect language with probabilities
            results = detect_langs(text)

            if results:
                top_result = results[0]
                language_code = top_result.lang
                confidence = top_result.prob

                # Get alternatives
                alternatives = [
                    (r.lang, r.prob) for r in results[1:4]
                ]

                result = LanguageDetection(
                    language=language_code,
                    language_name=self.LANGUAGE_NAMES.get(language_code, language_code),
                    confidence=confidence,
                    alternative_languages=alternatives
                )

                logger.info(
                    f"Language detected: {result.language_name} "
                    f"(confidence={result.confidence:.2f})"
                )

                return result
            else:
                # Fallback to English
                return LanguageDetection(
                    language='en',
                    language_name='English',
                    confidence=0.5,
                    alternative_languages=[]
                )

        except ImportError:
            logger.warning("langdetect not available, using simple heuristics")
            return self._detect_from_text_fallback(text)

        except Exception as e:
            logger.warning(f"Language detection failed: {e}, defaulting to English")
            return LanguageDetection(
                language='en',
                language_name='English',
                confidence=0.5,
                alternative_languages=[]
            )

    def detect_from_transcript(
        self,
        transcription_result
    ) -> LanguageDetection:
        """
        Detect language from transcription result

        Args:
            transcription_result: TranscriptionResult object

        Returns:
            LanguageDetection result
        """
        # Use language from transcription if available
        if hasattr(transcription_result, 'language') and transcription_result.language:
            language_code = transcription_result.language

            return LanguageDetection(
                language=language_code,
                language_name=self.LANGUAGE_NAMES.get(language_code, language_code),
                confidence=1.0,
                alternative_languages=[]
            )

        # Otherwise, detect from text
        text = transcription_result.text
        return self.detect_from_text(text)

    def _detect_from_audio_fallback(
        self,
        audio_path: Path
    ) -> LanguageDetection:
        """
        Fallback audio language detection using librosa + text detection

        Args:
            audio_path: Path to audio file

        Returns:
            LanguageDetection with low confidence
        """
        logger.info("Using fallback language detection (defaulting to English)")

        # Without proper models, default to English
        return LanguageDetection(
            language='en',
            language_name='English',
            confidence=0.3,
            alternative_languages=[]
        )

    def _detect_from_text_fallback(
        self,
        text: str
    ) -> LanguageDetection:
        """
        Simple heuristic-based text language detection

        Args:
            text: Input text

        Returns:
            LanguageDetection result
        """
        # Very simple heuristics based on character sets
        # This is not accurate but provides a basic fallback

        # Check for common non-Latin scripts
        if any('\u4e00' <= c <= '\u9fff' for c in text):
            # Chinese characters
            return LanguageDetection(
                language='zh',
                language_name='Chinese',
                confidence=0.7,
                alternative_languages=[]
            )

        if any('\u3040' <= c <= '\u309f' for c in text):
            # Hiragana (Japanese)
            return LanguageDetection(
                language='ja',
                language_name='Japanese',
                confidence=0.7,
                alternative_languages=[]
            )

        if any('\uac00' <= c <= '\ud7af' for c in text):
            # Hangul (Korean)
            return LanguageDetection(
                language='ko',
                language_name='Korean',
                confidence=0.7,
                alternative_languages=[]
            )

        if any('\u0600' <= c <= '\u06ff' for c in text):
            # Arabic script
            return LanguageDetection(
                language='ar',
                language_name='Arabic',
                confidence=0.7,
                alternative_languages=[]
            )

        if any('\u0400' <= c <= '\u04ff' for c in text):
            # Cyrillic (Russian and others)
            return LanguageDetection(
                language='ru',
                language_name='Russian',
                confidence=0.6,
                alternative_languages=[]
            )

        # Default to English for Latin script
        return LanguageDetection(
            language='en',
            language_name='English',
            confidence=0.5,
            alternative_languages=[]
        )

    def get_language_name(self, language_code: str) -> str:
        """
        Get language name from code

        Args:
            language_code: ISO 639-1 language code

        Returns:
            Language name
        """
        return self.LANGUAGE_NAMES.get(language_code, language_code)

    def is_supported_language(self, language_code: str) -> bool:
        """
        Check if language is supported

        Args:
            language_code: ISO 639-1 language code

        Returns:
            True if supported
        """
        return language_code in self.LANGUAGE_NAMES


def detect_language_from_audio(
    audio_path: Path,
    sample_duration: float = 30.0
) -> LanguageDetection:
    """
    Convenience function to detect language from audio

    Args:
        audio_path: Path to audio file
        sample_duration: Duration of sample to analyze

    Returns:
        LanguageDetection result
    """
    detector = LanguageDetector()
    return detector.detect_from_audio(audio_path, sample_duration)


def detect_language_from_text(text: str) -> LanguageDetection:
    """
    Convenience function to detect language from text

    Args:
        text: Text to analyze

    Returns:
        LanguageDetection result
    """
    detector = LanguageDetector()
    return detector.detect_from_text(text)
