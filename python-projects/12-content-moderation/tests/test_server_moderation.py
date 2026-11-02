"""
The server end to end (workers and models faked): accounts, submissions, files, reviews, appeals, policies,
the job WebSocket and start-up.

Found by running the app: a username was shown unescaped in the admin dashboard (any text was accepted); the
login limit could be skipped by sending a different X-Forwarded-For each time; a user uploading a file
somebody else had submitted was handed that person's record; any user could pick the critical queue; a
text file called x.png was accepted as an image; moderators got a 404 for the picture they were asked to
judge; a review could be repeated and an appeal decided twice, flipping the outcome; policy numbers were
not checked; the job WebSocket answered anyone; and the server listened on every interface.
"""

import io
import itertools
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from starlette.websockets import WebSocketDisconnect

import server
from src.core import queue_manager as qm
from src.core.database import ContentItem, ContentStatus, DatabaseManager, Review, User, UserRole

ROOT = Path(__file__).resolve().parent.parent
counter = itertools.count()
PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    server.login_throttle._failures.clear()
    sent = []
    monkeypatch.setattr(qm.classify_text_task, "apply_async", lambda **kw: sent.append(("text", kw)))
    monkeypatch.setattr(qm.classify_image_task, "apply_async", lambda **kw: sent.append(("image", kw)))
    monkeypatch.setattr(qm.classify_video_task, "apply_async", lambda **kw: sent.append(("video", kw)))
    return sent


@pytest.fixture
def sent(reset_state):
    return reset_state


def register(client, username=None, password=PASSWORD, email=None):
    n = next(counter)
    return client.post("/api/auth/register", json={
        "username": username if username is not None else f"user_{n}_{uuid.uuid4().hex[:6]}",
        "email": email or f"u{n}_{uuid.uuid4().hex[:6]}@example.com", "password": password})


def new_user(role=UserRole.USER):
    client = TestClient(server.app)
    response = register(client)
    assert response.status_code == 200, response.text
    if role != UserRole.USER:
        with DatabaseManager().get_session() as db:
            db.query(User).filter_by(id=response.json()["user"]["id"]).first().role = role
            db.commit()
    client.user_id = response.json()["user"]["id"]
    return client


@pytest.fixture
def user():
    return new_user()


@pytest.fixture
def moderator():
    return new_user(UserRole.MODERATOR)


def submit_text(client, text="a friendly comment", priority=0):
    return client.post("/api/content", data={"content_type": "text", "text_content": text, "priority": str(priority)})


