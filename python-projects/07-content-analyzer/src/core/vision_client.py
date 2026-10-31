"""Vision API client for image analysis using various providers."""
import os
import base64
import hashlib
import io
import requests
from pathlib import Path
from typing import List, Optional, Tuple, Union
from PIL import Image

from .image_processor import ImageProcessor
from .rate_limiter import get_rate_limiter
from .retry_handler import RetryHandler

OLLAMA_TIMEOUT = 300   # CPU-only inference on a multi-image prompt really can take minutes


class VisionError(Exception):
    """A failed model call with a one-line, user-readable message.

    kind: unavailable (backend not reachable), auth (key rejected), model (not installed/found),
          bad_request (the provider refused the input), timeout, rate_limit, empty (no text came back)
          or other.
    transient: worth retrying (timeouts, rate limits, 5xx, dropped connections).
    """

    TRANSIENT = ("timeout", "rate_limit", "server", "connection")

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind

    @property
    def transient(self) -> bool:
        return self.kind in self.TRANSIENT


class VisionClient:
    """Unified interface for vision-capable LLMs."""

    def __init__(
        self,
        backend: str = "ollama",
        model: Optional[str] = None,
        api_url: Optional[str] = None,
        cache_manager: Optional[object] = None,
        enable_cache: bool = True,
        retry_handler: Optional[RetryHandler] = None,
        rate_limit: bool = True
    ):
        """Initialize vision client.

        Args:
            backend: Provider name ('ollama', 'anthropic', 'openai')
            model: Model name (defaults per provider if None)
            api_url: API URL (for Ollama, defaults to localhost:11434)
            cache_manager: CacheManager instance for response caching
            enable_cache: Enable caching for API responses
            retry_handler: Retries transient failures (default: 2 retries with backoff for hosted
                providers, 1 quick retry for Ollama)
            rate_limit: Keep hosted-provider calls under the provider's request limits
        """
        self.backend = backend.lower()
        if self.backend not in ('ollama', 'anthropic', 'openai'):
            raise ValueError(f"Unsupported backend: {backend}. Choose from: ollama, anthropic, openai")
        self.model = model or self._get_default_model()
        self.api_url = (api_url or os.getenv("OLLAMA_API_URL", "http://localhost:11434")).rstrip('/')
        self.cache_manager = cache_manager
        self.enable_cache = enable_cache and cache_manager is not None
        self.images = ImageProcessor()
        self.rate_limit = rate_limit and self.backend != 'ollama'
        if retry_handler is None:
            retry_handler = RetryHandler(max_retries=1, base_delay=1.0) if self.backend == 'ollama' \
                else RetryHandler(max_retries=2, base_delay=2.0)
        self.retry_handler = retry_handler
        # True when the last reply was cut off by the token limit
        self.truncated = False
        # True when the last reply came from the cache
        self.last_cached = False

    def _get_default_model(self) -> str:
        """Get default model for the backend."""
        defaults = {
            'ollama': os.getenv('OLLAMA_VISION_MODEL', 'llava'),
            'anthropic': os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-5-5'),
            'openai': os.getenv('OPENAI_MODEL', 'gpt-4o')
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
            str: Model response (never empty: an empty reply raises VisionError)

        Raises:
            VisionError: the call failed (see VisionError.kind)
        """
        self.last_cached = False
        encoded = self._prepare_images(images)          # [(base64, media_type)]

        # Compute image hash for caching
        image_hash = None
        cache_params = {'max_tokens': max_tokens, 'temperature': round(float(temperature), 2)}
        if self.enable_cache:
            digest = hashlib.sha256()
            for data, media_type in encoded:
                digest.update(media_type.encode())
                digest.update(data.encode())
            image_hash = digest.hexdigest()

            cached_response = self.cache_manager.get_response(
                prompt=prompt,
                image_hash=image_hash,
                provider=self.backend,
                model=self.model,
                params=cache_params
            )

            if cached_response:
                self.last_cached = True
                return cached_response

        self.truncated = False
        response = self.retry_handler.retry(
            self._call_backend, prompt, encoded, max_tokens, temperature,
            retryable_exceptions=(VisionError,),
            should_retry=lambda error: isinstance(error, VisionError) and error.transient
        )

        if not response or not response.strip():
            raise VisionError("empty", f"{self.model} returned an empty reply")

        # A reply that was cut off is shown, but not remembered: asking again with a bigger limit
        # must not return the stump.
        if self.enable_cache and image_hash and not self.truncated:
            self.cache_manager.save_response(
                prompt=prompt,
                image_hash=image_hash,
                provider=self.backend,
                model=self.model,
                response=response,
                params=cache_params
            )

        return response

    def _call_backend(self, prompt, encoded, max_tokens, temperature) -> str:
        if self.rate_limit:
            try:
                get_rate_limiter(self.backend).acquire(timeout=120)
            except TimeoutError:
                raise VisionError("rate_limit", f"Waited two minutes for a free {self.backend} request slot")
        if self.backend == 'ollama':
            return self._analyze_ollama(prompt, encoded, max_tokens, temperature)
        if self.backend == 'anthropic':
            return self._analyze_anthropic(prompt, encoded, max_tokens, temperature)
        return self._analyze_openai(prompt, encoded, max_tokens, temperature)

    def _prepare_images(
        self,
        images: List[Union[str, bytes, Image.Image]]
    ) -> List[Tuple[str, str]]:
        """Turn images into (base64, media type) pairs that match the bytes actually sent.

        Every image is opened safely, put upright, scaled to the configured maximum size and
        encoded as PNG or JPEG; the media type says which.
        """
        encoded = []
        for img in images:
            if isinstance(img, str):
                pil = self.images.load_image(img)
            elif isinstance(img, bytes):
                pil = self.images.open_bytes(img)
            elif isinstance(img, Image.Image):
                pil = img
            else:
                raise TypeError(f"Unsupported image type: {type(img)}")
            data, media_type = self.images.encode_for_model(pil)
            encoded.append((base64.b64encode(data).decode('utf-8'), media_type))

        return encoded

    # ------------------------------------------------------------------ Ollama

    def _analyze_ollama(
        self,
        prompt: str,
        images: List[Tuple[str, str]],
        max_tokens: int,
        temperature: float
    ) -> str:
        """Analyze images using Ollama (LLaVA and other vision models)."""
        url = f"{self.api_url}/api/chat"

        payload = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": prompt,
                "images": [data for data, _ in images]
            }],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }

        try:
            response = requests.post(url, json=payload, timeout=(5, OLLAMA_TIMEOUT))
        except requests.Timeout:
            raise VisionError("timeout", f"{self.model} did not answer within {OLLAMA_TIMEOUT}s (large images are slow on CPU)")
        except requests.ConnectionError:
            raise VisionError("unavailable", f"Cannot reach Ollama at {self.api_url}. Is it running? Start it with: ollama serve")
        except requests.RequestException as e:
            raise VisionError("other", f"Ollama request failed: {' '.join(str(e).split())[:200]}")

        if response.status_code >= 400:
            raise self._ollama_error(response)
        try:
            data = response.json()
        except ValueError:
            raise VisionError("other", "Ollama sent an invalid reply (not JSON)")
        self.truncated = data.get('done_reason') == 'length'
        return (data.get('message') or {}).get('content', '') or ''

    def _ollama_error(self, response) -> VisionError:
        try:
            detail = (response.json() or {}).get('error') or ''
        except ValueError:
            detail = ''
        detail = ' '.join(str(detail).split()) or f"HTTP {response.status_code}"
        low = detail.lower()
        if response.status_code == 404 and 'not found' in low:
            return VisionError("model", f"Model '{self.model}' is not installed. Install it with: ollama pull {self.model}")
        if 'image' in low and ('support' in low or 'vision' in low or 'multimodal' in low):
            return VisionError("bad_request", f"Model '{self.model}' cannot read images. Use a vision model such as llava")
        if response.status_code >= 500:
            return VisionError("server", f"Ollama error ({response.status_code}): {detail}")
        return VisionError("bad_request", f"Ollama refused the request ({response.status_code}): {detail}")

    # ------------------------------------------------------------------ hosted providers

    @staticmethod
    def _classify(error: Exception, provider: str) -> VisionError:
        """Turn an SDK exception into a VisionError without depending on the SDK's own classes."""
        status = getattr(error, 'status_code', None)
        name = type(error).__name__
        detail = ' '.join(str(error).split())[:200]
        if status in (401, 403):
            return VisionError("auth", f"{provider} rejected the API key ({status}). Check it in your .env file")
        if status == 404:
            return VisionError("model", f"{provider} does not know this model name")
        if status == 429:
            return VisionError("rate_limit", f"{provider} rate limit reached; try again in a moment")
        if status is not None and status >= 500:
            return VisionError("server", f"{provider} had a server error ({status})")
        if status == 400 or status == 413 or status == 422:
            return VisionError("bad_request", f"{provider} refused the request: {detail}")
        if "Timeout" in name:
            return VisionError("timeout", f"{provider} did not answer in time")
        if "Connection" in name:
            return VisionError("connection", f"Cannot reach {provider}. Check your network connection")
        return VisionError("other", f"{provider} error: {detail or name}")

    def _analyze_anthropic(
        self,
        prompt: str,
        images: List[Tuple[str, str]],
        max_tokens: int,
        temperature: float
    ) -> str:
        """Analyze images using Anthropic Claude."""
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "Anthropic library not installed. "
                "Install with: pip install anthropic"
            )

        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not found in environment. "
                "Set it in .env file or export ANTHROPIC_API_KEY=your_key"
            )

        client = anthropic.Anthropic(api_key=api_key, max_retries=0)   # retries are ours

        content_blocks = []
        for data, media_type in images:
            content_blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": data}
            })
        content_blocks.append({"type": "text", "text": prompt})

        try:
            message = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=min(max(temperature, 0.0), 1.0),     # Anthropic accepts 0..1
                messages=[{"role": "user", "content": content_blocks}]
            )
        except Exception as e:
            raise self._classify(e, "Anthropic")

        self.truncated = getattr(message, 'stop_reason', None) == 'max_tokens'
        return ''.join(b.text for b in message.content if getattr(b, 'type', 'text') == 'text')

    def _analyze_openai(
        self,
        prompt: str,
        images: List[Tuple[str, str]],
        max_tokens: int,
        temperature: float
    ) -> str:
        """Analyze images using OpenAI GPT vision models."""
        try:
            import openai
        except ImportError:
            raise ImportError(
                "OpenAI library not installed. "
                "Install with: pip install openai"
            )

        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY not found in environment. "
                "Set it in .env file or export OPENAI_API_KEY=your_key"
            )

        client = openai.OpenAI(api_key=api_key, max_retries=0)

        content_blocks = [{"type": "text", "text": prompt}]
        for data, media_type in images:
            content_blocks.append({
                "type": "image_url",
                "image_url": {"url": f"data:{media_type};base64,{data}"}
            })

        try:
            response = client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": content_blocks}]
            )
        except Exception as e:
            raise self._classify(e, "OpenAI")

        choice = response.choices[0]
        self.truncated = getattr(choice, 'finish_reason', None) == 'length'
        return choice.message.content or ''
