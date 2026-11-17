"""Serving the built web app: the page, the hashed assets, the security headers, and that the API stays behind its gate"""
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import web
from tests.conftest import use_settings


@pytest.fixture
def dist(tmp_path):
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text('<!doctype html><title>App</title><script type="module" src="/assets/app-abc123.js"></script><div id="root"></div>')
    (d / "assets" / "app-abc123.js").write_text("console.log('hi')")
    (d / "assets" / "app-abc123.css").write_text("body{margin:0}")
    return d


def make_app(dist):
    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"pong": True}

    web.mount_frontend(app, dist)
    return TestClient(app)


# ---------------------------------------------------------------- the page

def test_root_serves_the_app_page(dist):
    r = make_app(dist).get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert '<div id="root">' in r.text


@pytest.mark.parametrize("path", ["/graph", "/graph/anything/deep", "/documents", "/some/unknown/address", "/index.html", "/favicon.ico"])
def test_any_other_address_gets_the_app_page(dist, path):
    r = make_app(dist).get(path)
    assert r.status_code == 200
    assert '<div id="root">' in r.text


def test_the_page_has_a_strict_content_security_policy_and_no_cache(dist):
    h = make_app(dist).get("/").headers
    csp = h["content-security-policy"]
    assert "script-src 'self'" in csp
    assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]     # no inline script
    assert "'unsafe-eval'" not in csp
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "base-uri 'self'" in csp
    assert "connect-src 'self'" in csp
    assert h["x-frame-options"] == "DENY"
    assert h["x-content-type-options"] == "nosniff"
    assert h["referrer-policy"] == "same-origin"
    assert h["cache-control"] == "no-cache"


def test_the_policy_allows_only_this_server(dist):
    csp = make_app(dist).get("/").headers["content-security-policy"]
    assert not re.search(r"https?://|\*", csp)


# ---------------------------------------------------------------- assets

def test_assets_are_served_and_cached_for_a_year(dist):
    c = make_app(dist)
    r = c.get("/assets/app-abc123.js")
    assert r.status_code == 200
    assert r.text == "console.log('hi')"
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert c.get("/assets/app-abc123.css").headers["cache-control"] == "public, max-age=31536000, immutable"


def test_a_missing_asset_is_a_404_and_not_the_app_page(dist):
    r = make_app(dist).get("/assets/missing-0000.js")
    assert r.status_code == 404
    assert '<div id="root">' not in r.text


def test_assets_cannot_reach_files_outside_the_folder(dist, tmp_path):
    (tmp_path / "secret.txt").write_text("secret")
    c = make_app(dist)
    for path in ["/assets/../../secret.txt", "/assets/..%2f..%2fsecret.txt", "/assets/%2e%2e/%2e%2e/secret.txt"]:
        r = c.get(path)
        assert "secret" not in r.text


def test_the_page_is_not_cached_forever(dist):
    assert "immutable" not in make_app(dist).get("/").headers["cache-control"]
    assert "immutable" not in make_app(dist).get("/graph").headers["cache-control"]


# ---------------------------------------------------------------- the API is not swallowed by the page

def test_api_routes_still_work(dist):
    assert make_app(dist).get("/api/ping").json() == {"pong": True}


@pytest.mark.parametrize("path", ["/api", "/api/nothing-here", "/api/deep/nothing", "/docs/x", "/redoc/x", "/openapi.json/x", "/assets"])
def test_unknown_api_addresses_are_404_not_the_app_page(dist, path):
    r = make_app(dist).get(path)
    assert r.status_code == 404
    assert '<div id="root">' not in r.text


def test_only_get_is_answered_for_pages(dist):
    r = make_app(dist).post("/graph")
    assert r.status_code == 405


def test_the_app_page_is_not_in_the_api_schema():
    app = FastAPI()
    web.mount_frontend(app, None)
    assert "/{path}" not in app.openapi()["paths"]
    assert "/" not in app.openapi()["paths"]


# ---------------------------------------------------------------- not built

def test_says_how_to_build_when_there_is_no_build(tmp_path):
    r = make_app(tmp_path / "nothing").get("/")
    assert r.status_code == 503
    assert "not built yet" in r.text
    assert "npm run build" in r.text
    assert "frame-ancestors" in r.headers["content-security-policy"]


def test_not_built_still_answers_other_pages_and_keeps_the_api(tmp_path):
    c = make_app(tmp_path / "nothing")
    assert c.get("/graph").status_code == 503
    assert c.get("/api/ping").status_code == 200
    assert c.get("/api/nope").status_code == 404


def test_a_build_without_assets_still_serves_the_page_but_never_answers_an_asset_with_it(tmp_path):
    d = tmp_path / "dist"
    d.mkdir()
    (d / "index.html").write_text("<div id=root></div>")
    c = make_app(d)
    assert c.get("/").status_code == 200
    assert c.get("/assets/x.js").status_code == 404


# ---------------------------------------------------------------- the real app and the real build

def test_the_committed_build_is_complete():
    """index.html points at files that exist, and the build is from the current sources (no dev-server references)"""
    index = (web.DIST / "index.html").read_text()
    refs = re.findall(r'(?:src|href)="(/assets/[^"]+)"', index)
    assert any(r.endswith(".js") for r in refs) and any(r.endswith(".css") for r in refs)
    for r in refs:
        assert (web.DIST / r.lstrip("/")).is_file(), r
    assert "localhost:5173" not in index and "/@vite" not in index and "/src/main.jsx" not in index
    assert "<script>" not in index                       # no inline script: the policy would block it


def test_the_real_server_serves_the_app_and_keeps_the_gate_closed(factory, monkeypatch):
    import server
    use_settings(monkeypatch, require_login=True)
    c = TestClient(server.app)
    page = c.get("/")
    assert page.status_code == 200 and "content-security-policy" in page.headers
    assert c.get("/graph/anything").status_code == 200                     # the page itself needs no sign-in
    assert c.get("/api/graph").status_code == 401                          # the data does
    assert c.get("/api/documents").status_code == 401
    assert c.get("/api/nope").status_code in (401, 404)
    assert c.get("/api/auth/config").status_code == 200                    # what the sign-in screen needs
    assert c.get("/docs").status_code == 200                               # the API docs still open
    assert c.get("/openapi.json").status_code == 200


def test_api_responses_carry_no_page_policy(factory, monkeypatch):
    import server
    use_settings(monkeypatch, require_login=True)
    c = TestClient(server.app)
    assert "content-security-policy" not in c.get("/api/auth/config").headers
    assert "content-security-policy" not in c.get("/api/health").headers


def test_the_real_server_in_single_user_mode_needs_no_sign_in(factory, monkeypatch):
    import server
    use_settings(monkeypatch, require_login=False)
    c = TestClient(server.app)
    assert c.get("/").status_code == 200
    assert c.get("/api/graph/stats").status_code == 200
