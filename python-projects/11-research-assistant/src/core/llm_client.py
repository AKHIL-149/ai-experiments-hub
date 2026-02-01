"""
LLM Client for Research Assistant.

Supports multiple providers: Ollama (local), OpenAI, Anthropic.
Used for synthesis and analysis tasks.
"""

import logging
import os
from typing import List, Dict, Any, Optional
from enum import Enum


class LLMProvider(Enum):
    """Supported LLM providers."""
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class LLMClient:
    """Unified LLM client for multiple providers."""

    def __init__(
        self,
        provider: str = 'ollama',
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        cost_tracker: Optional[Any] = None
    ):
        """
        Initialize LLM client.

        Args:
            provider: Provider name ('ollama', 'openai', 'anthropic')
            model: Model name (provider-specific)
            api_key: API key for cloud providers
            api_url: API URL (for Ollama)
            cost_tracker: Optional CostTracker instance for usage tracking
        """
        self.provider = provider.lower()
        self.model = model
        self.api_key = api_key
        self.api_url = api_url or os.getenv('OLLAMA_API_URL', 'http://localhost:11434')
        self.cost_tracker = cost_tracker

        # Set default models
        if not self.model:
            if self.provider == 'ollama':
                self.model = os.getenv('OLLAMA_MODEL', 'llama3.2:3b')
            elif self.provider == 'openai':
                self.model = os.getenv('OPENAI_MODEL', 'gpt-4')
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

    def generate(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 2000,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """
        Generate response from LLM.

        Args:
            messages: List of message dictionaries with 'role' and 'content'
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0-1)

        Returns:
            Dictionary with 'content', 'tokens', and 'cost'
        """
        if self.provider == 'ollama':
            return self._generate_ollama(messages, max_tokens, temperature)
        elif self.provider == 'openai':
            return self._generate_openai(messages, max_tokens, temperature)
        elif self.provider == 'anthropic':
            return self._generate_anthropic(messages, max_tokens, temperature)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def _generate_ollama(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float
    ) -> Dict[str, Any]:
        """Generate using Ollama."""
        import requests

        # Convert messages to Ollama format
        ollama_messages = []
        for msg in messages:
            ollama_messages.append({
                'role': msg['role'],
                'content': msg['content']
            })

        payload = {
            'model': self.model,
            'messages': ollama_messages,
            'stream': False,
            'options': {
                'temperature': temperature,
                'num_predict': max_tokens
            }
        }

        try:
            response = requests.post(
                f"{self.api_url}/api/chat",
                json=payload,
                timeout=120
            )
            response.raise_for_status()
            data = response.json()

            input_tokens = data.get('prompt_eval_count', 0)
            output_tokens = data.get('eval_count', 0)

            # Track cost
            if self.cost_tracker:
                self.cost_tracker.track_llm_call(
                    provider='ollama',
                    model=self.model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens
                )

            return {
                'content': data['message']['content'],
                'tokens': input_tokens + output_tokens,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'cost': 0.0  # Local, free
            }

        except Exception as e:
            logging.error(f"Ollama generation failed: {e}")
            raise

    def _generate_openai(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float
    ) -> Dict[str, Any]:
        """Generate using OpenAI."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
            )

            content = response.choices[0].message.content
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            total_tokens = response.usage.total_tokens

            # Track cost
            cost = 0.0
            if self.cost_tracker:
                cost_record = self.cost_tracker.track_llm_call(
                    provider='openai',
                    model=self.model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens
                )
                cost = cost_record['total_cost']
            else:
                # Fallback estimation
                cost = self._estimate_openai_cost(total_tokens)

            return {
                'content': content,
                'tokens': total_tokens,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'cost': cost
            }

        except Exception as e:
            logging.error(f"OpenAI generation failed: {e}")
            raise

    def _generate_anthropic(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float
    ) -> Dict[str, Any]:
        """Generate using Anthropic."""
        try:
            # Extract system message if present
            system_message = None
            anthropic_messages = []

            for msg in messages:
                if msg['role'] == 'system':
                    system_message = msg['content']
                else:
                    anthropic_messages.append({
                        'role': msg['role'],
                        'content': msg['content']
                    })

            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_message,
                messages=anthropic_messages
            )

            content = response.content[0].text
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            total_tokens = input_tokens + output_tokens

            # Track cost
            cost = 0.0
            if self.cost_tracker:
                cost_record = self.cost_tracker.track_llm_call(
                    provider='anthropic',
                    model=self.model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens
                )
                cost = cost_record['total_cost']
            else:
                # Fallback estimation
                cost = self._estimate_anthropic_cost(input_tokens, output_tokens)

            return {
                'content': content,
                'tokens': total_tokens,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'cost': cost
            }

        except Exception as e:
            logging.error(f"Anthropic generation failed: {e}")
            raise

    def _estimate_openai_cost(self, tokens: int) -> float:
        """Estimate OpenAI cost."""
        # Rough estimates for GPT-4
        if 'gpt-4' in self.model:
            return tokens * 0.00003  # $0.03 per 1K tokens (average)
        else:
            return tokens * 0.000002  # GPT-3.5

    def _estimate_anthropic_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate Anthropic cost."""
        # Rough estimates for Claude
        if 'claude-3-5-sonnet' in self.model:
            return (input_tokens * 0.000003) + (output_tokens * 0.000015)
        else:
            return (input_tokens * 0.000001) + (output_tokens * 0.000005)

    def get_info(self) -> Dict[str, Any]:
        """Get information about the LLM client."""
        return {
            'provider': self.provider,
            'model': self.model,
            'api_url': self.api_url if self.provider == 'ollama' else None,
            'available': True  # Simplified for now
        }
