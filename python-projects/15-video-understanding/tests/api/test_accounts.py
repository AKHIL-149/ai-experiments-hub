"""
Accounts: sign in, create an account, continue as guest, and the rule that every account only sees its own
videos.

Drives the real FastAPI app (gate, routers, ownership helpers) against a real SQLite database and a real
Chroma store in a temporary folder; only the heavy video processing is switched off. Each test makes its own
people, so nothing depends on test order.
"""

import shutil
import subprocess
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from starlette.websockets import WebSocketDisconnect

from src.core.config import settings
from src.models import (
    Chapter, Clip, ClipStatus, Frame, Highlight, Scene, SourceType, Summary, Transcript, Video, VideoStatus,
)
from src.models.user import User, UserSession

pytestmark = pytest.mark.accounts

FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
needs_ffmpeg = pytest.mark.skipif(not Path(FFMPEG).exists(), reason="ffmpeg not installed")
PASSWORD = "correct horse battery"


# ---------------------------------------------------------------------------
# A real database and an app that does no heavy work
# ---------------------------------------------------------------------------

class World:
    def __init__(self, tmp_path):
        from src.core.database import Base
        import src.models  # noqa: F401

        self.tmp = tmp_path
        self.engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})

        @event.listens_for(self.engine, "connect")
        def _fk(conn, _):
            conn.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False)

    @contextmanager
    def get_db(self):
        db = self.Session()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def client(self):
        from server import app
        return TestClient(app)

    def signup(self, name, client=None):
        client = client or self.client()
        response = client.post("/api/auth/register", json={"username": name, "password": PASSWORD})
        assert response.status_code == 200, response.text
        client.user = response.json()
        return client

    def guest(self):
        client = self.client()
        response = client.post("/api/auth/guest")
        assert response.status_code == 200, response.text
        client.user = response.json()
        return client

    def add_video(self, owner, ext, status=VideoStatus.COMPLETED, title=None, rich=False):
        """A video row for `owner` (a user id or a client). rich=True adds a transcript, scene, frame..."""
        owner_id = owner.user["id"] if hasattr(owner, "user") else owner
        folder = self.tmp / "media"
        folder.mkdir(exist_ok=True)
        with self.get_db() as db:
            video = Video(
                external_id=ext, user_id=owner_id, title=title or f"title-{ext}", source_type=SourceType.LOCAL,
                file_path=str(folder / f"{ext}.mp4"), duration_seconds=60.0, processing_status=status,
            )
            db.add(video)
            db.flush()
            if rich:
                (folder / f"{ext}.mp4").write_bytes(b"video")
                frame_file = folder / f"{ext}-frame.jpg"
                frame_file.write_bytes(b"\xff\xd8jpeg")
                thumb = folder / f"{ext}-thumb.jpg"
                thumb.write_bytes(b"\xff\xd8jpeg")
                clip_file = folder / f"{ext}-clip.mp4"
                clip_file.write_bytes(b"clip")
                db.add(Transcript(video_id=video.id, start_time=1.0, end_time=4.0, text=f"secret words of {ext}"))
                db.add(Scene(video_id=video.id, scene_number=1, start_time=0.0, end_time=30.0, duration=30.0))
                frame = Frame(video_id=video.id, timestamp=1.0, frame_number=1, file_path=str(frame_file))
                db.add(frame)
                db.add(Highlight(video_id=video.id, title="h", start_time=1.0, end_time=5.0, thumbnail_path=str(thumb)))
                db.add(Summary(video_id=video.id, content="a summary"))
                db.add(Chapter(video_id=video.id, chapter_number=1, title="c", start_time=0.0, end_time=30.0))
                db.add(Clip(external_id=f"clip-{ext}", video_id=video.id, title="clip", start_time=1.0, end_time=3.0,
                            file_path=str(clip_file), thumbnail_path=str(thumb), status=ClipStatus.COMPLETED))
            db.flush()
        return ext

    def ids(self, ext):
        """frame_id and highlight_id of a rich video"""
        with self.get_db() as db:
            video = db.query(Video).filter(Video.external_id == ext).first()
            frame = db.query(Frame).filter(Frame.video_id == video.id).first()
            highlight = db.query(Highlight).filter(Highlight.video_id == video.id).first()
            return frame.id, highlight.id

    def count(self, model, **where):
        with self.get_db() as db:
            return db.query(model).filter_by(**where).count()


@pytest.fixture
def world(tmp_path, monkeypatch):
    w = World(tmp_path)
    monkeypatch.chdir(tmp_path)  # uploads and the stored frames go to the temp folder
    monkeypatch.setattr(settings, "frames_path", str(tmp_path / "frames"))
    monkeypatch.setattr(settings, "chroma_persist_directory", str(tmp_path / "chroma"))
    monkeypatch.setattr(settings, "allow_registration", True)
    monkeypatch.setattr(settings, "allow_guests", True)
    monkeypatch.setattr(settings, "admin_usernames", "")
    monkeypatch.setattr("src.core.auth._SCRYPT_N", 2 ** 4)  # tests make many accounts; real cost is for real use

    for target in ("src.core.database.SessionLocal", "src.core.login_gate.SessionLocal"):
        monkeypatch.setattr(target, w.Session)
    for target in ("src.core.database.get_db", "src.api.videos.get_db", "src.api.auth.get_db"):
        monkeypatch.setattr(target, w.get_db)

    # no heavy work: processing is scheduled but never run, and the rate limiter is not what is under test
    async def _no_dispatch(self, request, call_next):
        return await call_next(request)

    from src.core.middleware import RateLimitMiddleware
    monkeypatch.setattr(RateLimitMiddleware, "dispatch", _no_dispatch)
    monkeypatch.setattr("starlette.background.BackgroundTasks.add_task", lambda self, *a, **k: None)
    monkeypatch.setattr("fastapi.BackgroundTasks.add_task", lambda self, *a, **k: None)

    from src.api import auth as auth_api
    auth_api.login_failures.events.clear()
    auth_api.creations.events.clear()
    return w


