"""
Tests for Custom Rule Service
"""

import pytest
from src.services.custom_rule_service import CustomRuleService


class TestCustomRuleService:
    """Test CustomRuleService"""

    @pytest.fixture
    def service(self):
        """Create service instance"""
        return CustomRuleService()

    @pytest.fixture
    def sample_python_code(self):
        """Sample Python code for testing"""
        return """
import os
password = "hardcoded123"

def vulnerable_function(user_input):
    query = "SELECT * FROM users WHERE id = " + user_input
    os.system(user_input)
    return query
"""

    @pytest.fixture
    def regex_rule(self):
        """Sample regex rule"""
        return {
            'id': 'CUSTOM001',
            'name': 'Hardcoded Secrets',
            'description': 'Detects hardcoded passwords',
            'category': 'security',
            'severity': 'critical',
            'pattern_type': 'regex',
            'regex_pattern': {
                'pattern': r'password\s*=\s*["\'].+["\']',
                'flags': {
                    'case_insensitive': False,
                    'multiline': False,
                    'dotall': False
                }
            },
            'message': 'Hardcoded password detected: {matched_text}'
        }

    @pytest.fixture
    def ast_rule(self):
        """Sample AST rule"""
        return {
            'id': 'CUSTOM002',
            'name': 'Function Call Detection',
            'description': 'Detects os.system calls',
            'category': 'security',
            'severity': 'critical',
            'pattern_type': 'ast',
            'ast_patterns': [
                {
                    'nodeType': 'Call',
                    'attributes': {}
                }
            ],
            'message': 'Potentially unsafe function call detected'
        }

    def test_regex_pattern_matching(self, service, regex_rule, sample_python_code):
        """Test regex pattern matching"""
        matches = service.test_rule(
            rule=regex_rule,
            code=sample_python_code,
            language='python'
        )

        assert len(matches) > 0
        assert any('password' in match['code_snippet'].lower() for match in matches)
        assert all(match['severity'] == 'critical' for match in matches)

    def test_ast_pattern_matching(self, service, ast_rule, sample_python_code):
        """Test AST pattern matching"""
        matches = service.test_rule(
            rule=ast_rule,
            code=sample_python_code,
            language='python'
        )

        assert len(matches) > 0
        assert all(match['node_type'] == 'Call' for match in matches)

    def test_regex_with_flags(self, service, sample_python_code):
        """Test regex with case insensitive flag"""
        rule = {
            'id': 'CUSTOM003',
            'name': 'SQL Injection',
            'category': 'security',
            'severity': 'critical',
            'pattern_type': 'regex',
            'regex_pattern': {
                'pattern': r'SELECT.*FROM',
                'flags': {
                    'case_insensitive': True,
                    'multiline': False,
                    'dotall': False
                }
            },
            'message': 'Potential SQL injection'
        }

        matches = service.test_rule(rule, sample_python_code, 'python')
        assert len(matches) > 0

    def test_combined_pattern(self, service, sample_python_code):
        """Test combined regex and AST patterns"""
        rule = {
            'id': 'CUSTOM004',
            'name': 'Combined Rule',
            'category': 'security',
            'severity': 'warning',
            'pattern_type': 'both',
            'regex_pattern': {
                'pattern': r'password',
                'flags': {
                    'case_insensitive': True,
                    'multiline': False,
                    'dotall': False
                }
            },
            'ast_patterns': [
                {
                    'nodeType': 'Assign',
                    'attributes': {}
                }
            ],
            'message': 'Pattern matched'
        }

        matches = service.test_rule(rule, sample_python_code, 'python')
        assert len(matches) > 0

    def test_no_matches(self, service):
        """Test rule that doesn't match"""
        rule = {
            'id': 'CUSTOM005',
            'name': 'No Match Rule',
            'category': 'custom',
            'severity': 'info',
            'pattern_type': 'regex',
            'regex_pattern': {
                'pattern': r'NONEXISTENT_PATTERN_XYZ123',
                'flags': {}
            },
            'message': 'Pattern matched'
        }

        code = "print('hello world')"
        matches = service.test_rule(rule, code, 'python')
        assert len(matches) == 0

    def test_invalid_regex(self, service):
        """Test invalid regex pattern"""
        rule = {
            'id': 'CUSTOM006',
            'name': 'Invalid Regex',
            'category': 'custom',
            'severity': 'error',
            'pattern_type': 'regex',
            'regex_pattern': {
                'pattern': r'[invalid(regex',  # Invalid regex
                'flags': {}
            },
            'message': 'Pattern matched'
        }

        code = "test code"
        with pytest.raises(Exception) as exc_info:
            service.test_rule(rule, code, 'python')
        assert 'Invalid regex' in str(exc_info.value)

    def test_invalid_python_syntax(self, service, regex_rule):
        """Test with invalid Python syntax"""
        invalid_code = "def broken_function(\n  invalid syntax here"

        # Regex should still work even with invalid Python
        matches = service.test_rule(regex_rule, invalid_code, 'python')
        # Should not crash, just return empty or partial results

    def test_ast_with_invalid_syntax(self, service, ast_rule):
        """Test AST rule with invalid Python syntax"""
        invalid_code = "def broken_function(\n  invalid syntax here"

        with pytest.raises(Exception) as exc_info:
            service.test_rule(ast_rule, invalid_code, 'python')
        assert 'Invalid Python code' in str(exc_info.value)

    def test_multiline_regex(self, service):
        """Test multiline regex pattern"""
        rule = {
            'id': 'CUSTOM007',
            'name': 'Multiline Pattern',
            'category': 'custom',
            'severity': 'warning',
            'pattern_type': 'regex',
            'regex_pattern': {
                'pattern': r'def.*:',
                'flags': {
                    'multiline': True,
                    'dotall': True
                }
            },
            'message': 'Function definition found'
        }

        code = """
def test_function():
    pass

def another_function():
    pass
"""

        matches = service.test_rule(rule, code, 'python')
        assert len(matches) >= 2  # Should find both function definitions

    def test_ast_attribute_matching(self, service):
        """Test AST pattern with attribute matching"""
        rule = {
            'id': 'CUSTOM008',
            'name': 'Function Name Match',
            'category': 'custom',
            'severity': 'info',
            'pattern_type': 'ast',
            'ast_patterns': [
                {
                    'nodeType': 'FunctionDef',
                    'attributes': {
                        'name': 'vulnerable_function'
                    }
                }
            ],
            'message': 'Vulnerable function found'
        }

        code = """
def vulnerable_function():
    pass

def safe_function():
    pass
"""

        matches = service.test_rule(rule, code, 'python')
        assert len(matches) == 1
        assert matches[0]['node_type'] == 'FunctionDef'

    def test_unique_matches_by_line(self, service):
        """Test that duplicate matches on same line are filtered"""
        rule = {
            'id': 'CUSTOM009',
            'name': 'Duplicate Filter',
            'category': 'custom',
            'severity': 'info',
            'pattern_type': 'both',
            'regex_pattern': {
                'pattern': r'test',
                'flags': {'case_insensitive': True}
            },
            'ast_patterns': [
                {
                    'nodeType': 'Name',
                    'attributes': {}
                }
            ],
            'message': 'Pattern matched'
        }

        code = "test = test + test"  # Multiple matches on same line
        matches = service.test_rule(rule, code, 'python')

        # Should have matches but not duplicates on same line
        line_numbers = [m['line'] for m in matches]
        assert len(line_numbers) == len(set(line_numbers))  # All unique

    def test_message_formatting(self, service):
        """Test message formatting with placeholders"""
        rule = {
            'id': 'CUSTOM010',
            'name': 'Message Format',
            'category': 'custom',
            'severity': 'info',
            'pattern_type': 'regex',
            'regex_pattern': {
                'pattern': r'password',
                'flags': {}
            },
            'message': 'Found: {matched_text}'
        }

        code = "password = 'test'"
        matches = service.test_rule(rule, code, 'python')

        assert len(matches) > 0
        assert 'password' in matches[0]['message']


class TestCustomRuleAttributes:
    """Test AST attribute matching logic"""

    def test_evaluate_condition_greater_than(self):
        """Test > condition"""
        service = CustomRuleService()
        assert service._evaluate_condition(5, '>0') == True
        assert service._evaluate_condition(0, '>0') == False
        assert service._evaluate_condition(5, '>10') == False

    def test_evaluate_condition_less_than(self):
        """Test < condition"""
        service = CustomRuleService()
        assert service._evaluate_condition(5, '<10') == True
        assert service._evaluate_condition(10, '<10') == False

    def test_evaluate_condition_equals(self):
        """Test == condition"""
        service = CustomRuleService()
        assert service._evaluate_condition(5, '==5') == True
        assert service._evaluate_condition(5, '==10') == False

    def test_evaluate_condition_not_equals(self):
        """Test != condition"""
        service = CustomRuleService()
        assert service._evaluate_condition(5, '!=10') == True
        assert service._evaluate_condition(5, '!=5') == False
