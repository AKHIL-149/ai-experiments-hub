"""
Data isolation: one account must not see or change another account's issues, refactorings,
analytics, notifications, teams or pull requests.

A brand-new guest used to land on an Issues page showing every other account's 453 issues:
the endpoints took `user` only to require a login and then read every row in the database.

Two real accounts are used: `owner` has data, `other` is a fresh account (what a guest is).
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.core.database import (
    CodeFile, DatabaseManager, Issue, IssueCategory, IssueSeverity, PullRequest, Refactoring,
    Repository, User, UserRole,
)
from src.workers import analysis_worker


def make_account(prefix):
    from server import app

    client = TestClient(app)
    name = f'{prefix}_{uuid.uuid4().hex[:8]}'
    response = client.post('/api/auth/register', json={
        'username': name, 'email': f'{name}@example.com', 'password': 'TmpPass-12345'})
    assert response.status_code == 200, response.text
    client.account = response.json()['user']
    return client


@pytest.fixture
def owner():
    client = make_account('iso_owner')
    yield client
    _delete_user(client.account['id'])


@pytest.fixture
def other():
    client = make_account('iso_other')
    yield client
    _delete_user(client.account['id'])


def _delete_user(user_id):
    from src.core.database import Base, Team, TeamInvitation, TeamMember

    with DatabaseManager().get_session() as db:
        # Teams first, with every membership and invitation of them (and those sent or got by the account)
        team_ids = [m.team_id for m in db.query(TeamMember).filter(TeamMember.user_id == user_id)]
        db.query(TeamInvitation).filter(
            TeamInvitation.team_id.in_(team_ids) | (TeamInvitation.invited_by_id == user_id)
            | (TeamInvitation.user_id == user_id)).delete(synchronize_session=False)
        db.query(TeamMember).filter(TeamMember.team_id.in_(team_ids)).delete(synchronize_session=False)
        db.query(Team).filter(Team.id.in_(team_ids)).delete(synchronize_session=False)
        # Schedules (and their runs) of the account's repositories
        from src.core.database import AnalysisSchedule, Repository, ScheduledRun
        repo_ids = [r.id for r in db.query(Repository).filter(Repository.user_id == user_id)]
        schedule_ids = [x.id for x in db.query(AnalysisSchedule).filter(AnalysisSchedule.repository_id.in_(repo_ids))]
        db.query(ScheduledRun).filter(ScheduledRun.schedule_id.in_(schedule_ids)).delete(synchronize_session=False)
        db.query(AnalysisSchedule).filter(AnalysisSchedule.id.in_(schedule_ids)).delete(synchronize_session=False)
        # Then everything else the account owns that the ORM does not cascade (plugins, Slack and Discord settings ...)
        for table in Base.metadata.sorted_tables:
            if table.name not in ('users', 'repositories', 'sessions') and 'user_id' in table.c:
                db.execute(table.delete().where(table.c.user_id == user_id))
        db.commit()
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            db.delete(user)
            db.commit()


def make_issue(session, code_file, title='SQL Injection', severity=IssueSeverity.CRITICAL):
    issue = Issue(
        code_file_id=code_file.id, category=IssueCategory.SECURITY, severity=severity,
        rule_id='SEC001', title=title, description='Unsafe SQL query', line_number=3,
        code_snippet='q = "..." + x',
    )
    session.add(issue)
    session.commit()
    return issue


@pytest.fixture
def data(owner):
    """The owner's repository with an issue and a refactoring, plus a pull request file with an issue"""
    with DatabaseManager().get_session() as db:
        repository = Repository(user_id=owner.account['id'], name='mine', github_url='https://github.com/o/mine')
        db.add(repository)
        db.commit()
        file_ = CodeFile(repository_id=repository.id, file_path='app.py', file_hash='h1',
                         language='python', lines_of_code=200)
        db.add(file_)
        db.commit()
        issue = make_issue(db, file_)

        pull_request = PullRequest(repository_id=repository.id, pr_number=1, title='PR',
                                   source_branch='f', target_branch='main')
        db.add(pull_request)
        db.commit()
        pr_file = CodeFile(pull_request_id=pull_request.id, file_path='pr.py', file_hash='h2',
                           language='python', lines_of_code=50)
        db.add(pr_file)
        db.commit()
        pr_issue = make_issue(db, pr_file, title='From a PR', severity=IssueSeverity.WARNING)

        refactoring = Refactoring(issue_id=issue.id, code_file_id=file_.id, refactoring_type='simplify',
                                  original_code='a', refactored_code='b', explanation='why',
                                  confidence=0.9)
        db.add(refactoring)
        db.commit()
        yield {
            'repository': repository.id, 'issue': issue.id, 'pr_issue': pr_issue.id,
            'file': file_.id, 'refactoring': refactoring.id, 'pull_request': pull_request.id,
        }


