"""
Cost Tracker for AI API Usage.

Tracks and calculates costs for LLM and vision API calls.
"""

import logging
from typing import Dict, Optional
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)


class CostTracker:
    """Tracks API costs for different providers and models."""

    # Pricing per 1000 tokens (input/output) - as of 2026
    PRICING = {
        'openai': {
            'gpt-4o': {'input': 0.0025, 'output': 0.010},
            'gpt-4o-mini': {'input': 0.00015, 'output': 0.0006},
            'gpt-4-turbo': {'input': 0.01, 'output': 0.03},
            'gpt-3.5-turbo': {'input': 0.0005, 'output': 0.0015}
        },
        'anthropic': {
            'claude-3-5-sonnet-20241022': {'input': 0.003, 'output': 0.015},
            'claude-3-5-haiku-20241022': {'input': 0.0008, 'output': 0.004},
            'claude-3-opus-20240229': {'input': 0.015, 'output': 0.075}
        },
        'ollama': {
            # Ollama is free (local)
            'llama3.2:3b': {'input': 0.0, 'output': 0.0},
            'llama3.1:8b': {'input': 0.0, 'output': 0.0},
            'llama3.1:70b': {'input': 0.0, 'output': 0.0}
        }
    }

    # Image pricing (per image)
    IMAGE_PRICING = {
        'openai': {
            'gpt-4o': 0.00765,  # per image (1024x1024)
            'gpt-4o-mini': 0.0015
        },
        'anthropic': {
            'claude-3-5-sonnet-20241022': 0.0048,  # per image
            'claude-3-opus-20240229': 0.024
        },
        'ollama': {
            'llava': 0.0  # Free (local)
        }
    }

    def __init__(self):
        """Initialize cost tracker."""
        self.session_costs = []
        logging.info("CostTracker initialized")

    def calculate_text_cost(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int
    ) -> float:
        """
        Calculate cost for text API call.

        Args:
            provider: Provider name (openai, anthropic, ollama)
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Cost in USD
        """
        try:
            provider_lower = provider.lower()

            if provider_lower not in self.PRICING:
                logging.warning(f"Unknown provider: {provider}")
                return 0.0

            if model not in self.PRICING[provider_lower]:
                # Try to find a matching model
                for model_key in self.PRICING[provider_lower].keys():
                    if model_key in model.lower():
                        model = model_key
                        break
                else:
                    logging.warning(f"Unknown model: {model} for provider {provider}")
                    return 0.0

            pricing = self.PRICING[provider_lower][model]
            input_cost = (input_tokens / 1000) * pricing['input']
            output_cost = (output_tokens / 1000) * pricing['output']
            total_cost = input_cost + output_cost

            logging.debug(
                f"Cost calculated: {provider}/{model} - "
                f"Input: {input_tokens} tokens (${input_cost:.6f}), "
                f"Output: {output_tokens} tokens (${output_cost:.6f}), "
                f"Total: ${total_cost:.6f}"
            )

            return round(total_cost, 6)

        except Exception as e:
            logging.error(f"Error calculating text cost: {e}")
            return 0.0

    def calculate_image_cost(
        self,
        provider: str,
        model: str,
        image_count: int = 1
    ) -> float:
        """
        Calculate cost for image/vision API call.

        Args:
            provider: Provider name
            model: Model name
            image_count: Number of images processed

        Returns:
            Cost in USD
        """
        try:
            provider_lower = provider.lower()

            if provider_lower not in self.IMAGE_PRICING:
                logging.warning(f"Unknown provider for images: {provider}")
                return 0.0

            # Find matching model
            cost_per_image = 0.0
            for model_key, price in self.IMAGE_PRICING[provider_lower].items():
                if model_key in model.lower():
                    cost_per_image = price
                    break

            if cost_per_image == 0.0 and provider_lower != 'ollama':
                logging.warning(f"Unknown image model: {model} for provider {provider}")

            total_cost = cost_per_image * image_count

            logging.debug(
                f"Image cost calculated: {provider}/{model} - "
                f"{image_count} images × ${cost_per_image} = ${total_cost:.6f}"
            )

            return round(total_cost, 6)

        except Exception as e:
            logging.error(f"Error calculating image cost: {e}")
            return 0.0

    def estimate_text_tokens(self, text: str) -> int:
        """
        Estimate number of tokens in text.
        Uses rough approximation: 1 token ≈ 4 characters.

        Args:
            text: Input text

        Returns:
            Estimated token count
        """
        if not text:
            return 0

        # Rough estimation: 1 token ≈ 4 characters
        # This is approximate; real tokenizers vary
        return len(text) // 4

    def track_usage(
        self,
        provider: str,
        model: str,
        content_type: str,
        cost: float,
        tokens: Optional[Dict[str, int]] = None
    ):
        """
        Track API usage for analytics.

        Args:
            provider: Provider name
            model: Model name
            content_type: Type of content (text, image, video)
            cost: Cost of the call
            tokens: Token usage dict with 'input' and 'output' keys
        """
        self.session_costs.append({
            'timestamp': datetime.utcnow().isoformat(),
            'provider': provider,
            'model': model,
            'content_type': content_type,
            'cost': cost,
            'tokens': tokens or {}
        })

    def get_session_total(self) -> float:
        """
        Get total cost for current session.

        Returns:
            Total cost in USD
        """
        return sum(item['cost'] for item in self.session_costs)

    def get_session_stats(self) -> Dict:
        """
        Get session statistics.

        Returns:
            Dictionary with usage statistics
        """
        total_cost = self.get_session_total()

        # Group by provider
        by_provider = {}
        for item in self.session_costs:
            provider = item['provider']
            if provider not in by_provider:
                by_provider[provider] = {'cost': 0, 'calls': 0}
            by_provider[provider]['cost'] += item['cost']
            by_provider[provider]['calls'] += 1

        # Group by content type
        by_type = {}
        for item in self.session_costs:
            content_type = item['content_type']
            if content_type not in by_type:
                by_type[content_type] = {'cost': 0, 'calls': 0}
            by_type[content_type]['cost'] += item['cost']
            by_type[content_type]['calls'] += 1

        return {
            'total_cost': round(total_cost, 6),
            'total_calls': len(self.session_costs),
            'by_provider': by_provider,
            'by_content_type': by_type,
            'session_start': self.session_costs[0]['timestamp'] if self.session_costs else None,
            'session_end': self.session_costs[-1]['timestamp'] if self.session_costs else None
        }

    def reset_session(self):
        """Reset session costs."""
        self.session_costs = []
        logging.info("Session costs reset")


# Global cost tracker instance
_cost_tracker_instance = None


def get_cost_tracker() -> CostTracker:
    """
    Get global CostTracker instance.

    Returns:
        CostTracker singleton
    """
    global _cost_tracker_instance
    if _cost_tracker_instance is None:
        _cost_tracker_instance = CostTracker()
    return _cost_tracker_instance
