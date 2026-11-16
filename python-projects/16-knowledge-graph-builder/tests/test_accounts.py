from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from src.api import auth as auth_api
from src.core import auth
from src.core.auth import hash_password, verify_password
from src.core.config import Settings
from src.core.database import get_db
from src.models.embedding import Embedding
from src.models.graph import Chunk, Document, DocumentStatus, Entity, Fact
from src.models.user import User, UserSession
from src.services import pipeline
from tests.conftest import FakeEmbedder, FakeLLM, rel, use_settings

DOCS = {
    "A": "Acme Corp acquired Beta Systems in March 2020. ACME hired Dana Reyes in 2021.",
    "B": "Zed Inc bought Omega Labs in 2019. Zed Inc founded Orion Works in 2015.",
}
RAWS = {
    "A": [rel("Acme Corp", "acquired", "Beta Systems", "Acme Corp acquired Beta Systems in March 2020.", "March 2020", otype="organization", stype="organization"),
          rel("ACME", "hired", "Dana Reyes", "ACME hired Dana Reyes in 2021.", "2021", otype="person", stype="organization")],
    "B": [rel("Zed Inc", "bought", "Omega Labs", "Zed Inc bought Omega Labs in 2019.", "2019", otype="organization", stype="organization"),
          rel("Zed Inc", "founded", "Orion Works", "Zed Inc founded Orion Works in 2015.", "2015", otype="organization", stype="organization")],
}


@pytest.fixture
def site(factory, monkeypatch):
    """The real app with sign-in switched on, a fake model, and a way to get clients that each hold their own cookies"""
    import server
    settings = use_settings(monkeypatch, require_login=True)

    def override():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    def extract(prompt):
        for key, text in DOCS.items():
            if text.split(".")[0] in prompt:
                return {"relations": RAWS[key]}
        return {"relations": []}

    llm = FakeLLM(extract=extract)
    monkeypatch.setattr(pipeline, "get_llm", lambda s=None: llm)
    monkeypatch.setattr(pipeline, "get_settings", lambda: Settings(_env_file=None, verify_facts=False, gleaning_passes=0, auto_resolve=True))
    monkeypatch.setattr(pipeline, "get_embedder", lambda s=None: FakeEmbedder())
    monkeypatch.setattr("src.api.query.get_embedder", lambda s=None: FakeEmbedder())
    monkeypatch.setattr("src.api.query.get_settings", lambda: Settings(_env_file=None))
    server.app.dependency_overrides[get_db] = override

    class Site:
        pass
    st = Site()
    st.settings, st.llm, st.factory, st.app = settings, llm, factory, server.app
    st.client = lambda: TestClient(server.app)

    def user(name, password="correct horse"):
        c = TestClient(server.app)
        r = c.post("/api/auth/register", json={"username": name, "password": password})
        assert r.status_code == 200, r.text
        c.user = r.json()
        return c
    st.user = user
    yield st
    server.app.dependency_overrides.clear()


# ---------------------------------------------------------------- passwords

def test_password_hashing():
    h = hash_password("correct horse")
    assert h.startswith("scrypt$") and "correct horse" not in h and verify_password("correct horse", h)
    assert not verify_password("wrong", h) and not verify_password("x", "garbage") and not verify_password("x", "md5$1$2$3$4$5")
    assert hash_password("correct horse") != h            # a fresh salt every time


@pytest.mark.parametrize("name,ok", [("ann", True), ("Ann.Lee-1", True), ("ab", False), ("a" * 33, False), ("an n", False), ("-ann", False),
                                    ("guest-1234", False), ("", False), ("ann!", False)])
def test_username_rules(name, ok):
    if ok:
        assert auth.check_username(name) == name.strip().lower()
    else:
        with pytest.raises(ValueError):
            auth.check_username(name)