class TestIssues:
    def test_the_owner_sees_their_issues_including_those_from_pull_requests(self, owner, data):
        body = owner.get('/api/issues').json()
        assert {i['id'] for i in body['issues']} == {data['issue'], data['pr_issue']}
        assert body['total'] == 2

    def test_another_account_sees_none(self, other, data):
        body = other.get('/api/issues').json()
        assert body['total'] == 0 and body['issues'] == []

    def test_filters_do_not_reach_across_accounts(self, other, data):
        for query in ('?severity=critical', f"?repository={data['repository']}", '?category=security', '?file_path=app'):
            assert other.get('/api/issues' + query).json()['issues'] == [], query

    def test_stats_count_only_own_issues(self, owner, other, data):
        assert owner.get('/api/issues/summary/stats').json()['total_issues'] == 2
        stats = other.get('/api/issues/summary/stats').json()
        assert stats['total_issues'] == 0 and stats['by_file'] == {}

    def test_detail_is_not_found_for_someone_else(self, owner, other, data):
        assert owner.get(f"/api/issues/{data['issue']}").status_code == 200
        assert other.get(f"/api/issues/{data['issue']}").status_code == 404
        assert other.get(f"/api/issues/{data['pr_issue']}").status_code == 404

    def test_dismiss_and_restore_only_work_on_own_issues(self, owner, other, data):
        assert other.post(f"/api/issues/{data['issue']}/dismiss").status_code == 404
        assert other.post(f"/api/issues/{data['issue']}/restore").status_code == 404
        with DatabaseManager().get_session() as db:
            assert db.query(Issue).get(data['issue']).dismissed is False
        assert owner.post(f"/api/issues/{data['issue']}/dismiss").status_code == 200
        assert owner.get('/api/issues/summary/stats').json()['total_issues'] == 1

    def test_someone_else_cannot_file_your_issue_on_github(self, other, data):
        assert other.post(f"/api/issues/{data['issue']}/create-github-issue").status_code == 404

    def test_health_score_is_not_shared(self, owner, other, data):
        assert owner.get('/api/analytics/health-score').json()['severity_counts']['critical'] == 1
        assert other.get('/api/analytics/health-score').json()['severity_counts'].get('critical', 0) == 0


class TestRefactorings:
    def test_list_and_stats_are_scoped(self, owner, other, data):
        assert owner.get('/api/refactorings').json()['total'] == 1
        assert other.get('/api/refactorings').json()['total'] == 0
        assert owner.get('/api/refactorings/stats/summary').json()['total'] == 1
        assert other.get('/api/refactorings/stats/summary').json()['total'] == 0

    def test_filters_cannot_pull_in_someone_elses(self, other, data):
        for query in (f"?issue_id={data['issue']}", f"?code_file_id={data['file']}", '?status=suggested'):
            assert other.get('/api/refactorings' + query).json()['total'] == 0, query

    @pytest.mark.parametrize('method,path', [
        ('get', ''), ('post', '/accept'), ('post', '/reject'), ('post', '/apply'),
    ])
    def test_by_id_actions_are_not_found_for_someone_else(self, owner, other, data, method, path):
        url = f"/api/refactorings/{data['refactoring']}{path}"
        assert getattr(other, method)(url).status_code == 404
        with DatabaseManager().get_session() as db:
            assert db.query(Refactoring).get(data['refactoring']).status.value == 'suggested'

    def test_the_owner_can_still_use_them(self, owner, data):
        assert owner.get(f"/api/refactorings/{data['refactoring']}").status_code == 200
        assert owner.post(f"/api/refactorings/{data['refactoring']}/accept").status_code == 200

    def test_cannot_attach_a_refactoring_to_someone_elses_issue(self, other, data):
        response = other.post('/api/refactorings', json={
            'issue_id': data['issue'], 'code_file_id': data['file'], 'refactoring_type': 'x',
            'original_code': 'a', 'refactored_code': 'b', 'explanation': 'e'})
        assert response.status_code == 404

    def test_cannot_pair_your_issue_with_someone_elses_file(self, owner, data):
        # The issue is the owner's, the file id is not the issue's file
        response = owner.post('/api/refactorings', json={
            'issue_id': data['issue'], 'code_file_id': 'not-its-file', 'refactoring_type': 'x',
            'original_code': 'a', 'refactored_code': 'b', 'explanation': 'e'})
        assert response.status_code == 404

    def test_auto_fix_is_not_available_on_someone_elses_issue(self, other, data):
        assert other.post(f"/api/refactor/auto-fix/{data['issue']}").status_code == 404


