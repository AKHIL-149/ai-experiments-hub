"""
The Ollama client against a fake Ollama server. Ollama reports a missing model as HTTP 404 with
{"error": "..."} and a failure mid-stream as an {"error": ...} line; both used to be ignored, so the
chat "succeeded" with an empty reply that was then saved and shown as a blank bubble.
"""

import asyncio
import json

import pytest
from aiohttp import web

from src.core.llm_client import LLMClient


class FakeOllama:
    """Serves /api/chat and /api/tags from a script"""

    def __init__(self):
        self.status = 200
        self.lines = []                 # NDJSON objects sent for /api/chat
        self.error_body = None
        self.models = []
        self.requests = []

    async def chat(self, request):
        self.requests.append(await request.json())
        if self.status != 200:
            return web.json_response(self.error_body or {}, status=self.status)
        response = web.StreamResponse()
        await response.prepare(request)
        for line in self.lines:
            await response.write((json.dumps(line) + "\n").encode())
        return response

    async def tags(self, request):
        return web.json_response({"models": self.models}, status=self.status)


def run_with_server(fake, coroutine_factory):
    async def main():
        app = web.Application()
        app.router.add_post("/api/chat", fake.chat)
        app.router.add_get("/api/tags", fake.tags)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        client = LLMClient()
        client.ollama_url = f"http://127.0.0.1:{port}"
        try:
            return await coroutine_factory(client)
        finally:
            await runner.cleanup()
    return asyncio.run(main())


async def collect(client, model="llama3.2:3b"):
    return [t async for t in client.stream_completion([{"role": "user", "content": "hi"}], "ollama", model)]


def tokens(*texts):
    return [{"message": {"content": t}, "done": False} for t in texts] + [{"message": {"content": ""}, "done": True}]


def test_normal_stream():
    fake = FakeOllama()
    fake.lines = tokens("Hel", "lo", "!")
    assert run_with_server(fake, collect) == ["Hel", "lo", "!"]
    assert fake.requests[0]["model"] == "llama3.2:3b" and fake.requests[0]["stream"] is True


def test_a_model_that_is_not_installed_says_how_to_install_it():
    fake = FakeOllama()
    fake.status, fake.error_body = 404, {"error": "model 'phi3:mini' not found"}
    with pytest.raises(RuntimeError) as error:
        run_with_server(fake, lambda c: collect(c, "phi3:mini"))
    assert str(error.value) == "Ollama does not have the model 'phi3:mini'. Install it with: ollama pull phi3:mini"


def test_other_http_errors_carry_ollamas_message():
    fake = FakeOllama()
    fake.status, fake.error_body = 500, {"error": "out of memory"}
    with pytest.raises(RuntimeError, match="Ollama error: out of memory"):
        run_with_server(fake, collect)


def test_http_error_without_a_body_still_reports_something():
    fake = FakeOllama()
    fake.status = 503
    with pytest.raises(RuntimeError, match="Ollama error: HTTP 503"):
        run_with_server(fake, collect)


def test_an_error_in_the_middle_of_the_stream_is_raised_after_the_text_so_far():
    fake = FakeOllama()
    fake.lines = [{"message": {"content": "partial "}}, {"error": "model runner crashed"}]
    async def go(client):
        got = []
        with pytest.raises(RuntimeError, match="Ollama error: model runner crashed"):
            async for token in client.stream_completion([{"role": "user", "content": "x"}], "ollama", "m"):
                got.append(token)
        return got
    assert run_with_server(fake, go) == ["partial "]


def test_a_stream_with_no_text_is_an_error_not_an_empty_answer():
    fake = FakeOllama()
    fake.lines = tokens()                      # just the "done" line
    with pytest.raises(RuntimeError, match="returned an empty response"):
        run_with_server(fake, collect)


def test_ollama_not_running():
    async def go():
        client = LLMClient()
        client.ollama_url = "http://127.0.0.1:1"           # nothing listens here
        return await collect(client)
    with pytest.raises(RuntimeError, match="Could not reach Ollama.*ollama serve"):
        asyncio.run(go())


def test_blank_lines_and_garbage_lines_are_skipped():
    fake = FakeOllama()
    async def raw_chat(request):
        response = web.StreamResponse(); await response.prepare(request)
        await response.write(b"\n   \nnot json\n" + json.dumps({"message": {"content": "ok"}}).encode() + b"\n")
        return response
    fake.chat = raw_chat
    assert run_with_server(fake, collect) == ["ok"]


class TestInstalledModels:
    def test_lists_installed_chat_models_sorted(self):
        fake = FakeOllama()
        fake.models = [
            {"name": "qwen3:8b", "details": {"family": "qwen3"}},
            {"name": "llama3.2:3b", "details": {"family": "llama"}},
            {"name": "nomic-embed-text:latest", "details": {"family": "nomic-bert"}},
            {"name": "some-bert-model", "details": {"family": "bert"}},
            {"name": "my-embedding-model:latest", "details": {"family": "llama"}},      # only its name says "embedding"
            {"name": "llava:latest", "details": {"family": "llama"}},
        ]
        names = run_with_server(fake, lambda c: c.list_ollama_models())
        assert names == ["llama3.2:3b", "llava:latest", "qwen3:8b"]          # no embedding models

    def test_empty_when_ollama_is_down_or_errors(self):
        fake = FakeOllama()
        fake.status = 500
        assert run_with_server(fake, lambda c: c.list_ollama_models()) == []

        async def unreachable():
            client = LLMClient(); client.ollama_url = "http://127.0.0.1:1"
            return await client.list_ollama_models()
        assert asyncio.run(unreachable()) == []

    def test_models_without_details_do_not_break_the_list(self):
        fake = FakeOllama()
        fake.models = [{"name": "plain"}, {"name": "x", "details": None}, {"details": {}}]
        assert run_with_server(fake, lambda c: c.list_ollama_models()) == ["plain", "x"]