def png(color=(10, 120, 200), size=(32, 24)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def submit_image(client, data=None, name="pic.png"):
    return client.post("/api/content", data={"content_type": "image"}, files={"file": (name, data if data is not None else png(), "image/png")})


def set_status(content_id, status):
    with DatabaseManager().get_session() as db:
        db.query(ContentItem).filter_by(id=content_id).first().status = status
        db.commit()


class TestAccounts:
    @pytest.mark.parametrize("username", ["<img src=x onerror=alert(1)>", "a b c", "name;drop", "x\ny", "ab", "x" * 51, "   ", "naïve"])
    def test_a_username_that_is_not_plain_is_refused(self, username):
        assert register(TestClient(server.app), username=username).status_code == 400

    @pytest.mark.parametrize("username", ["alice", "Alice_99", "a.b-c", "x" * 50])
    def test_plain_usernames_are_fine(self, username):
        username = username + uuid.uuid4().hex[:4] if len(username) < 50 else username[:46] + uuid.uuid4().hex[:4]
        assert register(TestClient(server.app), username=username).status_code == 200

    def test_usernames_and_emails_are_unique_ignoring_case(self):
        base = f"CaseTest{uuid.uuid4().hex[:6]}"
        assert register(TestClient(server.app), username=base, email=f"{base}@example.com").status_code == 200
        assert register(TestClient(server.app), username=base.lower(), email="other@example.com").status_code == 400
        assert register(TestClient(server.app), username="someone_else_x", email=f"{base.upper()}@EXAMPLE.COM").status_code == 400

    def test_surrounding_spaces_are_trimmed(self):
        name = f"trim{uuid.uuid4().hex[:6]}"
        response = register(TestClient(server.app), username=f"  {name}  ")
        assert response.status_code == 200 and response.json()["user"]["username"] == name

    @pytest.mark.parametrize("email", ["a@b", "a b@c.de", "<x>@c.de", "no-at.example.com", "a@b@c.de", "x" * 100 + "@c.de"])
    def test_bad_emails(self, email):
        assert register(TestClient(server.app), email=email).status_code == 400

    def test_a_password_bcrypt_would_cut_is_refused(self):
        assert register(TestClient(server.app), password="x" * 73).status_code == 400
        assert register(TestClient(server.app), password="x" * 72).status_code == 200
        assert register(TestClient(server.app), password="é" * 37).status_code == 400     # 74 bytes

    def test_login_is_throttled_per_username_and_client(self):
        name = f"thr{uuid.uuid4().hex[:6]}"
        client = TestClient(server.app)
        register(client, username=name)
        for _ in range(server.login_throttle.max_failures):
            assert client.post("/api/auth/login", json={"username": name, "password": "wrong-password"}).status_code == 401
        blocked = client.post("/api/auth/login", json={"username": name, "password": PASSWORD})
        assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) > 0
        assert client.post("/api/auth/login", json={"username": "someone_else", "password": "x"}).status_code == 401

    def test_a_deactivated_account_is_not_revealed_without_its_password(self):
        name = f"deact{uuid.uuid4().hex[:6]}"
        client = TestClient(server.app)
        user_id = register(client, username=name).json()["user"]["id"]
        with DatabaseManager().get_session() as db:
            db.query(User).filter_by(id=user_id).first().is_active = False
            db.commit()
        wrong = TestClient(server.app).post("/api/auth/login", json={"username": name, "password": "not-the-password"})
        right = TestClient(server.app).post("/api/auth/login", json={"username": name, "password": PASSWORD})
        assert wrong.status_code == 401 and wrong.json()["detail"] == "Invalid username or password"
        assert right.status_code == 401 and right.json()["detail"] == "Account is deactivated"

    def test_an_unknown_user_costs_the_same_work_as_a_wrong_password(self, monkeypatch):
        import bcrypt
        from src.core import auth_manager
        checks = []
        real = bcrypt.checkpw
        monkeypatch.setattr(auth_manager.bcrypt, "checkpw", lambda p, h: checks.append(h) or real(p, h))
        TestClient(server.app).post("/api/auth/login", json={"username": "nobody_at_all", "password": "whatever1"})
        assert checks == [auth_manager._DUMMY_HASH]

    def test_login_register_and_guest_run_in_a_worker_thread(self):
        import inspect
        for handler in (server.login, server.register, server.guest_login):
            assert not inspect.iscoroutinefunction(handler), handler.__name__

    def test_validation_errors_are_one_sentence(self, user):
        detail = user.get("/api/content?limit=0").json()["detail"]
        assert isinstance(detail, str) and detail.startswith("limit: ")


class TestForwardedAddresses:
    def request(self, headers, host="10.0.0.5"):
        from starlette.requests import Request
        scope = {"type": "http", "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
                 "client": (host, 1234), "method": "GET", "path": "/"}
        return Request(scope)

    def test_forwarding_headers_are_ignored_by_default(self, monkeypatch):
        from src.middleware.rate_limiter import client_ip
        monkeypatch.delenv("TRUST_PROXY", raising=False)
        assert client_ip(self.request({"X-Forwarded-For": "6.6.6.6", "X-Real-IP": "7.7.7.7"})) == "10.0.0.5"

    def test_they_are_read_behind_a_proxy_you_run(self, monkeypatch):
        from src.middleware.rate_limiter import client_ip
        monkeypatch.setenv("TRUST_PROXY", "true")
        assert client_ip(self.request({"X-Forwarded-For": "6.6.6.6, 10.0.0.1"})) == "6.6.6.6"
        assert client_ip(self.request({"X-Real-IP": "7.7.7.7"})) == "7.7.7.7"
        assert client_ip(self.request({})) == "10.0.0.5"

    def test_rate_limits_follow_the_real_address_not_a_header(self, monkeypatch):
        from src.middleware.rate_limiter import RateLimitMiddleware
        monkeypatch.delenv("TRUST_PROXY", raising=False)
        middleware = RateLimitMiddleware.__new__(RateLimitMiddleware)
        ids = {middleware._get_identifier(self.request({"X-Forwarded-For": f"1.2.3.{i}"})) for i in range(5)}
        assert ids == {"ip:10.0.0.5"}               # five "different" clients are one
        assert server.get_client_ip(self.request({"X-Forwarded-For": "9.9.9.9"})) == "10.0.0.5"


