"""Tests for Enhanced Analyzer"""
import pytest
from unittest.mock import Mock, patch, mock_open
from src.services.enhanced_analyzer import EnhancedAnalyzer


@pytest.fixture
def sample_code():
    """Sample code for testing"""
    return """def get_user(user_id):
    query = "SELECT * FROM users WHERE id = " + user_id
    cursor.execute(query)
    return cursor.fetchone()"""


@pytest.fixture
def sample_analysis_results():
    """Sample analysis results from code analyzer"""
    return {
        'language': 'python',
        'issues': [
            {
                'severity': 'critical',
                'category': 'security',
                'title': 'SQL Injection',
                'description': 'String concatenation in SQL',
                'line_number': 2
            },
            {
                'severity': 'warning',
                'category': 'style',
                'title': 'Missing docstring',
                'description': 'Function should have docstring',
                'line_number': 1
            }
        ]
    }


def test_enhanced_analyzer_initialization_with_ai():
    """Test initializing enhanced analyzer with AI enabled"""
    with patch('src.services.enhanced_analyzer.AIAnalysisService'):
        analyzer = EnhancedAnalyzer(enable_ai=True)
        assert analyzer.enable_ai is True
        assert analyzer.ai_service is not None


def test_enhanced_analyzer_initialization_without_ai():
    """Test initializing enhanced analyzer without AI"""
    analyzer = EnhancedAnalyzer(enable_ai=False)
    assert analyzer.enable_ai is False
    assert analyzer.ai_service is None


def test_analyze_code_without_ai(sample_code):
    """Test analyzing code without AI enhancement"""
    with patch('src.services.enhanced_analyzer.CodeAnalyzerService') as MockAnalyzer:
        mock_analyzer_instance = Mock()
        mock_analyzer_instance.analyze_code.return_value = {
            'issues': [],
            'language': 'python'
        }
        MockAnalyzer.return_value = mock_analyzer_instance

        analyzer = EnhancedAnalyzer(enable_ai=False)
        results = analyzer.analyze_code(sample_code, 'test.py')

        assert 'issues' in results
        assert 'ai_enhanced' not in results or results['ai_enhanced'] is False


def test_analyze_code_with_ai(sample_code, sample_analysis_results):
    """Test analyzing code with AI enhancement"""
    with patch('src.services.enhanced_analyzer.CodeAnalyzerService') as MockAnalyzer:
        with patch('src.services.enhanced_analyzer.AIAnalysisService') as MockAI:
            # Mock code analyzer
            mock_analyzer = Mock()
            mock_analyzer.analyze_code.return_value = sample_analysis_results
            MockAnalyzer.return_value = mock_analyzer

            # Mock AI service
            mock_ai = Mock()
            mock_ai.enhance_issue_with_ai.return_value = {
                'severity': 'critical',
                'category': 'security',
                'title': 'SQL Injection',
                'has_ai_explanation': True,
                'ai_explanation': 'This is vulnerable to SQL injection...'
            }
            MockAI.return_value = mock_ai

            analyzer = EnhancedAnalyzer(enable_ai=True)
            analyzer.ai_service = mock_ai

            results = analyzer.analyze_code(sample_code, 'test.py')

            assert results['ai_enhanced'] is True
            assert 'ai_issues_enhanced' in results
            assert mock_ai.enhance_issue_with_ai.called


def test_analyze_code_with_fixes(sample_code, sample_analysis_results):
    """Test analyzing code with fix suggestions enabled"""
    with patch('src.services.enhanced_analyzer.CodeAnalyzerService') as MockAnalyzer:
        with patch('src.services.enhanced_analyzer.AIAnalysisService') as MockAI:
            mock_analyzer = Mock()
            mock_analyzer.analyze_code.return_value = sample_analysis_results
            MockAnalyzer.return_value = mock_analyzer

            mock_ai = Mock()
            mock_ai.enhance_issue_with_ai.return_value = {
                'has_ai_explanation': True,
                'ai_explanation': 'Explanation'
            }
            mock_ai.suggest_fix.return_value = {
                'suggested_fix': 'Use parameterized queries',
                'confidence_score': 0.9
            }
            MockAI.return_value = mock_ai

            analyzer = EnhancedAnalyzer(enable_ai=True)
            analyzer.ai_service = mock_ai

            results = analyzer.analyze_code(
                sample_code,
                'test.py',
                enable_fixes=True
            )

            assert results['ai_enhanced'] is True
            assert mock_ai.suggest_fix.called


def test_analyze_file(tmp_path, sample_code):
    """Test analyzing a file"""
    # Create test file
    test_file = tmp_path / "test.py"
    test_file.write_text(sample_code)

    with patch('src.services.enhanced_analyzer.CodeAnalyzerService') as MockAnalyzer:
        mock_analyzer = Mock()
        mock_analyzer.analyze_file.return_value = {
            'issues': [],
            'language': 'python'
        }
        MockAnalyzer.return_value = mock_analyzer

        analyzer = EnhancedAnalyzer(enable_ai=False)
        results = analyzer.analyze_file(str(test_file))

        assert 'issues' in results
        assert mock_analyzer.analyze_file.called


def test_analyze_file_with_ai_enhancement(tmp_path, sample_code):
    """Test analyzing file with AI enhancement"""
    test_file = tmp_path / "test.py"
    test_file.write_text(sample_code)

    with patch('src.services.enhanced_analyzer.CodeAnalyzerService') as MockAnalyzer:
        with patch('src.services.enhanced_analyzer.AIAnalysisService') as MockAI:
            mock_analyzer = Mock()
            mock_analyzer.analyze_file.return_value = {
                'issues': [{
                    'severity': 'error',
                    'title': 'Issue',
                    'line_number': 2
                }],
                'language': 'python'
            }
            MockAnalyzer.return_value = mock_analyzer

            mock_ai = Mock()
            mock_ai.enhance_issue_with_ai.return_value = {
                'has_ai_explanation': True
            }
            MockAI.return_value = mock_ai

            analyzer = EnhancedAnalyzer(enable_ai=True)
            analyzer.ai_service = mock_ai

            results = analyzer.analyze_file(str(test_file))

            assert results.get('ai_enhanced') is True


