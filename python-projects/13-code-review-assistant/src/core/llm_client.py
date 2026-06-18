"""
Unified LLM client interface for multiple backends with retry logic and error handling
"""
import os
import time
import requests
from typing import Optional, Dict, Any
from pathlib import Path


class LLMClient:
    """Unified interface for different LLM backends (Ollama, Anthropic, OpenAI)."""

    def __init__(
        self,
        backend: str = "ollama",
        model: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """
        Initialize LLM client.

        Args:
            backend: LLM backend to use ('ollama', 'anthropic', or 'openai')
            model: Model name (uses defaults if not specified)
            max_retries: Maximum number of retry attempts on failure
            retry_delay: Delay between retries in seconds
        """
        self.backend = backend.lower()
        self.model = model or self._get_default_model()
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Initialize backend-specific client
        self._initialize_backend()

    def _initialize_backend(self):
        """Initialize the specific backend client."""
        if self.backend == "anthropic":
            try:
                import anthropic
                api_key = os.getenv("ANTHROPIC_API_KEY")
                if not api_key:
                    raise ValueError("ANTHROPIC_API_KEY not found in environment")
                self.client = anthropic.Anthropic(api_key=api_key)
            except ImportError:
                raise ImportError(
                    "anthropic package required for Anthropic backend. "
                    "Install it with: pip install anthropic"
                )

        elif self.backend == "openai":
            try:
                import openai
                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    raise ValueError("OPENAI_API_KEY not found in environment")
                self.client = openai.OpenAI(api_key=api_key)
            except ImportError:
                raise ImportError(
                    "openai package required for OpenAI backend. "
                    "Install it with: pip install openai"
                )

        elif self.backend == "ollama":
            self.ollama_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
            # Test connection
            try:
                response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
                response.raise_for_status()
            except requests.RequestException:
                print(f"Warning: Could not connect to Ollama at {self.ollama_url}")

        else:
            raise ValueError(f"Unsupported backend: {self.backend}")

    def _get_default_model(self) -> str:
        """Get default model for each backend."""
        defaults = {
            "ollama": os.getenv("OLLAMA_MODEL", "llama3.2"),
            "anthropic": "claude-3-5-sonnet-20241022",
            "openai": "gpt-4o-mini"
        }
        return defaults.get(self.backend, "llama3.2")

    def generate(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        system: Optional[str] = None
    ) -> str:
        """
        Generate text based on prompt with retry logic.

        Args:
            prompt: The input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 to 1.0)
            system: Optional system message/instructions

        Returns:
            Generated text response

        Raises:
            Exception: If generation fails after all retries
        """
        last_error = None

        for attempt in range(self.max_retries):
            try:
                if self.backend == "ollama":
                    return self._generate_ollama(prompt, max_tokens, temperature, system)
                elif self.backend == "anthropic":
                    return self._generate_anthropic(prompt, max_tokens, temperature, system)
                elif self.backend == "openai":
                    return self._generate_openai(prompt, max_tokens, temperature, system)

            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    print(f"LLM generation attempt {attempt + 1} failed: {e}. Retrying...")
                    time.sleep(self.retry_delay * (attempt + 1))  # Exponential backoff
                else:
                    raise Exception(
                        f"Generation failed after {self.max_retries} attempts "
                        f"({self.backend}): {str(last_error)}"
                    )

        raise Exception(f"Generation failed: {last_error}")

    def _generate_ollama(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        system: Optional[str]
    ) -> str:
        """Generate using Ollama local model."""
        url = f"{self.ollama_url}/api/generate"

        # Add system message to prompt if provided
        if system:
            full_prompt = f"{system}\n\n{prompt}"
        else:
            full_prompt = prompt

        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }

        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        return response.json()["response"]

    def _generate_anthropic(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        system: Optional[str]
    ) -> str:
        """Generate using Anthropic Claude."""
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}]
        }

        if system:
            kwargs["system"] = system

        message = self.client.messages.create(**kwargs)
        return message.content[0].text

    def _generate_openai(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        system: Optional[str]
    ) -> str:
        """Generate using OpenAI."""
        messages = []

        if system:
            messages.append({"role": "system", "content": system})

        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=messages
        )
        return response.choices[0].message.content

    def load_prompt_template(
        self,
        template_name: str,
        prompts_dir: Optional[Path] = None,
        **variables
    ) -> str:
        """
        Load and render a prompt template.

        Args:
            template_name: Name of the template file (without .txt extension)
            prompts_dir: Optional custom prompts directory (for testing)
            **variables: Variables to substitute in the template

        Returns:
            Rendered prompt string

        Raises:
            FileNotFoundError: If template file doesn't exist
        """
        # Find prompts directory
        if prompts_dir is None:
            prompts_dir = Path(__file__).parent.parent / "prompts"
        template_path = prompts_dir / f"{template_name}.txt"

        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        # Load template
        with open(template_path, 'r') as f:
            template = f.read()

        # Simple variable substitution
        rendered = template
        for key, value in variables.items():
            placeholder = f"{{{key}}}"
            rendered = rendered.replace(placeholder, str(value))

        return rendered

    def generate_from_template(
        self,
        template_name: str,
        variables: Dict[str, Any],
        max_tokens: int = 1000,
        temperature: float = 0.7,
        system: Optional[str] = None,
        prompts_dir: Optional[Path] = None
    ) -> str:
        """
        Generate text using a prompt template.

        Args:
            template_name: Name of the template file
            variables: Dictionary of variables to substitute
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            system: Optional system message
            prompts_dir: Optional custom prompts directory (for testing)

        Returns:
            Generated text response
        """
        prompt = self.load_prompt_template(template_name, prompts_dir=prompts_dir, **variables)
        return self.generate(prompt, max_tokens, temperature, system)

    def test_connection(self) -> bool:
        """
        Test if the LLM backend is accessible.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Try a simple generation
            result = self.generate(
                "Say 'OK'",
                max_tokens=10,
                temperature=0.0
            )
            return len(result) > 0
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False

    def get_info(self) -> Dict[str, Any]:
        """
        Get information about the current LLM configuration.

        Returns:
            Dictionary with backend info
        """
        return {
            "backend": self.backend,
            "model": self.model,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay
        }
