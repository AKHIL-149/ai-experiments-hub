import pytest

from src.core.config import Settings
from src.services import ask as ask_mod
from src.services.embedding import EmbeddingError
from src.services.llm import LLMBadOutput, LLMError
from tests.conftest import FakeEmbedder, ScriptedLLM

S = Settings(_env_file=None)


def run(story, question, llm, mode="graph", embedder="default", **kw):
    emb = FakeEmbedder() if embedder == "default" else embedder
    return ask_mod.ask(story.db, question, mode=mode, llm=llm, embedder=emb, settings=kw.pop("settings", S), **kw)


def plan(start, *steps):
    return lambda q: {"start": list(start), "steps": [{"relation": r, "direction": d} for r, d in steps]}


def answer_citing(*labels, text="Imani Okafor", found=True):
    return lambda prompt: {"found": found, "answer": text, "cited": list(labels)}


# ---------------------------------------------------------------- the plan

def test_plan_is_cleaned_and_limited():
    good = {"start": ["Soro Labs", " ", 5, "A", "B", "C"], "steps": [
        {"relation": "founded", "direction": "in"}, {"relation": " ", "direction": "in"}, {"relation": "x", "direction": "sideways"},
        "junk", {"relation": "a", "direction": "out"}, {"relation": "b", "direction": "out"}, {"relation": "c", "direction": "out"},
        {"relation": "d", "direction": "out"}]}
    p = ask_mod.plan_question(ScriptedLLM(plan=lambda q: good), "Q?")
    assert p.start == ["Soro Labs", "A", "B"] and [s["relation"] for s in p.steps] == ["founded", "a", "b", "c"]   # junk skipped, then at most 4


def test_plan_retries_bad_output_once_then_gives_up():
    answers = iter([LLMBadOutput("x"), {"start": ["A"], "steps": []}])
    llm = ScriptedLLM(plan=lambda q: (_ for _ in ()).throw(a) if isinstance(a := next(answers), Exception) else a)
    assert ask_mod.plan_question(llm, "Q?").start == ["A"]
    always = ScriptedLLM(plan=lambda q: LLMBadOutput("x"))
    assert ask_mod.plan_question(always, "Q?") is None and len(always.prompts["plan"]) == 2


def test_the_plan_prompt_teaches_direction_with_examples():
    assert "out = the current entity is the SUBJECT" in ask_mod.PLAN_SYSTEM and "Who founded the company that acquired Tessel AI?" in ask_mod.PLAN_SYSTEM


# ---------------------------------------------------------------- graph mode

def test_a_two_hop_question_is_answered_from_the_chain_with_citations(story):
    llm = ScriptedLLM(plan=plan(["Veltra Dynamics"], ("acquired", "out"), ("founded", "in")), answer=answer_citing("F1", "F2"))
    r = run(story, "Who founded the company that Veltra Dynamics acquired?", llm)
    assert r["found"] and r["answer"] == "Imani Okafor" and r["reasoning"]["mode"] == "graph" and r["reasoning"]["fallback"] is None
    assert [c["text"] for c in r["citations"]] == ["Veltra Dynamics acquired Soro Labs (2018..)", "Imani Okafor founded Soro Labs (2011..)"]
    assert r["citations"][0]["quote"] == "Veltra Dynamics acquired Soro Labs." and r["citations"][0]["document_title"] == "d01"
    assert r["reasoning"]["answer_entities"] == ["Imani Okafor"] and r["reasoning"]["evidence_documents"] == ["d01", "d02"]
    assert [s["relation"] for s in r["reasoning"]["steps"]] == ["acquired", "founded"]
    assert r["reasoning"]["steps"][0]["links"][0] == {"from": "Veltra Dynamics", "fact": "Veltra Dynamics acquired Soro Labs (2018..)", "to": "Soro Labs"}
    prompt = llm.prompts["answer"][0]
    assert "[F1] Veltra Dynamics acquired Soro Labs (2018..)" in prompt and 'source: "Veltra Dynamics acquired Soro Labs."' in prompt
    assert "Question: Who founded the company that Veltra Dynamics acquired?" in prompt and "Passages" not in prompt
    assert r["timings_ms"].keys() == {"retrieve", "answer"}


