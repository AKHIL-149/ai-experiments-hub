"""
Production Hardening Tests
Tests for rate limiting, logging, error handling, and configuration validation
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from src.middleware.rate_limiter import RateLimiter, RATE_LIMITS
from src.middleware.logging_middleware import StructuredLogger
from src.middleware.error_handler import ErrorResponse, retry_on_transient_error
from src.core.config_validator import ConfigValidator, ConfigLevel, ConfigRule


class TestRateLimiter:
    """Test suite for rate limiter"""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client"""
        redis_mock = MagicMock()
        redis_mock.ping.return_value = True
        redis_mock.zremrangebyscore.return_value = 0
        redis_mock.zcard.return_value = 0
        redis_mock.zadd.return_value = 1
        redis_mock.expire.return_value = True
        redis_mock.zrange.return_value = []
        return redis_mock

    @pytest.fixture
    def rate_limiter(self, mock_redis):
        """Create rate limiter with mocked Redis"""
        with patch('redis.from_url', return_value=mock_redis):
            return RateLimiter()

    def test_rate_limiter_initialization_success(self, mock_redis):
        """Test successful rate limiter initialization"""
        with patch('redis.from_url', return_value=mock_redis):
            limiter = RateLimiter()
            assert limiter.enabled is True

    def test_rate_limiter_initialization_failure(self):
        """Test rate limiter initialization failure"""
        with patch('redis.from_url', side_effect=Exception("No Redis")):
            limiter = RateLimiter()
            assert limiter.enabled is False

    def test_rate_limit_allowed(self, rate_limiter, mock_redis):
        """Test request allowed under rate limit"""
        mock_redis.zcard.return_value = 5  # Under limit

        allowed, retry_after = rate_limiter.is_allowed(
            identifier="user:123",
            endpoint="/api/test",
            limit=10,
            window=60
        )

        assert allowed is True
        assert retry_after == 0

    def test_rate_limit_exceeded(self, rate_limiter, mock_redis):
        """Test request blocked when rate limit exceeded"""
        mock_redis.zcard.return_value = 10  # At limit
        mock_redis.zrange.return_value = [(str(time.time() - 30), time.time() - 30)]

        allowed, retry_after = rate_limiter.is_allowed(
            identifier="user:123",
            endpoint="/api/test",
            limit=10,
            window=60
        )

        assert allowed is False
        assert retry_after > 0

    def test_rate_limit_memory_fallback(self):
        """Test rate limiter memory fallback"""
        with patch('redis.from_url', side_effect=Exception("No Redis")):
            limiter = RateLimiter()

            # First request should be allowed
            allowed1, _ = limiter.is_allowed("user:1", "/test", limit=2, window=60)
            assert allowed1 is True

            # Second request should be allowed
            allowed2, _ = limiter.is_allowed("user:1", "/test", limit=2, window=60)
            assert allowed2 is True

            # Third request should be blocked
            allowed3, retry = limiter.is_allowed("user:1", "/test", limit=2, window=60)
            assert allowed3 is False
            assert retry > 0

    def test_rate_limit_configs_exist(self):
        """Test that rate limit configurations are defined"""
        assert '/api/auth/register' in RATE_LIMITS
        assert '/api/auth/login' in RATE_LIMITS
        assert 'default' in RATE_LIMITS

        # Check auth endpoints have strict limits
        assert RATE_LIMITS['/api/auth/register']['limit'] <= 10
        assert RATE_LIMITS['/api/auth/login']['limit'] <= 10


class TestStructuredLogger:
    """Test suite for structured logger"""

    def test_mask_sensitive_dict(self):
        """Test masking sensitive data in dictionary"""
        data = {
            'username': 'test',
            'password': 'secret123',
            'token': 'abc123'
        }

        masked = StructuredLogger.mask_sensitive_data(data)

        assert masked['username'] == 'test'
        assert masked['password'] == '[REDACTED]'
        assert masked['token'] == '[REDACTED]'

    def test_mask_sensitive_nested(self):
        """Test masking nested sensitive data"""
        data = {
            'user': {
                'name': 'test',
                'password': 'secret'
            },
            'api_key': 'key123'
        }

        masked = StructuredLogger.mask_sensitive_data(data)

        assert masked['user']['name'] == 'test'
        assert masked['user']['password'] == '[REDACTED]'
        assert masked['api_key'] == '[REDACTED]'

    def test_mask_sensitive_string_jwt(self):
        """Test masking JWT tokens in strings"""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyIjoiMTIzIn0.abc"

        masked = StructuredLogger.mask_sensitive_data(text)

        assert 'Bearer [REDACTED]' in masked
        assert 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9' not in masked

    def test_mask_sensitive_string_github_token(self):
        """Test masking GitHub tokens in strings"""
        text = "Token: ghp_1234567890123456789012345678901234"

        masked = StructuredLogger.mask_sensitive_data(text)

        assert 'ghp_[REDACTED]' in masked
        assert 'ghp_1234567890123456789012345678901234' not in masked


