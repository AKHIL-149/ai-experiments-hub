"""Tests for AI Analysis Service"""
import pytest
from unittest.mock import Mock, patch
from src.services.ai_analysis_service import AIAnalysisService


@pytest.fixture
def ai_service():
    """Create AI analysis service with mocked LLM"""
    with patch('src.services.ai_analysis_service.LLMClient') as MockLLM:
        mock_client = Mock()
        mock_client.test_connection.return_value = True
        mock_client.get_info.return_value = {
            "backend": "ollama",
            "model": "llama3.2",
            "max_retries": 3
        }
        MockLLM.return_value = mock_client

        service = AIAnalysisService()
        service.llm_client = mock_client
        return service


@pytest.fixture
def sample_issue():
    """Sample code issue"""
    return {
        "severity": "critical",
        "category": "security",
        "title": "SQL Injection Risk",
        "description": "Avoid string concatenation in SQL queries",
        "line_number": 10
    }


@pytest.fixture
def sample_code_snippet():
    """Sample vulnerable code"""
    return '''def get_user(user_id):
    query = "SELECT * FROM users WHERE id = " + user_id
    cursor.execute(query)
    return cursor.fetchone()'''


def test_ai_service_initialization():
    """Test AI service initialization"""
    with patch('src.services.ai_analysis_service.LLMClient'):
        service = AIAnalysisService(llm_backend="ollama", model="custom-model")
        assert service is not None


def test_enhance_issue_with_ai_success(ai_service, sample_issue, sample_code_snippet):
    """Test successful AI enhancement of issue"""
    # Mock LLM response
    ai_service.llm_client.generate_from_template.return_value = (
        "This is a SQL injection vulnerability. String concatenation allows "
        "attackers to inject malicious SQL code. Use parameterized queries instead."
    )

    enhanced = ai_service.enhance_issue_with_ai(
        sample_issue,
        sample_code_snippet,
        language="python"
    )

    assert enhanced["has_ai_explanation"] is True
    assert "ai_explanation" in enhanced
    assert "SQL injection" in enhanced["ai_explanation"]
    assert ai_service.llm_client.generate_from_template.called


def test_enhance_issue_with_ai_failure(ai_service, sample_issue, sample_code_snippet):
    """Test AI enhancement failure handling"""
    # Mock LLM to raise exception
    ai_service.llm_client.generate_from_template.side_effect = Exception("LLM error")

    enhanced = ai_service.enhance_issue_with_ai(
        sample_issue,
        sample_code_snippet
    )

    assert enhanced["has_ai_explanation"] is False
    assert "ai_error" in enhanced
    assert enhanced["ai_error"] == "LLM error"


def test_suggest_fix_success(ai_service, sample_issue, sample_code_snippet):
    """Test successful fix suggestion"""
    ai_service.llm_client.generate_from_template.return_value = '''
Use parameterized queries instead:

```python
def get_user(user_id):
    query = "SELECT * FROM users WHERE id = ?"
    cursor.execute(query, (user_id,))
    return cursor.fetchone()
```

This prevents SQL injection by properly escaping user input.
'''

    fix_info = ai_service.suggest_fix(
        sample_issue,
        sample_code_snippet
    )

    assert fix_info["suggested_fix"] is not None
    assert "confidence_score" in fix_info
    assert 0.0 <= fix_info["confidence_score"] <= 1.0
    assert isinstance(fix_info["can_auto_apply"], bool)


def test_suggest_fix_failure(ai_service, sample_issue, sample_code_snippet):
    """Test fix suggestion failure handling"""
    ai_service.llm_client.generate_from_template.side_effect = Exception("LLM error")

    fix_info = ai_service.suggest_fix(sample_issue, sample_code_snippet)

    assert fix_info["suggested_fix"] is None
    assert fix_info["confidence_score"] == 0.0
    assert fix_info["can_auto_apply"] is False
    assert "error" in fix_info


def test_suggest_refactoring_success(ai_service):
    """Test refactoring suggestion"""
    long_method = '''def process_data(data):
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
    return result'''

    ai_service.llm_client.generate_from_template.return_value = '''
Here's a refactored version using list comprehension:

```python
def process_data(data):
    return [item * 2 for item in data if item > 0]
```

This is more Pythonic and concise.
'''

    refactoring = ai_service.suggest_refactoring(
        long_method,
        issue_type="complexity"
    )

    assert "refactoring_suggestion" in refactoring
    assert "confidence_score" in refactoring
    assert 0.0 <= refactoring["confidence_score"] <= 1.0


