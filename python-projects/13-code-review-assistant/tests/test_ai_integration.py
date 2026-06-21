"""
Integration tests for AI features

Tests the complete AI workflow including:
- LLM client integration
- AI analysis service
- Enhanced analyzer
- Refactoring generation
"""
import pytest
from unittest.mock import Mock, patch
from src.core.llm_client import LLMClient
from src.services.ai_analysis_service import AIAnalysisService
from src.services.enhanced_analyzer import EnhancedAnalyzer
from src.services.refactoring_service import RefactoringService
from src.core.database import (
    DatabaseManager,
    CodeFile,
    Issue,
    PullRequest,
    Repository,
    RepositoryStatus,
    PRStatus
)


@pytest.fixture
def sample_vulnerable_code():
    """Sample vulnerable code for testing"""
    return '''def get_user(user_id):
    query = "SELECT * FROM users WHERE id = " + user_id
    cursor.execute(query)
    return cursor.fetchone()

def process_payment(amount):
    api_key = "sk_test_1234567890"  # Hardcoded secret
    return make_payment(api_key, amount)'''


@pytest.fixture
def sample_complex_code():
    """Sample complex code for refactoring"""
    return '''def process_data(data):
    results = []
    for item in data:
        if item['status'] == 'active':
            if item['type'] == 'premium':
                if item['age'] > 18:
                    results.append(item)
    return results'''


def test_llm_client_to_ai_service_integration():
    """Test LLM client integration with AI service"""
    with patch('src.services.ai_analysis_service.LLMClient') as MockLLM:
        # Mock LLM responses
        mock_client = Mock()
        mock_client.generate_from_template.return_value = "This is a SQL injection vulnerability..."
        mock_client.test_connection.return_value = True
        MockLLM.return_value = mock_client

        # Create AI service
        ai_service = AIAnalysisService()

        # Test issue enhancement
        issue = {
            'severity': 'critical',
            'category': 'security',
            'title': 'SQL Injection',
            'description': 'String concatenation in SQL',
            'line_number': 2
        }

        enhanced = ai_service.enhance_issue_with_ai(
            issue,
            'SELECT * FROM users WHERE id = " + user_id',
            language='python'
        )

        assert enhanced['has_ai_explanation'] is True
        assert 'ai_explanation' in enhanced
        assert mock_client.generate_from_template.called


def test_ai_service_to_enhanced_analyzer_integration(sample_vulnerable_code):
    """Test AI service integration with enhanced analyzer"""
    with patch('src.services.enhanced_analyzer.CodeAnalyzerService') as MockAnalyzer:
        with patch('src.services.enhanced_analyzer.AIAnalysisService') as MockAI:
            # Mock code analyzer results
            mock_analyzer = Mock()
            mock_analyzer.analyze_code.return_value = {
                'language': 'python',
                'issues': [
                    {
                        'severity': 'critical',
                        'category': 'security',
                        'title': 'SQL Injection',
                        'line_number': 2
                    }
                ]
            }
            MockAnalyzer.return_value = mock_analyzer

            # Mock AI service
            mock_ai = Mock()
            mock_ai.enhance_issue_with_ai.return_value = {
                'severity': 'critical',
                'has_ai_explanation': True,
                'ai_explanation': 'SQL injection vulnerability detected'
            }
            MockAI.return_value = mock_ai

            # Create enhanced analyzer
            analyzer = EnhancedAnalyzer(enable_ai=True)
            analyzer.ai_service = mock_ai

            # Analyze code
            results = analyzer.analyze_code(
                sample_vulnerable_code,
                'test.py',
                language='python'
            )

            assert results['ai_enhanced'] is True
            assert 'ai_issues_enhanced' in results
            assert mock_ai.enhance_issue_with_ai.called


