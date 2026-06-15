"""Celery worker for code analysis tasks"""
import os
import tempfile
from typing import Dict, Any, Optional, List
from celery_app import celery_app
from src.services.code_analyzer_service import CodeAnalyzerService


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
    try:
        # Update task state
        self.update_state(state='PROCESSING', meta={'status': 'Analyzing code...'})

        # Create analyzer service
        service = CodeAnalyzerService()

        # Analyze the code
        result = service.analyze_code(
            source_code=file_content,
            file_path=filename,
            analyzer_ids=analyzer_ids
        )

        if result['success']:
            self.update_state(
                state='SUCCESS',
                meta={
                    'status': 'Analysis complete',
                    'issues_found': result['report']['total_issues']
                }
            )

        return result

    except Exception as e:
        self.update_state(state='FAILURE', meta={'error': str(e)})
        return {
            'success': False,
            'error': str(e),
            'file_path': filename
        }


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