class TestSubmitting:
    def test_a_text_is_accepted_and_sent_to_a_worker(self, user, sent):
        response = submit_text(user, "hello")
        assert response.status_code == 200 and response.json()["content"]["status"] == "processing"
        assert sent[0][0] == "text" and sent[0][1]["args"][1] == "hello"

    @pytest.mark.parametrize("text", ["", "   \n"])
    def test_a_blank_text_is_refused(self, user, text):
        assert submit_text(user, text).status_code in (400, 422)

    def test_a_text_over_the_limit_is_refused_and_one_at_the_limit_is_not(self, user, sent):
        assert submit_text(user, "x" * (server.MAX_TEXT_CHARS + 1)).status_code == 400
        assert submit_text(user, "x" * server.MAX_TEXT_CHARS).status_code == 200
        assert len(sent) == 1

    def test_the_status_is_processing_before_the_task_is_sent(self, user, monkeypatch):
        seen = {}

        def apply_async(**kw):
            with DatabaseManager().get_session() as db:
                seen["status"] = db.query(ContentItem).filter_by(id=kw["args"][0]).first().status
        monkeypatch.setattr(qm.classify_text_task, "apply_async", apply_async)
        submit_text(user)
        assert seen["status"] == ContentStatus.PROCESSING      # a worker's later result cannot be overwritten by this

    def test_a_failed_send_flags_the_content_for_review(self, user, monkeypatch):
        monkeypatch.setattr(qm.classify_text_task, "apply_async", lambda **kw: (_ for _ in ()).throw(ConnectionError("redis down")))
        response = submit_text(user)
        assert response.status_code == 200 and response.json()["content"]["status"] == "flagged"
        assert "redis down" in response.json()["error"]

    @pytest.mark.parametrize("priority,code", [(0, 200), (5, 200), (6, 403), (10, 403), (11, 400), (-1, 400)])
    def test_users_choose_normal_or_high_priority(self, user, priority, code):
        assert submit_text(user, priority=priority).status_code == code

    def test_moderators_may_use_the_critical_queue(self, moderator, sent):
        assert submit_text(moderator, priority=10).status_code == 200
        assert sent[0][1]["queue"] == "critical"

    def test_the_rate_of_priority_is_not_trusted_from_the_client_for_queue_names(self, user, sent):
        submit_text(user, priority=5)
        assert sent[0][1]["queue"] == "high" and sent[0][1]["priority"] == 5

    def test_an_image_is_accepted(self, user, sent):
        response = submit_image(user)
        assert response.status_code == 200 and sent[0][0] == "image"

    @pytest.mark.parametrize("payload,name", [
        (b"this is not an image at all", "x.png"), (b"MZ\x90\x00 executable", "x.jpg"), (b"", "x.png"), (png()[:20], "x.png"),
    ])
    def test_a_file_that_is_not_an_image_is_refused(self, user, sent, payload, name):
        response = submit_image(user, payload, name)
        assert response.status_code == 400 and not sent

    def test_an_image_that_claims_billions_of_pixels_is_refused(self, user, sent):
        buffer = io.BytesIO()
        Image.new("1", (20000, 20000)).save(buffer, format="PNG")        # compresses to a few KB
        assert len(buffer.getvalue()) < 1_000_000
        response = submit_image(user, buffer.getvalue())
        assert response.status_code == 400 and "too large" in response.json()["detail"]

    def test_a_large_but_not_extreme_image_is_refused_by_the_pixel_limit(self, user, sent):
        buffer = io.BytesIO()
        Image.new("1", (8000, 8000)).save(buffer, format="PNG")          # 64 million pixels: over our 50 million
        response = submit_image(user, buffer.getvalue())
        assert response.status_code == 400 and "too large" in response.json()["detail"] and not sent

    def test_the_wrong_extension_is_refused(self, user):
        assert submit_image(user, png(), "pic.exe").status_code == 400

    def test_an_oversized_upload_is_refused(self, user, monkeypatch):
        monkeypatch.setattr(server.get_file_handler(), "max_upload_size", 100)
        assert submit_image(user, png(size=(200, 200))).status_code == 400

    def test_the_upload_is_read_in_pieces_and_stops_at_the_limit(self, user, monkeypatch):
        import asyncio
        from fastapi import HTTPException
        monkeypatch.setattr(server.get_file_handler(), "max_upload_size", 2 * 1024 * 1024)
        reads = []

        class Upload:
            filename = "huge.png"

            async def read(self, n=-1):
                reads.append(n)
                return b"x" * (n if n > 0 else 500_000_000)

        with DatabaseManager().get_session() as db:
            owner = db.query(User).filter_by(id=user.user_id).first()
            db.expunge(owner)
        with pytest.raises(HTTPException) as refused:
            asyncio.run(server.submit_content(content_type="image", text_content=None, priority=0, file=Upload(), user=owner))
        assert refused.value.status_code == 400
        assert reads and all(n == 1024 * 1024 for n in reads) and len(reads) <= 3

    def test_the_same_file_from_the_same_user_returns_their_existing_item(self, user, sent):
        data = png((1, 2, 3))
        first = submit_image(user, data).json()["content"]["id"]
        again = submit_image(user, data).json()
        assert again["duplicate"] is True and again["content"]["id"] == first and len(sent) == 1

    def test_another_users_identical_file_is_their_own_submission_not_a_leak(self, user, sent):
        data = png((9, 8, 7))
        mine = submit_image(user, data).json()["content"]
        other = new_user()
        theirs = other.post("/api/content", data={"content_type": "image"}, files={"file": ("pic.png", data, "image/png")}).json()
        assert not theirs.get("duplicate") and theirs["content"]["id"] != mine["id"]
        assert theirs["content"]["user_id"] == other.user_id and len(sent) == 2