@pytest.fixture
def people(world):
    """The first account (an administrator), and two ordinary users, each with a full set of data"""
    root = world.signup("root")
    ann = world.signup("ann")
    bob = world.signup("bob")
    world.add_video(ann, "vid-ann", rich=True)
    world.add_video(bob, "vid-bob", rich=True)
    return NS(world=world, root=root, ann=ann, bob=bob)


def make_video(path, seconds=2):
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=blue:s=160x120:d={seconds}",
                    "-pix_fmt", "yuv420p", str(path)], check=True, capture_output=True)
    return path


def upload(client, path, **form):
    return client.post("/api/videos/upload", files={"file": (Path(path).name, Path(path).read_bytes(), "video/mp4")},
                       data={"auto_process": "false", **form})


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

class TestGate:
    def test_the_api_needs_a_sign_in(self, world):
        anon = world.client()
        for method, path in [("get", "/api/videos"), ("get", "/api/videos/x"), ("get", "/api/clips"),
                             ("post", "/api/search/semantic"), ("get", "/api/auth/me"), ("delete", "/api/videos/x")]:
            response = getattr(anon, method)(path)
            assert response.status_code == 401, (method, path)
            assert response.json() == {"detail": "Not signed in"}

    def test_only_the_sign_in_paths_and_pages_are_public(self, world):
        anon = world.client()
        assert anon.get("/api/auth/config").status_code == 200
        assert anon.get("/api/info").status_code == 200
        assert anon.get("/health").status_code == 200
        assert anon.get("/login", headers={"accept": "text/html"}).status_code == 200
        assert anon.get("/static/login.js").status_code == 200
        assert anon.get("/static/app.js").status_code == 200
        assert "Video Understanding" in anon.get("/", headers={"accept": "text/html"}).text

    def test_files_are_not_served_without_the_owner_check(self, world):
        """/uploads, /clips and /thumbnails used to be mounted: any file was public to anyone who guessed a name"""
        (world.tmp / "uploads" / "videos").mkdir(parents=True)
        (world.tmp / "uploads" / "videos" / "secret.mp4").write_bytes(b"secret")
        anon = world.client()
        user = world.signup("ann")
        for path in ("/uploads/videos/secret.mp4", "/clips/x.mp4", "/thumbnails/x.jpg"):
            for who in (anon, user):
                # the page's own fallback may answer (the single-page app serves index.html for unknown paths): never the file
                assert b"secret" not in who.get(path).content, path

    def test_a_made_up_cookie_is_not_a_sign_in(self, world):
        anon = world.client()
        anon.cookies.set("vu_session", "a" * 43)
        assert anon.get("/api/videos").status_code == 401

    def test_signed_in_requests_pass(self, world):
        ann = world.signup("ann")
        assert ann.get("/api/videos").status_code == 200
        assert ann.get("/api/auth/me").json()["username"] == "ann"

    def test_single_user_mode_needs_no_sign_in(self, world, monkeypatch):
        monkeypatch.setattr(settings, "require_login", False)
        anon = world.client()
        assert anon.get("/api/videos").status_code == 200
        me = anon.get("/api/auth/me").json()
        assert me["username"] == "local" and me["is_admin"] is True and me["local_mode"] is True


# ---------------------------------------------------------------------------
# Creating accounts and signing in
# ---------------------------------------------------------------------------

