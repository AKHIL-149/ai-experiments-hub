"""
Unit tests for input validators
"""

import pytest
from src.core.validators import Validators
from src.core.exceptions import InvalidInputError
from src.models import TaskStatus, AgentRole, AgentStatus


class TestValidateRequired:
    """Tests for validate_required method"""

    def test_valid_string(self):
        """Test with valid non-empty string"""
        result = Validators.validate_required("test value", "field")
        assert result == "test value"

    def test_valid_integer(self):
        """Test with valid integer"""
        result = Validators.validate_required(42, "field")
        assert result == 42

    def test_none_value_raises_error(self):
        """Test that None raises InvalidInputError"""
        with pytest.raises(InvalidInputError) as exc_info:
            Validators.validate_required(None, "field")
        assert "Field is required" in str(exc_info.value)

    def test_empty_string_raises_error(self):
        """Test that empty string raises InvalidInputError"""
        with pytest.raises(InvalidInputError) as exc_info:
            Validators.validate_required("   ", "field")
        assert "Field cannot be empty" in str(exc_info.value)


class TestValidateString:
    """Tests for validate_string method"""

    def test_valid_string(self):
        """Test with valid string"""
        result = Validators.validate_string("test", "field")
        assert result == "test"

    def test_string_with_whitespace_stripped(self):
        """Test that whitespace is stripped"""
        result = Validators.validate_string("  test  ", "field")
        assert result == "test"

    def test_non_string_raises_error(self):
        """Test that non-string raises InvalidInputError"""
        with pytest.raises(InvalidInputError) as exc_info:
            Validators.validate_string(123, "field")
        assert "Must be a string" in str(exc_info.value)

    def test_min_length_validation(self):
        """Test minimum length validation"""
        with pytest.raises(InvalidInputError) as exc_info:
            Validators.validate_string("ab", "field", min_length=3)
        assert "at least 3 characters" in str(exc_info.value)

    def test_max_length_validation(self):
        """Test maximum length validation"""
        with pytest.raises(InvalidInputError) as exc_info:
            Validators.validate_string("abcdef", "field", max_length=5)
        assert "at most 5 characters" in str(exc_info.value)

    def test_pattern_validation_success(self):
        """Test regex pattern validation success"""
        result = Validators.validate_string(
            "test123",
            "field",
            pattern=r"^[a-z0-9]+$"
        )
        assert result == "test123"

    def test_pattern_validation_failure(self):
        """Test regex pattern validation failure"""
        with pytest.raises(InvalidInputError) as exc_info:
            Validators.validate_string(
                "test-123",
                "field",
                pattern=r"^[a-z0-9]+$"
            )
        assert "Must match pattern" in str(exc_info.value)


class TestValidateInteger:
    """Tests for validate_integer method"""

    def test_valid_integer(self):
        """Test with valid integer"""
        result = Validators.validate_integer(42, "field")
        assert result == 42

    def test_non_integer_raises_error(self):
        """Test that non-integer raises InvalidInputError"""
        with pytest.raises(InvalidInputError) as exc_info:
            Validators.validate_integer("42", "field")
        assert "Must be an integer" in str(exc_info.value)

    def test_boolean_raises_error(self):
        """Test that boolean raises InvalidInputError"""
        with pytest.raises(InvalidInputError) as exc_info:
            Validators.validate_integer(True, "field")
        assert "Must be an integer" in str(exc_info.value)

    def test_min_value_validation(self):
        """Test minimum value validation"""
        with pytest.raises(InvalidInputError) as exc_info:
            Validators.validate_integer(5, "field", min_value=10)
        assert "at least 10" in str(exc_info.value)

    def test_max_value_validation(self):
        """Test maximum value validation"""
        with pytest.raises(InvalidInputError) as exc_info:
            Validators.validate_integer(15, "field", max_value=10)
        assert "at most 10" in str(exc_info.value)


class TestValidateFloat:
    """Tests for validate_float method"""

    def test_valid_float(self):
        """Test with valid float"""
        result = Validators.validate_float(3.14, "field")
        assert result == 3.14

    def test_integer_converted_to_float(self):
        """Test that integer is converted to float"""
        result = Validators.validate_float(42, "field")
        assert result == 42.0
        assert isinstance(result, float)

    def test_non_numeric_raises_error(self):
        """Test that non-numeric raises InvalidInputError"""
        with pytest.raises(InvalidInputError) as exc_info:
            Validators.validate_float("3.14", "field")
        assert "Must be a number" in str(exc_info.value)

    def test_boolean_raises_error(self):
        """Test that boolean raises InvalidInputError"""
        with pytest.raises(InvalidInputError) as exc_info:
            Validators.validate_float(True, "field")
        assert "Must be a number" in str(exc_info.value)

    def test_min_value_validation(self):
        """Test minimum value validation"""
        with pytest.raises(InvalidInputError) as exc_info:
            Validators.validate_float(0.5, "field", min_value=1.0)
        assert "at least 1.0" in str(exc_info.value)

    def test_max_value_validation(self):
        """Test maximum value validation"""
        with pytest.raises(InvalidInputError) as exc_info:
            Validators.validate_float(2.5, "field", max_value=2.0)
        assert "at most 2.0" in str(exc_info.value)