def test_ai_service_to_refactoring_service_integration():
    """Test AI service integration with refactoring service"""
    db_manager = DatabaseManager('sqlite:///:memory:')

    with db_manager.get_session() as db:
        # Create test data
        repo = Repository(
            user_id='test-user',
            name='test-repo',
            github_url='https://github.com/test/repo',
            status=RepositoryStatus.READY
        )
        db.add(repo)
        db.commit()

        pr = PullRequest(
            repository_id=repo.id,
            pr_number=1,
            title='Test PR',
            author='author',
            source_branch='feature',
            target_branch='main',
            status=PRStatus.OPEN
        )
        db.add(pr)
        db.commit()

        code_file = CodeFile(
            pull_request_id=pr.id,
            file_path='app.py',
            file_hash='abc123',
            language='python',
            lines_of_code=50
        )
        db.add(code_file)
        db.commit()

        issue = Issue(
            code_file_id=code_file.id,
            category='complexity',
            severity='warning',
            rule_id='complexity_high',
            title='High complexity',
            description='Function is too complex',
            line_number=10
        )
        db.add(issue)
        db.commit()

        # Mock AI service
        mock_ai = Mock()
        mock_ai.suggest_refactoring.return_value = {
            'refactored_code': 'def simple(): return None',
            'explanation': 'Simplified function',
            'refactoring_suggestion': 'This improves code quality',
            'confidence_score': 0.85
        }

        # Create refactoring service with AI
        refactoring_service = RefactoringService(db, ai_service=mock_ai)

        # Generate refactoring
        success, refactoring, error = refactoring_service.generate_refactoring_from_issue(
            issue.id,
            code_file.id,
            'def foo(): pass'
        )

        assert success is True
        assert refactoring is not None
        assert refactoring.confidence == 0.85
        assert mock_ai.suggest_refactoring.called


def test_complete_ai_workflow(sample_complex_code):
    """Test complete AI workflow from code to refactoring"""
    db_manager = DatabaseManager('sqlite:///:memory:')

    with patch('src.services.enhanced_analyzer.CodeAnalyzerService') as MockAnalyzer:
        with patch('src.services.enhanced_analyzer.AIAnalysisService') as MockAI:
            # Mock code analyzer
            mock_analyzer = Mock()
            mock_analyzer.analyze_code.return_value = {
                'language': 'python',
                'issues': [
                    {
                        'severity': 'warning',
                        'category': 'complexity',
                        'title': 'Deep nesting',
                        'description': 'Too many nested if statements',
                        'line_number': 3
                    }
                ]
            }
            MockAnalyzer.return_value = mock_analyzer

            # Mock AI service
            mock_ai = Mock()
            mock_ai.enhance_issue_with_ai.return_value = {
                'severity': 'warning',
                'has_ai_explanation': True,
                'ai_explanation': 'Deep nesting reduces readability',
                'category': 'complexity'
            }
            mock_ai.suggest_fix.return_value = {
                'suggested_fix': 'Use list comprehension',
                'confidence_score': 0.9,
                'can_auto_apply': True
            }
            mock_ai.suggest_refactoring.return_value = {
                'refactored_code': 'return [item for item in data if item["status"] == "active"]',
                'explanation': 'Use list comprehension for clarity',
                'confidence_score': 0.85
            }
            MockAI.return_value = mock_ai

            # Step 1: Analyze code with AI
            analyzer = EnhancedAnalyzer(enable_ai=True)
            analyzer.ai_service = mock_ai

            results = analyzer.analyze_code(
                sample_complex_code,
                'test.py',
                enable_fixes=True
            )

            # Verify analysis
            assert results['ai_enhanced'] is True
            assert len(results['issues']) > 0
            first_issue = results['issues'][0]
            assert first_issue['has_ai_explanation'] is True
            assert 'fix_suggestion' in first_issue

            # Step 2: Create refactoring from issue
            with db_manager.get_session() as db:
                repo = Repository(
                    user_id='test-user',
                    name='test-repo',
                    github_url='https://github.com/test/repo',
                    status=RepositoryStatus.READY
                )
                db.add(repo)
                db.commit()

                pr = PullRequest(
                    repository_id=repo.id,
                    pr_number=1,
                    title='Test PR',
                    author='author',
                    source_branch='feature',
                    target_branch='main'
                )
                db.add(pr)
                db.commit()

                code_file = CodeFile(
                    pull_request_id=pr.id,
                    file_path='test.py',
                    file_hash='hash123',
                    language='python',
                    lines_of_code=10
                )
                db.add(code_file)
                db.commit()

                issue = Issue(
                    code_file_id=code_file.id,
                    category='complexity',
                    severity='warning',
                    rule_id='deep_nesting',
                    title='Deep nesting',
                    description='Too many nested ifs',
                    line_number=3
                )
                db.add(issue)
                db.commit()

                # Generate refactoring
                refactoring_service = RefactoringService(db, ai_service=mock_ai)
                success, refactoring, error = refactoring_service.generate_refactoring_from_issue(
                    issue.id,
                    code_file.id,
                    sample_complex_code
                )

                assert success is True
                assert refactoring is not None
                assert refactoring.confidence == 0.85
                # Verify refactored code contains list comprehension syntax
                assert '[item for item in' in refactoring.refactored_code