class TestRegister:
    def test_account_is_created_and_signed_in(self, world):
        client = world.client()
        response = client.post("/api/auth/register", json={"username": "Ann", "password": PASSWORD, "display_name": " Ann B "})
        assert response.status_code == 200
        body = response.json()
        assert body["username"] == "ann" and body["display_name"] == "Ann B" and body["is_guest"] is False
        assert "password" not in str(body).lower() and "hash" not in str(body).lower()
        assert client.get("/api/auth/me").json()["username"] == "ann"

    def test_cookie_is_http_only_same_site_and_not_the_database_key(self, world):
        client = world.client()
        response = client.post("/api/auth/register", json={"username": "ann", "password": PASSWORD})
        header = response.headers["set-cookie"].lower()
        assert "httponly" in header and "samesite=lax" in header and "path=/" in header and "max-age=" in header
        token = client.cookies.get("vu_session")
        with world.get_db() as db:
            stored_id = db.query(UserSession).one().id
        assert stored_id != token and token not in stored_id  # only a hash is stored: a leaked database replays nothing

    def test_secure_flag_follows_the_setting(self, world, monkeypatch):
        monkeypatch.setattr(settings, "cookie_secure", True)
        response = world.client().post("/api/auth/register", json={"username": "ann", "password": PASSWORD})
        assert "secure" in response.headers["set-cookie"].lower()

    def test_password_is_stored_hashed(self, world):
        world.signup("ann")
        with world.get_db() as db:
            stored = db.query(User).one().password_hash
        assert stored.startswith("scrypt$") and PASSWORD not in stored

    @pytest.mark.parametrize("username,why", [
        ("ab", "too short"), ("a" * 33, "too long"), ("has space", "space"), ("bad/name", "slash"), ("-start", "starts with dash"),
        ("<script>", "markup"), ("guest-1234", "reserved prefix"), ("Guest-ABCD", "reserved prefix, any case"), ("", "empty"),
    ])
    def test_bad_usernames_are_refused(self, world, username, why):
        response = world.client().post("/api/auth/register", json={"username": username, "password": PASSWORD})
        assert response.status_code == 400, why
        assert world.count(User) == 0

    @pytest.mark.parametrize("password", ["short", "1234567", " " * 10, "x" * 129, ""])
    def test_bad_passwords_are_refused(self, world, password):
        response = world.client().post("/api/auth/register", json={"username": "ann", "password": password})
        assert response.status_code in (400, 422)
        assert world.count(User) == 0

    def test_username_is_unique_ignoring_case(self, world):
        world.signup("ann")
        response = world.client().post("/api/auth/register", json={"username": "ANN", "password": PASSWORD})
        assert response.status_code == 409 and world.count(User) == 1

    def test_registration_can_be_switched_off(self, world, monkeypatch):
        monkeypatch.setattr(settings, "allow_registration", False)
        response = world.client().post("/api/auth/register", json={"username": "ann", "password": PASSWORD})
        assert response.status_code == 403 and world.count(User) == 0
        assert world.client().get("/api/auth/config").json()["registration"] is False

    def test_first_account_is_the_administrator_and_later_ones_are_not(self, world):
        first, second = world.signup("root"), world.signup("ann")
        assert first.user["is_admin"] is True and second.user["is_admin"] is False

    def test_admin_usernames_setting_promotes_a_name(self, world, monkeypatch):
        world.signup("root")
        monkeypatch.setattr(settings, "admin_usernames", "boss, other")
        assert world.signup("boss").user["is_admin"] is True
        assert world.signup("ann").user["is_admin"] is False

    def test_first_account_adopts_videos_from_before_accounts(self, world):
        world.add_video(None, "old-1")
        world.add_video(None, "old-2")
        root = world.signup("root")
        assert root.user["adopted_videos"] == 2
        assert {v["video_id"] for v in root.get("/api/videos").json()["videos"]} == {"old-1", "old-2"}
        ann = world.signup("ann")
        assert ann.get("/api/videos").json()["videos"] == []

    def test_later_accounts_do_not_adopt_anything(self, world):
        world.signup("root")
        world.add_video(None, "orphan")
        ann = world.signup("ann")
        assert ann.user["adopted_videos"] == 0
        assert ann.get("/api/videos/orphan").status_code == 404

    def test_many_registrations_from_one_address_are_slowed_down(self, world):
        for i in range(20):
            assert world.client().post("/api/auth/register", json={"username": f"user{i:02d}", "password": PASSWORD}).status_code == 200
        response = world.client().post("/api/auth/register", json={"username": "one-too-many", "password": PASSWORD})
        assert response.status_code == 429 and world.count(User) == 20

    def test_many_accounts_from_one_address_are_slowed_down(self, world):
        for i in range(20):
            world.client().post("/api/auth/guest")
        response = world.client().post("/api/auth/guest")
        assert response.status_code == 429 and "Retry-After" in response.headers


class TestLogin:
    def test_right_password_signs_in_on_a_second_device(self, world):
        world.signup("ann")
        other = world.client()
        response = other.post("/api/auth/login", json={"username": "ANN", "password": PASSWORD})
        assert response.status_code == 200 and other.get("/api/auth/me").json()["username"] == "ann"

    def test_wrong_password_and_unknown_user_look_the_same(self, world):
        world.signup("ann")
        wrong = world.client().post("/api/auth/login", json={"username": "ann", "password": "not the password"})
        unknown = world.client().post("/api/auth/login", json={"username": "nobody", "password": "not the password"})
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json() == unknown.json() == {"detail": "Wrong username or password"}
        assert "set-cookie" not in wrong.headers

    def test_guest_accounts_cannot_be_signed_in_to_with_a_password(self, world):
        from src.core.auth import hash_password
        guest = world.guest()
        with world.get_db() as db:  # even if a guest row somehow had a password we know
            db.query(User).filter(User.id == guest.user["id"]).update({"password_hash": hash_password("known-password-1")})
        response = world.client().post("/api/auth/login", json={"username": guest.user["username"], "password": "known-password-1"})
        assert response.status_code == 401

    def test_repeated_failures_lock_the_username_even_for_the_right_password(self, world):
        world.signup("ann")
        victim = world.client()
        for _ in range(8):
            assert victim.post("/api/auth/login", json={"username": "ann", "password": "wrong-password"}).status_code == 401
        blocked = victim.post("/api/auth/login", json={"username": "ann", "password": PASSWORD})
        assert blocked.status_code == 429

    def test_failures_for_one_name_do_not_lock_other_names_on_other_addresses(self, world):
        from src.api import auth as auth_api
        world.signup("ann")
        world.signup("bob")
        for _ in range(8):
            auth_api.login_failures.add("user:ann")
        assert world.client().post("/api/auth/login", json={"username": "bob", "password": PASSWORD}).status_code == 200

    def test_a_good_login_clears_the_username_counter(self, world):
        from src.api import auth as auth_api
        world.signup("ann")
        client = world.client()
        for _ in range(5):
            client.post("/api/auth/login", json={"username": "ann", "password": "wrong-password"})
        assert len(auth_api.login_failures.events["user:ann"]) == 5
        assert client.post("/api/auth/login", json={"username": "ann", "password": PASSWORD}).status_code == 200
        assert "user:ann" not in auth_api.login_failures.events

    def test_a_deactivated_account_cannot_sign_in_or_keep_its_session(self, world):
        ann = world.signup("ann")
        with world.get_db() as db:
            db.query(User).filter(User.username == "ann").update({"is_active": False})
        assert ann.get("/api/videos").status_code == 401
        assert world.client().post("/api/auth/login", json={"username": "ann", "password": PASSWORD}).status_code == 401