class TestListing:
    @pytest.mark.parametrize("query", ["limit=0", "limit=201", "limit=-1", "offset=-1"])
    def test_paging_is_bounded(self, user, query):
        assert user.get(f"/api/content?{query}").status_code == 422

    def test_only_the_users_own_items_are_listed(self, user):
        submit_text(user, "mine")
        other = new_user()
        assert other.get("/api/content").json()["total"] == 0 and user.get("/api/content").json()["total"] == 1

    def test_moderator_lists_are_bounded_too(self, moderator):
        assert moderator.get("/api/moderation/queue?limit=500").status_code == 422
        assert moderator.get("/api/moderation/queue?limit=200").status_code == 200

    def test_analytics_days_are_bounded(self, moderator):
        assert moderator.get("/api/analytics/trends?days=0").status_code == 422
        assert moderator.get("/api/analytics/trends?days=100000").status_code == 422


class TestUploadedFiles:
    def test_the_owner_and_moderators_can_open_the_file(self, user, moderator):
        content_id = submit_image(user).json()["content"]["id"]
        for who in (user, moderator):
            response = who.get(f"/api/content/{content_id}/file")
            assert response.status_code == 200 and response.headers["content-type"] == "image/png"
            assert response.headers["x-content-type-options"] == "nosniff" and response.content[:4] == b"\x89PNG"

    def test_other_users_get_the_answer_for_a_missing_file(self, user):
        content_id = submit_image(user).json()["content"]["id"]
        other = new_user()
        assert other.get(f"/api/content/{content_id}/file").status_code == 404
        assert other.get("/api/content/no-such-id/file").status_code == 404

    def test_a_text_item_has_no_file(self, user):
        content_id = submit_text(user).json()["content"]["id"]
        assert user.get(f"/api/content/{content_id}/file").status_code == 404

    def test_a_path_outside_the_upload_directory_is_never_served(self, user, moderator):
        content_id = submit_image(user).json()["content"]["id"]
        with DatabaseManager().get_session() as db:
            db.query(ContentItem).filter_by(id=content_id).first().file_path = "/etc/hosts"
            db.commit()
        assert moderator.get(f"/api/content/{content_id}/file").status_code == 404
        with DatabaseManager().get_session() as db:
            db.query(ContentItem).filter_by(id=content_id).first().file_path = str(server.UPLOAD_DIR / ".." / ".." / "server.py")
            db.commit()
        assert moderator.get(f"/api/content/{content_id}/file").status_code == 404

    def test_the_dashboard_points_at_the_file_endpoint(self):
        source = (ROOT / "static/js/admin/dashboard.js").read_text()
        assert "/api/content/${item.id}/file" in source and "/api/content/${content.id}/file" in source
        assert 'src="${item.file_path}"' not in source and 'src="${content.file_path}"' not in source


