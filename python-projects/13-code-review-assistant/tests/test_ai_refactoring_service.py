"""
Tests for AI Refactoring Service
Tests multi-step refactoring, automated fixes, technical debt estimation, and code smell prediction
"""

import pytest
from unittest.mock import Mock, patch
from src.services.ai_refactoring_service import (
    AIRefactoringService,
    RefactoringChain,
    RefactoringType
)


class TestAIRefactoringService:
    """Test suite for AI refactoring service"""

    @pytest.fixture
    def service(self):
        """Create AI refactoring service instance"""
        with patch('src.services.ai_refactoring_service.LLMClient'):
            with patch('src.services.ai_refactoring_service.DatabaseManager'):
                return AIRefactoringService()

    @pytest.fixture
    def sample_code(self):
        """Sample code with issues"""
        return '''
def long_function(a, b, c, d, e, f):
    """A function with too many parameters"""
    password = "hardcoded123"  # Security issue
    if a > 0:
        if b > 0:
            if c > 0:
                if d > 0:  # Deep nesting
                    return a + b + c + d + e + f
    return 0
'''

    @pytest.fixture
    def sample_issues(self):
        """Sample issues to fix"""
        return [
            {
                'severity': 'critical',
                'category': 'security',
                'title': 'Hardcoded password',
                'line_number': 4
            },
            {
                'severity': 'warning',
                'category': 'smell',
                'title': 'Too many parameters',
                'line_number': 2
            },
            {
                'severity': 'warning',
                'category': 'complexity',
                'title': 'Deep nesting',
                'line_number': 5
            }
        ]

    def test_generate_multi_step_refactoring(self, service, sample_code, sample_issues):
        """Test multi-step refactoring chain generation"""
        # Mock LLM response
        mock_response = '''
{
    "steps": [
        {
            "step_number": 1,
            "type": "security_fix",
            "description": "Remove hardcoded password",
            "code_after": "def long_function(a, b, c, d, e, f, password):\\n    pass",
            "issues_addressed": ["Hardcoded password"],
            "confidence": 0.95
        },
        {
            "step_number": 2,
            "type": "simplify",
            "description": "Reduce parameters",
            "code_after": "def improved_function(params):\\n    pass",
            "issues_addressed": ["Too many parameters"],
            "confidence": 0.85
        }
    ],
    "overall_confidence": 0.9,
    "estimated_time": "15 minutes",
    "explanation": "Two-step refactoring to address security and code smell issues"
}
'''
        service.llm.complete = Mock(return_value=mock_response)

        # Generate refactoring
        chain = service.generate_multi_step_refactoring(
            code=sample_code,
            language='python',
            issues=sample_issues,
            max_steps=5
        )

        # Assertions
        assert isinstance(chain, RefactoringChain)
        assert len(chain.steps) == 2
        assert chain.confidence == 0.9
        assert chain.estimated_time == "15 minutes"
        assert "Two-step" in chain.explanation
        assert chain.original_code == sample_code

    def test_generate_multi_step_refactoring_json_error(self, service, sample_code, sample_issues):
        """Test fallback when JSON parsing fails"""
        # Mock invalid JSON response
        service.llm.complete = Mock(return_value="Invalid JSON")

        # Should fallback to simple refactoring
        chain = service.generate_multi_step_refactoring(
            code=sample_code,
            language='python',
            issues=sample_issues
        )

        # Assertions
        assert isinstance(chain, RefactoringChain)
        assert len(chain.steps) == 1
        assert chain.steps[0]['type'] == 'simplify'

    def test_apply_automated_fix(self, service):
        """Test automated fix application"""
        # Mock database
        mock_db = Mock()
        mock_issue = Mock()
        mock_issue.id = "issue_123"
        mock_issue.title = "SQL Injection"
        mock_issue.description = "Unsafe SQL query"
        mock_issue.severity = "critical"
        mock_issue.category = "security"
        mock_issue.code_snippet = "query = 'SELECT * FROM users WHERE id = ' + user_input"

        mock_db.query().filter().first.return_value = mock_issue
        service.db_manager.get_session().__enter__ = Mock(return_value=mock_db)
        service.db_manager.get_session().__exit__ = Mock(return_value=None)

        # Mock LLM response
        mock_response = '''
{
    "fixed_code": "query = 'SELECT * FROM users WHERE id = ?'\\nparams = (user_input,)",
    "explanation": "Use parameterized queries to prevent SQL injection",
    "test_code": "def test_query():\\n    assert '?' in query",
    "confidence": 0.95
}
'''
        service.llm.complete = Mock(return_value=mock_response)

        # Apply fix
        result = service.apply_automated_fix(
            issue_id="issue_123",
            generate_test=True
        )

        # Assertions
        assert result['success'] is True
        assert 'fixed_code' in result
        assert 'explanation' in result
        assert 'test_code' in result
        assert result['confidence'] == 0.95
        assert 'parameterized' in result['explanation']

    def test_apply_automated_fix_no_test(self, service):
        """Test automated fix without test generation"""
        # Mock database
        mock_db = Mock()
        mock_issue = Mock()
        mock_issue.id = "issue_123"
        mock_issue.title = "Long method"
        mock_issue.description = "Method too long"
        mock_issue.severity = "warning"
        mock_issue.category = "smell"
        mock_issue.code_snippet = "def long_method():\n    pass"

        mock_db.query().filter().first.return_value = mock_issue
        service.db_manager.get_session().__enter__ = Mock(return_value=mock_db)
        service.db_manager.get_session().__exit__ = Mock(return_value=None)

        # Mock LLM response
        mock_response = '''
{
    "fixed_code": "def short_method():\\n    pass",
    "explanation": "Extracted helper methods",
    "confidence": 0.85
}
'''
        service.llm.complete = Mock(return_value=mock_response)

        # Apply fix without test
        result = service.apply_automated_fix(
            issue_id="issue_123",
            generate_test=False
        )

        # Assertions
        assert result['success'] is True
        assert result['test_code'] is None

    def test_apply_automated_fix_issue_not_found(self, service):
        """Test fix application when issue doesn't exist"""
        # Mock database
        mock_db = Mock()
        mock_db.query().filter().first.return_value = None
        service.db_manager.get_session().__enter__ = Mock(return_value=mock_db)
        service.db_manager.get_session().__exit__ = Mock(return_value=None)

        # Apply fix
        result = service.apply_automated_fix(issue_id="nonexistent")

        # Assertions
        assert result['success'] is False
        assert 'error' in result
        assert result['error'] == 'Issue not found'

    def test_estimate_technical_debt(self, service):
        """Test technical debt estimation"""
        code_files = [
            {'file_path': 'app.py', 'lines_of_code': 1000, 'language': 'python'},
            {'file_path': 'utils.py', 'lines_of_code': 500, 'language': 'python'}
        ]

        issues = [
            {'severity': 'critical', 'category': 'security', 'title': 'SQL Injection'},
            {'severity': 'critical', 'category': 'security', 'title': 'XSS'},
            {'severity': 'error', 'category': 'smell', 'title': 'Long method'},
            {'severity': 'error', 'category': 'smell', 'title': 'God class'},
            {'severity': 'warning', 'category': 'complexity', 'title': 'High complexity'},
            {'severity': 'info', 'category': 'style', 'title': 'Missing docstring'}
        ]

        # Estimate debt
        estimation = service.estimate_technical_debt(code_files, issues)

        # Assertions
        assert estimation['total_files'] == 2
        assert estimation['total_loc'] == 1500
        assert estimation['total_issues'] == 6
        assert estimation['severity_counts']['critical'] == 2
        assert estimation['severity_counts']['error'] == 2
        assert estimation['severity_counts']['warning'] == 1
        assert estimation['severity_counts']['info'] == 1

        # Check time estimates (2*4 + 2*2 + 1*1 + 1*0.5 = 13.5 hours)
        assert estimation['estimated_hours'] == 13.5
        assert estimation['estimated_days'] == 1.7  # 13.5 / 8
        assert estimation['estimated_cost'] == 1350.0  # 13.5 * 100

        # Check debt ratio (6 issues / 1500 LOC * 1000 = 4.0)
        assert estimation['debt_ratio'] == 4.0
        assert estimation['debt_level'] == 'low'  # < 5
        assert estimation['debt_color'] == 'green'

        # Check recommendations
        assert len(estimation['recommendations']) > 0
        assert any('critical' in str(r).lower() for r in estimation['recommendations'])

    def test_estimate_technical_debt_high(self, service):
        """Test high technical debt estimation"""
        code_files = [{'file_path': 'app.py', 'lines_of_code': 100, 'language': 'python'}]

        # Create 30 issues (30/100*1000 = 300 debt ratio)
        issues = [
            {'severity': 'critical', 'category': 'security', 'title': f'Issue {i}'}
            for i in range(30)
        ]

        estimation = service.estimate_technical_debt(code_files, issues)

        # Assertions
        assert estimation['debt_ratio'] == 300.0
        assert estimation['debt_level'] == 'critical'  # > 30
        assert estimation['debt_color'] == 'red'

    def test_ai_pair_programming(self, service):
        """Test AI pair programming mode"""
        # Mock LLM response
        mock_response = '''
{
    "code": "def calculate_total(items):\\n    return sum(item.price for item in items)",
    "explanation": "Use sum() with generator expression for cleaner code",
    "warnings": ["Ensure items have price attribute"],
    "alternatives": ["Use reduce()", "Use list comprehension"],
    "confidence": 0.9
}
'''
        service.llm.complete = Mock(return_value=mock_response)

        # Request assistance
        result = service.ai_pair_programming(
            prompt="How do I calculate total price of items?",
            context={
                'current_file': 'shopping_cart.py',
                'issues': []
            },
            language='python'
        )

        # Assertions
        assert result['success'] is True
        assert 'code' in result
        assert 'explanation' in result
        assert 'warnings' in result
        assert 'alternatives' in result
        assert result['confidence'] == 0.9
        assert 'sum()' in result['code']

    def test_ai_pair_programming_no_context(self, service):
        """Test AI pair programming without context"""
        # Mock LLM response
        mock_response = '''
{
    "code": "print('Hello, World!')",
    "explanation": "Simple print statement",
    "warnings": [],
    "alternatives": [],
    "confidence": 1.0
}
'''
        service.llm.complete = Mock(return_value=mock_response)

        # Request assistance
        result = service.ai_pair_programming(
            prompt="Show me hello world",
            context=None,
            language='python'
        )

        # Assertions
        assert result['success'] is True

    def test_ai_pair_programming_json_error(self, service):
        """Test AI pair programming with JSON parsing error"""
        service.llm.complete = Mock(return_value="Invalid JSON response")

        result = service.ai_pair_programming(prompt="Help me")

        # Assertions
        assert result['success'] is False
        assert 'raw_response' in result

    def test_predict_code_smells(self, service):
        """Test code smell prediction"""
        # Mock LLM response
        mock_response = '''
[
    {
        "smell_type": "long_method",
        "location": "line 10-50",
        "description": "Method is too long and does too many things",
        "severity": "warning",
        "confidence": 0.9,
        "refactoring_suggestion": "Extract smaller methods"
    },
    {
        "smell_type": "god_class",
        "location": "line 1-200",
        "description": "Class has too many responsibilities",
        "severity": "error",
        "confidence": 0.85,
        "refactoring_suggestion": "Split into multiple classes"
    }
]
'''
        service.llm.complete = Mock(return_value=mock_response)

        # Predict smells
        smells = service.predict_code_smells(
            code="class LargeClass:\n    pass",
            language='python'
        )

        # Assertions
        assert isinstance(smells, list)
        assert len(smells) == 2
        assert smells[0]['smell_type'] == 'long_method'
        assert smells[1]['smell_type'] == 'god_class'
        assert all('confidence' in smell for smell in smells)
        assert all('refactoring_suggestion' in smell for smell in smells)

    def test_predict_code_smells_json_error(self, service):
        """Test code smell prediction with JSON error"""
        service.llm.complete = Mock(return_value="Not valid JSON")

        smells = service.predict_code_smells(code="pass", language='python')

        # Should return empty list on error
        assert smells == []

    def test_get_severity_priority(self, service):
        """Test severity priority mapping"""
        assert service._get_severity_priority('critical') == 4
        assert service._get_severity_priority('error') == 3
        assert service._get_severity_priority('warning') == 2
        assert service._get_severity_priority('info') == 1
        assert service._get_severity_priority('unknown') == 0

    def test_group_related_issues(self, service):
        """Test issue grouping by category"""
        issues = [
            {'category': 'security', 'title': 'SQL Injection'},
            {'category': 'security', 'title': 'XSS'},
            {'category': 'smell', 'title': 'Long method'},
            {'category': 'complexity', 'title': 'High complexity'}
        ]

        groups = service._group_related_issues(issues)

        # Assertions
        assert len(groups) == 3
        # Check that security issues are grouped
        security_group = next(g for g in groups if len(g) == 2)
        assert all(i['category'] == 'security' for i in security_group)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