class TestSessions:
    def test_logout_ends_that_sign_in_at_once(self, world):
        ann = world.signup("ann")
        stolen = world.client()
        stolen.cookies.set("vu_session", ann.cookies.get("vu_session"))
        assert stolen.get("/api/videos").status_code == 200
        assert ann.post("/api/auth/logout").json() == {"success": True}
        assert stolen.get("/api/videos").status_code == 401
        assert ann.get("/api/videos").status_code == 401

    def test_logout_without_a_sign_in_is_harmless(self, world):
        assert world.client().post("/api/auth/logout").status_code == 200

    def test_other_devices_stay_signed_in_after_one_signs_out(self, world):
        phone = world.signup("ann")
        laptop = world.client()
        laptop.post("/api/auth/login", json={"username": "ann", "password": PASSWORD})
        phone.post("/api/auth/logout")
        assert laptop.get("/api/videos").status_code == 200

    def test_an_expired_session_is_refused(self, world):
        ann = world.signup("ann")
        with world.get_db() as db:
            db.query(UserSession).update({"expires_at": datetime.utcnow() - timedelta(seconds=1)})
        assert ann.get("/api/videos").status_code == 401

    def test_session_length_follows_the_setting_and_guests_get_the_shorter_of_the_two(self, world, monkeypatch):
        from src.core import auth
        monkeypatch.setattr(settings, "session_days", 14)
        monkeypatch.setattr(settings, "guest_ttl_hours", 24)
        assert auth.session_lifetime(NS(is_guest=False)) == timedelta(days=14)
        assert auth.session_lifetime(NS(is_guest=True)) == timedelta(hours=24)
        monkeypatch.setattr(settings, "session_days", 0)
        assert auth.session_lifetime(NS(is_guest=True)) == timedelta(0)

    def test_dead_sessions_are_cleaned_up_but_recent_ones_are_kept(self, world):
        from src.services.video_cleanup import purge_dead_sessions
        ann = world.signup("ann")
        with world.get_db() as db:
            user = db.query(User).one()
            old = datetime.utcnow() - timedelta(days=30)
            db.add(UserSession(id="old", user_id=user.id, created_at=old, last_seen_at=old, expires_at=old))
            db.add(UserSession(id="just-expired", user_id=user.id, expires_at=datetime.utcnow() - timedelta(hours=1)))
        with world.get_db() as db:
            assert purge_dead_sessions(db) == 1
        assert world.count(UserSession) == 2 and ann.get("/api/videos").status_code == 200


# ---------------------------------------------------------------------------
# Guests
# ---------------------------------------------------------------------------