class TestReviews:
    def flagged(self, user):
        content_id = submit_text(user).json()["content"]["id"]
        set_status(content_id, ContentStatus.FLAGGED)
        return content_id

    def test_a_flagged_item_can_be_reviewed(self, user, moderator):
        content_id = self.flagged(user)
        response = moderator.post("/api/moderation/review", json={"content_id": content_id, "approved": True, "notes": "fine"})
        assert response.status_code == 200 and moderator.get(f"/api/content/{content_id}").json()["status"] == "approved"

    @pytest.mark.parametrize("status", [ContentStatus.PENDING, ContentStatus.PROCESSING])
    def test_content_still_being_classified_cannot_be_reviewed(self, user, moderator, status):
        content_id = self.flagged(user)
        set_status(content_id, status)
        response = moderator.post("/api/moderation/review", json={"content_id": content_id, "approved": True})
        assert response.status_code == 400 and "still being classified" in response.json()["detail"]

    def test_a_review_note_is_limited(self, user, moderator):
        content_id = self.flagged(user)
        assert moderator.post("/api/moderation/review", json={"content_id": content_id, "approved": True, "notes": "x" * 5001}).status_code == 422
        assert moderator.post("/api/moderation/review", json={"content_id": content_id, "approved": True, "notes": "x" * 2001}).status_code == 400

    def test_only_moderators_review(self, user):
        content_id = self.flagged(user)
        assert user.post("/api/moderation/review", json={"content_id": content_id, "approved": True}).status_code == 403


class TestAppeals:
    def rejected(self, user):
        content_id = submit_text(user).json()["content"]["id"]
        set_status(content_id, ContentStatus.REJECTED)
        return content_id

    def appeal(self, user, content_id, reason="this was a joke"):
        return user.post("/api/appeals", json={"content_id": content_id, "reason": reason})

    def test_an_appeal_is_decided_once(self, user, moderator):
        appeal_id = self.appeal(user, self.rejected(user)).json()["appeal_id"]
        first = moderator.post(f"/api/appeals/{appeal_id}/review", json={"approved": True, "notes": "ok"})
        second = moderator.post(f"/api/appeals/{appeal_id}/review", json={"approved": False})
        assert first.status_code == 200 and first.json()["review"]["action"] == "appeal_approved"
        assert second.status_code == 400 and "already been reviewed" in second.json()["detail"]

    def test_the_second_decision_changes_nothing(self, user, moderator):
        content_id = self.rejected(user)
        appeal_id = self.appeal(user, content_id).json()["appeal_id"]
        moderator.post(f"/api/appeals/{appeal_id}/review", json={"approved": True})
        moderator.post(f"/api/appeals/{appeal_id}/review", json={"approved": False})
        assert moderator.get(f"/api/content/{content_id}").json()["status"] == "approved"

    def test_a_manual_review_settles_an_open_appeal_too(self, user, moderator):
        content_id = self.rejected(user)
        appeal_id = self.appeal(user, content_id).json()["appeal_id"]
        assert moderator.post("/api/moderation/review", json={"content_id": content_id, "approved": False}).status_code == 200
        later = moderator.post(f"/api/appeals/{appeal_id}/review", json={"approved": True})
        assert later.status_code == 400 and "already been reviewed" in later.json()["detail"]
        with DatabaseManager().get_session() as db:
            assert db.query(Review).filter_by(id=appeal_id).first().action == "appeal_rejected"

    @pytest.mark.parametrize("reason", ["", "   ", "x" * 1001])
    def test_the_reason_must_be_there_and_a_sane_size(self, user, reason):
        assert self.appeal(user, self.rejected(user), reason).status_code in (400, 422)

    def test_only_rejected_content_can_be_appealed_and_only_once(self, user):
        approved = submit_text(user).json()["content"]["id"]
        set_status(approved, ContentStatus.APPROVED)
        assert self.appeal(user, approved).status_code == 400
        rejected = self.rejected(user)
        assert self.appeal(user, rejected).status_code == 200
        assert self.appeal(user, rejected).status_code == 400

    def test_nobody_appeals_for_someone_else(self, user):
        content_id = self.rejected(user)
        assert self.appeal(new_user(), content_id).status_code == 400


