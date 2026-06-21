"""Celery worker for pull request analysis tasks"""
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from celery_app import celery_app
from src.core.database import DatabaseManager, PullRequest, PRStatus, CodeFile, AnalysisJob, JobStatus, Issue
from src.core.github_app import get_github_app
from src.services.github_service import GitHubService
from src.utils.git_utils import DiffParser
from src.services.code_analyzer_service import CodeAnalyzerService
from src.parsers import get_registry


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


@celery_app.task(name='src.workers.pr_worker.analyze_pr_webhook', bind=True)
def analyze_pr_webhook(
    self,
    job_id: str,
    repository_id: int,
    pr_number: int,
    installation_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Async task to analyze a pull request triggered by GitHub webhook.

    Uses GitHub App authentication for better rate limits and permissions.
    Analyzes all supported languages (Python, JavaScript, TypeScript, Java, Go, Rust).

    Args:
        job_id: Analysis job ID
        repository_id: Repository ID
        pr_number: Pull request number
        installation_id: GitHub App installation ID (optional)

    Returns:
        Analysis results dictionary
    """
    try:
        # Update job status to running
        with db_manager.get_session() as db:
            job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
            if job:
                job.status = JobStatus.PROCESSING
                job.celery_task_id = self.request.id
                db.commit()

        # Update task state
        self.update_state(
            state='FETCHING',
            meta={
                'status': 'Fetching pull request from GitHub...',
                'job_id': job_id,
                'pr_number': pr_number,
                'started_at': datetime.now(timezone.utc).isoformat()
            }
        )

        # Get repository and PR from database
        with db_manager.get_session() as db:
            from src.core.database import Repository

            repository = db.query(Repository).filter(Repository.id == repository_id).first()
            if not repository:
                raise ValueError(f"Repository {repository_id} not found")

            # Find or create PR record
            pr = db.query(PullRequest).filter(
                PullRequest.repository_id == repository_id,
                PullRequest.pr_number == pr_number
            ).first()

            if not pr:
                # Create PR record
                pr = PullRequest(
                    repository_id=repository_id,
                    pr_number=pr_number,
                    title=f"PR #{pr_number}",
                    author="unknown",
                    status=PRStatus.ANALYZING,
                    source_branch="unknown",
                    target_branch="unknown"
                )
                db.add(pr)
                db.commit()
                db.refresh(pr)
            else:
                pr.status = PRStatus.ANALYZING
                db.commit()

            pr_id = pr.id
            repo_owner, repo_name = repository.github_url.replace('https://github.com/', '').split('/')

        # Get GitHub App authentication
        github_app = get_github_app()

        if installation_id and github_app.is_configured():
            # Use GitHub App token
            token = github_app.get_installation_token(installation_id)
        else:
            # Fall back to personal access token from env
            token = os.environ.get('GITHUB_TOKEN', '')
            if not token:
                raise ValueError("No GitHub authentication available")

        # Fetch PR info from GitHub
        self.update_state(
            state='FETCHING',
            meta={
                'status': 'Fetching PR details...',
                'job_id': job_id,
                'pr_number': pr_number
            }
        )

        github_service = GitHubService(github_token=token)

        # Get PR information
        success, pr_info, error = github_service.get_pull_request_info(
            f"https://github.com/{repo_owner}/{repo_name}",
            pr_number
        )

        if not success:
            raise ValueError(f"Failed to fetch PR info: {error}")

        # Update PR with fetched information
        with db_manager.get_session() as db:
            pr = db.query(PullRequest).filter(PullRequest.id == pr_id).first()
            pr.title = pr_info.get('title', pr.title)
            pr.author = pr_info.get('author', pr.author)
            pr.source_branch = pr_info.get('source_branch', pr.source_branch)
            pr.target_branch = pr_info.get('target_branch', pr.target_branch)
            pr.commits_count = pr_info.get('commits_count', 0)
            pr.additions = pr_info.get('additions', 0)
            pr.deletions = pr_info.get('deletions', 0)
            pr.changed_files = pr_info.get('changed_files', 0)
            db.commit()

        # Get PR diff
        success, diff_text, error = github_service.get_pull_request_diff(
            f"https://github.com/{repo_owner}/{repo_name}",
            pr_number
        )

        if not success:
            raise ValueError(f"Failed to fetch diff: {error}")

        # Parse diff to get changed files
        diff_files = DiffParser.parse_diff(diff_text)

        # Filter for supported files (not deleted)
        parser_registry = get_registry()
        supported_files: List[Any] = []

        for diff_file in diff_files:
            if diff_file.path and not diff_file.is_deleted_file:
                # Check if we have a parser for this file
                if parser_registry.is_supported(diff_file.path):
                    supported_files.append(diff_file)

        if not supported_files:
            # No files to analyze
            with db_manager.get_session() as db:
                pr = db.query(PullRequest).filter(PullRequest.id == pr_id).first()
                pr.status = PRStatus.REVIEWED
                pr.reviewed_at = datetime.now(timezone.utc)
                db.commit()

                job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
                if job:
                    job.status = JobStatus.COMPLETED
                    job.completed_at = datetime.now(timezone.utc)
                    job.result_json = {
                        'success': True,
                        'message': 'No supported files to analyze',
                        'files_analyzed': 0,
                        'total_issues': 0
                    }
                    db.commit()

            return {
                'success': True,
                'message': 'No supported files to analyze',
                'files_analyzed': 0,
                'total_issues': 0
            }

        # Analyze each supported file
        self.update_state(
            state='ANALYZING',
            meta={
                'status': f'Analyzing {len(supported_files)} files...',
                'job_id': job_id,
                'pr_number': pr_number,
                'total_files': len(supported_files),
                'current_file': 0
            }
        )

        total_issues = 0
        analyzed_files = []
        all_issues: List[Dict[str, Any]] = []

        for idx, diff_file in enumerate(supported_files):
            self.update_state(
                state='ANALYZING',
                meta={
                    'status': f'Analyzing {diff_file.path}...',
                    'job_id': job_id,
                    'total_files': len(supported_files),
                    'current_file': idx + 1
                }
            )

            try:
                # Get file content from GitHub
                success, files_info, error = github_service.get_pull_request_files(
                    f"https://github.com/{repo_owner}/{repo_name}",
                    pr_number
                )

                if not success:
                    continue

                # Find matching file
                file_info = next(
                    (f for f in files_info if f['filename'] == diff_file.path),
                    None
                )

                if not file_info:
                    continue

                # Get full file content (not just patch)
                # For webhook analysis, we'll use the patch for now
                # In production, you'd fetch the full file from the PR's head commit
                patch_content = file_info.get('patch', '')

                if not patch_content:
                    continue

                # Detect language from file extension
                language = parser_registry.detect_language(diff_file.path)

                # Analyze the file
                analyzer = CodeAnalyzerService()
                result = analyzer.analyze_code(
                    source_code=patch_content,
                    file_path=diff_file.path,
                    language=language
                )

                if result['success']:
                    issues_count = result['report']['total_issues']
                    total_issues += issues_count

                    # Store code file in database
                    with db_manager.get_session() as db:
                        code_file = CodeFile(
                            pull_request_id=pr_id,
                            file_path=diff_file.path,
                            language=language or 'unknown',
                            lines_of_code=diff_file.get_added_lines_count() if hasattr(diff_file, 'get_added_lines_count') else 0,
                            last_analyzed_at=datetime.now(timezone.utc)
                        )
                        db.add(code_file)
                        db.commit()
                        db.refresh(code_file)

                        # Store issues in database
                        for issue_data in result['report'].get('issues', []):
                            issue = Issue(
                                code_file_id=code_file.id,
                                category=issue_data.get('category', 'unknown'),
                                severity=issue_data.get('severity', 'info'),
                                rule_id=issue_data.get('rule_id', ''),
                                title=issue_data.get('title', ''),
                                description=issue_data.get('description', ''),
                                line_number=issue_data.get('line_number'),
                                code_snippet=issue_data.get('code_snippet', ''),
                                confidence=issue_data.get('confidence', 0.5)
                            )
                            db.add(issue)
                            all_issues.append(issue_data)

                        db.commit()

                    analyzed_files.append({
                        'path': diff_file.path,
                        'language': language,
                        'issues': issues_count
                    })

            except Exception as e:
                # Log error but continue with other files
                print(f"Error analyzing {diff_file.path}: {str(e)}")
                continue

        github_service.close()

        # Update PR and job status
        with db_manager.get_session() as db:
            pr = db.query(PullRequest).filter(PullRequest.id == pr_id).first()
            pr.status = PRStatus.REVIEWED
            pr.reviewed_at = datetime.now(timezone.utc)
            db.commit()

            job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
            if job:
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.now(timezone.utc)
                job.result_json = {
                    'success': True,
                    'files_analyzed': len(analyzed_files),
                    'total_issues': total_issues,
                    'analyzed_files': analyzed_files,
                    'issues_summary': {
                        'critical': len([i for i in all_issues if i.get('severity') == 'critical']),
                        'error': len([i for i in all_issues if i.get('severity') == 'error']),
                        'warning': len([i for i in all_issues if i.get('severity') == 'warning']),
                        'info': len([i for i in all_issues if i.get('severity') == 'info'])
                    }
                }
                db.commit()

        self.update_state(
            state='SUCCESS',
            meta={
                'status': 'Analysis complete',
                'job_id': job_id,
                'pr_number': pr_number,
                'files_analyzed': len(analyzed_files),
                'total_issues': total_issues
            }
        )

        return {
            'success': True,
            'job_id': job_id,
            'pr_number': pr_number,
            'files_analyzed': len(analyzed_files),
            'total_issues': total_issues,
            'analyzed_files': analyzed_files
        }

    except Exception as e:
        # Update job status on error
        try:
            with db_manager.get_session() as db:
                job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
                if job:
                    job.status = JobStatus.FAILED
                    job.completed_at = datetime.now(timezone.utc)
                    job.result_json = {'error': str(e)}
                    db.commit()

                # Also update PR status if it exists
                pr = db.query(PullRequest).filter(
                    PullRequest.repository_id == repository_id,
                    PullRequest.pr_number == pr_number
                ).first()
                if pr:
                    pr.status = PRStatus.OPEN
                    db.commit()
        except:
            pass

        self.update_state(
            state='FAILURE',
            meta={
                'error': str(e),
                'job_id': job_id,
                'pr_number': pr_number
            }
        )

        return {
            'success': False,
            'error': str(e),
            'job_id': job_id,
            'pr_number': pr_number
        }