class TestGuests:
    def test_continue_as_guest(self, world):
        guest = world.guest()
        assert guest.user["is_guest"] is True and guest.user["username"].startswith("guest-")
        assert guest.get("/api/videos").status_code == 200
        me = guest.get("/api/auth/me").json()
        assert me["is_guest"] and me["guest_ttl_hours"] == settings.guest_ttl_hours

    def test_a_guest_is_never_the_administrator_and_does_not_count_as_the_first_account(self, world):
        guest = world.guest()
        assert guest.user["is_admin"] is False
        assert world.signup("root").user["is_admin"] is True

    def test_guests_can_be_switched_off(self, world, monkeypatch):
        monkeypatch.setattr(settings, "allow_guests", False)
        assert world.client().post("/api/auth/guest").status_code == 403
        assert world.client().get("/api/auth/config").json()["guests"] is False

    def test_each_guest_is_a_separate_person(self, world):
        one, two = world.guest(), world.guest()
        world.add_video(one, "guest-vid")
        assert one.get("/api/videos/guest-vid").status_code == 200
        assert two.get("/api/videos/guest-vid").status_code == 404

    def test_a_guest_who_creates_an_account_keeps_their_videos(self, world):
        world.signup("root")
        guest = world.guest()
        world.add_video(guest, "mine")
        guest_id = guest.user["id"]
        response = guest.post("/api/auth/register", json={"username": "newbie", "password": PASSWORD})
        assert response.status_code == 200
        assert response.json()["id"] == guest_id and response.json()["is_guest"] is False
        assert guest.get("/api/videos/mine").status_code == 200
        assert world.count(User) == 2  # root and newbie: the guest row became the account, none was added
        again = world.client()
        again.post("/api/auth/login", json={"username": "newbie", "password": PASSWORD})
        assert again.get("/api/videos/mine").status_code == 200

    def test_upgrading_does_not_make_the_guest_an_administrator_or_adopt_old_videos(self, world):
        world.signup("root")
        world.add_video(None, "orphan")
        guest = world.guest()
        guest.post("/api/auth/register", json={"username": "newbie", "password": PASSWORD})
        assert guest.get("/api/auth/me").json()["is_admin"] is False
        assert guest.get("/api/videos/orphan").status_code == 404

    @needs_ffmpeg
    def test_guests_may_keep_only_a_few_videos(self, world, monkeypatch):
        monkeypatch.setattr(settings, "guest_max_videos", 2)
        clip = make_video(world.tmp / "a.mp4")
        guest = world.guest()
        assert upload(guest, clip).status_code == 200
        assert upload(guest, clip).status_code == 200
        refused = upload(guest, clip)
        assert refused.status_code == 403 and "at most 2" in refused.json()["detail"]
        assert world.count(Video, user_id=guest.user["id"]) == 2
        assert len(list((world.tmp / "uploads" / "videos").glob("*"))) == 2  # the refused one left nothing behind

    @needs_ffmpeg
    def test_the_limit_counts_only_that_persons_videos(self, world, monkeypatch):
        monkeypatch.setattr(settings, "guest_max_videos", 1)
        clip = make_video(world.tmp / "a.mp4")
        assert upload(world.guest(), clip).status_code == 200
        assert upload(world.guest(), clip).status_code == 200

    @needs_ffmpeg
    def test_guests_have_a_smaller_upload_size_than_accounts(self, world, monkeypatch):
        monkeypatch.setattr(settings, "guest_max_video_size_mb", 0)
        clip = make_video(world.tmp / "a.mp4")
        refused = upload(world.guest(), clip)
        assert refused.status_code == 413 and "0 MB" in refused.json()["detail"]
        assert upload(world.signup("ann"), clip).status_code == 200

    @needs_ffmpeg
    def test_accounts_have_a_video_limit_too_but_administrators_do_not(self, world, monkeypatch):
        monkeypatch.setattr(settings, "max_videos_per_user", 1)
        clip = make_video(world.tmp / "a.mp4")
        root, ann = world.signup("root"), world.signup("ann")
        assert upload(ann, clip).status_code == 200
        assert upload(ann, clip).status_code == 403
        assert upload(root, clip).status_code == 200 and upload(root, clip).status_code == 200

    def test_expired_guests_are_removed_with_everything_they_uploaded(self, world):
        from src.services.video_cleanup import purge_expired_guests
        world.signup("root")
        old, fresh, member = world.guest(), world.guest(), world.signup("ann")
        world.add_video(old, "old-vid", rich=True)
        world.add_video(fresh, "fresh-vid", rich=True)
        world.add_video(member, "member-vid", rich=True)
        with world.get_db() as db:
            db.query(User).filter(User.id == old.user["id"]).update(
                {"created_at": datetime.utcnow() - timedelta(hours=settings.guest_ttl_hours + 1)})
        with world.get_db() as db:
            assert purge_expired_guests(db) == 1

        assert world.count(User, id=old.user["id"]) == 0
        assert world.count(Video, external_id="old-vid") == 0
        assert world.count(Transcript) == 2 and world.count(Clip) == 2  # only the other two videos' rows are left
        assert not (world.tmp / "media" / "old-vid.mp4").exists() and not (world.tmp / "media" / "old-vid-clip.mp4").exists()
        assert (world.tmp / "media" / "fresh-vid.mp4").exists() and (world.tmp / "media" / "member-vid.mp4").exists()
        assert old.get("/api/videos").status_code == 401  # their sign-in went with them
        assert fresh.get("/api/videos/fresh-vid").status_code == 200 and member.get("/api/videos/member-vid").status_code == 200

    def test_accounts_are_never_removed_for_age(self, world):
        from src.services.video_cleanup import purge_expired_guests
        world.signup("root")
        ann = world.signup("ann")
        with world.get_db() as db:
            db.query(User).update({"created_at": datetime.utcnow() - timedelta(days=900)})
        with world.get_db() as db:
            assert purge_expired_guests(db) == 0
        assert ann.get("/api/auth/me").status_code == 200


# ---------------------------------------------------------------------------
# Every account only sees its own videos
# ---------------------------------------------------------------------------

BODIES = {
    "/api/videos/{video_id}/clip": {"start_time": 1, "end_time": 3},
    "/api/videos/{video_id}/clips/batch": {"video_id": "{video_id}", "clips": [{"start_time": 1, "end_time": 3}]},
    "/api/search/videos/{video_id}/ask": {"question": "what is said?"},
    "/api/clips/highlight-reel": {"title": "reel", "clip_ids": ["{clip_id}"]},
}


def owned_routes():
    """Every route that takes a video, clip, frame or highlight, from the app's own OpenAPI description"""
    from server import app
    found = []
    for path, operations in app.openapi()["paths"].items():
        if any(p in path for p in ("{video_id}", "{clip_id}")):
            for method in operations:
                found.append((method.upper(), path))
    return sorted(found)


def fill(text, ext, ids):
    frame_id, highlight_id = ids
    return (text.replace("{video_id}", ext).replace("{clip_id}", f"clip-{ext}")
            .replace("{frame_id}", str(frame_id)).replace("{highlight_id}", str(highlight_id)))


def send(client, method, path, ext, ids):
    url = fill(path, ext, ids)
    body = BODIES.get(path, {} if method == "POST" else None)
    if body is not None:
        body = {k: (fill(v, ext, ids) if isinstance(v, str) else [fill(x, ext, ids) for x in v] if isinstance(v, list) and v and isinstance(v[0], str) else v)
                for k, v in body.items()}
    return client.request(method, url, json=body) if method in ("POST", "PUT", "PATCH") else client.request(method, url)