def test_the_chain_only_shows_the_model_the_facts_on_the_way(story):
    llm = ScriptedLLM(plan=plan(["Veltra Dynamics"], ("acquired", "out"), ("founded", "in")), answer=answer_citing("F1"))
    run(story, "q about Veltra Dynamics", llm)
    prompt = llm.prompts["answer"][0]
    assert "Pennant" not in prompt and "Kellmar" not in prompt and prompt.count("[F") == 2


def test_a_wrong_direction_from_the_model_is_flipped_and_reported(story):
    llm = ScriptedLLM(plan=plan(["Soro Labs"], ("founded", "out")), answer=answer_citing("F1"))
    r = run(story, "Who founded Soro Labs?", llm)
    assert r["found"] and r["reasoning"]["steps"][0]["flipped"] is True and r["reasoning"]["answer_entities"] == ["Imani Okafor"]


def test_a_broken_chain_falls_back_to_the_facts_around_the_entities_and_tells_the_model(story):
    llm = ScriptedLLM(plan=plan(["Soro Labs"], ("married to", "out")), answer=answer_citing("F1", text="Imani Okafor founded it"))
    r = run(story, "Who did the founder of Soro Labs marry?", llm)
    assert "nothing matches 'married to'" in r["reasoning"]["fallback"] and r["reasoning"]["facts_considered"] > 0
    prompt = llm.prompts["answer"][0]
    assert "Soro Labs" in prompt and "Note: The relations the question asks for could not be followed" in prompt and "nothing matches 'married to'" in prompt


def test_a_chain_that_works_adds_no_note(story):
    llm = ScriptedLLM(plan=plan(["Soro Labs"], ("founded", "in")), answer=answer_citing("F1"))
    run(story, "Who founded Soro Labs?", llm)
    assert "Note:" not in llm.prompts["answer"][0]


@pytest.mark.parametrize("question,expected", [
    ("How is Imani Okafor connected to Veltra Dynamics?", True), ("What is the connection between Noor Haddad and Tobias Marsh?", True),
    ("How are Lee and Quill related?", True), ("Which company is linked to Kellmar?", True), ("What is the relationship of A to B", True),
    ("Who founded Soro Labs?", False), ("How many people work at Acme?", False), ("How are things going and why", True),
])
def test_connection_questions(question, expected):
    assert ask_mod.is_connection_question(question) is expected


def test_a_connection_question_is_answered_from_the_path_without_planning(story):
    llm = ScriptedLLM(plan=plan(["Imani Okafor"], ("works at", "out")), answer=answer_citing("F1", "F2", text="through Soro Labs"))
    r = run(story, "How is Imani Okafor connected to Veltra Dynamics?", llm)
    assert llm.prompts["plan"] == [] and r["reasoning"]["connection_question"] is True
    assert r["reasoning"]["paths"] == [["Imani Okafor founded Soro Labs (2011..)", "Veltra Dynamics acquired Soro Labs (2018..)"]]
    assert r["found"] and len(r["citations"]) == 2
    assert "Describe the whole chain, naming every entity on it." in llm.prompts["answer"][0]


def test_only_path_answers_ask_for_the_whole_chain(story):
    llm = ScriptedLLM(plan=plan(["Soro Labs"], ("founded", "in")), answer=answer_citing("F1"))
    run(story, "Who founded Soro Labs?", llm)
    assert "whole chain" not in llm.prompts["answer"][0]


def test_a_connection_question_with_one_known_entity_still_uses_the_planner(story):
    llm = ScriptedLLM(plan=plan(["Soro Labs"], ("founded", "in")), answer=answer_citing("F1"))
    r = run(story, "How is Soro Labs connected to Zorg Industries?", llm)
    assert llm.prompts["plan"] and "connection_question" not in r["reasoning"]


def test_the_answer_rules_warn_about_near_misses():
    assert "does not answer the question" in ask_mod.ANSWER_SYSTEM and "invested in" in ask_mod.ANSWER_SYSTEM


def test_no_plan_falls_back_and_still_answers(story):
    llm = ScriptedLLM(plan=lambda q: LLMBadOutput("junk"), answer=answer_citing("F1"))
    r = run(story, "What happened to Soro Labs?", llm)
    assert r["reasoning"]["fallback"] == "the model did not give a usable plan" and r["reasoning"]["facts_considered"] > 0 and r["found"]