def test_ai_service_error_handling():
    """Test AI service error handling"""
    with patch('src.services.ai_analysis_service.LLMClient') as MockLLM:
        mock_client = Mock()
        mock_client.generate_from_template.side_effect = Exception("LLM error")
        MockLLM.return_value = mock_client

        ai_service = AIAnalysisService()

        # Test graceful error handling
        issue = {'title': 'Test', 'severity': 'error'}
        enhanced = ai_service.enhance_issue_with_ai(issue, 'code', 'python')

        assert enhanced['has_ai_explanation'] is False
        assert 'ai_error' in enhanced


def test_enhanced_analyzer_without_ai(sample_vulnerable_code):
    """Test enhanced analyzer works without AI"""
    with patch('src.services.enhanced_analyzer.CodeAnalyzerService') as MockAnalyzer:
        mock_analyzer = Mock()
        mock_analyzer.analyze_code.return_value = {
            'issues': [{'title': 'Issue'}],
            'language': 'python'
        }
        MockAnalyzer.return_value = mock_analyzer

        analyzer = EnhancedAnalyzer(enable_ai=False)
        results = analyzer.analyze_code(sample_vulnerable_code, 'test.py')

        assert 'ai_enhanced' not in results or results['ai_enhanced'] is False


def test_refactoring_service_without_ai():
    """Test refactoring service works without AI"""
    db_manager = DatabaseManager('sqlite:///:memory:')

    with db_manager.get_session() as db:
        repo = Repository(
            user_id='test-user',
            name='test-repo',
            github_url='https://github.com/test/repo',
            status=RepositoryStatus.READY
        )
        db.add(repo)
        db.commit()

        pr = PullRequest(
            repository_id=repo.id,
            pr_number=1,
            title='Test PR',
            author='author',
            source_branch='feature',
            target_branch='main'
        )
        db.add(pr)
        db.commit()

        code_file = CodeFile(
            pull_request_id=pr.id,
            file_path='app.py',
            file_hash='abc123',
            language='python',
            lines_of_code=50
        )
        db.add(code_file)
        db.commit()

        issue = Issue(
            code_file_id=code_file.id,
            category='style',
            severity='info',
            rule_id='style_issue',
            title='Style issue',
            description='Bad style',
            line_number=5
        )
        db.add(issue)
        db.commit()

        # Service without AI
        service = RefactoringService(db)

        success, refactoring, error = service.generate_refactoring_from_issue(
            issue.id,
            code_file.id,
            'code'
        )

        assert success is False
        assert 'AI service not configured' in error


def test_ai_confidence_scoring():
    """Test AI confidence scoring in various scenarios"""
    with patch('src.services.ai_analysis_service.LLMClient') as MockLLM:
        mock_client = Mock()
        MockLLM.return_value = mock_client

        ai_service = AIAnalysisService()

        # High confidence for simple style issues
        style_issue = {'severity': 'info', 'category': 'style'}
        confidence = ai_service._calculate_fix_confidence(
            style_issue,
            '```python\nFixed code\n```\nDetailed explanation'
        )
        assert confidence >= 0.9

        # Lower confidence for critical complexity issues
        complex_issue = {'severity': 'critical', 'category': 'complexity'}
        confidence = ai_service._calculate_fix_confidence(
            complex_issue,
            'Short fix'
        )
        assert confidence < 0.7


def test_ai_template_usage():
    """Test that AI service uses correct templates"""
    with patch('src.services.ai_analysis_service.LLMClient') as MockLLM:
        mock_client = Mock()
        mock_client.generate_from_template.return_value = "Explanation"
        MockLLM.return_value = mock_client

        ai_service = AIAnalysisService()

        # Test explain_issue template
        issue = {'title': 'Test', 'severity': 'error', 'category': 'security'}
        ai_service.enhance_issue_with_ai(issue, 'code', 'python')

        assert mock_client.generate_from_template.called
        call_args = mock_client.generate_from_template.call_args
        assert call_args[0][0] == 'explain_issue'

        # Test suggest_fix template
        ai_service.suggest_fix(issue, 'code', 'python')
        call_args = mock_client.generate_from_template.call_args
        assert call_args[0][0] == 'suggest_fix'

        # Test refactor_code template
        ai_service.suggest_refactoring('code', 'complexity', 'python')
        call_args = mock_client.generate_from_template.call_args
        assert call_args[0][0] == 'refactor_code'
