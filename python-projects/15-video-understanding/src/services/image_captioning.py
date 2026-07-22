"""
Image captioning service
Generates natural language descriptions of images using vision-language models
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict
from dataclasses import dataclass
import base64

logger = logging.getLogger(__name__)


@dataclass
class ImageCaption:
    """Generated image caption"""
    text: str
    confidence: Optional[float] = None
    model: str = "unknown"
    metadata: Optional[Dict[str, any]] = None


class ImageCaptioningService:
    """
    Generate captions for images using vision-language models
    Supports BLIP, GPT-4 Vision, and local models
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4-vision",
        use_local: bool = False
    ):
        """
        Initialize image captioning service

        Args:
            api_key: API key for cloud models (OpenAI)
            model: Model to use (gpt-4-vision, blip)
            use_local: Use local model instead of API
        """
        self.api_key = api_key
        self.model = model
        self.use_local = use_local
        self.local_model = None

    def caption_image(
        self,
        image_path: Path,
        prompt: Optional[str] = None,
        max_tokens: int = 100
    ) -> ImageCaption:
        """
        Generate caption for single image

        Args:
            image_path: Path to image file
            prompt: Optional custom prompt
            max_tokens: Maximum caption length

        Returns:
            ImageCaption

        Raises:
            ValueError: If image not found
            RuntimeError: If captioning fails
        """
        if not image_path.exists():
            raise ValueError(f"Image not found: {image_path}")

        logger.info(f"Generating caption for {image_path}")

        if self.use_local or not self.api_key:
            return self._caption_local(image_path, prompt)
        else:
            return self._caption_api(image_path, prompt, max_tokens)

    def caption_batch(
        self,
        image_paths: List[Path],
        prompt: Optional[str] = None
    ) -> List[ImageCaption]:
        """
        Generate captions for multiple images

        Args:
            image_paths: List of image paths
            prompt: Optional custom prompt

        Returns:
            List of ImageCaption
        """
        logger.info(f"Generating captions for {len(image_paths)} images")

        captions = []
        for idx, image_path in enumerate(image_paths):
            try:
                logger.debug(f"Processing {idx + 1}/{len(image_paths)}: {image_path.name}")
                caption = self.caption_image(image_path, prompt)
                captions.append(caption)
            except Exception as e:
                logger.error(f"Failed to caption {image_path}: {e}")
                captions.append(ImageCaption(
                    text="",
                    confidence=0.0,
                    model=self.model,
                    metadata={'error': str(e)}
                ))

        logger.info(f"Caption generation complete: {len(captions)} captions")
        return captions

    def _caption_api(
        self,
        image_path: Path,
        prompt: Optional[str],
        max_tokens: int
    ) -> ImageCaption:
        """Generate caption using OpenAI GPT-4 Vision API"""
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key)

            # Encode image to base64
            with open(image_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')

            # Determine image format
            ext = image_path.suffix.lower()
            if ext == '.png':
                mime_type = 'image/png'
            elif ext in ['.jpg', '.jpeg']:
                mime_type = 'image/jpeg'
            elif ext == '.gif':
                mime_type = 'image/gif'
            elif ext == '.webp':
                mime_type = 'image/webp'
            else:
                mime_type = 'image/jpeg'

            # Default prompt if not provided
            if not prompt:
                prompt = "Describe this image in detail."

            # Call GPT-4 Vision
            response = client.chat.completions.create(
                model="gpt-4-vision-preview",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{image_data}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=max_tokens
            )

            caption_text = response.choices[0].message.content

            return ImageCaption(
                text=caption_text,
                confidence=1.0,
                model="gpt-4-vision-preview",
                metadata={
                    'finish_reason': response.choices[0].finish_reason,
                    'usage': {
                        'prompt_tokens': response.usage.prompt_tokens,
                        'completion_tokens': response.usage.completion_tokens
                    }
                }
            )

        except ImportError:
            raise RuntimeError("openai package required. Install with: pip install openai")
        except Exception as e:
            raise RuntimeError(f"API captioning failed: {e}") from e

    def _caption_local(
        self,
        image_path: Path,
        prompt: Optional[str]
    ) -> ImageCaption:
        """Generate caption using local BLIP model"""
        try:
            from PIL import Image
            from transformers import BlipProcessor, BlipForConditionalGeneration

            # Load model if not loaded
            if self.local_model is None:
                logger.info("Loading BLIP model...")
                self.processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
                self.local_model = BlipForConditionalGeneration.from_pretrained(
                    "Salesforce/blip-image-captioning-base"
                )
                logger.info("BLIP model loaded")

            # Load and process image
            image = Image.open(image_path).convert('RGB')

            # Generate caption
            if prompt:
                # Conditional captioning
                inputs = self.processor(image, prompt, return_tensors="pt")
            else:
                # Unconditional captioning
                inputs = self.processor(image, return_tensors="pt")

            outputs = self.local_model.generate(**inputs, max_length=50)
            caption_text = self.processor.decode(outputs[0], skip_special_tokens=True)

            return ImageCaption(
                text=caption_text,
                confidence=0.9,
                model="blip-base",
                metadata={'prompt': prompt}
            )

        except ImportError:
            raise RuntimeError(
                "transformers and PIL required for local captioning. "
                "Install with: pip install transformers pillow"
            )
        except Exception as e:
            raise RuntimeError(f"Local captioning failed: {e}") from e

    def describe_visual_elements(
        self,
        image_path: Path
    ) -> Dict[str, str]:
        """
        Get detailed descriptions of visual elements

        Args:
            image_path: Path to image

        Returns:
            Dictionary with different aspects
        """
        logger.info(f"Describing visual elements in {image_path}")

        aspects = {
            'objects': "What objects are in this image? List them.",
            'scene': "What type of scene or setting is this?",
            'actions': "What actions or activities are taking place?",
            'mood': "What is the mood or atmosphere of this image?",
            'colors': "What are the dominant colors in this image?"
        }

        descriptions = {}

        for aspect, prompt in aspects.items():
            try:
                caption = self.caption_image(image_path, prompt, max_tokens=50)
                descriptions[aspect] = caption.text
            except Exception as e:
                logger.warning(f"Failed to describe {aspect}: {e}")
                descriptions[aspect] = ""

        return descriptions

    def generate_alt_text(
        self,
        image_path: Path,
        max_length: int = 125
    ) -> str:
        """
        Generate accessibility alt text for image

        Args:
            image_path: Path to image
            max_length: Maximum character length

        Returns:
            Alt text string
        """
        prompt = (
            "Generate concise alt text for this image that would be helpful "
            "for visually impaired users. Focus on the most important elements."
        )

        caption = self.caption_image(image_path, prompt, max_tokens=30)
        alt_text = caption.text

        # Truncate if needed
        if len(alt_text) > max_length:
            alt_text = alt_text[:max_length - 3] + "..."

        return alt_text


def caption_image(
    image_path: Path,
    api_key: Optional[str] = None,
    use_local: bool = False
) -> ImageCaption:
    """
    Convenience function to caption an image

    Args:
        image_path: Path to image file
        api_key: Optional API key
        use_local: Use local model

    Returns:
        ImageCaption
    """
    service = ImageCaptioningService(api_key=api_key, use_local=use_local)
    return service.caption_image(image_path)


def caption_frames(
    frame_paths: List[Path],
    api_key: Optional[str] = None,
    use_local: bool = True
) -> List[ImageCaption]:
    """
    Convenience function to caption multiple frames

    Args:
        frame_paths: List of frame paths
        api_key: Optional API key
        use_local: Use local model (recommended for batch)

    Returns:
        List of ImageCaption
    """
    service = ImageCaptioningService(api_key=api_key, use_local=use_local)
    return service.caption_batch(frame_paths)