def test_the_planner_name_is_used_even_when_the_question_words_differ(story):
    llm = ScriptedLLM(plan=plan(["the Soro company"], ("founded", "in")), answer=answer_citing("F1"))
    r = run(story, "Who started it?", llm)      # the question itself names nothing; the plan's start does
    assert r["reasoning"]["seeds"][0]["name"] == "Soro Labs" and r["found"]


def test_two_entities_without_steps_are_connected_by_a_path(story):
    llm = ScriptedLLM(plan=plan(["Imani Okafor", "Veltra Dynamics"]), answer=answer_citing("F1", "F2", text="through Soro Labs"))
    r = run(story, "How is Imani Okafor connected to Veltra Dynamics?", llm)
    assert r["reasoning"]["paths"] == [["Imani Okafor founded Soro Labs (2011..)", "Veltra Dynamics acquired Soro Labs (2018..)"]]
    assert {c["text"] for c in r["citations"]} == {"Imani Okafor founded Soro Labs (2011..)", "Veltra Dynamics acquired Soro Labs (2018..)"}


def test_a_plan_with_two_entities_and_no_steps_uses_paths_whatever_the_wording(story):
    llm = ScriptedLLM(plan=plan(["Imani Okafor", "Veltra Dynamics"]), answer=answer_citing("F1", "F2", text="Soro Labs"))
    r = run(story, "Who is Imani Okafor to Veltra Dynamics?", llm)     # no 'connected' in the question: the planner decides
    assert "connection_question" not in r["reasoning"] and len(r["reasoning"]["paths"]) == 1 and llm.prompts["plan"]


def test_only_graph_modes_use_the_connection_shortcut(story):
    llm = ScriptedLLM(answer=answer_citing("F1"))
    r = run(story, "How is Imani Okafor connected to Veltra Dynamics?", llm, mode="subgraph")
    assert "connection_question" not in r["reasoning"] and r["reasoning"]["paths"] == []


def test_a_connection_question_shows_every_fact_between_the_two_entities(story):
    story.fact(story.veltra, "partnered with", story.soro, title="d30")
    story.db.commit()
    llm = ScriptedLLM(answer=answer_citing("F1"))
    run(story, "How is Veltra Dynamics connected to Soro Labs?", llm)
    prompt = llm.prompts["answer"][0]
    assert "acquired Soro Labs (2018..)" in prompt and "partnered with Soro Labs" in prompt and llm.prompts["plan"] == []


def test_two_entities_get_every_direct_fact_between_them(story):
    story.fact(story.veltra, "partnered with", story.soro, title="d30")
    story.db.commit()
    llm = ScriptedLLM(plan=plan(["Veltra Dynamics", "Soro Labs"]), answer=answer_citing("F1", text="2018"))
    r = run(story, "When did Veltra Dynamics acquire Soro Labs?", llm)
    prompt = llm.prompts["answer"][0]
    assert "acquired Soro Labs (2018..)" in prompt and "partnered with Soro Labs" in prompt


def test_a_question_about_one_entity_gets_its_neighbourhood(story):
    llm = ScriptedLLM(plan=plan(["Kellmar"]), answer=answer_citing("F1"))
    r = run(story, "What do we know about Kellmar?", llm)
    prompt = llm.prompts["answer"][0]
    assert "located in Kellmar" in prompt and "is a city in Dravia" in prompt


# ---------------------------------------------------------------- the other modes

def test_subgraph_mode_does_not_plan(story):
    llm = ScriptedLLM(answer=answer_citing("F1"))
    r = run(story, "Tell me about Soro Labs", llm, mode="subgraph")
    assert llm.prompts["plan"] == [] and r["reasoning"]["plan"] is None and r["reasoning"]["facts_considered"] > 0


def test_vector_mode_uses_only_passages(story):
    from src.models.graph import Chunk
    story.db.get(Chunk, story.docs["d01"][1]).text = "Veltra Dynamics acquired Soro Labs in 2018."
    story.db.commit()
    llm = ScriptedLLM(answer=answer_citing("P1", text="Veltra Dynamics"))
    r = run(story, "Who acquired Soro Labs?", llm, mode="vector")
    assert r["found"] and r["citations"][0]["kind"] == "passage" and r["citations"][0]["document_title"] == "d01"
    assert "Facts:" not in llm.prompts["answer"][0] and llm.prompts["plan"] == [] and r["reasoning"]["passages_considered"] == 4
    assert r["reasoning"]["facts_considered"] == 0 and "d01" in r["reasoning"]["evidence_documents"]


