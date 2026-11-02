"""
The research pipeline end to end with fake search and model clients (nothing leaves the machine).

Found by running the app: the web search matched an everyday word of the question and its dictionary
and arcade results were kept as evidence; max_sources was split in half per source whatever was
ticked (1 gave "No sources found"); a failed search looked like "nothing found"; saved research
downloaded without its findings because the stored and the fresh result had different shapes; and
citations were saved against ids that are not keys of the sources table, always as APA.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.core.database import Citation, DatabaseManager, ResearchQuery, Source, User
from src.core.research_orchestrator import ResearchOrchestrator
from src.core.web_search_client import WebSearchError
from src.core.arxiv_client import ArXivSearchError

QUESTION = "retrieval augmented generation versus fine tuning for knowledge"


class FakeWeb:
    def __init__(self, results=(), error=None):
        self.results, self.error, self.calls, self.fetched = list(results), error, [], []

    def search(self, query, max_results=10, extract_content=True, raise_on_error=False):
        self.calls.append({"query": query, "max_results": max_results, "extract_content": extract_content})
        if self.error:
            raise self.error
        return self.results[:max_results]

    def fetch_contents(self, results):
        self.fetched.extend(r.url for r in results)
        for r in results:
            r.content = "Full page text about retrieval augmented generation and fine tuning. " * 20
        return results


class FakeArxiv:
    def __init__(self, papers=(), error=None):
        self.papers, self.error, self.calls = list(papers), error, []

    def search(self, query, max_results=10, extract_text=True, raise_on_error=False, **kw):
        self.calls.append({"query": query, "max_results": max_results, "extract_text": extract_text})
        if self.error:
            raise self.error
        return self.papers[:max_results]


class FakeLLM:
    """Answers each step of the synthesis in the format the engine asks for"""

    def __init__(self, fail=None):
        self.fail, self.prompts = fail, []

    def generate(self, messages, max_tokens=0, temperature=0):
        if self.fail:
            raise RuntimeError(self.fail)
        user = messages[-1]["content"]
        self.prompts.append(user)
        if "Extract 3-5 key points" in user:
            return {"content": "- RAG retrieves documents at answer time."}
        if "Provide up to" in user:
            return {"content": "Finding: RAG retrieves documents when answering.\nType: fact\nSources: [1, 2]\nConfidence: 0.9\n\n"
                               "Finding: Fine tuning changes the model weights.\nType: fact\nSources: [1]\nConfidence: 0.8"}
        return {"content": "RAG retrieves, fine tuning trains. (Source: 1)"}


def web(n, relevant=True):
    return [SimpleNamespace(
        title=f"Retrieval augmented generation vs fine tuning {i}" if relevant else f"Arcade games and bowling {i}",
        url=f"https://example.com/{'rag' if relevant else 'arcade'}/{i}",
        # distinct text: identical sources are removed as duplicates
        snippet=(f"retrieval augmented generation versus fine tuning for knowledge, part {i}" if relevant else f"play games all day, round {i}"),
        content=None, relevance_score=1.0 - i / 10) for i in range(n)]


def paper(i, title=None):
    return SimpleNamespace(
        arxiv_id=f"2501.0000{i}", title=title or f"Fine tuning versus retrieval augmented generation {i}",
        summary=f"We compare retrieval augmented generation with fine tuning for knowledge, study {i}.", content=None,
        pdf_url=f"https://arxiv.org/pdf/2501.0000{i}", published=datetime(2025, 1, 1, tzinfo=timezone.utc),
        authors=[f"Author {i}"], citation_count=None)


@pytest.fixture
def user_id():
    db = DatabaseManager("sqlite:///./data/database.db")   # redirected to the scratch database by conftest
    with db.get_session() as session:
        user = User(username=f"orch_{datetime.utcnow().timestamp()}", email=f"o{datetime.utcnow().timestamp()}@example.com",
                    password_hash="x")
        session.add(user)
        session.commit()
        return user.id


def orchestrator(web_client=None, arxiv_client=None, llm=None):
    return ResearchOrchestrator(
        db_path="sqlite:///./data/database.db", web_search_client=web_client, arxiv_client=arxiv_client,
        llm_client=llm or FakeLLM(), embedding_model=None, cache_manager=None)


def research(o, user, **kw):
    kw = {"search_web": True, "search_arxiv": True, "max_sources": 6, **kw}
    return o.conduct_research(user_id=user, query=kw.pop("query", QUESTION), **kw)


class TestSearching:
    def test_a_full_run_returns_one_stored_shape_with_findings_sources_and_citations(self, user_id):
        result = research(orchestrator(FakeWeb(web(3)), FakeArxiv([paper(1), paper(2)])), user_id)
        assert result["status"] == "completed" and result["summary"]
        assert result["findings"][0]["text"] == result["findings"][0]["finding_text"]
        assert {s["type"] for s in result["sources"]} == {s["source_type"] for s in result["sources"]} <= {"web", "arxiv"}
        assert result["citations"] and result["stats"]["findings"] == len(result["findings"])
        assert result["warnings"] == []

    def test_the_budget_is_split_between_the_sources_really_searched(self, user_id):
        w, a = FakeWeb(web(10)), FakeArxiv([paper(i) for i in range(1, 10)])
        research(orchestrator(w, a), user_id, max_sources=10)
        assert w.calls[0]["max_results"] == 5 and a.calls[0]["max_results"] == 5

    def test_an_odd_budget_is_rounded_up_so_the_total_is_reached(self, user_id):
        w, a = FakeWeb(web(10)), FakeArxiv([paper(i) for i in range(1, 10)])
        research(orchestrator(w, a), user_id, max_sources=5)
        assert w.calls[0]["max_results"] == 3 and a.calls[0]["max_results"] == 3

    def test_one_source_gets_the_whole_budget(self, user_id):
        w = FakeWeb(web(10))
        research(orchestrator(w, FakeArxiv()), user_id, search_arxiv=False, max_sources=8)
        assert w.calls[0]["max_results"] == 8

    def test_a_budget_of_one_still_searches(self, user_id):
        a = FakeArxiv([paper(1)])
        result = research(orchestrator(None, a), user_id, search_web=False, max_sources=1)
        assert a.calls[0]["max_results"] == 1 and result["sources"]

    def test_keywords_not_the_sentence_go_to_arxiv_and_pdfs_are_not_downloaded(self, user_id):
        a = FakeArxiv([paper(1), paper(2), paper(3)])
        research(orchestrator(None, a), user_id, search_web=False, max_sources=3)
        assert a.calls[0]["query"].startswith("all:") and " AND " in a.calls[0]["query"]
        assert a.calls[0]["extract_text"] is False

    def test_broader_arxiv_queries_add_only_what_was_not_found(self, user_id):
        class Narrowing(FakeArxiv):
            def search(self, query, **kw):
                super().search(query, **kw)
                return [paper(1)] if len(self.calls) == 1 else [paper(1), paper(2)]
        a = Narrowing()
        result = research(orchestrator(None, a), user_id, search_web=False, max_sources=4)
        assert len(a.calls) >= 2
        assert len([s for s in result["sources"] if s["type"] == "arxiv"]) == 2        # paper 1 was not counted twice

    def test_the_web_is_searched_with_the_sentence_and_then_the_keywords_until_enough_is_found(self, user_id):
        class Picky(FakeWeb):
            def search(self, query, **kw):
                super().search(query, **kw)
                return [] if len(self.calls) == 1 else self.results      # the sentence found nothing
        w = Picky(web(4))
        result = research(orchestrator(w, None), user_id, search_arxiv=False, max_sources=4)
        assert [c["query"] for c in w.calls] == [QUESTION, "retrieval augmented generation fine tuning knowledge"]
        assert result["sources"]

    def test_pages_are_read_only_for_the_sources_that_are_kept(self, user_id):
        w = FakeWeb(web(2) + web(4, relevant=False))
        result = research(orchestrator(w, None), user_id, search_arxiv=False, max_sources=6)
        assert all("/rag/" in url for url in w.fetched) and len(w.fetched) == 2
        assert all(not c["extract_content"] for c in w.calls)
        assert result["sources"]

    def test_an_empty_web_search_is_reported(self, user_id):
        result = research(orchestrator(FakeWeb([]), FakeArxiv([paper(1)])), user_id)
        assert any("web search returned no results" in w for w in result["warnings"])


class TestRelevance:
    def test_sources_unrelated_to_the_question_are_left_out_and_reported(self, user_id):
        w = FakeWeb(web(2) + web(2, relevant=False))
        result = research(orchestrator(w, None), user_id, search_arxiv=False, max_sources=8)
        assert [s["url"] for s in result["sources"]] and all("/rag/" in s["url"] for s in result["sources"])
        assert any("Ignored 2 source(s)" in w for w in result["warnings"])

    def test_when_nothing_is_relevant_the_answer_says_so_and_the_model_is_not_asked(self, user_id):
        llm = FakeLLM()
        result = research(orchestrator(FakeWeb(web(3, relevant=False)), None, llm), user_id, search_arxiv=False)
        assert result["status"] == "completed" and "No relevant sources" in result["summary"]
        assert result["findings"] == [] and llm.prompts == []

    def test_the_floor_can_be_set(self, user_id, monkeypatch):
        monkeypatch.setenv("RESEARCH_MIN_RELEVANCE", "0.0")
        result = research(orchestrator(FakeWeb(web(2, relevant=False)), None), user_id, search_arxiv=False)
        assert result["sources"]


class TestFailures:
    def test_a_failed_search_is_an_error_not_an_empty_result(self, user_id):
        o = orchestrator(FakeWeb(error=WebSearchError("Web search failed: rate limited")), FakeArxiv(error=ArXivSearchError("ArXiv search failed: 429")))
        with pytest.raises(RuntimeError) as error:
            research(o, user_id)
        assert "rate limited" in str(error.value) and "429" in str(error.value)

    def test_one_search_failing_is_a_warning_when_the_other_found_sources(self, user_id):
        o = orchestrator(FakeWeb(error=WebSearchError("Web search failed: boom")), FakeArxiv([paper(1)]))
        result = research(o, user_id)
        assert result["sources"] and any("boom" in w for w in result["warnings"])

    def test_a_failed_research_is_saved_as_failed_with_its_reason(self, user_id):
        o = orchestrator(FakeWeb(error=WebSearchError("Web search failed: boom")), None)
        with pytest.raises(RuntimeError):
            research(o, user_id, search_arxiv=False)
        saved = o.list_user_queries(user_id)[0]
        assert saved["status"] == "failed"
        assert "boom" in o.get_research_query(saved["query_id"])["error_message"]

    def test_a_model_that_cannot_be_reached_fails_the_research_instead_of_completing_empty(self, user_id):
        o = orchestrator(None, FakeArxiv([paper(1)]), FakeLLM(fail="Could not reach Ollama at http://localhost:11434"))
        with pytest.raises(RuntimeError) as error:
            research(o, user_id, search_web=False)
        assert "Could not reach Ollama" in str(error.value)
        assert o.list_user_queries(user_id)[0]["status"] == "failed"

    def test_no_sources_at_all_is_a_completed_empty_result(self, user_id):
        result = research(orchestrator(FakeWeb([]), FakeArxiv([])), user_id)
        assert result["summary"] == "No sources found for the query." and result["sources"] == []

    def test_progress_is_reported_for_each_step(self, user_id):
        steps = []
        research(orchestrator(FakeWeb(web(2)), FakeArxiv([paper(1)])), user_id,
                 progress=lambda step, total, message: steps.append((step, total)))
        assert [s for s, _ in steps] == [1, 2, 3, 4, 5, 6] and {t for _, t in steps} == {6}

    def test_a_progress_callback_that_raises_does_not_stop_the_research(self, user_id):
        def boom(*a):
            raise ValueError("callback bug")
        assert research(orchestrator(None, FakeArxiv([paper(1)])), user_id, search_web=False, progress=boom)["findings"]


class TestSavedResearch:
    def test_citations_belong_to_stored_sources_in_the_requested_style(self, user_id):
        o = orchestrator(None, FakeArxiv([paper(1), paper(2)]))
        result = research(o, user_id, search_web=False, citation_style="IEEE")
        db = DatabaseManager("sqlite:///./data/database.db")
        with db.get_session() as session:
            source_ids = {s.id for s in session.query(Source).filter_by(query_id=result["query_id"])}
            citations = session.query(Citation).filter_by(query_id=result["query_id"]).order_by(Citation.citation_number).all()
            assert citations and {c.source_id for c in citations} <= source_ids
            assert {c.citation_style for c in citations} == {"IEEE"}
            assert session.query(ResearchQuery).get(result["query_id"]).citation_style == "IEEE"
        assert result["citations"][0].startswith("[1] ")

    def test_every_cited_source_gets_a_citation(self, user_id):
        result = research(orchestrator(None, FakeArxiv([paper(1), paper(2)])), user_id, search_web=False)
        assert len(result["citations"]) == 2          # findings cite sources 1 and 2

    def test_only_the_owner_can_load_a_query(self, user_id):
        o = orchestrator(None, FakeArxiv([paper(1)]))
        query_id = research(o, user_id, search_web=False)["query_id"]
        assert o.get_research_query(query_id, user_id=user_id)["query_id"] == query_id
        assert o.get_research_query(query_id, user_id="someone-else") is None
        assert o.get_research_query("no-such-id", user_id=user_id) is None

    def test_the_total_counts_all_queries_not_the_page(self, user_id):
        o = orchestrator(None, FakeArxiv([paper(1)]))
        for _ in range(3):
            research(o, user_id, search_web=False)
        assert o.count_user_queries(user_id) == 3 and len(o.list_user_queries(user_id, limit=2)) == 2

    def test_queries_left_processing_by_a_stopped_server_are_failed(self, user_id):
        o = orchestrator()
        db = DatabaseManager("sqlite:///./data/database.db")
        with db.get_session() as session:
            session.add(ResearchQuery(user_id=user_id, query_text="stuck", status="processing"))
            session.commit()
        assert o.fail_interrupted_queries() >= 1
        stuck = [q for q in o.list_user_queries(user_id) if q["query"] == "stuck"][0]
        assert stuck["status"] == "failed"
