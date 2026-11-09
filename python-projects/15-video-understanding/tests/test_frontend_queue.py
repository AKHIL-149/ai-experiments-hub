"""
The Videos page and the queue: where a video stands, and the Cancel / Retry / Process buttons.

Runs the real frontend/app.js in node against a stub DOM and stub fetch (skipped when node is not installed),
reusing the harness of test_frontend_auth.py.
"""

import json

import pytest

from tests.test_frontend_auth import run

HOSTILE = '"><img src=x onerror="PWN()">'


def video(**fields):
    base = {"video_id": "v1", "title": "T", "duration_seconds": 5, "processing_status": "completed", "error_message": None,
            "job_id": None, "job_status": None, "queue_position": None}
    return {**base, **fields}


def page_for(videos, script="await loadVideos();"):
    return run(["app.js"], [["/api/videos", 200, {"videos": videos, "total": len(videos)}]], script)


def html_of(page):
    return page["byId"]["videos-list"]["innerHTML"]


class TestStatusWords:
    @pytest.mark.parametrize("fields,label,css", [
        ({"job_status": "queued", "queue_position": 1}, "queued: next", "queued"),
        ({"job_status": "queued", "queue_position": 3}, "queued: #3", "queued"),
        ({"job_status": "queued", "queue_position": None}, "queued", "queued"),
        ({"job_status": "running", "processing_status": "processing"}, "processing", "processing"),
        ({"job_status": "running", "processing_status": "downloading"}, "downloading", "processing"),
        ({"processing_status": "completed"}, "completed", "completed"),
        ({"processing_status": "failed"}, "failed", "failed"),
        ({"processing_status": "pending"}, "pending", "pending"),
        # a finished video that is queued for another run says so
        ({"processing_status": "completed", "job_status": "queued", "queue_position": 2}, "queued: #2", "queued"),
    ])
    def test_the_label_and_style(self, fields, label, css):
        page = page_for([video(**fields)])
        html = html_of(page)
        assert f"status-{css}" in html and label in html


class TestButtons:
    def test_a_waiting_or_running_video_offers_cancel(self):
        html = html_of(page_for([video(job_id="job-1", job_status="queued", queue_position=1)]))
        assert "Cancel" in html and 'data-job="job-1"' in html
        assert "Retry" not in html and "Process<" not in html

    def test_a_failed_video_offers_retry_and_shows_why(self):
        html = html_of(page_for([video(processing_status="failed", error_message="The file is not a valid video")]))
        assert "Retry" in html and 'data-video="v1"' in html and "The file is not a valid video" in html

    def test_an_uploaded_video_that_never_ran_offers_process(self):
        html = html_of(page_for([video(processing_status="pending")]))
        assert "Process" in html and "Cancel" not in html

    def test_a_completed_video_has_no_button(self):
        html = html_of(page_for([video()]))
        assert "<button" not in html and "Cancel" not in html and "Retry" not in html

    def test_a_cancelled_video_shows_its_message_and_can_be_started_again(self):
        html = html_of(page_for([video(processing_status="pending", error_message="Processing cancelled")]))
        assert "Processing cancelled" in html and "Process" in html

    def test_an_old_error_is_not_shown_on_a_completed_video(self):
        assert "stale" not in html_of(page_for([video(processing_status="completed", error_message="stale")]))

    def test_hostile_values_stay_text_and_ids_never_enter_inline_script(self):
        page = page_for([video(video_id=HOSTILE, title=HOSTILE, job_id=HOSTILE, job_status="queued", queue_position=1,
                               processing_status="failed", error_message=HOSTILE)])
        html = html_of(page)
        assert "<img src=x" not in html and 'onerror="PWN' not in html
        # the buttons read ids from data- attributes, not from a script string a quote could break out of
        assert 'onclick="cancelJob(event, this.dataset.job)"' in html


class TestActions:
    def test_cancel_posts_to_the_job_and_stops_the_click_reaching_the_card(self):
        script = ("let stopped = false; await cancelJob({stopPropagation() { stopped = true; }}, 'job/1?x');"
                  "document.getElementById('flag').textContent = String(stopped);")
        page = run(["app.js"], [["/api/jobs/", 200, {"status": "cancelled"}], ["/api/videos", 200, {"videos": [], "total": 0}]], script)
        post = [c for c in page["calls"] if "/cancel" in c["url"]][0]
        assert post["method"] == "POST" and post["credentials"] == "include"
        assert post["url"].endswith("/api/jobs/job%2F1%3Fx/cancel")  # the id cannot change the path
        assert page["byId"]["flag"]["textContent"] == "true"
        assert any(c["url"].endswith("/api/videos") for c in page["calls"])  # the list was refreshed

    def test_process_posts_to_the_video(self):
        script = "await startProcessing({stopPropagation() {}}, 'v 1');"
        page = run(["app.js"], [["/process", 200, {"status": "queued"}], ["/api/videos", 200, {"videos": [], "total": 0}]], script)
        post = [c for c in page["calls"] if c["url"].endswith("/process")][0]
        assert post["method"] == "POST" and "/api/videos/v%201/process" in post["url"] and json.loads(post["body"]) == {}

    def test_a_refused_cancel_is_reported_not_swallowed_silently(self):
        script = "await cancelJob({stopPropagation() {}}, 'job-1');"
        page = run(["app.js"], [["/api/jobs/", 409, {"detail": "The job is already completed"}],
                                ["/api/videos", 200, {"videos": [], "total": 0}]], script)
        toasts = [c for c in page["created"] if "already completed" in c["textContent"]]
        assert toasts


class TestAutoRefresh:
    def test_the_list_refreshes_itself_while_something_waits_or_runs(self):
        page = page_for([video(job_id="j", job_status="queued", queue_position=2)])
        assert 5000 in page["timers"]

    def test_it_does_not_poll_when_nothing_is_active(self):
        page = page_for([video(), video(video_id="v2", processing_status="failed")])
        assert 5000 not in page["timers"]
