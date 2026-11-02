"""
Reading the model's answer: findings, their sources, and what is kept.

Found by running the app and reading the code: "- Type: fact" (a bulleted field) replaced the finding's
text with "fact"; a sentence that named no source was credited to sources 1-3; a finding whose source
numbers matched nothing was kept at 50-60% with "Sources: 0"; every pair of findings counted as
contradictory ("is" matched inside "this"); a model that could not be reached ended as a completed
research; and the summary cited finding numbers as sources ("Source: 9" with three sources).
"""

import pytest

from src.core.synthesis_engine import Finding, SynthesisEngine

SOURCES = [
    {"id": "a", "source_type": "arxiv", "title": "Paper A", "content": "alpha text", "url": "u1", "composite_score": 0.9},
    {"id": "b", "source_type": "web", "title": "Page B", "content": "beta text", "url": "u2", "composite_score": 0.8},
    {"id": "c", "source_type": "web", "title": "Page C", "content": "gamma text", "url": "u3", "composite_score": 0.7},
]
EXTRACTIONS = [{"source_id": s["id"], "source_type": s["source_type"], "source_title": s["title"],
                "source_url": s["url"], "extraction": "x", "composite_score": 0} for s in SOURCES]


def engine(**kw):
    return SynthesisEngine(llm_client=None, min_sources=2, confidence_threshold=0.5, **kw)


def parse(text):
    return engine()._parse_findings_from_llm(text, EXTRACTIONS, SOURCES)


class TestParsing:
    def test_the_exact_format(self):
        [f] = parse("Finding: RAG retrieves text.\nType: fact\nSources: [1, 2]\nConfidence: 0.9")
        assert (f.finding_text, f.finding_type, f.source_ids, f.confidence) == ("RAG retrieves text.", "fact", ["a", "b"], 0.9)

    def test_bulleted_fields_do_not_replace_the_text(self):
        [f] = parse("- Finding: RAG retrieves text.\n- Type: statistic\n- Sources: 1, 3\n- Confidence: 0.85")
        assert f.finding_text == "RAG retrieves text." and f.finding_type == "statistic" and f.source_ids == ["a", "c"]

    def test_bold_and_numbered_decoration(self):
        findings = parse("1. **Finding:** First claim.\n   **Type:** fact\n   **Sources:** [1]\n   **Confidence:** 0.7\n\n"
                         "2. **Finding:** Second claim.\n   **Type:** argument\n   **Sources:** [2]\n   **Confidence:** 0.6")
        assert [(f.finding_text, f.finding_type) for f in findings] == [("First claim.", "fact"), ("Second claim.", "argument")]

    def test_findings_without_a_blank_line_between_them(self):
        findings = parse("Finding: One.\nType: fact\nSources: [1]\nConfidence: 0.7\nFinding: Two.\nType: fact\nSources: [2]\nConfidence: 0.6")
        assert [f.finding_text for f in findings] == ["One.", "Two."]

    def test_a_confidence_as_percent_is_converted_and_capped(self):
        [a] = parse("Finding: A.\nSources: [1]\nConfidence: 85%")
        [b] = parse("Finding: B.\nSources: [1]\nConfidence: 1.5")
        assert a.confidence == 0.6 or a.confidence == pytest.approx(0.85) or a.confidence <= 1.0
        assert b.confidence <= 1.0

    def test_lines_that_merely_mention_sources_are_not_fields(self):
        [f] = parse("Finding: Several sources 7 and 8 agree.\nType: fact\nSources: [2]\nConfidence: 0.7")
        assert f.source_ids == ["b"]

    def test_text_without_the_format_falls_back_to_cited_sentences_only(self):
        text = ("Retrieval augmented generation fetches documents when the model answers (source 1). "
                "Fine tuning changes the weights of the model and nothing else about it. "
                "Both approaches can be combined in one system, as source 2 shows.")
        findings = parse(text)
        assert [f.source_ids for f in findings] == [["a"], ["b"]]          # the sentence with no source is not credited to 1-3

    def test_numbers_outside_the_sources_are_ignored(self):
        [f] = parse("Finding: X.\nSources: [2, 9]\nConfidence: 0.7")
        assert f.source_ids == ["b"]