def test_analyze_multiple_files(tmp_path):
    """Test analyzing multiple files"""
    # Create test files
    file1 = tmp_path / "file1.py"
    file1.write_text("def foo(): pass")
    file2 = tmp_path / "file2.py"
    file2.write_text("def bar(): pass")

    with patch('src.services.enhanced_analyzer.CodeAnalyzerService') as MockAnalyzer:
        mock_analyzer = Mock()
        mock_analyzer.analyze_file.return_value = {
            'issues': [],
            'language': 'python'
        }
        MockAnalyzer.return_value = mock_analyzer

        analyzer = EnhancedAnalyzer(enable_ai=False)
        results = analyzer.analyze_multiple_files([str(file1), str(file2)])

        assert results['total_files'] == 2
        assert results['analyzed_files'] == 2
        assert len(results['files']) == 2


def test_analyze_multiple_files_with_error(tmp_path):
    """Test handling errors when analyzing multiple files"""
    file1 = tmp_path / "file1.py"
    file1.write_text("code")

    with patch('src.services.enhanced_analyzer.CodeAnalyzerService') as MockAnalyzer:
        mock_analyzer = Mock()
        mock_analyzer.analyze_file.side_effect = Exception("Analysis failed")
        MockAnalyzer.return_value = mock_analyzer

        analyzer = EnhancedAnalyzer(enable_ai=False)
        results = analyzer.analyze_multiple_files([str(file1)])

        assert results['total_files'] == 1
        assert results['files'][0]['error'] == "Analysis failed"


def test_get_severity_summary():
    """Test getting severity summary"""
    analyzer = EnhancedAnalyzer(enable_ai=False)

    results = {
        'issues': [
            {'severity': 'critical'},
            {'severity': 'critical'},
            {'severity': 'warning'},
            {'severity': 'info'}
        ]
    }

    summary = analyzer.get_severity_summary(results)

    assert summary['critical'] == 2
    assert summary['warning'] == 1
    assert summary['info'] == 1
    assert summary['error'] == 0


def test_get_severity_summary_from_files():
    """Test getting severity summary from file-level results"""
    analyzer = EnhancedAnalyzer(enable_ai=False)

    results = {
        'files': [
            {
                'issues': [
                    {'severity': 'error'},
                    {'severity': 'warning'}
                ]
            },
            {
                'issues': [
                    {'severity': 'critical'}
                ]
            }
        ]
    }

    summary = analyzer.get_severity_summary(results)

    assert summary['critical'] == 1
    assert summary['error'] == 1
    assert summary['warning'] == 1


def test_get_category_summary():
    """Test getting category summary"""
    analyzer = EnhancedAnalyzer(enable_ai=False)

    results = {
        'issues': [
            {'category': 'security'},
            {'category': 'security'},
            {'category': 'style'},
            {'category': 'complexity'}
        ]
    }

    summary = analyzer.get_category_summary(results)

    assert summary['security'] == 2
    assert summary['style'] == 1
    assert summary['complexity'] == 1


def test_extract_snippet():
    """Test code snippet extraction"""
    analyzer = EnhancedAnalyzer(enable_ai=False)

    code = "line1\nline2\nline3\nline4\nline5\nline6\nline7"
    snippet = analyzer._extract_snippet(code, line_number=4, context_lines=2)

    lines = snippet.split('\n')
    assert 'line2' in snippet
    assert 'line6' in snippet


def test_extract_snippet_empty_code():
    """Test snippet extraction with empty code"""
    analyzer = EnhancedAnalyzer(enable_ai=False)
    snippet = analyzer._extract_snippet("", 5)
    assert snippet == ""


def test_test_ai_connection_without_ai():
    """Test AI connection when AI is disabled"""
    analyzer = EnhancedAnalyzer(enable_ai=False)
    assert analyzer.test_ai_connection() is False


def test_test_ai_connection_with_ai():
    """Test AI connection when AI is enabled"""
    with patch('src.services.enhanced_analyzer.AIAnalysisService') as MockAI:
        mock_ai = Mock()
        mock_ai.test_connection.return_value = True
        MockAI.return_value = mock_ai

        analyzer = EnhancedAnalyzer(enable_ai=True)
        analyzer.ai_service = mock_ai

        assert analyzer.test_ai_connection() is True


def test_get_info_without_ai():
    """Test getting info when AI is disabled"""
    analyzer = EnhancedAnalyzer(enable_ai=False)
    info = analyzer.get_info()

    assert info['enhanced_analyzer'] is True
    assert info['ai_enabled'] is False
    assert 'code_analyzer' in info


def test_get_info_with_ai():
    """Test getting info when AI is enabled"""
    with patch('src.services.enhanced_analyzer.AIAnalysisService') as MockAI:
        mock_ai = Mock()
        mock_ai.get_info.return_value = {
            'service': 'AIAnalysisService',
            'llm_backend': 'ollama'
        }
        MockAI.return_value = mock_ai

        analyzer = EnhancedAnalyzer(enable_ai=True)
        analyzer.ai_service = mock_ai

        info = analyzer.get_info()

        assert info['ai_enabled'] is True
        assert 'ai_service' in info
        assert info['ai_service']['service'] == 'AIAnalysisService'
