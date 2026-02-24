"""
Unit Tests for Cost Tracker (Phase 6)
"""

import pytest
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.cost_tracker import CostTracker


@pytest.fixture
def cost_tracker():
    """Create fresh cost tracker"""
    return CostTracker()


# Text Cost Calculation Tests

def test_calculate_text_cost_openai(cost_tracker):
    """Test calculating cost for OpenAI text"""
    cost = cost_tracker.calculate_text_cost(
        provider='openai',
        model='gpt-4o-mini',
        input_tokens=1000,
        output_tokens=500
    )

    # gpt-4o-mini: input=$0.00015/1k, output=$0.0006/1k
    # Expected: (1000/1000 * 0.00015) + (500/1000 * 0.0006) = 0.00015 + 0.0003 = 0.00045
    assert cost == pytest.approx(0.00045, abs=0.000001)


def test_calculate_text_cost_anthropic(cost_tracker):
    """Test calculating cost for Anthropic text"""
    cost = cost_tracker.calculate_text_cost(
        provider='anthropic',
        model='claude-3-5-sonnet-20241022',
        input_tokens=2000,
        output_tokens=1000
    )

    # claude-3-5-sonnet: input=$0.003/1k, output=$0.015/1k
    # Expected: (2000/1000 * 0.003) + (1000/1000 * 0.015) = 0.006 + 0.015 = 0.021
    assert cost == pytest.approx(0.021, abs=0.000001)


def test_calculate_text_cost_ollama(cost_tracker):
    """Test calculating cost for Ollama (free)"""
    cost = cost_tracker.calculate_text_cost(
        provider='ollama',
        model='llama3.2:3b',
        input_tokens=5000,
        output_tokens=2000
    )

    # Ollama is free
    assert cost == 0.0


def test_calculate_text_cost_unknown_provider(cost_tracker):
    """Test calculating cost for unknown provider"""
    cost = cost_tracker.calculate_text_cost(
        provider='unknown',
        model='some-model',
        input_tokens=1000,
        output_tokens=500
    )

    # Should return 0 for unknown providers
    assert cost == 0.0


def test_calculate_text_cost_unknown_model(cost_tracker):
    """Test calculating cost for unknown model"""
    cost = cost_tracker.calculate_text_cost(
        provider='openai',
        model='unknown-model',
        input_tokens=1000,
        output_tokens=500
    )

    # Should return 0 for unknown models
    assert cost == 0.0


def test_calculate_text_cost_zero_tokens(cost_tracker):
    """Test calculating cost with zero tokens"""
    cost = cost_tracker.calculate_text_cost(
        provider='openai',
        model='gpt-4o-mini',
        input_tokens=0,
        output_tokens=0
    )

    assert cost == 0.0


# Image Cost Calculation Tests

def test_calculate_image_cost_openai(cost_tracker):
    """Test calculating cost for OpenAI image"""
    cost = cost_tracker.calculate_image_cost(
        provider='openai',
        model='gpt-4o',
        image_count=1
    )

    # gpt-4o: $0.00765 per image
    assert cost == pytest.approx(0.00765, abs=0.000001)


def test_calculate_image_cost_multiple_images(cost_tracker):
    """Test calculating cost for multiple images"""
    cost = cost_tracker.calculate_image_cost(
        provider='openai',
        model='gpt-4o-mini',
        image_count=5
    )

    # gpt-4o-mini: $0.0015 per image × 5
    assert cost == pytest.approx(0.0075, abs=0.000001)


def test_calculate_image_cost_anthropic(cost_tracker):
    """Test calculating cost for Anthropic image"""
    cost = cost_tracker.calculate_image_cost(
        provider='anthropic',
        model='claude-3-5-sonnet-20241022',
        image_count=2
    )

    # claude-3-5-sonnet: $0.0048 per image × 2
    assert cost == pytest.approx(0.0096, abs=0.000001)


def test_calculate_image_cost_ollama(cost_tracker):
    """Test calculating cost for Ollama image (free)"""
    cost = cost_tracker.calculate_image_cost(
        provider='ollama',
        model='llava',
        image_count=10
    )

    # Ollama is free
    assert cost == 0.0


def test_calculate_image_cost_unknown_provider(cost_tracker):
    """Test calculating image cost for unknown provider"""
    cost = cost_tracker.calculate_image_cost(
        provider='unknown',
        model='some-model',
        image_count=1
    )

    assert cost == 0.0


# Token Estimation Tests

def test_estimate_text_tokens(cost_tracker):
    """Test token estimation"""
    text = "This is a test message with several words"
    tokens = cost_tracker.estimate_text_tokens(text)

    # Rough estimate: 1 token ≈ 4 characters
    # len(text) = 42, so roughly 10-11 tokens
    assert tokens >= 10
    assert tokens <= 11


def test_estimate_text_tokens_empty(cost_tracker):
    """Test token estimation with empty text"""
    tokens = cost_tracker.estimate_text_tokens("")
    assert tokens == 0


def test_estimate_text_tokens_none(cost_tracker):
    """Test token estimation with None"""
    tokens = cost_tracker.estimate_text_tokens(None)
    assert tokens == 0


def test_estimate_text_tokens_long_text(cost_tracker):
    """Test token estimation with long text"""
    text = "word " * 100  # 500 characters
    tokens = cost_tracker.estimate_text_tokens(text)

    # Should be around 125 tokens (500/4)
    assert tokens >= 120
    assert tokens <= 130


# Usage Tracking Tests

def test_track_usage(cost_tracker):
    """Test tracking API usage"""
    cost_tracker.track_usage(
        provider='openai',
        model='gpt-4o-mini',
        content_type='text',
        cost=0.0001,
        tokens={'input': 100, 'output': 50}
    )

    assert len(cost_tracker.session_costs) == 1
    assert cost_tracker.session_costs[0]['provider'] == 'openai'
    assert cost_tracker.session_costs[0]['cost'] == 0.0001