class TestOwnership:
    def test_the_sweep_covers_every_route_that_takes_an_id(self):
        # a new route shows up here, so it cannot ship without this test running against it
        routes = owned_routes()
        assert len(routes) >= 25
        assert ("DELETE", "/api/videos/{video_id}") in routes and ("GET", "/api/clips/{clip_id}/download") in routes
        assert ("GET", "/api/videos/{video_id}/frames/{frame_id}/image") in routes

    @pytest.mark.parametrize("method,path", owned_routes(), ids=lambda v: v if isinstance(v, str) else None)
    def test_other_accounts_get_not_found_and_the_owner_does_not(self, people, method, path):
        w = people.world
        ann_ids = w.ids("vid-ann")

        theirs = send(people.bob, method, path, "vid-ann", ann_ids)
        assert theirs.status_code == 404, f"bob got {theirs.status_code}: {theirs.text[:200]}"

        # the request itself is fine: the owner is not told 'not found'
        mine = send(people.ann, method, path, "vid-ann", ann_ids)
        assert mine.status_code != 404 and mine.status_code < 500, f"ann got {mine.status_code}: {mine.text[:200]}"

    @pytest.mark.parametrize("method,path", [r for r in owned_routes() if r[0] == "GET"],
                             ids=lambda v: v if isinstance(v, str) else None)
    def test_administrators_can_open_anything(self, people, method, path):
        response = send(people.root, method, path, "vid-ann", people.world.ids("vid-ann"))
        assert response.status_code != 404 and response.status_code < 500

    def test_not_found_is_identical_for_other_peoples_and_missing_videos(self, people):
        theirs = people.bob.get("/api/videos/vid-ann")
        missing = people.bob.get("/api/videos/does-not-exist")
        assert theirs.status_code == missing.status_code == 404
        # the generic 404 body names the requested path; apart from that the two answers are the same
        assert theirs.json()["message"].replace("vid-ann", "X") == missing.json()["message"].replace("does-not-exist", "X")

    def test_lists_only_show_your_own(self, people):
        assert [v["video_id"] for v in people.ann.get("/api/videos").json()["videos"]] == ["vid-ann"]
        assert [v["video_id"] for v in people.bob.get("/api/videos").json()["videos"]] == ["vid-bob"]
        assert {v["video_id"] for v in people.root.get("/api/videos").json()["videos"]} == {"vid-ann", "vid-bob"}
        assert people.ann.get("/api/videos").json()["total"] == 1

    def test_clip_list_only_shows_your_own_even_when_asking_for_someone_elses_video(self, people):
        assert [c["clip_id"] for c in people.ann.get("/api/clips").json()["clips"]] == ["clip-vid-ann"]
        assert people.bob.get("/api/clips", params={"video_id": "vid-ann"}).json()["clips"] == []

    def test_a_frame_of_your_own_video_cannot_be_read_through_someone_elses_url(self, people):
        w = people.world
        ann_frame, _ = w.ids("vid-ann")
        assert people.ann.get(f"/api/videos/vid-ann/frames/{ann_frame}/image").status_code == 200
        # bob's own video id with ann's frame number
        assert people.bob.get(f"/api/videos/vid-bob/frames/{ann_frame}/image").status_code == 404

    def test_a_frame_of_your_other_video_is_not_reachable_through_this_videos_url(self, people):
        w = people.world
        w.add_video(people.ann, "vid-ann-2", rich=True)
        other_frame, _ = w.ids("vid-ann-2")
        assert people.ann.get(f"/api/videos/vid-ann-2/frames/{other_frame}/image").status_code == 200
        assert people.ann.get(f"/api/videos/vid-ann/frames/{other_frame}/image").status_code == 404

    def test_a_highlight_of_another_video_is_not_reachable(self, people):
        w = people.world
        _, ann_highlight = w.ids("vid-ann")
        assert people.ann.get(f"/api/videos/vid-ann/highlights/{ann_highlight}/thumbnail").status_code == 200
        assert people.bob.get(f"/api/videos/vid-bob/highlights/{ann_highlight}/thumbnail").status_code == 404

    def test_a_highlight_reel_cannot_include_someone_elses_clip(self, people):
        response = people.bob.post("/api/clips/highlight-reel", json={"title": "r", "clip_ids": ["clip-vid-bob", "clip-vid-ann"]})
        assert response.status_code == 404

    def test_other_accounts_cannot_delete_or_change_anything(self, people):
        w = people.world
        assert people.bob.delete("/api/videos/vid-ann").status_code == 404
        assert people.bob.delete("/api/clips/clip-vid-ann").status_code == 404
        assert people.bob.post("/api/videos/vid-ann/reprocess", json={}).status_code == 404
        assert w.count(Video, external_id="vid-ann") == 1 and w.count(Clip, external_id="clip-vid-ann") == 1
        assert (w.tmp / "media" / "vid-ann.mp4").exists()

    def test_deleting_removes_the_video_and_everything_stored_for_it(self, people):
        w = people.world
        frames_dir = Path(settings.frames_path) / "vid-ann"
        (frames_dir / "keyframes").mkdir(parents=True)
        (frames_dir / "keyframes" / "scene_001.jpg").write_bytes(b"jpg")
        assert people.ann.delete("/api/videos/vid-ann").status_code == 200
        assert w.count(Video, external_id="vid-ann") == 0
        assert w.count(Transcript) == 1 and w.count(Clip) == 1 and w.count(Frame) == 1  # bob's rows only
        assert not (w.tmp / "media" / "vid-ann.mp4").exists()
        assert not (w.tmp / "media" / "vid-ann-clip.mp4").exists()
        assert not frames_dir.exists()
        assert (w.tmp / "media" / "vid-bob.mp4").exists()

    def test_deleting_a_video_removes_its_search_embeddings_and_keeps_the_others(self, people):
        import numpy as np
        from src.core.vector_store import VideoVectorStore

        store = VideoVectorStore(persist_directory=Path(settings.chroma_persist_directory))
        store.initialize_collections()
        for ext in ("vid-ann", "vid-bob"):
            store.add_transcript_embeddings(ext, np.array([[1.0, 0.0, 0.0, 0.0]]), [f"{ext}-seg"], [f"words of {ext}"], [(0.0, 1.0)])

        assert people.ann.delete("/api/videos/vid-ann").status_code == 200

        fresh = VideoVectorStore(persist_directory=Path(settings.chroma_persist_directory))
        fresh.initialize_collections()
        left = fresh.search_transcripts(np.array([1.0, 0.0, 0.0, 0.0]), n_results=10)
        assert [m["video_id"] for m in left.metadatas] == ["vid-bob"]

    def test_deleting_an_account_cascades_nothing_to_others(self, people):
        w = people.world
        with w.get_db() as db:
            db.delete(db.query(User).filter(User.username == "ann").one())
        assert w.count(Video, external_id="vid-bob") == 1
        assert people.bob.get("/api/videos/vid-bob").status_code == 200

    @needs_ffmpeg
    def test_uploads_belong_to_the_uploader(self, world):
        clip = make_video(world.tmp / "a.mp4")
        ann, bob = world.signup("ann"), world.signup("bob")
        video_id = upload(ann, clip).json()["video_id"]
        assert world.count(Video, external_id=video_id, user_id=ann.user["id"]) == 1
        assert ann.get(f"/api/videos/{video_id}").status_code == 200
        assert bob.get(f"/api/videos/{video_id}").status_code == 404
        assert bob.get("/api/videos").json()["videos"] == []

    def test_urls_added_by_link_belong_to_the_person_who_added_them(self, world):
        ann = world.signup("ann")
        with patch("src.api.videos.check_public_http_url", lambda url: url):
            response = ann.post("/api/videos/stream", json={"url": "https://example.com/v.mp4"})
        assert response.status_code == 200
        assert world.count(Video, user_id=ann.user["id"]) == 1
        response = ann.post("/api/videos/youtube", json={"url": "https://youtu.be/abc"})
        assert response.status_code == 200 and world.count(Video, user_id=ann.user["id"]) == 2