@pytest.mark.parametrize("pw,ok", [("12345678", True), ("short", False), ("x" * 129, False), ("        ", False), (None, False)])
def test_password_rules(pw, ok):
    if ok:
        assert auth.check_password(pw) == pw
    else:
        with pytest.raises(ValueError):
            auth.check_password(pw)


def test_display_names_are_cleaned():
    assert auth.clean_display_name("  Ann\x00 Lee\n ") == "Ann Lee" and auth.clean_display_name("  ") is None
    assert len(auth.clean_display_name("x" * 200)) == 80


# ---------------------------------------------------------------- the gate

def test_the_api_needs_a_sign_in_but_a_few_paths_are_public(site):
    c = site.client()
    for method, url in (("get", "/api/documents"), ("get", "/api/graph"), ("get", "/api/graph/stats"), ("get", "/api/entities"),
                        ("post", "/api/ask"), ("get", "/api/resolution/suggestions"), ("get", "/api/index/status"), ("get", "/api/auth/me")):
        r = getattr(c, method)(url)
        assert r.status_code == 401 and r.json() == {"detail": "Not signed in"} and "www-authenticate" in r.headers, url
    assert c.get("/api/auth/config").json()["require_login"] is True
    assert c.get("/api/health").json() == {"status": "ok"}            # nothing about the model for strangers
    assert c.get("/docs").status_code == 200                           # only /api/* is gated


def test_a_signed_in_caller_gets_the_model_status_in_health(site, monkeypatch):
    monkeypatch.setattr("server.llm_status", lambda: {"ready": True})
    c = site.user("ann")
    assert c.get("/api/health").json() == {"status": "ok", "llm": {"ready": True}}


def test_a_garbage_cookie_is_not_a_sign_in(site):
    c = site.client()
    for token in ("garbage", "x" * 500, ""):
        c.cookies.set(auth.COOKIE_NAME, token)
        assert c.get("/api/documents").status_code == 401


def test_single_user_mode_needs_no_sign_in(factory, monkeypatch):
    import server
    use_settings(monkeypatch, require_login=False)
    def override():
        db = factory()
        try:
            yield db
        finally:
            db.close()
    server.app.dependency_overrides[get_db] = override
    c = TestClient(server.app)
    assert c.get("/api/documents").status_code == 200
    assert c.get("/api/auth/me").json() == {"id": None, "username": "local", "display_name": "Local user", "is_guest": False, "local_mode": True}
    server.app.dependency_overrides.clear()


def test_get_owner_fails_closed_without_a_caller(monkeypatch):
    import asyncio
    from fastapi import HTTPException
    from src.api.deps import get_owner
    use_settings(monkeypatch, require_login=True)
    with pytest.raises(HTTPException) as e:
        asyncio.run(get_owner())
    assert e.value.status_code == 401


# ---------------------------------------------------------------- registering and signing in

def test_register_signs_you_in_with_a_safe_cookie(site):
    c = site.client()
    r = c.post("/api/auth/register", json={"username": "Ann", "password": "correct horse", "display_name": " Ann Lee "})
    assert r.status_code == 200 and r.json()["username"] == "ann" and r.json()["display_name"] == "Ann Lee" and r.json()["is_guest"] is False
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie and "secure" not in cookie and "max-age=" in cookie
    assert c.get("/api/auth/me").json()["username"] == "ann"
    assert c.get("/api/documents").status_code == 200


def test_the_cookie_is_secure_when_asked(site, monkeypatch):
    use_settings(monkeypatch, require_login=True, cookie_secure=True)
    r = site.client().post("/api/auth/register", json={"username": "ann", "password": "correct horse"})
    assert "secure" in r.headers["set-cookie"].lower()


def test_only_a_hash_of_the_token_is_stored(site):
    c = site.user("ann")
    token = c.cookies.get(auth.COOKIE_NAME)
    with site.factory() as db:
        ids = [s.id for s in db.execute(select(UserSession)).scalars()]
        assert len(ids) == 1 and token not in ids and ids[0] == auth._digest(token) and len(ids[0]) == 64
        assert db.execute(select(User)).scalar_one().password_hash.startswith("scrypt$")


