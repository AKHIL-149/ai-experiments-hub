"""Tests for Logging Service"""
import pytest
from datetime import datetime
from src.services.logging_service import (
    LoggingService,
    LogLevel,
    logging_service
)


@pytest.fixture
def service():
    """Create fresh logging service"""
    svc = LoggingService()
    svc.clear_logs()
    svc.clear_errors()
    return svc


def test_create_debug_log(service):
    """Test creating a debug log entry"""
    log = service.debug("This is a debug message")

    assert log is not None
    assert log['level'] == 'DEBUG'
    assert log['message'] == "This is a debug message"
    assert 'timestamp' in log
    assert log['service'] == service.service_name


def test_create_info_log(service):
    """Test creating an info log entry"""
    log = service.info("This is an info message", metadata={'user_id': '123'})

    assert log['level'] == 'INFO'
    assert log['message'] == "This is an info message"
    assert log['metadata']['user_id'] == '123'


def test_create_warning_log(service):
    """Test creating a warning log entry"""
    log = service.warning("This is a warning")

    assert log['level'] == 'WARNING'
    assert log['message'] == "This is a warning"


def test_create_error_log(service):
    """Test creating an error log entry"""
    log = service.error("This is an error")

    assert log['level'] == 'ERROR'
    assert log['message'] == "This is an error"


def test_create_critical_log(service):
    """Test creating a critical log entry"""
    log = service.critical("This is critical")

    assert log['level'] == 'CRITICAL'
    assert log['message'] == "This is critical"


def test_log_with_metadata(service):
    """Test logging with metadata"""
    metadata = {
        'user_id': '123',
        'action': 'file_upload',
        'file_size': 1024
    }

    log = service.info("File uploaded", metadata=metadata)

    assert log['metadata'] == metadata


def test_log_with_exception(service):
    """Test logging with exception information"""
    try:
        raise ValueError("Test exception")
    except ValueError as e:
        log = service.error("An error occurred", exception=e)

    assert 'exception' in log
    assert log['exception']['type'] == 'ValueError'
    assert log['exception']['message'] == "Test exception"
    assert 'traceback' in log['exception']


def test_correlation_id_generation(service):
    """Test correlation ID generation"""
    corr_id = service.generate_correlation_id()

    assert corr_id is not None
    assert isinstance(corr_id, str)
    assert len(corr_id) > 0


def test_correlation_id_context(service):
    """Test correlation ID context manager"""
    with service.correlation_context() as corr_id:
        assert service.get_correlation_id() == corr_id

        log = service.info("Test message")
        assert log['correlation_id'] == corr_id

    # Should be reset after context
    assert service.get_correlation_id() is None


def test_correlation_id_custom(service):
    """Test setting custom correlation ID"""
    custom_id = "custom-correlation-123"

    with service.correlation_context(custom_id):
        assert service.get_correlation_id() == custom_id

        log = service.info("Test message")
        assert log['correlation_id'] == custom_id


def test_mask_api_key(service):
    """Test masking API keys"""
    text = 'api_key="sk-abc123xyz" and more text'
    masked = service.mask_sensitive_data(text)

    assert 'sk-abc123xyz' not in masked
    assert '***MASKED***' in masked


def test_mask_token(service):
    """Test masking tokens"""
    text = 'token: "ghp_1234567890abcdef"'
    masked = service.mask_sensitive_data(text)

    assert 'ghp_1234567890abcdef' not in masked
    assert '***MASKED***' in masked


def test_mask_password(service):
    """Test masking passwords"""
    text = 'password="secret123"'
    masked = service.mask_sensitive_data(text)

    assert 'secret123' not in masked
    assert '***MASKED***' in masked


def test_mask_email(service):
    """Test masking email addresses"""
    text = 'user@example.com sent a message'
    masked = service.mask_sensitive_data(text)

    assert 'user@example.com' not in masked
    assert '@example.com' in masked  # Domain is preserved


def test_mask_dict_sensitive_data(service):
    """Test masking sensitive data in dictionaries"""
    data = {
        'username': 'john',
        'password': 'secret123',
        'api_key': 'sk-abc123',
        'email': 'john@example.com'
    }

    masked = service.mask_dict_sensitive_data(data)

    assert masked['username'] == 'john'
    assert masked['password'] == '***MASKED***'
    assert masked['api_key'] == '***MASKED***'
    assert '@example.com' in masked['email']