# ---------------------------------------------------------------------------
# Search never crosses accounts
# ---------------------------------------------------------------------------

class TestSearchIsolation:
    def test_keyword_search_does_not_find_other_peoples_words(self, people):
        body = {"query": "secret words", "search_mode": "keyword", "top_k": 10}
        ann_hits = people.ann.post("/api/search/transcript", json=body).json()
        texts = [r["text"] if "text" in r else str(r) for r in ann_hits["results"]]
        assert texts and all("vid-ann" in t for t in texts) and not any("vid-bob" in t for t in texts)
        assert not any("vid-ann" in str(r) for r in people.bob.post("/api/search/transcript", json=body).json()["results"])

    def test_keyword_search_naming_someone_elses_video_finds_nothing(self, people):
        body = {"query": "secret words", "search_mode": "keyword", "video_ids": ["vid-ann"]}
        assert people.bob.post("/api/search/transcript", json=body).json()["results"] == []

    def test_a_scoped_store_hides_other_videos_inside_the_search_itself(self, people):
        """
        The closest vector belongs to ann. If the filter ran after the search, bob asking for one result
        would get nothing; filtering inside the search returns bob's own.
        """
        import numpy as np
        from src.core.access import scoped_store
        from src.core.auth import Caller, reset_current_caller, set_current_caller
        from src.core.vector_store import VideoVectorStore

        store = VideoVectorStore(persist_directory=Path(settings.chroma_persist_directory))
        store.initialize_collections()
        query = np.array([1.0, 0.0, 0.0] + [0.0] * 5)
        near, far = query.copy(), np.array([0.2, 1.0, 0, 0, 0, 0, 0, 0])
        for ext, vec in (("vid-ann", near), ("vid-bob", far)):
            store.add_transcript_embeddings(ext, np.array([vec]), [f"{ext}-seg"], [f"words of {ext}"], [(0.0, 1.0)])

        def search_as(user_id, is_admin=False, requested=None, **kw):
            token = set_current_caller(Caller(user_id, "u", is_admin, False))
            try:
                return scoped_store(store, requested).search_transcripts(query, n_results=1, **kw)
            finally:
                reset_current_caller(token)

        ann_id, bob_id = people.ann.user["id"], people.bob.user["id"]
        assert [m["video_id"] for m in search_as(bob_id).metadatas] == ["vid-bob"]
        assert [m["video_id"] for m in search_as(ann_id).metadatas] == ["vid-ann"]
        assert search_as(bob_id, requested=["vid-ann"]).ids == []               # asking for it by name does not help
        assert search_as(bob_id, video_id="vid-ann").ids == []                  # nor does a single-video filter
        assert [m["video_id"] for m in search_as(bob_id, requested=["vid-ann", "vid-bob"]).metadatas] == ["vid-bob"]
        assert [m["video_id"] for m in search_as(0, is_admin=True).metadatas] == ["vid-ann"]   # administrators see all
        assert search_as(999).ids == []                                          # someone with no videos finds nothing

    def test_a_request_without_a_caller_sees_nothing(self, world):
        """Forgetting to sign a request in must fail closed"""
        from src.core.access import find_video, visible_video_ids
        world.add_video(None, "v")
        with world.get_db() as db:
            assert find_video(db, "v") is None
            assert visible_video_ids(db) == []