class TestAnalytics:
    def test_technical_debt_counts_only_own_files(self, owner, other, data):
        mine = owner.get('/api/technical-debt').json()
        assert mine['total_files'] == 2 and mine['total_issues'] == 2
        theirs = other.get('/api/technical-debt').json()
        assert theirs['total_files'] == 0 and theirs['total_issues'] == 0

    @pytest.mark.parametrize('suffix', ['health', 'trends', 'developers', 'heatmap', 'quality-gate'])
    def test_repository_analytics_need_ownership(self, owner, other, data, suffix):
        url = f"/api/analytics/repository/{data['repository']}/{suffix}"
        assert other.get(url).status_code == 404
        assert owner.get(url).status_code == 200

    @pytest.fixture
    def cached(self, owner):
        analysis_worker._analysis_cache.clear()
        analysis_worker._analysis_cache['job-mine'] = {
            'user_id': owner.account['id'], 'filename': 'mine.py', 'analyzed_at': _now(),
            'issues': [{'severity': 'critical', 'category': 'security', 'title': 'T', 'description': 'd'}],
            'report': {},
        }
        analysis_worker._analysis_cache['job-nobody'] = {
            'user_id': None, 'filename': 'old.py', 'analyzed_at': _now(),
            'issues': [{'severity': 'error', 'category': 'smell', 'title': 'T', 'description': 'd'}],
            'report': {},
        }
        yield
        analysis_worker._analysis_cache.clear()

    def test_dashboard_metrics_use_only_the_users_own_analyses(self, owner, other, cached):
        assert owner.get('/api/dashboard/metrics').json()['total_issues'] == 1
        assert other.get('/api/dashboard/metrics').json()['total_issues'] == 0

    def test_dashboard_activity_and_trends_are_scoped(self, owner, other, cached):
        assert [a['title'] for a in owner.get('/api/dashboard/activity').json() if a['type'] == 'analysis'] == ['Analyzed mine.py']
        assert other.get('/api/dashboard/activity').json() == []
        assert sum(day['critical'] for day in other.get('/api/dashboard/trends').json()) == 0

    def test_the_cached_issue_listing_and_detail_are_scoped(self, owner, other, cached):
        # With nothing in the database the issues list falls back to the cached analyses
        assert owner.get('/api/issues').json()['total'] == 1
        assert other.get('/api/issues').json()['total'] == 0
        assert other.get('/api/issues?job_id=job-mine').json()['issues'] == []
        assert other.get('/api/issues/mine.py_0').status_code == 404

    def test_other_cache_backed_analytics_are_scoped(self, other, cached):
        assert other.get('/api/analytics/repository').json()['total_issues'] == 0
        assert other.get('/api/analytics/export?format=json').status_code == 200

    def test_the_analysis_task_records_who_ran_it(self, owner):
        """The cache is only scoped if the worker writes the owner into every entry"""
        analysis_worker._analysis_cache.clear()
        try:
            task = analysis_worker.analyze_file_task
            args = ["import os\npassword = 'abc12345'\n", 'x.py', None, owner.account['id']]
            if hasattr(task, 'apply'):
                result = task.apply(args=args).result
            else:
                # Other test modules replace celery with a stub, leaving the plain function
                from types import SimpleNamespace
                fake_self = SimpleNamespace(request=SimpleNamespace(id='job-x'), update_state=lambda **kw: None)
                result = task(fake_self, *args)
            assert result['success']
            entry = next(iter(analysis_worker._analysis_cache.values()))
            assert entry['user_id'] == owner.account['id']
            assert [a['filename'] for a in analysis_worker.get_all_cached_analyses(owner.account['id'])] == ['x.py']
            assert analysis_worker.get_all_cached_analyses('someone-else') == []
        finally:
            analysis_worker._analysis_cache.clear()

    def test_cache_helper_filters_by_user(self, owner, cached):
        mine = analysis_worker.get_all_cached_analyses(owner.account['id'])
        assert [a['filename'] for a in mine] == ['mine.py']
        assert len(analysis_worker.get_all_cached_analyses()) == 2
        assert analysis_worker.get_all_cached_analyses('someone-else') == []


