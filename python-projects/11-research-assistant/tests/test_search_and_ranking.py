"""
Web search, ArXiv error handling and source ranking.

Found by reading and running them: pages were fetched one by one (a timeout and retry each), with no size limit, and a PDF was
decoded as text; ".edu" matched inside "education-blog.com"; and the keyword fallback counted every word
of the question ("the", "what") as a substring, and divided by zero on an empty one.
"""

import pytest

from src.core import web_search_client as wsc
from src.core.web_search_client import SearchResult, WebSearchClient, WebSearchError
from src.utils.source_ranker import SourceRanker


class Cache:
    def __init__(self):
        self.store = {}

    def get(self, key, category=None):
        return self.store.get(key)

    def set(self, key, value, category=None, ttl_days=None):
        self.store[key] = value


class FakeDDGS:
    results = []
    error = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def text(self, query, max_results=10):
        if FakeDDGS.error:
            raise FakeDDGS.error
        return list(FakeDDGS.results)[:max_results]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(wsc, "DDGS", FakeDDGS)
    monkeypatch.setattr(wsc, "DUCKDUCKGO_AVAILABLE", True)
    FakeDDGS.results, FakeDDGS.error = [], None
    return WebSearchClient(cache_manager=Cache())


def hit(i):
    return {"title": f"T{i}", "href": f"https://example.com/{i}", "body": f"snippet {i}"}


class TestWebSearch:
    def test_results_are_returned_and_cached(self, client):
        FakeDDGS.results = [hit(1), hit(2)]
        assert [r.url for r in client.search("q", 5, extract_content=False)] == ["https://example.com/1", "https://example.com/2"]
        FakeDDGS.results = []                       # a second call is answered from the cache
        assert len(client.search("q", 5, extract_content=False)) == 2

    def test_an_empty_result_is_not_cached(self, client):
        assert client.search("q", 5, extract_content=False) == []
        FakeDDGS.results = [hit(1)]
        assert len(client.search("q", 5, extract_content=False)) == 1

    def test_a_failed_search_is_not_cached_either(self, client):
        FakeDDGS.error = RuntimeError("rate limited")
        assert client.search("q", 5, extract_content=False) == []
        FakeDDGS.error = None
        FakeDDGS.results = [hit(1)]
        assert len(client.search("q", 5, extract_content=False)) == 1

    def test_a_failure_can_be_raised(self, client):
        FakeDDGS.error = RuntimeError("rate limited")
        with pytest.raises(WebSearchError, match="rate limited"):
            client.search("q", 5, extract_content=False, raise_on_error=True)


class FakeResponse:
    def __init__(self, body=b"<html><body><p>Article text</p></body></html>", content_type="text/html; charset=utf-8", status=200):
        self.body, self.headers, self.status, self.encoding = body, {"Content-Type": content_type}, status, "utf-8"
        self.apparent_encoding = "utf-8"
        self.chunks_read = 0

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self.body), chunk_size):
            self.chunks_read += 1
            yield self.body[i:i + chunk_size]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestPageFetching:
    def fetch(self, client, response, url="https://example.com/x"):
        client.session = type("S", (), {"get": lambda self, u, **kw: response})()
        return client._fetch_and_extract_content(url)

    def test_an_html_page_is_read(self, client):
        assert "Article text" in self.fetch(client, FakeResponse())

    def test_a_pdf_is_not_decoded_as_text(self, client):
        with pytest.raises(ValueError, match="Not a text page"):
            self.fetch(client, FakeResponse(b"%PDF-1.4 binary", "application/pdf"))

    def test_reading_stops_at_the_size_limit(self, client):
        response = FakeResponse(b"<p>" + b"a" * 5_000_000 + b"</p>")
        self.fetch(client, response)
        assert response.chunks_read * 65536 < 1_500_000

    @pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/x", "javascript:alert(1)"])
    def test_only_web_addresses_are_fetched(self, client, url):
        with pytest.raises(ValueError, match="Not a web page"):
            self.fetch(client, FakeResponse(), url)

    def test_a_failing_page_keeps_the_snippet_and_the_others_are_still_read(self, client):
        results = [SearchResult("a", "https://example.com/bad", "bad snippet"), SearchResult("b", "https://example.com/ok", "ok snippet")]

        def get(self_, url, **kw):
            return FakeResponse(status=500) if "bad" in url else FakeResponse()
        client.session = type("S", (), {"get": get})()
        client.fetch_contents(results)
        assert results[0].content == "bad snippet" and "Article text" in results[1].content

    def test_pages_are_fetched_in_parallel(self, client):
        import threading, time
        active, peak = [0], [0]
        lock = threading.Lock()

        def get(self_, url, **kw):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.05)
            with lock:
                active[0] -= 1
            return FakeResponse()
        client.session = type("S", (), {"get": get})()
        client.fetch_contents([SearchResult(f"t{i}", f"https://example.com/{i}", "s") for i in range(5)])
        assert peak[0] > 1


class TestRanking:
    def rank(self, sources, query="neural networks"):
        return SourceRanker().rank_sources(sources, query)

    def src(self, url, title="x", content="y"):
        return {"id": url, "source_type": "web", "title": title, "content": content, "url": url}

    @pytest.mark.parametrize("url,score", [
        ("https://education-blog.com/post", 0.5),      # not ".edu"
        ("https://mygovernment.biz/", 0.5),            # not ".gov"
        ("https://my.education.example.com/", 0.5),    # ".edu" inside a label
        ("https://a.government.example.com/", 0.5),    # ".gov" inside a label
        ("https://www.uni.edu.au/", 0.8),              # ".edu." as a label of the host
        ("https://www.mit.edu/x", 0.8),
        ("https://cs.stanford.edu/", 0.8),
        ("https://data.nasa.gov/", 0.8),
        ("https://export.arxiv.org/abs/1", 1.0),
        ("https://en.wikipedia.org/wiki/X", 0.7),
        ("https://notarxiv.org/", 0.5),
    ])
    def test_domain_authority_matches_domains_not_substrings(self, url, score):
        assert self.rank([self.src(url)])[0].authority_score == score

    def test_a_lookalike_prefix_does_not_borrow_another_domains_score(self):
        # "nature.com" at the start of a ".edu" host: the host is a university, not Nature
        assert self.rank([self.src("https://nature.com.example.edu/")])[0].authority_score == 0.8

    def test_the_keyword_fallback_ignores_question_words(self):
        on_topic = self.src("https://a.example/", "Neural networks explained", "A neural network learns weights.")
        long_off_topic = self.src("https://b.example/", "Cooking", "what are the main ways to cook for the family " * 20)
        ranked = self.rank([long_off_topic, on_topic], "What are the main ways that neural networks learn?")
        assert ranked[0].url == "https://a.example/"
        assert ranked[1].similarity_score < ranked[0].similarity_score

    def test_whole_words_not_substrings(self):
        page = self.src("https://a.example/", "Catalog", "A catalogue of categories")
        assert self.rank([page], "cat")[0].similarity_score == 0.0

    def test_an_empty_question_does_not_divide_by_zero(self):
        assert self.rank([self.src("https://a.example/")], "")[0].similarity_score == 0.0
        assert self.rank([self.src("https://a.example/")], "the of and")[0].similarity_score == 0.0
