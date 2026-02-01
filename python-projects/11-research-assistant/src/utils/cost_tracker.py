"""
Cost Tracker for Research Assistant.

Tracks API usage costs for:
- OpenAI (GPT-4, GPT-3.5, Whisper)
- Anthropic (Claude models)
- Web search APIs (if paid)
- Embedding models
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path


class CostTracker:
    """Tracks and calculates API usage costs."""

    # Pricing per 1K tokens (as of 2024-01)
    # Source: https://openai.com/pricing, https://anthropic.com/pricing
    PRICING = {
        'openai': {
            'gpt-4': {'input': 0.03, 'output': 0.06},
            'gpt-4-turbo': {'input': 0.01, 'output': 0.03},
            'gpt-3.5-turbo': {'input': 0.0005, 'output': 0.0015},
            'whisper-1': {'audio_minute': 0.006},  # Per minute
            'text-embedding-3-small': {'input': 0.00002, 'output': 0},
            'text-embedding-ada-002': {'input': 0.0001, 'output': 0},
        },
        'anthropic': {
            'claude-3-opus': {'input': 0.015, 'output': 0.075},
            'claude-3-5-sonnet': {'input': 0.003, 'output': 0.015},
            'claude-3-sonnet': {'input': 0.003, 'output': 0.015},
            'claude-3-haiku': {'input': 0.00025, 'output': 0.00125},
        },
        'ollama': {
            'default': {'input': 0, 'output': 0},  # Local, free
        }
    }

    def __init__(self, log_file: Optional[str] = None):
        """
        Initialize cost tracker.

        Args:
            log_file: Optional file path to log costs
        """
        self.log_file = Path(log_file) if log_file else None
        self.session_costs = []

        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)

        logging.info("CostTracker initialized")

    def track_llm_call(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Track LLM API call and calculate cost.

        Args:
            provider: LLM provider (openai, anthropic, ollama)
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            metadata: Optional metadata (query_id, operation, etc.)

        Returns:
            Dict with cost information
        """
        provider = provider.lower()
        model_key = self._get_model_key(provider, model)

        # Get pricing
        if provider not in self.PRICING:
            logging.warning(f"Unknown provider: {provider}, assuming free")
            input_cost = 0
            output_cost = 0
        elif model_key not in self.PRICING[provider]:
            logging.warning(f"Unknown model: {model_key} for {provider}, using default")
            # Use cheapest model as fallback
            model_pricing = list(self.PRICING[provider].values())[0]
            input_cost = (input_tokens / 1000) * model_pricing.get('input', 0)
            output_cost = (output_tokens / 1000) * model_pricing.get('output', 0)
        else:
            model_pricing = self.PRICING[provider][model_key]
            input_cost = (input_tokens / 1000) * model_pricing.get('input', 0)
            output_cost = (output_tokens / 1000) * model_pricing.get('output', 0)

        total_cost = input_cost + output_cost

        # Create cost record
        cost_record = {
            'timestamp': datetime.now().isoformat(),
            'provider': provider,
            'model': model,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': input_tokens + output_tokens,
            'input_cost': round(input_cost, 6),
            'output_cost': round(output_cost, 6),
            'total_cost': round(total_cost, 6),
            'metadata': metadata or {}
        }

        # Add to session costs
        self.session_costs.append(cost_record)

        # Log to file if configured
        if self.log_file:
            self._log_to_file(cost_record)

        logging.info(
            f"Cost tracked: {provider}/{model} - "
            f"{input_tokens} in + {output_tokens} out = ${total_cost:.6f}"
        )

        return cost_record

    def track_transcription(
        self,
        provider: str,
        duration_minutes: float,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Track audio transcription cost.

        Args:
            provider: Provider (openai, local)
            duration_minutes: Audio duration in minutes
            metadata: Optional metadata

        Returns:
            Dict with cost information
        """
        if provider.lower() == 'openai':
            cost = duration_minutes * self.PRICING['openai']['whisper-1']['audio_minute']
        else:
            cost = 0  # Local transcription is free

        cost_record = {
            'timestamp': datetime.now().isoformat(),
            'provider': provider,
            'service': 'transcription',
            'duration_minutes': round(duration_minutes, 2),
            'total_cost': round(cost, 6),
            'metadata': metadata or {}
        }

        self.session_costs.append(cost_record)

        if self.log_file:
            self._log_to_file(cost_record)

        logging.info(f"Transcription cost tracked: ${cost:.6f} ({duration_minutes:.1f} min)")

        return cost_record

    def track_web_search(
        self,
        provider: str,
        num_queries: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Track web search API cost.

        Args:
            provider: Search provider (duckduckgo, brave, serpapi)
            num_queries: Number of search queries
            metadata: Optional metadata

        Returns:
            Dict with cost information
        """
        # Cost per query
        search_costs = {
            'duckduckgo': 0,  # Free
            'brave': 0.005,   # $5 per 1000 queries
            'serpapi': 0.005  # Varies by plan
        }

        cost_per_query = search_costs.get(provider.lower(), 0)
        total_cost = num_queries * cost_per_query

        cost_record = {
            'timestamp': datetime.now().isoformat(),
            'provider': provider,
            'service': 'web_search',
            'num_queries': num_queries,
            'cost_per_query': cost_per_query,
            'total_cost': round(total_cost, 6),
            'metadata': metadata or {}
        }

        self.session_costs.append(cost_record)

        if self.log_file:
            self._log_to_file(cost_record)

        logging.info(f"Web search cost tracked: ${total_cost:.6f} ({num_queries} queries)")

        return cost_record

    def get_session_total(self) -> float:
        """Get total cost for current session."""
        return sum(record.get('total_cost', 0) for record in self.session_costs)

    def get_session_breakdown(self) -> Dict[str, Any]:
        """Get cost breakdown for current session."""
        breakdown = {
            'total_cost': 0,
            'total_calls': len(self.session_costs),
            'by_provider': {},
            'by_service': {},
            'total_tokens': 0
        }

        for record in self.session_costs:
            cost = record.get('total_cost', 0)
            provider = record.get('provider', 'unknown')
            service = record.get('service', 'llm')

            breakdown['total_cost'] += cost

            # By provider
            if provider not in breakdown['by_provider']:
                breakdown['by_provider'][provider] = {'cost': 0, 'calls': 0}
            breakdown['by_provider'][provider]['cost'] += cost
            breakdown['by_provider'][provider]['calls'] += 1

            # By service
            if service not in breakdown['by_service']:
                breakdown['by_service'][service] = {'cost': 0, 'calls': 0}
            breakdown['by_service'][service]['cost'] += cost
            breakdown['by_service'][service]['calls'] += 1

            # Total tokens
            breakdown['total_tokens'] += record.get('total_tokens', 0)

        # Round costs
        breakdown['total_cost'] = round(breakdown['total_cost'], 6)
        for provider_data in breakdown['by_provider'].values():
            provider_data['cost'] = round(provider_data['cost'], 6)
        for service_data in breakdown['by_service'].values():
            service_data['cost'] = round(service_data['cost'], 6)

        return breakdown

    def reset_session(self):
        """Reset session costs."""
        self.session_costs = []
        logging.info("Session costs reset")

    def _get_model_key(self, provider: str, model: str) -> str:
        """Extract model key from full model name."""
        model = model.lower()

        # OpenAI model mapping
        if provider == 'openai':
            if 'gpt-4-turbo' in model or 'gpt-4-1106' in model:
                return 'gpt-4-turbo'
            elif 'gpt-4' in model:
                return 'gpt-4'
            elif 'gpt-3.5' in model:
                return 'gpt-3.5-turbo'
            elif 'whisper' in model:
                return 'whisper-1'
            elif 'text-embedding-3-small' in model:
                return 'text-embedding-3-small'
            elif 'text-embedding-ada' in model:
                return 'text-embedding-ada-002'

        # Anthropic model mapping
        elif provider == 'anthropic':
            if 'claude-3-opus' in model:
                return 'claude-3-opus'
            elif 'claude-3-5-sonnet' in model or 'claude-3.5-sonnet' in model:
                return 'claude-3-5-sonnet'
            elif 'claude-3-sonnet' in model:
                return 'claude-3-sonnet'
            elif 'claude-3-haiku' in model:
                return 'claude-3-haiku'

        # Ollama (all free)
        elif provider == 'ollama':
            return 'default'

        return model

    def _log_to_file(self, cost_record: Dict[str, Any]):
        """Log cost record to file."""
        try:
            import json
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(cost_record) + '\n')
        except Exception as e:
            logging.error(f"Failed to log cost to file: {e}")

    def estimate_research_cost(
        self,
        provider: str,
        model: str,
        num_sources: int = 20,
        avg_source_length: int = 2000
    ) -> Dict[str, Any]:
        """
        Estimate cost for a research query.

        Args:
            provider: LLM provider
            model: Model name
            num_sources: Number of sources to process
            avg_source_length: Average source length in tokens

        Returns:
            Dict with cost estimate
        """
        # Estimate tokens
        # Input: query + sources + context
        estimated_input_tokens = (
            100 +  # Query
            (num_sources * avg_source_length) +  # Sources
            500  # System prompt + context
        )

        # Output: summary + findings + citations
        estimated_output_tokens = (
            500 +  # Summary
            (5 * 100) +  # 5 findings @ 100 tokens each
            (num_sources * 50)  # Citations
        )

        # Calculate cost
        model_key = self._get_model_key(provider, model)
        if provider in self.PRICING and model_key in self.PRICING[provider]:
            pricing = self.PRICING[provider][model_key]
            input_cost = (estimated_input_tokens / 1000) * pricing.get('input', 0)
            output_cost = (estimated_output_tokens / 1000) * pricing.get('output', 0)
            total_cost = input_cost + output_cost
        else:
            input_cost = output_cost = total_cost = 0

        return {
            'provider': provider,
            'model': model,
            'estimated_input_tokens': estimated_input_tokens,
            'estimated_output_tokens': estimated_output_tokens,
            'estimated_total_tokens': estimated_input_tokens + estimated_output_tokens,
            'estimated_input_cost': round(input_cost, 6),
            'estimated_output_cost': round(output_cost, 6),
            'estimated_total_cost': round(total_cost, 6)
        }
