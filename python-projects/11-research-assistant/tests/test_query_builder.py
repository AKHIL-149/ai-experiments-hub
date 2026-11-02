"""
Search queries built from a research question.

Found by running the app: the question as typed matched the everyday word "main" on the web (a
dictionary entry and an arcade chain were the top results) and ArXiv answered a long sentence with papers
about image and code generation. Keywords joined with AND found the papers about the question.
"""

from src.utils.query_builder import build_arxiv_queries, build_web_query, extract_keywords

QUESTION = "What are the main differences between retrieval-augmented generation and fine-tuning for adding knowledge to LLMs?"


def test_the_subject_words_are_kept_in_order():
    assert extract_keywords(QUESTION) == ["retrieval-augmented", "generation", "fine-tuning", "knowledge", "LLMs"]


def test_question_words_and_fillers_are_dropped():
    assert extract_keywords("How does the immune system work?") == ["immune", "system", "work"]


def test_repeats_are_dropped_ignoring_case():
    assert extract_keywords("Python python PYTHON typing") == ["Python", "typing"]


def test_punctuation_and_edges_are_cleaned():
    assert extract_keywords("(quantum) computing, error-correction.") == ["quantum", "computing", "error-correction"]


def test_technical_tokens_survive():
    assert extract_keywords("C++ vs C# performance") == ["C++", "C#", "performance"]


def test_a_question_with_only_filler_words_gives_no_keywords_and_falls_back_to_the_question():
    assert extract_keywords("what is the") == []
    assert build_web_query("what is the") == "what is the"
    assert build_arxiv_queries("what is the") == ["what is the"]


def test_empty_input_does_not_crash():
    assert extract_keywords("") == [] and extract_keywords(None) == []
    assert build_web_query("") == "" and build_arxiv_queries("") == []


def test_web_query_is_the_keywords():
    assert build_web_query(QUESTION) == "retrieval-augmented generation fine-tuning knowledge LLMs"


def test_arxiv_queries_go_from_every_keyword_to_fewer_and_end_with_the_sentence():
    queries = build_arxiv_queries(QUESTION)
    assert queries[0] == 'all:"retrieval-augmented" AND all:generation AND all:"fine-tuning" AND all:knowledge AND all:LLMs'
    assert len(queries[0].split(" AND ")) > len(queries[1].split(" AND ")) >= 3
    assert queries[-1] == QUESTION


def test_hyphenated_terms_are_quoted_phrases():
    assert 'all:"fine-tuning"' in build_arxiv_queries(QUESTION)[0]


def test_at_most_six_keywords_are_used():
    queries = build_arxiv_queries("alpha beta gamma delta epsilon zeta eta theta iota")
    assert queries[0].count("all:") == 6


def test_a_single_keyword_still_gives_a_query():
    assert build_arxiv_queries("photosynthesis") == ["all:photosynthesis", "photosynthesis"]
