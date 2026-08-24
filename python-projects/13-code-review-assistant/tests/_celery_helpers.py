"""
Shared Celery task-decorator mock for tests that stub out celery_app
before importing server.py, to avoid needing a real broker connection.

`lambda *args, **kwargs: lambda f: f` (the pattern this used to be
duplicated as, in 18 test files) is a bare identity decorator - it
strips `.delay()`/`.apply_async()` entirely, so any route that calls
task.delay(...) (e.g. POST /api/analyze/file, POST /api/repositories)
got a real AttributeError -> 500 the moment that route ran under
whichever of these files' mock happened to be the one still active in
sys.modules (module-level `sys.modules['celery_app'] = ...` assignments
race across files - whichever mock was set last when analysis_worker.py
first got imported determined behavior for the entire test session).
"""
from unittest.mock import Mock


def mock_task_decorator(*args, **kwargs):
    def decorator(f):
        f.delay = Mock(return_value=Mock(id='mock-task-id'))
        f.apply_async = Mock(return_value=Mock(id='mock-task-id'))
        return f
    return decorator
