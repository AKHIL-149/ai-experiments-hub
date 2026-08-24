"""
Shared helper for overriding the authenticated user in route tests.

`patch('server.get_current_user', return_value=mock_user)` looks correct
but never actually intercepts a real request: FastAPI's `Depends()`
captures the function object at route-decoration time (when server.py
is first imported), not a live name lookup - so rebinding the module
attribute `server.get_current_user` afterwards doesn't change what the
already-registered route calls. Every test using that pattern got a
real 401 from the real dependency instead of the mocked user, silently,
because TestClient still returns a normal HTTP response either way.

FastAPI's documented mechanism for this is `app.dependency_overrides`,
which is a dict FastAPI actually consults during dependency resolution.
"""
from contextlib import contextmanager


@contextmanager
def override_current_user(mock_user):
    from server import app, get_current_user

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@contextmanager
def override_current_user_optional(mock_user):
    """Same fix as override_current_user, for routes that depend on
    get_current_user_optional (page routes that render differently for
    logged-out visitors instead of 401ing)."""
    from server import app, get_current_user_optional

    app.dependency_overrides[get_current_user_optional] = lambda: mock_user
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user_optional, None)