@pytest.mark.parametrize("body,status,fragment", [
    ({"username": "ab", "password": "correct horse"}, 400, "Username"),
    ({"username": "ann", "password": "short"}, 400, "Password"),
    ({"username": "guest-abcd", "password": "correct horse"}, 400, "reserved"),
    ({"username": "ann"}, 422, ""),
    ({"username": "x" * 101, "password": "correct horse"}, 422, ""),
])
def test_register_validation(site, body, status, fragment):
    r = site.client().post("/api/auth/register", json=body)
    assert r.status_code == status and fragment in r.text


def test_usernames_are_unique_ignoring_case(site):
    site.user("ann")
    assert site.client().post("/api/auth/register", json={"username": "ANN", "password": "another pass"}).status_code == 409


def test_registration_can_be_switched_off(site, monkeypatch):
    use_settings(monkeypatch, require_login=True, allow_registration=False)
    assert site.client().post("/api/auth/register", json={"username": "ann", "password": "correct horse"}).status_code == 403
    assert site.client().get("/api/auth/config").json()["registration"] is False


def test_login_and_logout(site):
    site.user("ann")
    c = site.client()
    assert c.post("/api/auth/login", json={"username": "ANN", "password": "correct horse"}).status_code == 200
    assert c.get("/api/documents").status_code == 200
    assert c.post("/api/auth/logout").json() == {"success": True}
    assert c.get("/api/documents").status_code == 401          # the cookie was deleted...
    old = auth.COOKIE_NAME
    # ...and the sign-in itself is ended on the server, so a copied cookie is dead too
    d = site.client()
    d.post("/api/auth/login", json={"username": "ann", "password": "correct horse"})
    token = d.cookies.get(old)
    d.post("/api/auth/logout")
    e = site.client()
    e.cookies.set(old, token)
    assert e.get("/api/documents").status_code == 401