class TestPolicies:
    def create(self, admin, **fields):
        body = {"name": f"policy-{uuid.uuid4().hex[:8]}", "category": "spam", "auto_reject_threshold": 0.9,
                "auto_approve_threshold": 0.95, "flag_review_threshold": 0.5, "severity": 5, **fields}
        return admin.post("/api/admin/policies", json=body)

    @pytest.fixture
    def admin(self):
        return new_user(UserRole.ADMIN)

    def test_a_sound_policy_is_created(self, admin):
        assert self.create(admin).status_code == 200

    @pytest.mark.parametrize("fields,message", [
        ({"auto_reject_threshold": 7}, "between 0 and 1"), ({"auto_reject_threshold": -1}, "between 0 and 1"),
        ({"auto_approve_threshold": 1.5}, "between 0 and 1"), ({"flag_review_threshold": -0.1}, "between 0 and 1"),
        ({"severity": 0}, "between 1 and 10"), ({"severity": 11}, "between 1 and 10"),
        ({"auto_reject_threshold": 0.3, "flag_review_threshold": 0.6}, "cannot be above"),
        ({"name": "   "}, "1-100 characters"), ({"name": "n" * 101}, "1-100 characters"),
    ])
    def test_numbers_that_cannot_work_are_refused(self, admin, fields, message):
        response = self.create(admin, **fields)
        assert response.status_code in (400, 422) and message in response.json()["detail"]

    def test_an_update_is_checked_against_the_values_it_leaves_in_place(self, admin):
        policy = self.create(admin, auto_reject_threshold=0.9, flag_review_threshold=0.5).json()["policy"]
        bad = admin.patch(f"/api/admin/policies/{policy['id']}", json={"flag_review_threshold": 0.95})
        assert bad.status_code == 400 and "cannot be above" in bad.json()["detail"]
        assert admin.patch(f"/api/admin/policies/{policy['id']}", json={"flag_review_threshold": 0.7}).status_code == 200

    def test_switching_a_policy_off_needs_no_valid_numbers(self, admin):
        policy = self.create(admin).json()["policy"]
        with DatabaseManager().get_session() as db:
            from src.core.database import Policy
            db.query(Policy).filter_by(id=policy["id"]).first().flag_review_threshold = 0.99    # a policy saved before the checks existed
            db.commit()
        assert admin.patch(f"/api/admin/policies/{policy['id']}", json={"enabled": False}).status_code == 200

    def test_only_admins_create_policies(self, moderator):
        assert self.create(moderator).status_code == 403


class TestJobWebSocket:
    def job_for(self, owner):
        content_id = submit_text(owner).json()["content"]["id"]
        with DatabaseManager().get_session() as db:
            from src.core.database import ModerationJob
            return db.query(ModerationJob).filter_by(content_id=content_id).first().id

    @pytest.fixture(autouse=True)
    def finished_jobs(self, monkeypatch):
        monkeypatch.setattr(qm.QueueManager, "get_job_status", lambda self, job_id: {
            "job_id": job_id, "status": "completed", "celery_state": "SUCCESS", "result": {"category": "clean"}})
        import asyncio
        real_sleep = asyncio.sleep
        monkeypatch.setattr(server.asyncio, "sleep", lambda s: real_sleep(0))

    def test_the_owner_gets_updates_until_done(self, user):
        job_id = self.job_for(user)
        with user.websocket_connect(f"/ws/jobs/{job_id}") as ws:
            first = ws.receive_json()
            last = ws.receive_json()
        assert first["status"] == "completed" and last["done"] is True

    def test_a_job_the_database_calls_over_ends_the_stream_even_if_celery_says_nothing(self, user, monkeypatch):
        # a task's result expires from Redis: Celery then reports PENDING for a job that finished long ago
        monkeypatch.setattr(qm.QueueManager, "get_job_status", lambda self, job_id: {
            "job_id": job_id, "status": "failed", "celery_state": "PENDING"})
        job_id = self.job_for(user)
        with user.websocket_connect(f"/ws/jobs/{job_id}") as ws:
            assert ws.receive_json()["status"] == "failed"
            assert ws.receive_json()["done"] is True

    def test_a_moderator_may_watch_any_job(self, user, moderator):
        job_id = self.job_for(user)
        with moderator.websocket_connect(f"/ws/jobs/{job_id}") as ws:
            assert ws.receive_json()["job_id"] == job_id

    def test_anonymous_clients_are_refused(self, user):
        job_id = self.job_for(user)
        with pytest.raises(WebSocketDisconnect) as refused:
            with TestClient(server.app).websocket_connect(f"/ws/jobs/{job_id}"):
                pass
        assert refused.value.code == 1008

    def test_another_users_job_is_the_same_as_no_job(self, user):
        job_id = self.job_for(user)
        other = new_user()
        for target in (job_id, "no-such-job"):
            with pytest.raises(WebSocketDisconnect) as refused:
                with other.websocket_connect(f"/ws/jobs/{target}"):
                    pass
            assert refused.value.code == 1008 and refused.value.reason == "Job not found"

    def test_another_origin_is_refused(self, user):
        job_id = self.job_for(user)
        with pytest.raises(WebSocketDisconnect) as refused:
            with user.websocket_connect(f"/ws/jobs/{job_id}", headers={"origin": "http://localhost:3000"}):
                pass
        assert refused.value.reason == "Origin not allowed"

    @pytest.mark.parametrize("origin,host,ok", [
        (None, "localhost:8001", True), ("http://localhost:8001", "localhost:8001", True),
        ("http://192.168.1.5:8001", "192.168.1.5:8001", True), ("http://localhost:3000", "localhost:8001", False),
        ("http://evil.example", "localhost:8001", False), ("http://evil.example", None, False),
    ])
    def test_origin_rules(self, origin, host, ok, monkeypatch):
        monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:8001")
        assert server.origin_allowed(origin, host) is ok


