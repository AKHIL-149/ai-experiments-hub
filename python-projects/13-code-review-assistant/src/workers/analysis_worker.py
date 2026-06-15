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
