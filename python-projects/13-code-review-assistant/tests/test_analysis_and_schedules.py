"""
The analysis flow and the Schedules feature, found by running them.

  - the Analyze page said "No results available" after every successful analysis: the task marked itself
    SUCCESS with update_state(), and Celery then refused to store the report the task returned
  - the page's checkboxes name the Python analyzers, so a JavaScript or Java upload came back with no issues
  - nothing reported SQL injection in Python or JavaScript (the README lists it), Java reported one statement
    twice, yaml.load() went unreported and `password_field = "Password"` was a "critical" hardcoded secret
  - every Schedules endpoint failed with `name 'get_db_session' is not defined`, and once that was fixed the
    worker called CodeAnalyzerService with the wrong arguments and read results in the wrong shape; its
    file patterns were globbed unchecked, so '../../*' could analyze files anywhere on the server
  - schedule values were stored unchecked (a bogus type or cron expression, an interval of 10**12 minutes,
    any webhook URL)
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import server
from src.analyzers.analyzer_registry import AnalyzerRegistry
from src.analyzers.base_analyzer import BaseAnalyzer, CodeIssue, IssueCategory, IssueSeverity
from src.core.database import (
    AnalysisSchedule, DatabaseManager, Issue, Repository, ScheduledRun,
)
from src.services.code_analyzer_service import CodeAnalyzerService
from src.services.schedule_service import (
    MAX_INTERVAL_MINUTES, ScheduleService, normalize_timing, validate_fields,
)
from src.workers import analysis_worker, schedule_worker
from tests.test_data_isolation import make_account, _delete_user


def rules(code, file_path='t.py', analyzer_ids=None):
    result = CodeAnalyzerService().analyze_code(source_code=code, file_path=file_path, analyzer_ids=analyzer_ids)
    assert result['success'], result
    return [(i['rule_id'], i['line_number']) for i in result['report']['issues']]


class TestPythonSqlInjection:
    @pytest.mark.parametrize('code', [
        'def q(cur, u):\n    cur.execute("SELECT * FROM users WHERE name = \'" + u + "\'")\n',
        'def q(cur, u):\n    cur.execute(f"SELECT * FROM users WHERE name = \'{u}\'")\n',
        'def q(cur, u):\n    cur.execute("SELECT * FROM users WHERE name = \'%s\'" % u)\n',
        'def q(cur, u):\n    cur.execute("SELECT * FROM users WHERE name = \'%s\'" % (u,))\n',
        'def q(cur, u):\n    cur.execute("SELECT * FROM users WHERE name = %(a)s" % {"a": u})\n',
        'def q(cur, u):\n    cur.execute("SELECT * FROM users WHERE name = \'{}\'".format(u))\n',
        'def q(cur, u):\n    cur.execute("DELETE FROM users WHERE id = " + str(u))\n',
        'def q(cur, u):\n    sql = "SELECT * FROM users WHERE name = \'" + u + "\'"\n    cur.execute(sql)\n',
        'def q(cur, u):\n    sql = "SELECT * FROM users"\n    sql += " WHERE name = \'" + u + "\'"\n    cur.execute(sql)\n',
        'def q(cur, u):\n    cur.executemany("INSERT INTO t VALUES (" + u + ")", [])\n',
        'def q(db, u):\n    db.session.execute("UPDATE t SET a = 1 WHERE id = " + u)\n',
        'def q(cur, u):\n    cur.execute(sql="SELECT * FROM t WHERE a = " + u)\n',
        'class A:\n    def q(self, u):\n        self.cur.execute(f"SELECT 1 FROM t WHERE a = {u}")\n',
    ])
    def test_a_query_built_from_a_value_is_reported(self, code):
        found = rules(code)
        assert any(rule == 'SEC001' for rule, _ in found), code

    @pytest.mark.parametrize('code', [
        'def q(cur, u):\n    cur.execute("SELECT * FROM users WHERE name = %s", (u,))\n',
        'def q(cur, u):\n    cur.execute("SELECT * FROM users WHERE name = ?", [u])\n',
        'def q(cur):\n    cur.execute("SELECT * FROM " + "users")\n',
        'def q(cur):\n    cur.execute("SELECT * FROM t WHERE a = %s" % ("x",))\n',
        'def q(cur):\n    cur.execute("SELECT * FROM users")\n',
        'def q(cur):\n    sql = "SELECT * FROM users"\n    cur.execute(sql)\n',
        'def q(cur, u):\n    print("select " + u)\n',
        'def q(job, u):\n    job.run("please select " + u)\n',
        'def q(cur, u):\n    cur.execute(u)\n',
    ])
    def test_parameterized_and_constant_queries_are_not(self, code):
        assert [r for r, _ in rules(code) if r == 'SEC001'] == [], code

    def test_it_points_at_the_line_of_the_call_once(self):
        code = 'def q(cur, u):\n    sql = "SELECT * FROM t WHERE a = " + u\n    cur.execute(sql)\n'
        assert [item for item in rules(code) if item[0] == 'SEC001'] == [('SEC001', 3)]

    def test_the_finding_is_critical_and_explains_the_fix(self):
        result = CodeAnalyzerService().analyze_code(
            source_code='def q(cur, u):\n    cur.execute(f"SELECT 1 FROM t WHERE a = {u}")\n', file_path='t.py')
        issue = next(i for i in result['report']['issues'] if i['rule_id'] == 'SEC001')
        assert issue['severity'] == 'critical' and 'parameters' in issue['suggestion']


class TestOtherPythonRules:
    @pytest.mark.parametrize('code', [
        'import yaml\nx = yaml.load(data)\n',
        'import yaml\nx = yaml.load(data, Loader=yaml.Loader)\n',
        'import yaml\nx = yaml.load(data, yaml.UnsafeLoader)\n',
        'import yaml\nx = yaml.load_all(data)\n',
    ])
    def test_unsafe_yaml_is_reported(self, code):
        assert [r for r, _ in rules(code) if r == 'SEC006']

    @pytest.mark.parametrize('code', [
        'import yaml\nx = yaml.safe_load(data)\n',
        'import yaml\nx = yaml.load(data, Loader=yaml.SafeLoader)\n',
        'import yaml\nx = yaml.load(data, yaml.SafeLoader)\n',
    ])
    def test_safe_yaml_is_not(self, code):
        assert [r for r, _ in rules(code) if r == 'SEC006'] == []

    @pytest.mark.parametrize('code', [
        'password_field = "Password"\n', 'PASSWORD_LABEL = "Password:"\n', 'token_url = "https://x.com/token"\n',
        'secret_name = "my-secret"\n', 'password = "Enter your password"\n', 'api_key_header = "X-Api-Key"\n',
        'password_min_length = "8"\n',
    ])
    def test_names_and_labels_are_not_secrets(self, code):
        assert [r for r, _ in rules(code) if r == 'SEC004'] == [], code

    @pytest.mark.parametrize('code', [
        'password = "secret"\n', 'password = "hunter2hunter2"\n', 'api_key = "abc12345"\n', 'token = "abc123"\n',
        'SECRET_KEY = "dev-key-123"\n', 'db_password = "postgres"\n',
    ])
    def test_real_looking_secrets_still_are(self, code):
        assert [r for r, _ in rules(code) if r == 'SEC004'], code

    def test_rule_ids_include_the_new_one(self):
        from src.analyzers.security_analyzer import SecurityAnalyzer
        assert 'SEC001' in SecurityAnalyzer().get_rule_ids()


class TestJavaScriptSqlInjection:
    @pytest.mark.parametrize('code', [
        'db.query("SELECT * FROM t WHERE id=" + req.query.id);\n',
        "db.query('SELECT * FROM t WHERE id=' + id);\n",
        'db.query(`SELECT * FROM t WHERE id=${req.query.id}`);\n',
        'db.run("INSERT INTO t VALUES (\'" + v + "\')");\n',
        'db.execute("DELETE FROM t WHERE a = " + a + " AND b = 1");\n',
        'const sql = "SELECT * FROM t WHERE id=" + id;\ndb.query(sql);\n',
        'const sql = `UPDATE t SET a = ${a} WHERE id = 1`;\n',
        'knex.raw("SELECT * FROM t WHERE a = " + a);\n',
    ])
    def test_a_query_built_from_a_value_is_reported(self, code):
        assert [r for r, _ in rules(code, 'a.js') if r == 'JS-SEC007'], code

    @pytest.mark.parametrize('code', [
        'db.query("SELECT * FROM t WHERE id = ?", [id]);\n',
        'db.query("SELECT * FROM t");\n',
        'const msg = "select an option " + x;\n',
        'const label = `Select a ${thing} to delete from the list`;\n',
        'logger.info("update " + name);\n',
    ])
    def test_placeholders_and_sentences_are_not(self, code):
        assert [r for r, _ in rules(code, 'a.js') if r == 'JS-SEC007'] == [], code

    def test_each_line_is_reported_once(self):
        code = 'const sql = "SELECT * FROM t WHERE id=" + id;\ndb.query("SELECT * FROM t WHERE id=" + id);\n'
        lines = [line for rule, line in rules(code, 'a.js') if rule == 'JS-SEC007']
        assert sorted(lines) == [1, 2]


class TestDuplicateFindings:
    def test_java_reports_one_statement_once(self):
        code = ('class A { void f(java.sql.Statement st, String u) throws Exception {\n'
                '  st.executeQuery("select * from t where n=\'" + u + "\'"); } }\n')
        found = [item for item in rules(code, 'A.java') if item[0] == 'JAVA-SEC001']
        assert len(found) == len(set(found)) == 1

    def test_the_registry_keeps_one_finding_per_rule_place_and_title(self):
        class Twice(BaseAnalyzer):
            analyzer_id = 'twice'
            category = IssueCategory.SECURITY

            def analyze(self, parsed_module, source_code):
                make = lambda title, line: CodeIssue(
                    category=IssueCategory.SECURITY, severity=IssueSeverity.ERROR, rule_id='R1', title=title,
                    description='d', file_path='f.py', line_number=line)
                return [make('same', 3), make('same', 3), make('same', 4), make('other', 3)]

        registry = AnalyzerRegistry()
        registry.register_analyzer(Twice())
        found = registry.analyze(SimpleNamespace(file_path='f.py'), 'x', analyzer_ids=['twice'])
        assert [(i.title, i.line_number) for i in found] == [('same', 3), ('same', 4), ('other', 3)]


class TestAnalyzerNamesFromThePage:
    JS = 'const a = 1;\neval(req.query.q);\ndb.query("SELECT * FROM t WHERE id=" + id);\n'
    JAVA = ('class A { String password = "supersecret123"; void f(java.sql.Statement st, String u) throws Exception {\n'
            '  st.executeQuery("select * from t where n=\'" + u + "\'"); } }\n')

    FORM = ['security', 'smell', 'complexity']

    def test_javascript_gets_its_own_analyzers(self):
        # security/smell/complexity are the Python analyzers' ids: a JS file used to get nothing
        assert {r for r, _ in rules(self.JS, 'a.js', self.FORM)} >= {'JS-SEC001', 'JS-SEC007'}

    def test_java_gets_its_own_analyzers(self):
        assert {r for r, _ in rules(self.JAVA, 'A.java', self.FORM)} >= {'JAVA-SEC001', 'JAVA-SEC006'}

    def test_python_is_unchanged(self):
        assert [r for r, _ in rules('password = "hunter2hunter2"\n', 'a.py', self.FORM)] == ['SEC004']

    def test_one_choice_means_that_kind_of_analysis(self):
        only_security = {r for r, _ in rules(self.JS, 'a.js', ['security'])}
        assert 'JS-SEC001' in only_security and not any(r.startswith('JS-SMELL') for r in only_security)

    def test_a_choice_the_language_does_not_have_finds_nothing(self):
        assert rules(self.JS, 'a.js', ['complexity']) == []

    def test_exact_ids_and_unknown_names(self):
        service = CodeAnalyzerService()
        assert service._analyzer_ids_for_language(['javascript-security'], 'javascript') == ['javascript-security']
        assert service._analyzer_ids_for_language(['nonsense'], 'javascript') == []
        assert service._analyzer_ids_for_language(['security', 'security'], 'java') == ['java_security']


def run_task(task, *args):
    """Run a Celery task body in this process (some test modules replace celery with a stub)"""
    if hasattr(task, 'apply'):
        return task.apply(args=args).result
    fake_self = SimpleNamespace(
        request=SimpleNamespace(id='job-test'), db=DatabaseManager(), update_state=Mock())
    return task(fake_self, *args)


class TestAnalysisTaskResult:
    CODE = "import os\npassword = 'abc12345'\nos.system('ls ' + input())\n"

    def test_the_task_returns_the_report_the_page_needs(self):
        analysis_worker._analysis_cache.clear()
        result = run_task(analysis_worker.analyze_file_task, self.CODE, 'x.py', None, None)
        analysis_worker._analysis_cache.clear()
        # analyze.html reads result.success, result.report.total_issues, report.stats.code_lines, report.health_score...
        assert result['success'] is True
        report = result['report']
        assert report['total_issues'] == 2 and report['issues'][0]['rule_id']
        assert 'code_lines' in report['stats'] and 'overall_score' in report['health_score']
        assert result['issues_found'] == 2 and result['status'] == 'Analysis complete'
        assert result['health_score'] == report['health_score']['overall_score']
        assert result['code_file_id'] is None          # nobody to save it for

    def test_it_never_marks_itself_successful_early(self):
        # Celery keeps a result that is already SUCCESS, so the returned report was thrown away
        states = []
        fake_self = SimpleNamespace(request=SimpleNamespace(id='job-1'),
                                    update_state=lambda **kw: states.append(kw.get('state')))
        task = analysis_worker.analyze_file_task
        body = task.__wrapped__ if hasattr(task, '__wrapped__') else task
        if hasattr(task, 'run'):
            body = task.run.__func__
        body(fake_self, self.CODE, 'x.py', None, None)
        analysis_worker._analysis_cache.clear()
        assert 'SUCCESS' not in states and states == ['PROCESSING']

    def test_a_parse_error_comes_back_as_an_error_not_a_report(self):
        result = run_task(analysis_worker.analyze_file_task, 'def (:\n x =', 'bad.py', None, None)
        analysis_worker._analysis_cache.clear()
        assert result['success'] is False and 'Syntax error' in result['error']

    def test_the_result_is_saved_for_the_account_and_shown_on_the_issues_page(self):
        owner = make_account('analysis')
        try:
            result = run_task(analysis_worker.analyze_file_task, self.CODE, 'saved.py', None, owner.account['id'])
            analysis_worker._analysis_cache.clear()
            assert result['code_file_id']
            issues = owner.get('/api/issues').json()
            assert issues['total'] == 2 and {i['file_path'] for i in issues['issues']} == {'saved.py'}
        finally:
            _delete_user(owner.account['id'])


@pytest.fixture
def owner():
    client = make_account('sched')
    yield client
    _delete_user(client.account['id'])


@pytest.fixture
def repository(owner, tmp_path):
    """A 'cloned' repository on disk"""
    (tmp_path / 'app.py').write_text('def q(cur, u):\n    cur.execute("SELECT * FROM t WHERE a = " + u)\n')
    (tmp_path / 'util.py').write_text('x = 1\n')
    (tmp_path / 'web.js').write_text('eval(input);\n')
    (tmp_path / 'notes.txt').write_text('not source\n')
    (tmp_path / 'src').mkdir()
    (tmp_path / 'src' / 'deep.py').write_text('password = "hunter2hunter2"\n')
    (tmp_path / 'node_modules').mkdir()
    (tmp_path / 'node_modules' / 'dep.py').write_text('password = "should-not-be-read"\n')
    (tmp_path / '.git').mkdir()
    (tmp_path / '.git' / 'hook.py').write_text('password = "nor-this-one"\n')
    with DatabaseManager().get_session() as db:
        repo = Repository(user_id=owner.account['id'], name='cloned', github_url='https://github.com/o/cloned',
                          clone_path=str(tmp_path))
        db.add(repo)
        db.commit()
        return SimpleNamespace(id=repo.id, path=tmp_path)


class TestScheduleValidation:
    @pytest.mark.parametrize('kind,cron,interval', [
        ('cron', '*/5 * * * *', None), ('interval', None, 1), ('interval', None, MAX_INTERVAL_MINUTES),
        ('daily', None, None), ('weekly', 'ignored', None),
    ])
    def test_good_timing(self, kind, cron, interval):
        result = normalize_timing(kind, cron, interval)
        assert {'daily': '0 0 * * *', 'weekly': '0 0 * * 0'}.get(kind, cron) == result

    @pytest.mark.parametrize('kind,cron,interval,message', [
        ('bogus', None, None, 'Invalid schedule type'), (None, None, None, 'Invalid schedule type'),
        ('cron', None, None, 'Cron expression required'), ('cron', 'nope', None, 'Invalid cron'),
        ('cron', '* * * * * * * *', None, 'Invalid cron'), ('cron', 5, None, 'Cron expression required'),
        ('cron', '*' * 200, None, 'Invalid cron'),
        ('interval', None, None, 'Interval minutes'), ('interval', None, 0, 'Interval minutes'),
        ('interval', None, -5, 'Interval minutes'), ('interval', None, 10 ** 12, 'Interval minutes'),
        ('interval', None, 1.5, 'Interval minutes'), ('interval', None, True, 'Interval minutes'),
        ('interval', None, '60', 'Interval minutes'),
    ])
    def test_bad_timing(self, kind, cron, interval, message):
        with pytest.raises(ValueError, match=message):
            normalize_timing(kind, cron, interval)

    @pytest.mark.parametrize('fields,message', [
        ({'name': None}, 'Name is required'), ({'name': '   '}, 'Name is required'),
        ({'name': 5}, 'Name must be text'), ({'name': 'x' * 201}, 'at most 200'),
        ({'description': 'x' * 2001}, 'at most 2000'),
        ({'severity_threshold': 'loud'}, 'Severity threshold'),
        ({'slack_webhook_url': 'http://169.254.169.254/x'}, 'must start with https://hooks.slack.com/'),
        ({'slack_webhook_url': 'https://hooks.slack.com.evil.example/x'}, 'must start with'),
        ({'slack_webhook_url': 'https://hooks.slack.com/' + 'x' * 600}, 'at most 500'),
        ({'file_patterns': 'src/*.py'}, 'list of text'), ({'file_patterns': [1]}, 'list of text'),
        ({'file_patterns': ['../../*']}, 'inside the repository'),
        ({'file_patterns': ['/etc/*']}, 'inside the repository'),
        ({'file_patterns': ['a/../../b']}, 'inside the repository'),
        ({'file_patterns': ['x'] * 51}, 'at most 50'),
        ({'enabled_rules': ['R'] * 201}, 'at most 200'),
        ({'notification_emails': ['no-at-sign']}, 'Invalid notification email'),
        ({'notification_emails': ['a b@c.co']}, 'Invalid notification email'),
        ({'notification_emails': ['<x>@c.co']}, 'Invalid notification email'),
        ({'notification_emails': ['a@b.co'] * 21}, 'at most 20'),
        ({'enabled': 'yes'}, 'true or false'), ({'notify_on_issues': 1}, 'true or false'),
    ])
    def test_bad_fields(self, fields, message):
        with pytest.raises(ValueError, match=message):
            validate_fields(fields)

    def test_good_fields_are_cleaned(self):
        cleaned = validate_fields({
            'name': '  Nightly  ', 'description': None, 'severity_threshold': 'error',
            'slack_webhook_url': 'https://hooks.slack.com/services/T/B/x', 'file_patterns': ['src/**/*.py'],
            'notification_emails': ['a@b.co'], 'enabled': True})
        assert cleaned['name'] == 'Nightly' and cleaned['description'] is None

    def test_only_present_fields_are_checked(self):
        assert validate_fields({'enabled': False}) == {'enabled': False}


class TestScheduleApi:
    @pytest.fixture(autouse=True)
    def queue(self, monkeypatch):
        self.delay = Mock(return_value=Mock(id='run-task-1'))
        monkeypatch.setattr(schedule_worker.run_scheduled_analysis, 'delay', self.delay, raising=False)

    def make(self, owner, repository, **kw):
        return owner.post('/api/schedules', json={
            'repository_id': repository.id, 'name': 'Nightly', 'schedule_type': 'interval',
            'interval_minutes': 60, **kw})

    def test_the_whole_cycle_works(self, owner, repository):
        # Every one of these returned 500 "name 'get_db_session' is not defined"
        created = self.make(owner, repository)
        assert created.status_code == 200, created.text
        sid = created.json()['id']
        assert owner.get('/api/schedules').json()['schedules'][0]['id'] == sid
        assert owner.get(f'/api/schedules/{sid}').json()['name'] == 'Nightly'
        assert owner.put(f'/api/schedules/{sid}', json={'name': 'Renamed'}).json()['name'] == 'Renamed'
        assert owner.post(f'/api/schedules/{sid}/toggle', json={'enabled': False}).json()['enabled'] is False
        run = owner.post(f'/api/schedules/{sid}/trigger')
        assert run.status_code == 200 and run.json()['status'] == 'pending'
        self.delay.assert_called_once()
        assert owner.get(f'/api/schedules/{sid}/runs').json()['runs'][0]['id'] == run.json()['id']
        assert owner.get(f"/api/runs/{run.json()['id']}").status_code == 200
        assert owner.delete(f'/api/schedules/{sid}').status_code == 200
        assert owner.get(f'/api/schedules/{sid}').status_code == 404

    @pytest.mark.parametrize('changes,message', [
        ({'schedule_type': 'bogus'}, 'Invalid schedule type'), ({'schedule_type': 'cron'}, 'Cron expression required'),
        ({'schedule_type': 'cron', 'cron_expression': 'x'}, 'Invalid cron'),
        ({'interval_minutes': 10 ** 12}, 'Interval minutes'), ({'name': None}, 'Name is required'),
        ({'slack_webhook_url': 'http://localhost:6379'}, 'must start with'),
        ({'file_patterns': ['../../etc/*']}, 'inside the repository'),
    ])
    def test_bad_values_are_a_400_with_the_reason(self, owner, repository, changes, message):
        response = self.make(owner, repository, **changes)
        assert response.status_code == 400 and message in response.json()['detail']
        sid = self.make(owner, repository).json()['id']
        response = owner.put(f'/api/schedules/{sid}', json=changes)
        assert response.status_code == 400 and message in response.json()['detail']
        # and the schedule is as it was
        assert owner.get(f'/api/schedules/{sid}').json()['interval_minutes'] == 60

    def test_a_missing_repository_is_a_404(self, owner):
        response = owner.post('/api/schedules', json={
            'repository_id': 'nope', 'name': 'x', 'schedule_type': 'daily'})
        assert response.status_code == 404
        assert owner.post('/api/schedules', json={'name': 'x', 'schedule_type': 'daily'}).status_code == 404

    def test_switching_to_cron_with_an_expression_recalculates_the_next_run(self, owner, repository):
        sid = self.make(owner, repository).json()['id']
        before = owner.get(f'/api/schedules/{sid}').json()['next_run_at']
        changed = owner.put(f'/api/schedules/{sid}', json={
            'schedule_type': 'cron', 'cron_expression': '0 3 * * *'}).json()
        assert changed['cron_expression'] == '0 3 * * *' and changed['next_run_at'] != before

    def test_daily_and_weekly_get_their_fixed_expression(self, owner, repository):
        created = owner.post('/api/schedules', json={
            'repository_id': repository.id, 'name': 'd', 'schedule_type': 'daily'}).json()
        assert created['cron_expression'] == '0 0 * * *'
        assert owner.put(f"/api/schedules/{created['id']}", json={'schedule_type': 'weekly'}).json()['cron_expression'] == '0 0 * * 0'

    def test_unknown_fields_are_ignored_not_stored(self, owner, repository):
        sid = self.make(owner, repository).json()['id']
        response = owner.put(f'/api/schedules/{sid}', json={'repository_id': 'other', 'created_by_id': 'x', 'name': 'ok'})
        assert response.status_code == 200 and response.json()['repository_id'] == repository.id

    def test_someone_elses_schedule_is_not_found(self, owner, repository):
        sid = self.make(owner, repository).json()['id']
        other = make_account('schedother')
        try:
            for method, path, body in [
                ('get', f'/api/schedules/{sid}', None), ('put', f'/api/schedules/{sid}', {'name': 'x'}),
                ('delete', f'/api/schedules/{sid}', None), ('post', f'/api/schedules/{sid}/trigger', None),
                ('post', f'/api/schedules/{sid}/toggle', {'enabled': False}), ('get', f'/api/schedules/{sid}/runs', None),
            ]:
                response = getattr(other, method)(path, **({'json': body} if body is not None else {}))
                assert response.status_code == 404, (method, path, response.text)
                # the same answer as for a schedule that does not exist
                assert 'not found' in response.json()['detail'].lower(), (method, path)
            assert other.post('/api/schedules', json={
                'repository_id': repository.id, 'name': 'x', 'schedule_type': 'daily'}).status_code == 404
            assert other.get('/api/schedules').json()['schedules'] == []
        finally:
            _delete_user(other.account['id'])
        self.delay.assert_not_called()

    def test_the_run_of_someone_elses_schedule_is_not_readable(self, owner, repository):
        sid = self.make(owner, repository).json()['id']
        run_id = owner.post(f'/api/schedules/{sid}/trigger').json()['id']
        other = make_account('runother')
        try:
            assert other.get(f'/api/runs/{run_id}').status_code == 404
        finally:
            _delete_user(other.account['id'])

    def test_the_page_renders_for_the_account(self, owner):
        page = owner.get('/schedules')
        assert page.status_code == 200 and owner.account['username'] in page.text

    def test_list_runs_has_a_bounded_limit(self, owner, repository):
        sid = self.make(owner, repository).json()['id']
        assert owner.get(f'/api/schedules/{sid}/runs?limit=0').status_code == 422
        assert owner.get(f'/api/schedules/{sid}/runs?limit=5000').status_code == 422


class TestScheduledAnalysis:
    def collect(self, root, patterns=None, all_files=True):
        found = schedule_worker.collect_source_files(
            root.resolve(), patterns, all_files, CodeAnalyzerService().parser_registry.get_supported_extensions())
        return [str(p.relative_to(root.resolve())) for p in found]

    def test_source_files_only_and_not_dependencies_or_git_internals(self, repository):
        assert self.collect(repository.path) == ['app.py', 'src/deep.py', 'util.py', 'web.js']

    def test_patterns_narrow_the_files(self, repository):
        assert self.collect(repository.path, ['src/**/*.py'], all_files=False) == ['src/deep.py']
        assert self.collect(repository.path, ['*.js'], all_files=False) == ['web.js']
        assert self.collect(repository.path, ['app.py'], all_files=True) == ['app.py']

    @pytest.mark.parametrize('pattern', ['../*', '../../*', '../**/*.py'])
    def test_patterns_cannot_leave_the_repository(self, repository, tmp_path_factory, pattern):
        outside = repository.path.parent / 'outside_secret.py'
        outside.write_text('password = "outside-the-repository"\n')
        try:
            assert all(name != 'outside_secret.py' and '..' not in name
                       for name in self.collect(repository.path, [pattern], all_files=False))
        finally:
            outside.unlink()

    def test_a_symlink_to_a_file_elsewhere_is_not_followed(self, repository, tmp_path_factory):
        elsewhere = tmp_path_factory.mktemp('elsewhere') / 'secret.py'
        elsewhere.write_text('password = "somewhere-else"\n')
        (repository.path / 'link.py').symlink_to(elsewhere)
        assert 'link.py' not in self.collect(repository.path)

    def test_large_files_and_the_file_count_are_bounded(self, repository, monkeypatch):
        (repository.path / 'huge.py').write_text('x = 1\n' * (schedule_worker.MAX_SCHEDULED_FILE_BYTES // 6 + 100))
        assert 'huge.py' not in self.collect(repository.path)
        monkeypatch.setattr(schedule_worker, 'MAX_SCHEDULED_FILES', 2)
        assert len(self.collect(repository.path)) == 2

    def make_run(self, repository, **fields):
        with DatabaseManager().get_session() as db:
            settings = dict(
                repository_id=repository.id, name='n', schedule_type='interval', interval_minutes=60,
                analyze_all_files=True, severity_threshold='info', notify_on_completion=False,
                notify_on_issues=False, enabled=True, next_run_at=datetime.now(timezone.utc),
                created_by_id=db.query(Repository).get(repository.id).user_id)
            schedule = AnalysisSchedule(**{**settings, **fields})
            db.add(schedule)
            db.commit()
            run = ScheduledRun(schedule_id=schedule.id, status='pending')
            db.add(run)
            db.commit()
            return run.id

    def finished(self, run_id):
        with DatabaseManager().get_session() as db:
            run = db.query(ScheduledRun).get(run_id)
            db.refresh(run)
            return run

    def test_a_run_analyzes_the_repository_and_reports_what_it_found(self, repository):
        run_id = self.make_run(repository)
        result = run_task(schedule_worker.run_scheduled_analysis, run_id)
        # the worker called CodeAnalyzerService(session) and analyze_code(code=...): every run "failed"
        assert result['success'] is True, result
        run = self.finished(run_id)
        assert run.status == 'completed' and run.files_analyzed == 4
        assert run.issues_found == 3 and run.critical_issues == 3
        summary = json.loads(run.result_summary)
        assert {i['rule_id'] for i in summary['top_issues']} == {'SEC001', 'SEC004', 'JS-SEC001'}
        assert summary['issues_by_category'] == {'security': 3}

    def test_the_severity_threshold_filters(self, repository):
        run_id = self.make_run(repository, **{})
        with DatabaseManager().get_session() as db:
            run = db.query(ScheduledRun).get(run_id)
            db.query(AnalysisSchedule).get(run.schedule_id).severity_threshold = 'critical'
            db.commit()
        run_task(schedule_worker.run_scheduled_analysis, run_id)
        assert self.finished(run_id).issues_found == 3
        (repository.path / 'warn.py').write_text('import os\nx = 1\n' + 'def f(a,b,c,d,e,f,g,h):\n  pass\n')

    def test_enabled_rules_filter_the_findings(self, repository):
        run_id = self.make_run(repository, enabled_rules=json.dumps(['SEC001']))
        run_task(schedule_worker.run_scheduled_analysis, run_id)
        run = self.finished(run_id)
        assert run.status == 'completed' and run.issues_found == 1

    def test_a_pattern_run_analyzes_only_those_files(self, repository):
        run_id = self.make_run(repository, file_patterns=json.dumps(['src/**/*.py']))
        run_task(schedule_worker.run_scheduled_analysis, run_id)
        run = self.finished(run_id)
        assert run.files_analyzed == 1 and run.issues_found == 1

    def test_stored_patterns_that_climb_out_are_still_confined(self, repository):
        # A schedule saved before the check existed
        outside = repository.path.parent / 'stored_outside.py'
        outside.write_text('password = "outside-the-repository"\n')
        try:
            run_id = self.make_run(repository, analyze_all_files=False, file_patterns=json.dumps(['../*.py']))
            run_task(schedule_worker.run_scheduled_analysis, run_id)
            run = self.finished(run_id)
            # 'src/../*.py' is the repository's own top folder; the file beside the repository has the
            # only hardcoded password among these, and it must not be read
            rules = {i['rule_id'] for i in json.loads(run.result_summary)['top_issues']}
            assert run.status == 'completed' and 'SEC004' not in rules
        finally:
            outside.unlink()

    def test_a_missing_clone_is_a_failed_run_with_the_reason(self, repository):
        with DatabaseManager().get_session() as db:
            db.query(Repository).get(repository.id).clone_path = '/nonexistent/clone'
            db.commit()
        run_id = self.make_run(repository)
        result = run_task(schedule_worker.run_scheduled_analysis, run_id)
        run = self.finished(run_id)
        assert result['success'] is False and run.status == 'failed'
        assert 'Repository path not found' in run.error_message

    def test_patterns_are_required_when_not_analyzing_everything(self, repository):
        run_id = self.make_run(repository, analyze_all_files=False)
        run_task(schedule_worker.run_scheduled_analysis, run_id)
        run = self.finished(run_id)
        assert run.status == 'failed' and 'file_patterns required' in run.error_message

    def test_a_file_that_cannot_be_parsed_does_not_fail_the_run(self, repository):
        (repository.path / 'broken.py').write_text('def (:\n x =')
        run_id = self.make_run(repository)
        run_task(schedule_worker.run_scheduled_analysis, run_id)
        run = self.finished(run_id)
        assert run.status == 'completed' and run.files_analyzed == 4
