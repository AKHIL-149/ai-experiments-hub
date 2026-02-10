"""
LLM Client for Content Moderation.

Supports multiple providers: Ollama (local), OpenAI, Anthropic.
Used for text and vision-based content classification.
"""

import logging
import os
import json
import re
from typing import List, Dict, Any, Optional
from enum import Enum
from .database import ViolationCategory


logging.basicConfig(level=logging.INFO)


class LLMProvider(Enum):
    """Supported LLM providers."""
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class LLMClient:
    """Unified LLM client for content moderation."""

    # Content moderation prompt template
    MODERATION_PROMPT = """You are a content moderation AI assistant. Analyze the following content and classify it.

Content to analyze:
{content}

Classify the content into ONE primary category from this list:
- clean: Safe, appropriate content
- spam: Unsolicited advertising, promotional content, or repetitive messages
- nsfw: Not safe for work content, explicit or sexual material
- hate_speech: Content promoting hate or discrimination based on race, religion, gender, etc.
- violence: Content depicting or promoting violence, gore, or harm
- harassment: Bullying, threats, or targeted harassment
- illegal_content: Content depicting illegal activities
- misinformation: Deliberately false or misleading information
- copyright: Content infringing on copyrights
- scam: Fraudulent or deceptive content

Provide your response in this EXACT JSON format (no additional text):
{{
    "category": "category_name",
    "confidence": 0.0-1.0,
    "is_violation": true/false,
    "reasoning": "brief explanation"
}}

Confidence scale:
- 0.0-0.3: Very uncertain
- 0.3-0.6: Somewhat uncertain
- 0.6-0.85: Moderately confident
- 0.85-0.95: Confident
- 0.95-1.0: Very confident

Respond with ONLY the JSON object, nothing else."""

    def __init__(
        self,
        provider: str = 'ollama',
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None
    ):
        """
        Initialize LLM client.

        Args:
            provider: Provider name ('ollama', 'openai', 'anthropic')
            model: Model name (provider-specific)
            api_key: API key for cloud providers
            api_url: API URL (for Ollama)
        """
        self.provider = provider.lower()
        self.model = model
        self.api_key = api_key
        self.api_url = api_url or os.getenv('OLLAMA_API_URL', 'http://localhost:11434')

        # Set default models
        if not self.model:
            if self.provider == 'ollama':
                self.model = os.getenv('OLLAMA_MODEL', 'llama3.2:3b')
            elif self.provider == 'openai':
                self.model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
            elif self.provider == 'anthropic':
                self.model = os.getenv('ANTHROPIC_MODEL', 'claude-3-5-sonnet-20241022')

        # Initialize provider client
        if self.provider == 'ollama':
            self._init_ollama()
        elif self.provider == 'openai':
            self._init_openai()
        elif self.provider == 'anthropic':
            self._init_anthropic()
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        logging.info(f"LLMClient initialized: {self.provider}/{self.model}")

    def _init_ollama(self):
        """Initialize Ollama client."""
        import requests
        self.client_type = 'ollama'
        # Test connection
        try:
            response = requests.get(f"{self.api_url}/api/tags", timeout=5)
            response.raise_for_status()
            logging.info(f"Ollama connection successful: {self.api_url}")
        except Exception as e:
            logging.warning(f"Ollama connection failed: {e}")

    def _init_openai(self):
        """Initialize OpenAI client."""
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key or os.getenv('OPENAI_API_KEY'))
            self.client_type = 'openai'
            logging.info("OpenAI client initialized")
        except ImportError:
            raise ValueError("OpenAI provider requires 'openai' package")

    def _init_anthropic(self):
        """Initialize Anthropic client."""
        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.api_key or os.getenv('ANTHROPIC_API_KEY'))
            self.client_type = 'anthropic'
            logging.info("Anthropic client initialized")
        except ImportError:
            raise ValueError("Anthropic provider requires 'anthropic' package")

    def classify_text(
        self,
        text_content: str,
        temperature: float = 0.3
    ) -> Dict[str, Any]:
        """
        Classify text content.

        Args:
            text_content: Text to classify
            temperature: Sampling temperature (lower = more deterministic)

        Returns:
            Dictionary with classification results
        """
        # Build prompt
        prompt = self.MODERATION_PROMPT.format(content=text_content)

        # Generate classification
        messages = [
            {"role": "user", "content": prompt}
        ]

        result = self._generate(messages, max_tokens=500, temperature=temperature)

        # Parse JSON response
        try:
            classification = self._parse_classification(result['content'])
            classification['processing_time_ms'] = result.get('processing_time_ms', 0)
            classification['cost'] = result.get('cost', 0.0)
            return classification
        except Exception as e:
            logging.error(f"Failed to parse classification: {e}")
            # Fallback
            return {
                'category': ViolationCategory.CLEAN.value,
                'confidence': 0.0,
                'is_violation': False,
                'reasoning': f"Error parsing response: {e}",
                'processing_time_ms': result.get('processing_time_ms', 0),
                'cost': result.get('cost', 0.0)
            }

    def classify_image(
        self,
        image_path: str,
        description: Optional[str] = None,
        temperature: float = 0.3
    ) -> Dict[str, Any]:
        """
        Classify image content using vision models.

        Args:
            image_path: Path to image file
            description: Optional text description from NSFW detector
            temperature: Sampling temperature

        Returns:
            Dictionary with classification results
        """
        if self.provider == 'openai':
            return self._classify_image_openai(image_path, description, temperature)
        elif self.provider == 'anthropic':
            return self._classify_image_anthropic(image_path, description, temperature)
        else:
            # Ollama vision support limited, use text-based classification with description
            if description:
                return self.classify_text(f"Image detected: {description}", temperature)
            else:
                return {
                    'category': ViolationCategory.CLEAN.value,
                    'confidence': 0.0,
                    'is_violation': False,
                    'reasoning': 'Vision not supported for this provider',
                    'processing_time_ms': 0,
                    'cost': 0.0
                }

    def _classify_image_openai(
        self,
        image_path: str,
        description: Optional[str],
        temperature: float
    ) -> Dict[str, Any]:
        """Classify image using OpenAI GPT-4V."""
        import base64

        try:
            # Read and encode image
            with open(image_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')

            # Build vision prompt
            prompt_text = "Analyze this image for content moderation. " + self.MODERATION_PROMPT.format(content="[Image]")

            if description:
                prompt_text = f"NSFW Detector Result: {description}\n\n" + prompt_text

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_data}"
                            }
                        }
                    ]
                }
            ]

            # Use GPT-4V model
            vision_model = os.getenv('VISION_MODEL', 'gpt-4o')
            original_model = self.model
            self.model = vision_model

            result = self._generate(messages, max_tokens=500, temperature=temperature)

            self.model = original_model

            classification = self._parse_classification(result['content'])
            classification['processing_time_ms'] = result.get('processing_time_ms', 0)
            classification['cost'] = result.get('cost', 0.0)
            return classification

        except Exception as e:
            logging.error(f"OpenAI vision classification failed: {e}")
            return {
                'category': ViolationCategory.CLEAN.value,
                'confidence': 0.0,
                'is_violation': False,
                'reasoning': f"Vision classification error: {e}",
                'processing_time_ms': 0,
                'cost': 0.0
            }

    def _classify_image_anthropic(
        self,
        image_path: str,
        description: Optional[str],
        temperature: float
    ) -> Dict[str, Any]:
        """Classify image using Anthropic Claude Vision."""
        import base64

        try:
            # Read and encode image
            with open(image_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')

            # Detect media type
            if image_path.lower().endswith('.png'):
                media_type = 'image/png'
            elif image_path.lower().endswith('.webp'):
                media_type = 'image/webp'
            elif image_path.lower().endswith('.gif'):
                media_type = 'image/gif'
            else:
                media_type = 'image/jpeg'

            # Build vision prompt
            prompt_text = "Analyze this image for content moderation. " + self.MODERATION_PROMPT.format(content="[Image]")

            if description:
                prompt_text = f"NSFW Detector Result: {description}\n\n" + prompt_text

            # Anthropic vision format
            system_message = "You are a content moderation AI assistant with vision capabilities."
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt_text
                        }
                    ]
                }
            ]

            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                temperature=temperature,
                system=system_message,
                messages=messages
            )

            content = response.content[0].text
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

            cost = self._estimate_anthropic_cost(input_tokens, output_tokens)

            classification = self._parse_classification(content)
            classification['cost'] = cost
            return classification

        except Exception as e:
            logging.error(f"Anthropic vision classification failed: {e}")
            return {
                'category': ViolationCategory.CLEAN.value,
                'confidence': 0.0,
                'is_violation': False,
                'reasoning': f"Vision classification error: {e}",
                'processing_time_ms': 0,
                'cost': 0.0
            }

    def _generate(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int = 500,
        temperature: float = 0.3
    ) -> Dict[str, Any]:
        """Generate response from LLM."""
        if self.provider == 'ollama':
            return self._generate_ollama(messages, max_tokens, temperature)
        elif self.provider == 'openai':
            return self._generate_openai(messages, max_tokens, temperature)
        elif self.provider == 'anthropic':
            return self._generate_anthropic(messages, max_tokens, temperature)

    def _generate_ollama(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int,
        temperature: float
    ) -> Dict[str, Any]:
        """Generate using Ollama."""
        import requests
        import time

        payload = {
            'model': self.model,
            'messages': messages,
            'stream': False,
            'options': {
                'temperature': temperature,
                'num_predict': max_tokens
            }
        }

        start_time = time.time()

        try:
            response = requests.post(
                f"{self.api_url}/api/chat",
                json=payload,
                timeout=120
            )
            response.raise_for_status()
            data = response.json()

            processing_time_ms = (time.time() - start_time) * 1000

            return {
                'content': data['message']['content'],
                'processing_time_ms': processing_time_ms,
                'cost': 0.0  # Local, free
            }

        except Exception as e:
            logging.error(f"Ollama generation failed: {e}")
            raise

    def _generate_openai(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int,
        temperature: float
    ) -> Dict[str, Any]:
        """Generate using OpenAI."""
        import time

        start_time = time.time()

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
            )

            processing_time_ms = (time.time() - start_time) * 1000

            content = response.choices[0].message.content
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens

            cost = self._estimate_openai_cost(input_tokens, output_tokens)

            return {
                'content': content,
                'processing_time_ms': processing_time_ms,
                'cost': cost
            }

        except Exception as e:
            logging.error(f"OpenAI generation failed: {e}")
            raise

    def _generate_anthropic(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int,
        temperature: float
    ) -> Dict[str, Any]:
        """Generate using Anthropic."""
        import time

        start_time = time.time()

        try:
            # Extract system message if present
            system_message = None
            anthropic_messages = []

            for msg in messages:
                if msg['role'] == 'system':
                    system_message = msg['content']
                else:
                    anthropic_messages.append(msg)

            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_message,
                messages=anthropic_messages
            )

            processing_time_ms = (time.time() - start_time) * 1000

            content = response.content[0].text
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

            cost = self._estimate_anthropic_cost(input_tokens, output_tokens)

            return {
                'content': content,
                'processing_time_ms': processing_time_ms,
                'cost': cost
            }

        except Exception as e:
            logging.error(f"Anthropic generation failed: {e}")
            raise

    def _parse_classification(self, response_text: str) -> Dict[str, Any]:
        """Parse classification JSON from LLM response."""
        # Try to extract JSON from response
        json_match = re.search(r'\{[^}]+\}', response_text, re.DOTALL)

        if json_match:
            json_str = json_match.group(0)
            try:
                data = json.loads(json_str)

                # Validate category
                try:
                    category = ViolationCategory(data.get('category', 'clean'))
                except ValueError:
                    category = ViolationCategory.CLEAN

                return {
                    'category': category.value,
                    'confidence': float(data.get('confidence', 0.0)),
                    'is_violation': bool(data.get('is_violation', False)),
                    'reasoning': str(data.get('reasoning', ''))
                }
            except json.JSONDecodeError:
                pass

        # Fallback parsing
        logging.warning(f"Failed to parse JSON, using fallback. Response: {response_text[:200]}")

        # Simple keyword detection
        text_lower = response_text.lower()

        if any(word in text_lower for word in ['spam', 'advertisement', 'promotional']):
            category = ViolationCategory.SPAM
            is_violation = True
            confidence = 0.6
        elif any(word in text_lower for word in ['nsfw', 'explicit', 'sexual']):
            category = ViolationCategory.NSFW
            is_violation = True
            confidence = 0.6
        elif any(word in text_lower for word in ['hate', 'discrimin', 'racist']):
            category = ViolationCategory.HATE_SPEECH
            is_violation = True
            confidence = 0.6
        elif any(word in text_lower for word in ['violence', 'gore', 'harm']):
            category = ViolationCategory.VIOLENCE
            is_violation = True
            confidence = 0.6
        else:
            category = ViolationCategory.CLEAN
            is_violation = False
            confidence = 0.5

        return {
            'category': category.value,
            'confidence': confidence,
            'is_violation': is_violation,
            'reasoning': 'Parsed from unstructured response'
        }

    def _estimate_openai_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate OpenAI cost."""
        if 'gpt-4o' in self.model:
            # GPT-4o: $2.50 per 1M input tokens, $10 per 1M output tokens
            return (input_tokens * 2.5 + output_tokens * 10) / 1_000_000
        elif 'gpt-4' in self.model:
            # GPT-4: $30 per 1M input tokens, $60 per 1M output tokens
            return (input_tokens * 30 + output_tokens * 60) / 1_000_000
        else:
            # GPT-3.5: $0.50 per 1M input tokens, $1.50 per 1M output tokens
            return (input_tokens * 0.5 + output_tokens * 1.5) / 1_000_000

    def _estimate_anthropic_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate Anthropic cost."""
        if 'opus' in self.model:
            # Opus: $15 per 1M input tokens, $75 per 1M output tokens
            return (input_tokens * 15 + output_tokens * 75) / 1_000_000
        elif 'sonnet' in self.model:
            # Sonnet: $3 per 1M input tokens, $15 per 1M output tokens
            return (input_tokens * 3 + output_tokens * 15) / 1_000_000
        else:
            # Haiku: $0.25 per 1M input tokens, $1.25 per 1M output tokens
            return (input_tokens * 0.25 + output_tokens * 1.25) / 1_000_000