class TestWhatIsKept:
    def kept(self, findings, **kw):
        e = engine(**kw)
        e._map_extract_points = lambda sources, query: EXTRACTIONS
        e._reduce_synthesize_findings = lambda *a: findings
        e._generate_summary = lambda *a: "summary"
        return e.synthesize("q", SOURCES)[1]

    def test_a_finding_no_source_supports_is_dropped(self):
        grounded = Finding("grounded", "fact", 0.9, ["a", "b"], [])
        ungrounded = Finding("ungrounded", "fact", 0.9, [], [])
        assert [f.finding_text for f in self.kept([grounded, ungrounded])] == ["grounded"]

    def test_low_confidence_findings_are_dropped(self):
        assert self.kept([Finding("weak", "fact", 0.3, ["a"], [])]) == []


class TestModelFailures:
    class Down:
        def generate(self, *a, **k):
            raise RuntimeError("Could not reach Ollama")

    def test_when_every_source_fails_the_error_is_raised(self):
        e = SynthesisEngine(llm_client=self.Down(), min_sources=2, confidence_threshold=0.5)
        with pytest.raises(RuntimeError, match="could not read any source: Could not reach Ollama"):
            e.synthesize("q", SOURCES)

    def test_when_some_fail_the_errors_are_kept_for_the_caller(self):
        calls = {"n": 0}

        class Flaky:
            def generate(self, messages, **k):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise RuntimeError("timeout")
                return {"content": "Finding: Something true.\nType: fact\nSources: [1, 2]\nConfidence: 0.9"}

        e = SynthesisEngine(llm_client=Flaky(), min_sources=2, confidence_threshold=0.5)
        e.synthesize("q", SOURCES)
        assert e.errors == ["timeout"]


class TestContradictions:
    def contradictory(self, a, b):
        return engine()._are_contradictory(Finding(a, "fact", 0.8, ["a"], []), Finding(b, "fact", 0.8, ["b"], []))

    def test_unrelated_findings_are_not_contradictory_just_because_of_substrings(self):
        # "is" matched inside "this", "more" inside "moreover"
        assert not self.contradictory("This paper studies retrieval systems for search engines.",
                                      "Moreover, fine tuning changes language model weights.")

    def test_a_real_contradiction_on_the_same_topic_is_found(self):
        assert self.contradictory("Retrieval augmented generation does reduce hallucination in language models.",
                                  "Retrieval augmented generation does not reduce hallucination in language models.")

    def test_a_word_inside_another_word_is_not_a_negation_pair(self):
        # same topic, but "is" only occurs inside "this" in the first, "is not" in the second
        assert not self.contradictory("This approach improves retrieval accuracy for language models.",
                                      "Retrieval accuracy for language models is not improved by this approach.")

    def test_different_topics_are_not_contradictory_even_with_a_negation(self):
        assert not self.contradictory("Retrieval does help.", "Cooking does not help.")

    def test_same_topic_without_a_negation_is_not(self):
        assert not self.contradictory("Retrieval augmented generation reduces hallucination in language models.",
                                      "Retrieval augmented generation improves hallucination metrics in language models.")


class TestSummaryPrompt:
    def test_the_summary_cites_source_numbers_and_stays_with_the_findings(self):
        prompts = []

        class Spy:
            def generate(self, messages, **k):
                prompts.append(messages)
                return {"content": "ok"}

        findings = [Finding("Claim one.", "fact", 0.9, ["b", "c"], []), Finding("Claim two.", "fact", 0.6, ["a"], [])]
        SynthesisEngine(llm_client=Spy(), min_sources=2)._generate_summary("q", findings, SOURCES)
        system, user = prompts[0][0]["content"], prompts[0][1]["content"]
        assert "ONLY the findings" in system and "what is missing" in system
        assert "1. Paper A" in user and "3. Page C" in user
        assert "Claim one. (confidence 0.90, sources: 2, 3)" in user and "Claim two. (confidence 0.60, sources: 1)" in user
        assert "never as a number of a finding" in user
