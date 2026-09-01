"""
Regression tests for the use_vision=False video moderation bug.

server.py's video submission path explicitly passed use_vision=False
("Faster processing") when enqueuing a video classification job, and
both create_video_job() and classify_video_task() defaulted to False
too. Since NudeNet only does a binary NSFW/nudity check, this meant
video moderation never actually analyzed content for anything else
(spam, hate speech, violence, misinformation, etc) - every video was
either a real NSFW hit or a content-blind "clean" result, regardless of
what it actually contained. That tradeoff made sense when vision meant
a slow, billed per-call API request; it doesn't with the free local
Ollama vision path. Confirmed live: a video correctly went from an
always-instant "clean" verdict to a real ~14s multi-frame vision
classification after this fix.

These tests lock in that the whole chain - server.py's endpoint,
create_video_job()'s default, and classify_video_task()'s default -
actually requests vision, not just that the feature exists somewhere.
"""

import inspect
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from server import app
from src.core.queue_manager import QueueManager
from src.workers.video_worker import classify_video_task


@pytest.fixture
def client():
    return TestClient(app)


def test_create_video_job_defaults_use_vision_true():
    sig = inspect.signature(QueueManager.create_video_job)
    assert sig.parameters['use_vision'].default is True


def test_classify_video_task_defaults_use_vision_true():
    sig = inspect.signature(classify_video_task)
    assert sig.parameters['use_vision'].default is True


def test_submit_video_endpoint_requests_vision(client):
    """The actual /api/content video path must not silently pass
    use_vision=False regardless of what the defaults above say - this
    is the exact line that caused the live bug."""
    fake_job = MagicMock(id='job-1', celery_task_id='task-1', queue_name='high')

    guest_response = client.post('/api/auth/guest')
    session_token = guest_response.cookies.get('session_token')

    with patch.object(QueueManager, 'create_video_job', return_value=fake_job) as mock_create:
        response = client.post(
            '/api/content',
            data={'content_type': 'video', 'priority': '0'},
            files={'file': ('test.mp4', b'\x00\x00\x00\x18ftypmp42fake-mp4-bytes', 'video/mp4')},
            cookies={'session_token': session_token}
        )

    assert response.status_code == 200
    assert mock_create.called
    _, kwargs = mock_create.call_args
    assert kwargs.get('use_vision') is True