def test_track_multiple_usage(cost_tracker):
    """Test tracking multiple API calls"""
    for i in range(5):
        cost_tracker.track_usage(
            provider='anthropic',
            model='claude-3-5-haiku-20241022',
            content_type='text',
            cost=0.0002 * (i + 1)
        )

    assert len(cost_tracker.session_costs) == 5


# Session Total Tests

def test_get_session_total(cost_tracker):
    """Test getting session total cost"""
    cost_tracker.track_usage('openai', 'gpt-4o-mini', 'text', 0.0001)
    cost_tracker.track_usage('openai', 'gpt-4o-mini', 'text', 0.0002)
    cost_tracker.track_usage('anthropic', 'claude-3-5-sonnet-20241022', 'text', 0.0003)

    total = cost_tracker.get_session_total()
    assert total == pytest.approx(0.0006, abs=0.000001)


def test_get_session_total_empty(cost_tracker):
    """Test getting session total with no usage"""
    total = cost_tracker.get_session_total()
    assert total == 0.0


# Session Stats Tests

def test_get_session_stats(cost_tracker):
    """Test getting session statistics"""
    cost_tracker.track_usage('openai', 'gpt-4o-mini', 'text', 0.0001)
    cost_tracker.track_usage('openai', 'gpt-4o-mini', 'image', 0.0002)
    cost_tracker.track_usage('anthropic', 'claude-3-5-sonnet-20241022', 'text', 0.0003)

    stats = cost_tracker.get_session_stats()

    assert stats['total_cost'] == pytest.approx(0.0006, abs=0.000001)
    assert stats['total_calls'] == 3

    # Check by_provider
    assert 'openai' in stats['by_provider']
    assert 'anthropic' in stats['by_provider']
    assert stats['by_provider']['openai']['calls'] == 2
    assert stats['by_provider']['anthropic']['calls'] == 1

    # Check by_content_type
    assert 'text' in stats['by_content_type']
    assert 'image' in stats['by_content_type']
    assert stats['by_content_type']['text']['calls'] == 2
    assert stats['by_content_type']['image']['calls'] == 1


def test_get_session_stats_empty(cost_tracker):
    """Test getting session stats with no usage"""
    stats = cost_tracker.get_session_stats()

    assert stats['total_cost'] == 0
    assert stats['total_calls'] == 0
    assert stats['session_start'] is None
    assert stats['session_end'] is None


# Reset Session Tests

def test_reset_session(cost_tracker):
    """Test resetting session"""
    cost_tracker.track_usage('openai', 'gpt-4o-mini', 'text', 0.0001)
    cost_tracker.track_usage('openai', 'gpt-4o-mini', 'text', 0.0002)

    assert len(cost_tracker.session_costs) == 2

    cost_tracker.reset_session()

    assert len(cost_tracker.session_costs) == 0
    assert cost_tracker.get_session_total() == 0.0


# Singleton Tests

def test_cost_tracker_singleton():
    """Test cost tracker singleton pattern"""
    from src.utils.cost_tracker import get_cost_tracker

    tracker1 = get_cost_tracker()
    tracker2 = get_cost_tracker()

    assert tracker1 is tracker2


# Edge Cases

def test_calculate_cost_with_large_numbers(cost_tracker):
    """Test cost calculation with large token counts"""
    cost = cost_tracker.calculate_text_cost(
        provider='openai',
        model='gpt-4o-mini',
        input_tokens=1000000,  # 1 million tokens
        output_tokens=500000
    )

    # Should handle large numbers correctly
    # Expected: (1000 * 0.00015) + (500 * 0.0006) = 0.15 + 0.3 = 0.45
    assert cost == pytest.approx(0.45, abs=0.001)


def test_track_usage_without_tokens(cost_tracker):
    """Test tracking usage without token info"""
    cost_tracker.track_usage(
        provider='openai',
        model='gpt-4o',
        content_type='image',
        cost=0.00765
    )

    assert len(cost_tracker.session_costs) == 1
    assert cost_tracker.session_costs[0]['tokens'] == {}


def test_cost_precision(cost_tracker):
    """Test cost calculation precision"""
    cost = cost_tracker.calculate_text_cost(
        provider='openai',
        model='gpt-4o-mini',
        input_tokens=123,
        output_tokens=456
    )

    # Should maintain 6 decimal places
    assert isinstance(cost, float)
    assert len(str(cost).split('.')[-1]) <= 6


# Integration Tests

def test_full_cost_tracking_workflow(cost_tracker):
    """Test complete cost tracking workflow"""
    # Calculate text cost
    text_cost = cost_tracker.calculate_text_cost(
        provider='openai',
        model='gpt-4o-mini',
        input_tokens=1000,
        output_tokens=500
    )

    # Track it
    cost_tracker.track_usage(
        provider='openai',
        model='gpt-4o-mini',
        content_type='text',
        cost=text_cost,
        tokens={'input': 1000, 'output': 500}
    )

    # Calculate image cost
    image_cost = cost_tracker.calculate_image_cost(
        provider='openai',
        model='gpt-4o',
        image_count=2
    )

    # Track it
    cost_tracker.track_usage(
        provider='openai',
        model='gpt-4o',
        content_type='image',
        cost=image_cost
    )

    # Get stats
    stats = cost_tracker.get_session_stats()

    assert stats['total_calls'] == 2
    assert stats['total_cost'] > 0
    assert 'openai' in stats['by_provider']
    assert stats['by_provider']['openai']['calls'] == 2