def test_a_wrong_password_and_an_unknown_user_look_the_same(site):
    site.user("ann")
    a = site.client().post("/api/auth/login", json={"username": "ann", "password": "wrong password"})
    b = site.client().post("/api/auth/login", json={"username": "nobody", "password": "wrong password"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json() == {"detail": "Wrong username or password"}


def test_too_many_wrong_passwords_lock_the_username_and_the_address(site):
    site.user("ann")
    c = site.client()
    for _ in range(8):
        assert c.post("/api/auth/login", json={"username": "ann", "password": "wrong password"}).status_code == 401
    r = c.post("/api/auth/login", json={"username": "ann", "password": "correct horse"})
    assert r.status_code == 429 and "retry-after" in r.headers          # even the right password is refused for now
    assert c.post("/api/auth/login", json={"username": "someone-else", "password": "x"}).status_code == 429   # the address is locked too


def test_a_good_login_forgets_earlier_failures_for_that_username(site):
    site.user("ann")
    c = site.client()
    for _ in range(5):
        c.post("/api/auth/login", json={"username": "ann", "password": "wrong password"})
    assert c.post("/api/auth/login", json={"username": "ann", "password": "correct horse"}).status_code == 200
    assert not auth_api.login_failures.blocked("user:ann")


def test_creating_accounts_is_limited_per_address(site):
    for i in range(auth_api.CREATE_LIMIT):
        assert site.client().post("/api/auth/register", json={"username": f"user{i:03d}", "password": "correct horse"}).status_code == 200
    r = site.client().post("/api/auth/register", json={"username": "onetoomany", "password": "correct horse"})
    assert r.status_code == 429


def test_expired_revoked_and_disabled_sign_ins_stop_working(site):
    c = site.user("ann")
    with site.factory() as db:
        s = db.execute(select(UserSession)).scalar_one()
        s.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert c.get("/api/documents").status_code == 401
    d = site.client()
    d.post("/api/auth/login", json={"username": "ann", "password": "correct horse"})
    assert d.get("/api/documents").status_code == 200
    with site.factory() as db:
        user = db.execute(select(User)).scalar_one()
        user.is_active = False
        db.commit()
    assert d.get("/api/documents").status_code == 401
    assert site.client().post("/api/auth/login", json={"username": "ann", "password": "correct horse"}).status_code == 401


def test_guests_cannot_sign_in_with_a_password(site):
    g = site.client()
    guest = g.post("/api/auth/guest").json()
    assert guest["is_guest"] is True and guest["username"].startswith("guest-")
    assert site.client().post("/api/auth/login", json={"username": guest["username"], "password": "anything"}).status_code == 401


# ---------------------------------------------------------------- cross-site requests

def test_a_write_from_another_website_is_refused_but_a_script_is_not(site):
    c = site.user("ann")
    body = {"title": "t", "text": DOCS["A"]}
    assert c.post("/api/documents/text", json=body, headers={"Origin": "https://evil.example"}).status_code == 403
    assert c.post("/api/documents/text", json=body, headers={"Origin": "null"}).status_code == 403
    assert c.post("/api/documents/text", json=body, headers={"Referer": "https://evil.example/page"}).status_code == 403
    assert c.post("/api/documents/text", json=body, headers={"Origin": "http://testserver"}).status_code == 202   # this site
    assert c.post("/api/documents/text", json=body).status_code == 202                                           # curl: no Origin
    assert c.get("/api/documents", headers={"Origin": "https://evil.example"}).status_code == 200                # reads are not writes


def test_allowed_origins_can_be_configured(site, monkeypatch):
    c = site.user("ann")
    use_settings(monkeypatch, require_login=True, allowed_origins="http://localhost:3000, https://app.example.com/")
    body = {"title": "t", "text": DOCS["A"]}
    assert c.post("/api/documents/text", json=body, headers={"Origin": "http://localhost:3000"}).status_code == 202
    assert c.post("/api/documents/text", json=body, headers={"Origin": "https://app.example.com"}).status_code == 202
    assert c.post("/api/documents/text", json=body, headers={"Origin": "http://localhost:9999"}).status_code == 403


def test_a_write_without_a_cookie_is_not_a_cross_site_question_it_is_just_unauthenticated(site):
    r = site.client().post("/api/documents/text", json={"title": "t", "text": DOCS["A"]}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 401


# ---------------------------------------------------------------- guests

def test_a_guest_has_a_small_allowance_and_can_become_an_account(site, monkeypatch):
    use_settings(monkeypatch, require_login=True, guest_max_documents=2)
    g = site.client()
    guest = g.post("/api/auth/guest").json()
    assert g.get("/api/auth/me").json()["guest_max_documents"] == 2
    for _ in range(2):
        assert g.post("/api/documents/text", json={"title": "t", "text": DOCS["A"]}).status_code == 202
    r = g.post("/api/documents/text", json={"title": "t", "text": DOCS["A"]})
    assert r.status_code == 403 and "Create an account" in r.json()["detail"]
    r = g.post("/api/auth/register", json={"username": "ann", "password": "correct horse"})      # upgrade in place
    assert r.json()["id"] == guest["id"] and r.json()["is_guest"] is False and r.json()["username"] == "ann"
    assert len(g.get("/api/documents").json()["documents"]) == 2
    assert g.post("/api/documents/text", json={"title": "t", "text": DOCS["A"]}).status_code == 202   # no longer limited


def test_guests_can_be_switched_off(site, monkeypatch):
    use_settings(monkeypatch, require_login=True, allow_guests=False)
    assert site.client().post("/api/auth/guest").status_code == 403


def test_expired_guests_and_all_their_data_are_removed(site):
    g = site.client()
    g.post("/api/auth/guest")
    g.post("/api/documents/text", json={"title": "t", "text": DOCS["A"]})
    ann = site.user("ann")
    ann.post("/api/documents/text", json={"title": "t", "text": DOCS["B"]})
    with site.factory() as db:
        assert db.scalar(select(func.count()).select_from(Embedding)) > 0
    assert auth_api.cleanup_expired_guests() == 0                       # not old enough yet
    assert auth_api.cleanup_expired_guests(datetime.now(timezone.utc) + timedelta(hours=25)) == 1
    with site.factory() as db:
        assert [u.username for u in db.execute(select(User)).scalars()] == ["ann"]
        assert db.scalar(select(func.count()).select_from(UserSession)) == 1
        owners = {d.owner_id for d in db.execute(select(Document)).scalars()}
        assert owners == {ann.user["id"]}
        assert {e.owner_id for e in db.execute(select(Entity)).scalars()} == {ann.user["id"]}
        assert {f.owner_id for f in db.execute(select(Fact)).scalars()} == {ann.user["id"]}
        chunk_ids = {c.id for c in db.execute(select(Chunk)).scalars()}
        assert {e.chunk_id for e in db.execute(select(Embedding).where(Embedding.chunk_id.is_not(None))).scalars()} <= chunk_ids
    assert g.get("/api/documents").status_code == 401                    # their cookie no longer works


def test_cleanup_forgets_old_ended_sign_ins(site):
    site.user("ann")
    with site.factory() as db:
        db.execute(UserSession.__table__.update().values(expires_at=datetime.now(timezone.utc) - timedelta(days=2)))
        db.commit()
    auth_api.cleanup_expired_guests()
    with site.factory() as db:
        assert db.scalar(select(func.count()).select_from(UserSession)) == 0


# ---------------------------------------------------------------- the first account adopts what was there before

def test_the_first_account_adopts_data_from_before_accounts_and_the_second_does_not(factory, site):
    with factory() as db:
        d = Document(title="old", text="Old Corp bought Older Ltd.", char_count=25, status=DocumentStatus.COMPLETED)
        db.add(d)
        e = Entity(name="Old Corp", key="old corp", type="organization")
        db.add(e)
        db.commit()
    first = site.client()
    r = first.post("/api/auth/register", json={"username": "ann", "password": "correct horse"})
    assert r.json()["adopted_documents"] == 1
    assert [d["title"] for d in first.get("/api/documents").json()["documents"]] == ["old"]
    assert [e["name"] for e in first.get("/api/entities").json()["entities"]] == ["Old Corp"]
    second = site.user("bob")
    assert second.get("/api/documents").json()["documents"] == [] and second.get("/api/entities").json()["entities"] == []


def test_a_guest_does_not_count_as_the_first_account(factory, site):
    with factory() as db:
        db.add(Document(title="old", text="x" * 30, char_count=30, status=DocumentStatus.COMPLETED))
        db.commit()
    g = site.client()
    g.post("/api/auth/guest")
    assert g.get("/api/documents").json()["documents"] == []             # a guest never sees the old data
    ann = site.user("ann")
    assert len(ann.get("/api/documents").json()["documents"]) == 1       # the first real account does


# ---------------------------------------------------------------- startup

def test_startup_creates_the_tables_and_adopts_an_old_database(tmp_path, monkeypatch):
    import server
    from sqlalchemy import inspect
    from sqlalchemy.orm import sessionmaker
    from src.core import database
    use_settings(monkeypatch, require_login=True)
    monkeypatch.setattr(server, "get_settings", lambda: Settings(_env_file=None, job_workers_enabled=False))   # no worker threads here
    engine = database.make_engine(f"sqlite:///{tmp_path}/fresh.db")
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine, autoflush=False, expire_on_commit=False))
    assert inspect(engine).get_table_names() == []
    with TestClient(server.app) as c:                        # runs the lifespan: migrations, then recovery
        assert c.get("/api/auth/config").status_code == 200
    names = set(inspect(engine).get_table_names())
    assert {"users", "user_sessions", "documents", "entities", "facts", "alembic_version"} <= names