class TestValidateEnum:
    """Tests for validate_enum method"""

    def test_valid_task_status(self):
        """Test with valid TaskStatus enum"""
        result = Validators.validate_enum("pending", TaskStatus, "status")
        assert result == TaskStatus.PENDING

    def test_valid_agent_role(self):
        """Test with valid AgentRole enum"""
        result = Validators.validate_enum("coder", AgentRole, "role")
        assert result == AgentRole.CODER

    def test_invalid_enum_value(self):
        """Test with invalid enum value"""
        with pytest.raises(InvalidInputError) as exc_info:
            Validators.validate_enum("invalid", TaskStatus, "status")
        assert "Must be one of" in str(exc_info.value)


class TestValidateList:
    """Tests for validate_list method"""

    def test_valid_list(self):
        """Test with valid list"""
        result = Validators.validate_list([1, 2, 3], "field")
        assert result == [1, 2, 3]

    def test_non_list_raises_error(self):
        """Test that non-list raises InvalidInputError"""
        with pytest.raises(InvalidInputError) as exc_info:
            Validators.validate_list("not a list", "field")
        assert "Must be a list" in str(exc_info.value)

    def test_min_length_validation(self):
        """Test minimum length validation"""
        with pytest.raises(InvalidInputError) as exc_info:
            Validators.validate_list([1, 2], "field", min_length=3)
        assert "at least 3 items" in str(exc_info.value)

    def test_max_length_validation(self):
        """Test maximum length validation"""
        with pytest.raises(InvalidInputError) as exc_info:
            Validators.validate_list([1, 2, 3], "field", max_length=2)
        assert "at most 2 items" in str(exc_info.value)


class TestValidateDict:
    """Tests for validate_dict method"""

    def test_valid_dict(self):
        """Test with valid dictionary"""
        result = Validators.validate_dict({"key": "value"}, "field")
        assert result == {"key": "value"}

    def test_non_dict_raises_error(self):
        """Test that non-dict raises InvalidInputError"""
        with pytest.raises(InvalidInputError) as exc_info:
            Validators.validate_dict("not a dict", "field")
        assert "Must be a dictionary" in str(exc_info.value)

    def test_required_keys_validation_success(self):
        """Test required keys validation success"""
        result = Validators.validate_dict(
            {"key1": "value1", "key2": "value2"},
            "field",
            required_keys=["key1", "key2"]
        )
        assert "key1" in result
        assert "key2" in result

    def test_required_keys_validation_failure(self):
        """Test required keys validation failure"""
        with pytest.raises(InvalidInputError) as exc_info:
            Validators.validate_dict(
                {"key1": "value1"},
                "field",
                required_keys=["key1", "key2"]
            )
        assert "Missing required keys: key2" in str(exc_info.value)


class TestDomainSpecificValidators:
    """Tests for domain-specific validators"""

    def test_validate_priority_valid(self):
        """Test priority validation with valid value"""
        result = Validators.validate_priority(5)
        assert result == 5

    def test_validate_priority_too_low(self):
        """Test priority validation with value too low"""
        with pytest.raises(InvalidInputError):
            Validators.validate_priority(0)

    def test_validate_priority_too_high(self):
        """Test priority validation with value too high"""
        with pytest.raises(InvalidInputError):
            Validators.validate_priority(11)

    def test_validate_temperature_valid(self):
        """Test temperature validation with valid value"""
        result = Validators.validate_temperature(0.7)
        assert result == 0.7

    def test_validate_temperature_too_low(self):
        """Test temperature validation with value too low"""
        with pytest.raises(InvalidInputError):
            Validators.validate_temperature(-0.1)

    def test_validate_temperature_too_high(self):
        """Test temperature validation with value too high"""
        with pytest.raises(InvalidInputError):
            Validators.validate_temperature(2.5)

    def test_validate_max_tokens_valid(self):
        """Test max tokens validation with valid value"""
        result = Validators.validate_max_tokens(2048)
        assert result == 2048

    def test_validate_max_tokens_too_low(self):
        """Test max tokens validation with value too low"""
        with pytest.raises(InvalidInputError):
            Validators.validate_max_tokens(0)

    def test_validate_max_tokens_too_high(self):
        """Test max tokens validation with value too high"""
        with pytest.raises(InvalidInputError):
            Validators.validate_max_tokens(200000)