def test_enhance_analysis_results(ai_service):
    """Test enhancing full analysis results"""
    analysis_results = {
        "total_files": 1,
        "total_issues": 2,
        "files": [
            {
                "file_path": "app.py",
                "issues": [
                    {
                        "severity": "error",
                        "category": "security",
                        "title": "Issue 1",
                        "description": "Description 1",
                        "line_number": 5
                    },
                    {
                        "severity": "warning",
                        "category": "style",
                        "title": "Issue 2",
                        "description": "Description 2",
                        "line_number": 10
                    }
                ]
            }
        ]
    }

    code_context = {
        "app.py": "def foo():\n    pass\n# ... more code"
    }

    ai_service.llm_client.generate_from_template.return_value = "AI explanation"

    enhanced = ai_service.enhance_analysis_results(
        analysis_results,
        code_context=code_context
    )

    assert enhanced["ai_enhanced"] is True
    assert "ai_issues_count" in enhanced
    assert len(enhanced["files"][0]["issues"]) == 2


def test_enhance_analysis_results_with_fixes(ai_service):
    """Test enhancing with fix suggestions enabled"""
    analysis_results = {
        "files": [
            {
                "file_path": "app.py",
                "issues": [
                    {
                        "severity": "error",
                        "title": "Issue",
                        "line_number": 5
                    }
                ]
            }
        ]
    }

    ai_service.llm_client.generate_from_template.return_value = "AI content"

    enhanced = ai_service.enhance_analysis_results(
        analysis_results,
        code_context={"app.py": "code"},
        enable_fixes=True
    )

    # Should have AI explanation
    first_issue = enhanced["files"][0]["issues"][0]
    assert "has_ai_explanation" in first_issue


def test_calculate_fix_confidence_high():
    """Test fix confidence for simple style issue"""
    service = AIAnalysisService.__new__(AIAnalysisService)

    issue = {
        "severity": "info",
        "category": "style"
    }

    confidence = service._calculate_fix_confidence(
        issue,
        "```python\nFixed code here\n```\nDetailed explanation of the fix."
    )

    # Should be high confidence (style + info + code block + long explanation)
    assert confidence >= 0.9


def test_calculate_fix_confidence_low():
    """Test fix confidence for complex critical issue"""
    service = AIAnalysisService.__new__(AIAnalysisService)

    issue = {
        "severity": "critical",
        "category": "complexity"
    }

    confidence = service._calculate_fix_confidence(issue, "Short fix")

    # Should be lower confidence
    assert confidence < 0.7


def test_calculate_refactoring_confidence():
    """Test refactoring confidence calculation"""
    service = AIAnalysisService.__new__(AIAnalysisService)

    original = "def foo():\n    pass\n"
    refactored = "def foo():\n    return None\n"

    confidence = service._calculate_refactoring_confidence(original, refactored)

    assert 0.0 <= confidence <= 1.0


def test_extract_code_snippet():
    """Test code snippet extraction"""
    service = AIAnalysisService.__new__(AIAnalysisService)

    code = "line1\nline2\nline3\nline4\nline5\nline6\nline7"
    snippet = service._extract_code_snippet(code, line_number=4, context_lines=2)

    # Should get lines 2-6 (4 +/- 2)
    assert "line2" in snippet
    assert "line6" in snippet


def test_extract_code_snippet_empty():
    """Test snippet extraction with empty code"""
    service = AIAnalysisService.__new__(AIAnalysisService)
    snippet = service._extract_code_snippet("", 5)
    assert snippet == ""


def test_parse_refactoring_response():
    """Test parsing refactoring response"""
    service = AIAnalysisService.__new__(AIAnalysisService)

    response = '''
Here's the refactored code:

```python
def improved_function():
    return result
```

This is better because...
'''

    parsed = service._parse_refactoring_response(response)

    assert "explanation" in parsed
    assert "after_code" in parsed
    assert parsed["after_code"] is not None
    assert "improved_function" in parsed["after_code"]


def test_test_connection(ai_service):
    """Test connection testing"""
    ai_service.llm_client.test_connection.return_value = True
    assert ai_service.test_connection() is True

    ai_service.llm_client.test_connection.return_value = False
    assert ai_service.test_connection() is False


def test_get_info(ai_service):
    """Test getting service info"""
    info = ai_service.get_info()

    assert info["service"] == "AIAnalysisService"
    assert "llm_backend" in info
    assert "capabilities" in info
    assert len(info["capabilities"]) > 0
