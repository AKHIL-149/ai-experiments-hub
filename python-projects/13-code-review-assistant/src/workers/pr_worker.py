"""Celery worker for pull request analysis tasks"""
import os
from datetime import datetime
from typing import Dict, Any, Optional
from celery_app import celery_app
from src.core.database import DatabaseManager, PullRequest, PRStatus, CodeFile
from src.services.github_service import GitHubService
from src.utils.git_utils import DiffParser
from src.services.code_analyzer_service import CodeAnalyzerService


# Get database manager
db_manager = DatabaseManager()


@celery_app.task(name='src.workers.pr_worker.analyze_pr_task', bind=True)
def analyze_pr_task(
    self,
    pr_id: str,
    github_token: str
) -> Dict[str, Any]:
    """
    Async task to analyze a pull request.

    Args:
        pr_id: Pull request ID
        github_token: GitHub personal access token

    Returns:
        Analysis results dictionary
    """
    job_id = self.request.id

    try:
        # Update task state
        self.update_state(
            state='FETCHING',
            meta={
                'status': 'Fetching pull request from GitHub...',
                'pr_id': pr_id,
                'started_at': datetime.utcnow().isoformat()
            }
        )

        # Get PR from database
        with db_manager.get_session() as db:
            pr = db.query(PullRequest).filter(PullRequest.id == pr_id).first()

            if not pr:
                return {
                    'success': False,
                    'error': 'Pull request not found',
                    'pr_id': pr_id
                }

            # Update PR status
            pr.status = PRStatus.ANALYZING
            db.commit()

            # Get repository
            repository = pr.repository

            if not repository:
                pr.status = PRStatus.OPEN
                db.commit()
                return {
                    'success': False,
                    'error': 'Repository not found',
                    'pr_id': pr_id
                }

        # Fetch PR diff from GitHub
        self.update_state(
            state='PARSING',
            meta={
                'status': 'Fetching diff from GitHub...',
                'pr_id': pr_id
            }
        )

        github_service = GitHubService(github_token=github_token)
        success, diff_text, error = github_service.get_pull_request_diff(
            repository.github_url,
            pr.pr_number
        )
        github_service.close()

        if not success:
            with db_manager.get_session() as db:
                pr = db.query(PullRequest).filter(PullRequest.id == pr_id).first()
                pr.status = PRStatus.OPEN
                db.commit()

            return {
                'success': False,
                'error': f'Failed to fetch diff: {error}',
                'pr_id': pr_id
            }

        # Parse diff
        self.update_state(
            state='PARSING',
            meta={
                'status': 'Parsing diff...',
                'pr_id': pr_id
            }
        )

        diff_files = DiffParser.parse_diff(diff_text)

        # Filter for Python files only
        python_files = [
            f for f in diff_files
            if f.path and f.path.endswith('.py') and not f.is_deleted_file
        ]

        if not python_files:
            with db_manager.get_session() as db:
                pr = db.query(PullRequest).filter(PullRequest.id == pr_id).first()
                pr.status = PRStatus.REVIEWED
                pr.reviewed_at = datetime.utcnow()
                db.commit()

            return {
                'success': True,
                'message': 'No Python files to analyze',
                'pr_id': pr_id,
                'files_analyzed': 0
            }

        # Analyze each Python file
        self.update_state(
            state='ANALYZING',
            meta={
                'status': f'Analyzing {len(python_files)} Python files...',
                'pr_id': pr_id,
                'total_files': len(python_files),
                'current_file': 0
            }
        )

        total_issues = 0
        analyzed_files = []

        for idx, diff_file in enumerate(python_files):
            self.update_state(
                state='ANALYZING',
                meta={
                    'status': f'Analyzing {diff_file.path}...',
                    'pr_id': pr_id,
                    'total_files': len(python_files),
                    'current_file': idx + 1
                }
            )

            # Get file content from GitHub
            github_service = GitHubService(github_token=github_token)
            success, files_info, error = github_service.get_pull_request_files(
                repository.github_url,
                pr.pr_number
            )
            github_service.close()

            if not success:
                continue

            # Find matching file
            file_info = next(
                (f for f in files_info if f['filename'] == diff_file.path),
                None
            )

            if not file_info or not file_info.get('patch'):
                continue

            # Analyze the file (using patch content)
            # Note: For full analysis, we'd need the complete file content
            # For now, we'll analyze just the patch
            try:
                analyzer = CodeAnalyzerService()
                # We'll analyze the patch as if it were a complete file
                # This is a simplified approach - in production, you'd fetch the full file
                patch_content = file_info['patch']

                result = analyzer.analyze_code(
                    source_code=patch_content,
                    file_path=diff_file.path
                )

                if result['success']:
                    issues_count = result['report']['total_issues']
                    total_issues += issues_count

                    # Store file analysis in database
                    with db_manager.get_session() as db:
                        code_file = CodeFile(
                            pull_request_id=pr_id,
                            file_path=diff_file.path,
                            language='python',
                            lines_of_code=diff_file.get_added_lines_count(),
                            last_analyzed_at=datetime.utcnow()
                        )
                        db.add(code_file)
                        db.commit()

                    analyzed_files.append({
                        'path': diff_file.path,
                        'issues': issues_count
                    })

            except Exception as e:
                # Log error but continue with other files
                print(f"Error analyzing {diff_file.path}: {str(e)}")
                continue

        # Update PR status
        with db_manager.get_session() as db:
            pr = db.query(PullRequest).filter(PullRequest.id == pr_id).first()
            pr.status = PRStatus.REVIEWED
            pr.reviewed_at = datetime.utcnow()
            db.commit()

        self.update_state(
            state='SUCCESS',
            meta={
                'status': 'Analysis complete',
                'pr_id': pr_id,
                'files_analyzed': len(analyzed_files),
                'total_issues': total_issues
            }
        )

        return {
            'success': True,
            'pr_id': pr_id,
            'files_analyzed': len(analyzed_files),
            'total_issues': total_issues,
            'analyzed_files': analyzed_files
        }

    except Exception as e:
        # Update PR status on error
        try:
            with db_manager.get_session() as db:
                pr = db.query(PullRequest).filter(PullRequest.id == pr_id).first()
                if pr:
                    pr.status = PRStatus.OPEN
                    db.commit()
        except:
            pass

        self.update_state(
            state='FAILURE',
            meta={
                'error': str(e),
                'pr_id': pr_id
            }
        )

        return {
            'success': False,
            'error': str(e),
            'pr_id': pr_id
        }