class TestHealthAndStartup:
    def test_health_says_whether_a_worker_is_running(self, monkeypatch):
        monkeypatch.setattr(qm.QueueManager, "worker_status", lambda self, max_age_seconds=10.0: {"available": False, "workers": 0})
        body = TestClient(server.app).get("/api/health").json()
        assert body["status"] == "ok" and body["worker"] == {"available": False, "workers": 0}

    def test_health_survives_a_broken_worker_check(self, monkeypatch):
        def broken(self, max_age_seconds=10.0):
            raise RuntimeError("inspect failed")
        monkeypatch.setattr(qm.QueueManager, "worker_status", broken)
        body = TestClient(server.app).get("/api/health").json()
        assert body["status"] == "ok" and body["worker"]["available"] is False

    def test_start_up_closes_jobs_of_moderated_content(self, user):
        import asyncio
        from src.core.database import JobStatus, ModerationJob
        content_id = submit_text(user).json()["content"]["id"]
        with DatabaseManager().get_session() as db:
            item = db.query(ContentItem).filter_by(id=content_id).first()
            item.status, item.moderated_at = ContentStatus.APPROVED, __import__("datetime").datetime.utcnow()
            db.commit()
        asyncio.run(server.startup_event())
        with DatabaseManager().get_session() as db:
            assert db.query(ModerationJob).filter_by(content_id=content_id).first().status == JobStatus.COMPLETED

    def run_main(self, env=None):
        code = ("import dotenv; dotenv.load_dotenv = lambda *a, **k: False\n"
                "import runpy, uvicorn\ncalls = []\nuvicorn.run = lambda app, **kw: calls.append(kw)\n"
                "runpy.run_path('server.py', run_name='__main__')\nprint(calls[0])\n")
        full_env = {**os.environ, "PYTHONPATH": str(ROOT), "DATABASE_URL": f"sqlite:///{tempfile.mkdtemp()}/s.db"}
        # importing server in this process loaded the developer's .env (HOST, PORT ...) into os.environ
        for key in ("HOST", "PORT", "ALLOWED_ORIGINS", "TRUST_PROXY"):
            full_env.pop(key, None)
        full_env.update(env or {})
        done = subprocess.run([sys.executable, "-W", "ignore", "-c", code], cwd=ROOT, env=full_env, capture_output=True, text=True, timeout=180)
        assert done.returncode == 0, done.stderr[-1500:]
        return done.stdout.strip().splitlines()[-1]

    def test_the_server_listens_on_loopback_by_default(self):
        assert self.run_main() == "{'host': '127.0.0.1', 'port': 7000, 'proxy_headers': False}"

    def test_host_and_port_come_from_the_environment(self):
        assert self.run_main({"HOST": "0.0.0.0", "PORT": "9100", "TRUST_PROXY": "true"}) == "{'host': '0.0.0.0', 'port': 9100, 'proxy_headers': True}"