# ---------------------------------------------------------------------------
# Cross-site requests
# ---------------------------------------------------------------------------

class TestCrossSite:
    def test_a_write_from_another_site_is_refused_even_with_the_cookie(self, people):
        response = people.ann.delete("/api/videos/vid-ann", headers={"Origin": "http://evil.example"})
        assert response.status_code == 403 and "Cross-site" in response.json()["detail"]
        assert people.world.count(Video, external_id="vid-ann") == 1

    def test_a_null_origin_and_a_foreign_referer_are_refused_too(self, people):
        assert people.ann.delete("/api/videos/vid-ann", headers={"Origin": "null"}).status_code == 403
        assert people.ann.delete("/api/videos/vid-ann", headers={"Referer": "http://evil.example/page"}).status_code == 403

    def test_our_own_pages_and_non_browser_clients_still_work(self, people):
        assert people.ann.post("/api/auth/logout", headers={"Origin": "http://testserver"}).status_code == 200
        bob = people.bob
        assert bob.delete("/api/videos/vid-bob").status_code == 200  # no Origin at all: curl, scripts

    def test_a_configured_origin_may_write(self, people, monkeypatch):
        monkeypatch.setattr(settings, "cors_origins", ["http://app.example.com"])
        assert people.ann.delete("/api/videos/vid-ann", headers={"Origin": "http://app.example.com"}).status_code == 200

    def test_a_lookalike_origin_is_not_our_site(self, people, monkeypatch):
        monkeypatch.setattr(settings, "cors_origins", ["http://app.example.com"])
        for origin in ("http://app.example.com.evil.example", "https://app.example.com", "http://evil.example/http://app.example.com"):
            assert people.ann.delete("/api/videos/vid-ann", headers={"Origin": origin}).status_code == 403, origin

    def test_a_lookalike_of_our_own_host_is_not_our_site(self, people):
        # the test client's host is "testserver"
        for origin in ("http://testserver.evil.example", "http://nottestserver", "http://testserver:9999",
                       "http://evil.example/testserver"):
            assert people.ann.delete("/api/videos/vid-ann", headers={"Origin": origin}).status_code == 403, origin
        assert people.ann.get("/api/auth/me").status_code == 200

    def test_reading_is_not_blocked_by_the_origin_check(self, people):
        # a cross-site page cannot read the answer (CORS), and the cookie is SameSite=Lax; blocking GETs would break links
        assert people.ann.get("/api/videos", headers={"Origin": "http://evil.example"}).status_code == 200

    def test_signing_in_from_another_site_is_refused_only_when_a_cookie_is_present(self, world):
        # login CSRF: a foreign site must not be able to sign a victim into the attacker's account
        victim = world.signup("ann")
        response = victim.post("/api/auth/login", json={"username": "ann", "password": PASSWORD},
                               headers={"Origin": "http://evil.example"})
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# WebSockets
# ---------------------------------------------------------------------------

class TestWebSockets:
    def test_progress_needs_a_sign_in(self, people):
        with pytest.raises(WebSocketDisconnect):
            with people.world.client().websocket_connect("/api/ws/process/vid-ann"):
                pass

    def test_other_accounts_cannot_watch_your_video(self, people):
        with pytest.raises(WebSocketDisconnect) as info:
            with people.bob.websocket_connect("/api/ws/process/vid-ann"):
                pass
        assert info.value.code == 4404

    def test_the_owner_and_administrators_can_watch(self, people):
        for client in (people.ann, people.root):
            with client.websocket_connect("/api/ws/process/vid-ann") as ws:
                assert ws.receive_json()["event"] == "connected"

    def test_a_page_on_another_site_cannot_open_the_socket(self, people):
        with pytest.raises(WebSocketDisconnect):
            with people.ann.websocket_connect("/api/ws/process/vid-ann", headers={"Origin": "http://evil.example"}):
                pass

    def test_notifications_need_a_sign_in(self, people):
        with pytest.raises(WebSocketDisconnect):
            with people.world.client().websocket_connect("/api/ws/notifications"):
                pass
        with people.ann.websocket_connect("/api/ws/notifications") as ws:
            assert ws.receive_json()["event"] == "connected"

    @pytest.mark.asyncio
    async def test_a_notification_about_a_video_reaches_its_owner_and_administrators_only(self, people, monkeypatch):
        from src.api import websockets as ws_api

        class FakeSocket:
            def __init__(self):
                self.got = []

            async def send_json(self, message):
                self.got.append(message)

        manager = ws_api.ConnectionManager()
        ann, bob, root, anyone = FakeSocket(), FakeSocket(), FakeSocket(), FakeSocket()
        for sock, owner, admin in ((ann, people.ann.user["id"], False), (bob, people.bob.user["id"], False),
                                   (root, people.root.user["id"], True), (anyone, None, False)):
            manager.all_connections.add(sock)
            manager.owners[sock] = (owner, admin)
        monkeypatch.setattr(ws_api, "manager", manager)

        await ws_api.send_notification("info", "Done", "ready", video_id="vid-ann")
        assert len(ann.got) == 1 and len(root.got) == 1
        assert bob.got == [] and anyone.got == []

        await ws_api.send_notification("info", "Maintenance", "restarting")  # not about a video: everyone
        assert all(len(s.got) >= 1 for s in (ann, bob, root, anyone)) and len(bob.got) == 1