@celery_app.task(name='src.workers.pr_worker.sync_pr_task', bind=True)
def sync_pr_task(
    self,
    pr_id: str,
    github_token: str
) -> Dict[str, Any]:
    """
    Async task to sync a pull request from GitHub.

    Args:
        pr_id: Pull request ID
        github_token: GitHub personal access token

    Returns:
        Sync results dictionary
    """
    try:
        self.update_state(
            state='SYNCING',
            meta={
                'status': 'Syncing pull request...',
                'pr_id': pr_id
            }
        )

        # Get PR from database
        with db_manager.get_session() as db:
            pr = db.query(PullRequest).filter(PullRequest.id == pr_id).first()

            if not pr:
                return {
                    'success': False,
                    'error': 'Pull request not found',
                    'pr_id': pr_id
                }

            repository = pr.repository

            # Fetch latest PR info from GitHub
            github_service = GitHubService(github_token=github_token)
            success, pr_info, error = github_service.get_pull_request_info(
                repository.github_url,
                pr.pr_number
            )
            github_service.close()

            if not success:
                return {
                    'success': False,
                    'error': error,
                    'pr_id': pr_id
                }

            # Update PR fields
            pr.title = pr_info['title']
            pr.description = pr_info['description']
            pr.is_draft = pr_info.get('is_draft', False)
            pr.is_merged = pr_info['is_merged']
            pr.commits_count = pr_info.get('commits_count', 0)
            pr.additions = pr_info.get('additions', 0)
            pr.deletions = pr_info.get('deletions', 0)
            pr.changed_files = pr_info.get('changed_files', 0)
            pr.mergeable = pr_info.get('mergeable')
            pr.mergeable_state = pr_info.get('mergeable_state')
            pr.updated_at = datetime.fromisoformat(pr_info['updated_at'])

            # Update status
            if pr_info['is_merged']:
                pr.status = PRStatus.MERGED
            elif pr_info['state'].lower() == 'closed':
                pr.status = PRStatus.CLOSED

            db.commit()

        return {
            'success': True,
            'pr_id': pr_id,
            'message': 'Pull request synced successfully'
        }

    except Exception as e:
        self.update_state(
            state='FAILURE',
            meta={
                'error': str(e),
                'pr_id': pr_id
            }
        )

        return {
            'success': False,
            'error': str(e),
            'pr_id': pr_id
        }