class TestErrorResponse:
    """Test suite for error response"""

    def test_create_basic_error(self):
        """Test creating basic error response"""
        response = ErrorResponse.create(
            status_code=404,
            error_type='not_found',
            message='Resource not found'
        )

        assert response['error']['code'] == 404
        assert response['error']['type'] == 'not_found'
        assert response['error']['message'] == 'Resource not found'

    def test_create_error_with_details(self):
        """Test creating error with details"""
        response = ErrorResponse.create(
            status_code=400,
            error_type='validation_error',
            message='Invalid input',
            details={'field': 'email', 'reason': 'Invalid format'}
        )

        assert 'details' in response['error']
        assert response['error']['details']['field'] == 'email'

    def test_create_error_with_correlation_id(self):
        """Test creating error with correlation ID"""
        response = ErrorResponse.create(
            status_code=500,
            error_type='internal_error',
            message='Server error',
            correlation_id='abc-123'
        )

        assert 'correlation_id' in response
        assert response['correlation_id'] == 'abc-123'


class TestRetryDecorator:
    """Test suite for retry decorator"""

    def test_retry_succeeds_first_try(self):
        """Test retry decorator when function succeeds first try"""
        call_count = 0

        @retry_on_transient_error(max_retries=3)
        def succeeds_first():
            nonlocal call_count
            call_count += 1
            return "success"

        result = succeeds_first()

        assert result == "success"
        assert call_count == 1

    def test_retry_succeeds_after_failures(self):
        """Test retry decorator with transient failures"""
        from sqlalchemy.exc import OperationalError

        call_count = 0

        @retry_on_transient_error(max_retries=3, delay=0.01)
        def fails_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise OperationalError("DB unavailable", None, None)
            return "success"

        result = fails_twice()

        assert result == "success"
        assert call_count == 3

    def test_retry_max_retries_exceeded(self):
        """Test retry decorator when max retries exceeded"""
        from sqlalchemy.exc import OperationalError

        @retry_on_transient_error(max_retries=2, delay=0.01)
        def always_fails():
            raise OperationalError("DB unavailable", None, None)

        with pytest.raises(OperationalError):
            always_fails()


class TestConfigValidator:
    """Test suite for configuration validator"""

    def test_validator_initialization(self):
        """Test config validator initialization"""
        validator = ConfigValidator()
        assert validator.errors == []
        assert validator.warnings == []
        assert validator.info == []

    def test_validate_required_missing(self):
        """Test validation fails for missing required config"""
        # Create a validator with a required rule
        validator = ConfigValidator()
        validator.RULES = [
            ConfigRule(
                name='TEST_REQUIRED',
                level=ConfigLevel.REQUIRED,
                description='Test required variable'
            )
        ]

        # Ensure variable is not set
        import os
        if 'TEST_REQUIRED' in os.environ:
            del os.environ['TEST_REQUIRED']

        is_valid = validator.validate()

        assert is_valid is False
        assert len(validator.errors) > 0

    def test_validate_optional_missing(self):
        """Test validation passes for missing optional config"""
        validator = ConfigValidator()
        validator.RULES = [
            ConfigRule(
                name='TEST_OPTIONAL',
                level=ConfigLevel.OPTIONAL,
                description='Test optional variable'
            )
        ]

        # Ensure variable is not set
        import os
        if 'TEST_OPTIONAL' in os.environ:
            del os.environ['TEST_OPTIONAL']

        is_valid = validator.validate()

        assert is_valid is True
        assert len(validator.errors) == 0

    def test_validate_with_validator_pass(self):
        """Test validation passes when validator succeeds"""
        import os
        os.environ['TEST_PORT'] = '8080'

        validator = ConfigValidator()
        validator.RULES = [
            ConfigRule(
                name='TEST_PORT',
                level=ConfigLevel.REQUIRED,
                validator=lambda x: x.isdigit() and 1 <= int(x) <= 65535,
                description='Test port'
            )
        ]

        is_valid = validator.validate()

        assert is_valid is True
        assert len(validator.errors) == 0

        # Cleanup
        del os.environ['TEST_PORT']

    def test_get_summary(self):
        """Test getting validation summary"""
        validator = ConfigValidator()
        validator.errors = ['Error 1']
        validator.warnings = ['Warning 1', 'Warning 2']

        summary = validator.get_summary()

        assert summary['valid'] is False
        assert summary['error_count'] == 1
        assert summary['warning_count'] == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
