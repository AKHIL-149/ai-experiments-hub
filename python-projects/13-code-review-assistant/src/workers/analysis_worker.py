"""Celery worker for code analysis tasks"""
import os
from datetime import datetime
from typing import Dict, Any, Optional, List
from celery_app import celery_app
from src.services.code_analyzer_service import CodeAnalyzerService


# In-memory cache for storing analysis results (for demo/development)
# In production, this should use Redis or database
_analysis_cache = {}


@celery_app.task(name='src.workers.analysis_worker.analyze_file_task', bind=True)
def analyze_file_task(
    self,
    file_content: str,
    filename: str,
    analyzer_ids: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Async task to analyze a code file.

    Args:
        file_content: Content of the file to analyze
        filename: Name of the file
        analyzer_ids: Optional list of specific analyzers to run

    Returns:
        Analysis results dictionary
    """
    job_id = self.request.id

    try:
        # Update task state
        self.update_state(
            state='PROCESSING',
            meta={
                'status': 'Analyzing code...',
                'filename': filename,
                'started_at': datetime.utcnow().isoformat()
            }
        )

        # Create analyzer service
        service = CodeAnalyzerService()

        # Analyze the code
        result = service.analyze_code(
            source_code=file_content,
            file_path=filename,
            analyzer_ids=analyzer_ids
        )

        if result['success']:
            # Store issues in cache for querying
            _analysis_cache[job_id] = {
                'filename': filename,
                'issues': result['report']['issues'],
                'report': result['report'],
                'analyzed_at': datetime.utcnow().isoformat()
            }

            self.update_state(
                state='SUCCESS',
                meta={
                    'status': 'Analysis complete',
                    'issues_found': result['report']['total_issues'],
                    'health_score': result['report']['health_score']['overall_score']
                }
            )

        return result

    except Exception as e:
        self.update_state(
            state='FAILURE',
            meta={
                'error': str(e),
                'filename': filename
            }
        )
        return {
            'success': False,
            'error': str(e),
            'file_path': filename
        }


def get_analysis_results(job_id: str) -> Optional[Dict[str, Any]]:
    """Get cached analysis results by job ID"""
    return _analysis_cache.get(job_id)


def get_all_cached_analyses() -> List[Dict[str, Any]]:
    """Get all cached analysis results"""
    return list(_analysis_cache.values())


def clear_analysis_cache():
    """Clear the analysis cache"""
    _analysis_cache.clear()


@celery_app.task(name='src.workers.analysis_worker.analyze_uploaded_file_task', bind=True)
def analyze_uploaded_file_task(
    self,
    file_path: str,
    analyzer_ids: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Async task to analyze an uploaded file.

    Args:
        file_path: Path to the uploaded file
        analyzer_ids: Optional list of specific analyzers to run

    Returns:
        Analysis results dictionary
    """
    try:
        self.update_state(state='PROCESSING', meta={'status': 'Reading file...'})

        # Read file content
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()

        # Get filename
        filename = os.path.basename(file_path)

        # Analyze
        return analyze_file_task(self, file_content, filename, analyzer_ids)

    except Exception as e:
        self.update_state(state='FAILURE', meta={'error': str(e)})
        return {
            'success': False,
            'error': str(e),
            'file_path': file_path
        }


@celery_app.task(name='src.workers.analysis_worker.analyze_repository_task', bind=True)
def analyze_repository_task(
    self,
    repository_id: str
) -> Dict[str, Any]:
    """
    Analyze all code files in a repository.

    Args:
        repository_id: Repository ID to analyze

    Returns:
        Analysis results dictionary with issue count and summary
    """
    from pathlib import Path
    from src.core.database import DatabaseManager, Repository, CodeFile, Issue
    from src.parsers.parser_registry import ParserRegistry

    db_manager = DatabaseManager()

    try:
        with db_manager.get_session() as session:
            # Get repository
            repository = session.query(Repository).filter_by(id=repository_id).first()
            if not repository:
                return {'success': False, 'error': 'Repository not found'}

            if not repository.clone_path or not os.path.exists(repository.clone_path):
                return {'success': False, 'error': 'Repository not cloned yet. Please sync first.'}

            self.update_state(state='PROGRESS', meta={'status': 'Discovering files...'})

            # Initialize services
            analyzer_service = CodeAnalyzerService()
            parser_registry = ParserRegistry()

            repo_path = Path(repository.clone_path)

            # Find all supported code files
            supported_extensions = {
                '.py': 'python',
                '.js': 'javascript',
                '.jsx': 'javascript',
                '.ts': 'typescript',
                '.tsx': 'typescript',
                '.java': 'java',
                '.go': 'go',
                '.rs': 'rust'
            }

            files_to_analyze = []
            for ext, lang in supported_extensions.items():
                files_to_analyze.extend([(f, lang) for f in repo_path.rglob(f'*{ext}')])

            # Filter out common non-code directories
            excluded_dirs = {'node_modules', 'venv', '.venv', 'dist', 'build', '__pycache__', '.git'}
            files_to_analyze = [
                (f, lang) for f, lang in files_to_analyze
                if not any(excl in f.parts for excl in excluded_dirs)
            ]

            total_files = len(files_to_analyze)
            if total_files == 0:
                return {
                    'success': True,
                    'message': 'No supported code files found',
                    'files_analyzed': 0,
                    'issues_found': 0
                }

            self.update_state(state='PROGRESS', meta={
                'status': f'Analyzing {total_files} files...',
                'total': total_files,
                'current': 0
            })

            total_issues = 0
            files_analyzed = 0

            for idx, (file_path, language) in enumerate(files_to_analyze, 1):
                try:
                    # Read file
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        code = f.read()

                    # Skip empty files
                    if not code.strip():
                        continue

                    relative_path = str(file_path.relative_to(repo_path))

                    # Analyze file
                    result = analyzer_service.analyze_code(
                        source_code=code,
                        file_path=relative_path
                    )

                    # Fix: issues are in result['report']['issues'], not result['issues']
                    if result.get('success'):
                        report = result.get('report', {})
                        issues = report.get('issues', [])
                        if issues:
                            total_issues += len(issues)
                            print(f"Found {len(issues)} issues in {relative_path}:")
                            for issue in issues[:3]:  # Print first 3 issues
                                print(f"  [{issue.get('severity')}] {issue.get('title')}")

                    files_analyzed += 1

                    # Update progress every 10 files
                    if idx % 10 == 0:
                        self.update_state(state='PROGRESS', meta={
                            'status': f'Analyzing files... ({idx}/{total_files})',
                            'total': total_files,
                            'current': idx,
                            'issues_found': total_issues
                        })

                except Exception as e:
                    # Log error but continue with other files
                    print(f"Error analyzing {file_path}: {e}")
                    continue

            return {
                'success': True,
                'repository_id': repository_id,
                'repository_name': repository.name,
                'files_analyzed': files_analyzed,
                'total_files': total_files,
                'issues_found': total_issues,
                'message': f'Analyzed {files_analyzed} files, found {total_issues} issues'
            }

    except Exception as e:
        self.update_state(state='FAILURE', meta={'error': str(e)})
        return {
            'success': False,
            'error': str(e),
            'repository_id': repository_id
        }