def test_mask_nested_dict(service):
    """Test masking sensitive data in nested dictionaries"""
    data = {
        'user': {
            'name': 'John',
            'credentials': {
                'password': 'secret',
                'token': 'abc123'
            }
        }
    }

    masked = service.mask_dict_sensitive_data(data)

    assert masked['user']['name'] == 'John'
    assert masked['user']['credentials']['password'] == '***MASKED***'
    assert masked['user']['credentials']['token'] == '***MASKED***'


def test_automatic_sensitive_masking(service):
    """Test that sensitive data is automatically masked in logs"""
    log = service.info("User logged in with password=secret123")

    assert 'secret123' not in log['message']
    assert '***MASKED***' in log['message']


def test_disable_sensitive_masking(service):
    """Test disabling sensitive data masking"""
    log = service.info("password=test", mask_sensitive=False)

    # Should not be masked when disabled
    assert 'password=test' in log['message']


def test_error_tracking(service):
    """Test that errors are tracked separately"""
    service.error("Error 1")
    service.error("Error 2")
    service.info("Info message")

    errors = service.get_errors()

    assert len(errors) >= 2
    assert all(log['level'] == 'ERROR' for log in errors)


def test_get_logs_with_filters(service):
    """Test retrieving logs with filters"""
    service.info("Info 1")
    service.error("Error 1")
    service.warning("Warning 1")
    service.info("Info 2")

    # Filter by level
    info_logs = service.get_logs(level=LogLevel.INFO)
    assert len(info_logs) >= 2
    assert all(log['level'] == 'INFO' for log in info_logs)

    # Filter by correlation ID
    with service.correlation_context("test-123"):
        service.info("Correlated message")

    correlated_logs = service.get_logs(correlation_id="test-123")
    assert len(correlated_logs) >= 1
    assert all(log['correlation_id'] == "test-123" for log in correlated_logs)


def test_get_logs_pagination(service):
    """Test log retrieval with pagination"""
    for i in range(10):
        service.info(f"Message {i}")

    # Get first 5
    logs = service.get_logs(limit=5, offset=0)
    assert len(logs) <= 5

    # Get next 5
    logs = service.get_logs(limit=5, offset=5)
    assert len(logs) <= 5


def test_get_statistics(service):
    """Test getting logging statistics"""
    service.debug("Debug")
    service.info("Info")
    service.info("Info 2")
    service.warning("Warning")
    service.error("Error")

    stats = service.get_statistics()

    assert stats['total_logs'] >= 5
    assert stats['level_counts']['DEBUG'] >= 1
    assert stats['level_counts']['INFO'] >= 2
    assert stats['level_counts']['WARNING'] >= 1
    assert stats['level_counts']['ERROR'] >= 1


def test_clear_logs(service):
    """Test clearing logs"""
    service.info("Message 1")
    service.info("Message 2")

    count = service.clear_logs()

    assert count >= 2
    assert len(service.logs) == 0


def test_clear_errors(service):
    """Test clearing error log"""
    service.error("Error 1")
    service.error("Error 2")

    count = service.clear_errors()

    assert count >= 2
    assert len(service.errors) == 0
    assert service.error_count == 0


def test_export_logs_json(service):
    """Test exporting logs to JSON"""
    service.info("Test message 1")
    service.error("Test error")

    exported = service.export_logs(format='json')

    assert isinstance(exported, str)
    assert 'Test message 1' in exported
    assert 'Test error' in exported

    # Should be valid JSON
    import json
    data = json.loads(exported)
    assert 'logs' in data
    assert 'service' in data


def test_export_logs_csv(service):
    """Test exporting logs to CSV"""
    service.info("Test message")
    service.error("Test error")

    exported = service.export_logs(format='csv')

    assert isinstance(exported, str)
    assert 'timestamp' in exported
    assert 'level' in exported
    assert 'Test message' in exported


def test_max_logs_limit(service):
    """Test that logs are trimmed when exceeding max"""
    service.max_logs = 10

    # Add more than max
    for i in range(20):
        service.info(f"Message {i}")

    # Should be trimmed to max
    assert len(service.logs) == 10


def test_global_logging_service_instance():
    """Test that global instance exists and is usable"""
    assert logging_service is not None
    assert isinstance(logging_service, LoggingService)

    # Can create logs
    log = logging_service.info("Global test")
    assert log is not None


def test_log_levels_enum():
    """Test LogLevel enum values"""
    assert LogLevel.DEBUG.value == "DEBUG"
    assert LogLevel.INFO.value == "INFO"
    assert LogLevel.WARNING.value == "WARNING"
    assert LogLevel.ERROR.value == "ERROR"
    assert LogLevel.CRITICAL.value == "CRITICAL"
