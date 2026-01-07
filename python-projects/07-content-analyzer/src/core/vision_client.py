"""Vision API client for image analysis using various providers."""
import os
import base64
import requests
from pathlib import Path
from typing import List, Optional, Union
from PIL import Image
import io


class VisionClient:
    """Unified interface for vision-capable LLMs."""

    def __init__(
        self,
        backend: str = "ollama",
        model: Optional[str] = None,
        api_url: Optional[str] = None
    ):
        """Initialize vision client.

        Args:
            backend: Provider name ('ollama', 'anthropic', 'openai')
            model: Model name (defaults per provider if None)
            api_url: API URL (for Ollama, defaults to localhost:11434)
        """
        self.backend = backend.lower()
        self.model = model or self._get_default_model()
        self.api_url = api_url or os.getenv("OLLAMA_API_URL", "http://localhost:11434")

    def _get_default_model(self) -> str:
        """Get default model for the backend."""
        defaults = {
            'ollama': os.getenv('OLLAMA_VISION_MODEL', 'llava'),
            'anthropic': os.getenv('ANTHROPIC_MODEL', 'claude-3-5-sonnet-20241022'),
            'openai': os.getenv('OPENAI_MODEL', 'gpt-4-vision-preview')
        }
        return defaults.get(self.backend, 'llava')

    def analyze(
        self,
        prompt: str,
        images: List[Union[str, bytes, Image.Image]],
        max_tokens: int = 1000,
        temperature: float = 0.7
    ) -> str:
        """Analyze images with a text prompt.

        Args:
            prompt: Text prompt/question about the image
            images: List of images (paths, bytes, or PIL Images)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0-2)

        Returns:
            str: Model response
        """
        # Convert all images to base64
        encoded_images = self._prepare_images(images)

        # Route to appropriate backend
        if self.backend == 'ollama':
            return self._analyze_ollama(prompt, encoded_images, max_tokens, temperature)
        elif self.backend == 'anthropic':
            return self._analyze_anthropic(prompt, encoded_images, max_tokens, temperature)
        elif self.backend == 'openai':
            return self._analyze_openai(prompt, encoded_images, max_tokens, temperature)
        else:
            raise ValueError(f"Unsupported backend: {self.backend}")

    def _prepare_images(
        self,
        images: List[Union[str, bytes, Image.Image]]
    ) -> List[str]:
        """Convert images to base64 strings.

        Args:
            images: List of images in various formats

        Returns:
            List[str]: Base64-encoded images
        """
        encoded = []
        for img in images:
            if isinstance(img, str):
                # File path
                with open(img, 'rb') as f:
                    img_bytes = f.read()
                encoded.append(base64.b64encode(img_bytes).decode('utf-8'))
            elif isinstance(img, bytes):
                # Raw bytes
                encoded.append(base64.b64encode(img).decode('utf-8'))
            elif isinstance(img, Image.Image):
                # PIL Image
                buffer = io.BytesIO()
                img.save(buffer, format='PNG')
                encoded.append(base64.b64encode(buffer.getvalue()).decode('utf-8'))
            else:
                raise TypeError(f"Unsupported image type: {type(img)}")

        return encoded

    def _analyze_ollama(
        self,
        prompt: str,
        images: List[str],
        max_tokens: int,
        temperature: float
    ) -> str:
        """Analyze images using Ollama/LLaVA.

        Args:
            prompt: Text prompt
            images: Base64-encoded images
            max_tokens: Maximum tokens
            temperature: Sampling temperature

        Returns:
            str: Model response
        """
        url = f"{self.api_url}/api/chat"

        payload = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": prompt,
                "images": images
            }],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }

        try:
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()

            result = response.json()
            return result.get('message', {}).get('content', '')

        except requests.exceptions.RequestException as e:
            raise Exception(f"Ollama API error: {str(e)}")

    def _analyze_anthropic(
        self,
        prompt: str,
        images: List[str],
        max_tokens: int,
        temperature: float
    ) -> str:
        """Analyze images using Anthropic Claude.

        Note: This is a placeholder for Phase 2 implementation.
        """
        raise NotImplementedError("Anthropic support coming in Phase 2")

    def _analyze_openai(
        self,
        prompt: str,
        images: List[str],
        max_tokens: int,
        temperature: float
    ) -> str:
        """Analyze images using OpenAI GPT-4 Vision.

        Note: This is a placeholder for Phase 2 implementation.
        """
        raise NotImplementedError("OpenAI support coming in Phase 2")