def _now():
    from datetime import datetime
    return datetime.now().isoformat()


class TestNotifications:
    @pytest.fixture
    def notifications(self, owner, other):
        from src.services.notification_service import NotificationType, notification_service
        notification_service.notifications.clear() if hasattr(notification_service, 'notifications') else None
        mine = notification_service.create_notification(
            NotificationType.INFO, 'Mine', 'm', user_id=owner.account['id'])
        theirs = notification_service.create_notification(
            NotificationType.INFO, 'Theirs', 't', user_id=other.account['id'])
        yield mine, theirs
        for n in (mine, theirs):
            notification_service.delete_notification(n['id'])

    def test_the_list_is_only_your_own_whatever_the_query_says(self, owner, other, notifications):
        mine, theirs = notifications
        assert [n['id'] for n in owner.get('/api/notifications').json()['notifications']] == [mine['id']]
        # user_id used to be a query parameter
        asked = owner.get(f"/api/notifications?user_id={other.account['id']}").json()['notifications']
        assert [n['id'] for n in asked] == [mine['id']]

    def test_by_id_endpoints_are_not_found_for_someone_else(self, owner, notifications):
        _, theirs = notifications
        assert owner.get(f"/api/notifications/{theirs['id']}").status_code == 404
        assert owner.post(f"/api/notifications/{theirs['id']}/read").status_code == 404
        assert owner.post(f"/api/notifications/{theirs['id']}/dismiss").status_code == 404
        assert owner.delete(f"/api/notifications/{theirs['id']}").status_code == 404

    def test_mark_all_read_leaves_other_accounts_alone(self, owner, notifications):
        from src.services.notification_service import notification_service
        _, theirs = notifications
        owner.post(f"/api/notifications/read-all?user_id={theirs['user_id']}")
        assert notification_service.get_notification(theirs['id'])['read'] is False

    def test_statistics_are_own(self, owner, other, notifications):
        assert owner.get('/api/notifications/statistics').json()['total'] == 1

    def test_own_notification_works(self, owner, notifications):
        mine, _ = notifications
        assert owner.get(f"/api/notifications/{mine['id']}").status_code == 200
        assert owner.post(f"/api/notifications/{mine['id']}/read").status_code == 200


class TestTeamsAndPullRequests:
    @pytest.fixture
    def team(self, owner):
        slug = f'iso-{uuid.uuid4().hex[:8]}'
        response = owner.post('/api/teams', json={'name': 'Iso', 'slug': slug})
        assert response.status_code == 200, response.text
        return response.json()['team']['id'] if 'team' in response.json() else response.json()['id']

    @pytest.mark.parametrize('suffix', ['', '/members', '/invitations', '/analytics', '/repositories',
                                        '/leaderboard', '/activity'])
    def test_team_data_is_for_members_only(self, owner, other, team, suffix):
        mine = owner.get(f'/api/teams/{team}{suffix}').status_code
        # /leaderboard fails for everyone (team_analytics_service queries Issue.repository_id, which
        # does not exist): not part of this change, so only require that the member is let in
        assert mine == 200 or (suffix == '/leaderboard' and mine == 500), suffix
        assert other.get(f'/api/teams/{team}{suffix}').status_code == 404, suffix

    def test_pull_request_review_endpoints_need_ownership(self, owner, other, data):
        url = f"/api/prs/{data['pull_request']}"
        assert other.get(f'{url}/approval-status').status_code == 404
        assert other.post(f'{url}/assign-reviewers', json={}).status_code == 404
        assert owner.get(f'{url}/approval-status').status_code != 404


class TestAdminLogs:
    @pytest.mark.parametrize('path', ['/api/logs', '/api/logs/errors', '/api/logs/statistics', '/api/logs/export'])
    def test_an_ordinary_account_cannot_read_the_logs(self, other, path):
        assert other.get(path).status_code == 403

    def test_an_admin_can(self, other):
        with DatabaseManager().get_session() as db:
            user = db.query(User).filter(User.id == other.account['id']).first()
            user.role = UserRole.ADMIN
            db.commit()
        assert other.get('/api/logs/statistics').status_code == 200