def test_vector_mode_needs_an_embedder(story):
    with pytest.raises(EmbeddingError):
        run(story, "Who acquired Soro Labs?", ScriptedLLM(), mode="vector", embedder=None)


def test_hybrid_mode_adds_passages_to_the_chain(story):
    llm = ScriptedLLM(plan=plan(["Veltra Dynamics"], ("acquired", "out"), ("founded", "in")), answer=answer_citing("F2", "P1"))
    r = run(story, "Who founded the company that Veltra Dynamics acquired?", llm, mode="hybrid")
    prompt = llm.prompts["answer"][0]
    assert "Facts:" in prompt and "Passages:" in prompt and r["reasoning"]["mode"] == "hybrid"
    assert {c["kind"] for c in r["citations"]} == {"fact", "passage"}


def test_auto_means_graph(story):
    llm = ScriptedLLM(plan=plan(["Soro Labs"], ("founded", "in")), answer=answer_citing("F1"))
    r = run(story, "Who founded Soro Labs?", llm, mode="auto")
    assert r["reasoning"]["mode"] == "graph" and "Passages:" not in llm.prompts["answer"][0]


def test_hybrid_survives_a_failing_embedding_model_for_the_passages(story):
    class Broken(FakeEmbedder):
        def embed(self, texts, kind="document"):
            if kind == "document" and len(texts) > 1 and any("Passage of" in t for t in texts):
                raise EmbeddingError("down")
            return super().embed(texts, kind)
    llm = ScriptedLLM(plan=plan(["Soro Labs"], ("founded", "in")), answer=answer_citing("F1"))
    r = run(story, "Who founded Soro Labs?", llm, mode="hybrid", embedder=Broken())
    assert r["found"] and "passages_skipped" in r["reasoning"]


# ---------------------------------------------------------------- no entity in the question

def test_a_question_naming_nothing_uses_the_facts_closest_in_wording(story):
    llm = ScriptedLLM(plan=plan([]), answer=answer_citing("F1", text="Tamsen"))
    r = run(story, "which university did somebody attend", llm)
    assert r["reasoning"]["fallback"].startswith("no entity of the question") and r["reasoning"]["facts_considered"] > 0 and r["found"]


def test_without_embeddings_and_without_entities_there_is_nothing_to_go_on(story):
    llm = ScriptedLLM(plan=plan([]))
    r = run(story, "what is the meaning of life", llm, embedder=None)
    assert r["found"] is False and r["answer"] == "not found" and llm.prompts["answer"] == [] and r["citations"] == []


def test_an_embedding_failure_in_the_chain_falls_back_to_word_stems(story):
    class Down(FakeEmbedder):
        def embed(self, texts, kind="document"):
            raise EmbeddingError("embedding model is down")
    llm = ScriptedLLM(plan=plan(["Soro Labs"], ("founded", "in")), answer=answer_citing("F1"))
    r = run(story, "Who founded Soro Labs?", llm, embedder=Down())
    assert r["found"] and "word stems only" in r["reasoning"]["fallback"] and r["reasoning"]["answer_entities"] == ["Imani Okafor"]


# ---------------------------------------------------------------- the answer and its citations

def test_nothing_retrieved_means_not_found_without_asking_the_model(world):
    llm = ScriptedLLM()
    r = ask_mod.ask(world.db, "Who founded Zorg?", mode="graph", llm=llm, embedder=None, settings=S)
    assert r["found"] is False and r["answer"] == "not found" and llm.prompts["answer"] == [] and "Nothing" in r["note"]


def test_the_model_can_say_it_is_not_in_the_facts(story):
    llm = ScriptedLLM(plan=plan(["Soro Labs"], ("founded", "in")), answer=lambda p: {"found": False, "answer": "not found", "cited": []})
    r = run(story, "Who is the CEO of Soro Labs?", llm)
    assert r["found"] is False and r["answer"] == "not found" and r["citations"] == []


def test_made_up_citations_are_dropped_and_reported(story):
    llm = ScriptedLLM(plan=plan(["Soro Labs"], ("founded", "in")), answer=answer_citing("F1", "F9", "[f1]", "P3", "nonsense"))
    r = run(story, "Who founded Soro Labs?", llm)
    assert [c["label"] for c in r["citations"]] == ["F1"] and r["dropped_citations"] == ["F9", "P3", "NONSENSE"]


def test_an_answer_without_any_valid_citation_is_flagged(story):
    llm = ScriptedLLM(plan=plan(["Soro Labs"], ("founded", "in")), answer=answer_citing("F9"))
    r = run(story, "Who founded Soro Labs?", llm)
    assert r["found"] and "without citing" in r["warning"]


def test_a_citation_list_that_is_not_a_list_is_ignored(story):
    for cited in (None, "F1", 5):
        llm = ScriptedLLM(plan=plan(["Soro Labs"], ("founded", "in")), answer=lambda p, c=cited: {"found": True, "answer": "Imani Okafor", "cited": c})
        r = run(story, "Who founded Soro Labs?", llm)
        assert r["found"] and r["citations"] == [] and "without citing" in r["warning"]


def test_repeated_citations_are_listed_once(story):
    llm = ScriptedLLM(plan=plan(["Soro Labs"], ("founded", "in")), answer=answer_citing("F1", "f1", "[F1]"))
    assert [c["label"] for c in run(story, "Who founded Soro Labs?", llm)["citations"]] == ["F1"]


def test_found_with_an_empty_answer_counts_as_not_found(story):
    llm = ScriptedLLM(plan=plan(["Soro Labs"], ("founded", "in")), answer=lambda p: {"found": True, "answer": "  ", "cited": []})
    r = run(story, "Who founded Soro Labs?", llm)
    assert r["found"] is False and r["answer"] == "not found"


def test_unusable_answers_are_retried_once_then_reported(story):
    answers = iter([LLMBadOutput("x"), {"found": True, "answer": "Imani Okafor", "cited": ["F1"]}])

    def flaky(p):
        a = next(answers)
        if isinstance(a, Exception):
            raise a
        return a
    r = run(story, "Who founded Soro Labs?", ScriptedLLM(plan=plan(["Soro Labs"], ("founded", "in")), answer=flaky))
    assert r["found"] and r["answer"] == "Imani Okafor"
    bad = ScriptedLLM(plan=plan(["Soro Labs"], ("founded", "in")), answer=lambda p: LLMBadOutput("x"))
    r = run(story, "Who founded Soro Labs?", bad)
    assert r["found"] is False and "usable answer" in r["warning"] and len(bad.prompts["answer"]) == 2


def test_a_model_that_is_down_raises(story):
    with pytest.raises(LLMError):
        run(story, "Who founded Soro Labs?", ScriptedLLM(plan=lambda q: LLMError("Cannot reach Ollama")))
    with pytest.raises(LLMError):
        run(story, "Who founded Soro Labs?", ScriptedLLM(plan=plan(["Soro Labs"], ("founded", "in")), answer=lambda p: LLMError("down")))


def test_a_verified_source_is_preferred_in_the_citation(story):
    from src.models.graph import FactSource
    f = story.fact(story.imani, "was born in", story.kellmar, quote="unverified quote", title="dA")
    did, cid = story.new_doc("dB")
    story.db.add(FactSource(fact_id=f.id, document_id=did, chunk_id=cid, evidence="verified quote", verified=True))
    story.db.commit()
    llm = ScriptedLLM(plan=plan(["Imani Okafor"], ("born in", "out")), answer=answer_citing("F1", text="Kellmar"))
    r = run(story, "Where was Imani Okafor born?", llm)
    assert r["citations"][0]["quote"] == "verified quote" and r["citations"][0]["verified"] is True


def test_scope_to_one_document(story):
    llm = ScriptedLLM(plan=plan(["Soro Labs"], ("acquired", "in")), answer=answer_citing("F1"))
    r = run(story, "Who acquired Soro Labs?", llm, document_id=story.docs["d02"][0])
    assert "nothing matches 'acquired'" in r["reasoning"]["fallback"]               # the acquisition is in another document
    assert "Veltra" not in llm.prompts["answer"][0] and r["reasoning"]["evidence_documents"] == ["d02"]


def test_modes_are_listed():
    assert ask_mod.MODES == ("auto", "vector", "subgraph", "graph", "hybrid")
