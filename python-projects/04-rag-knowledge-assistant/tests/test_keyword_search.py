from keyword_search import bm25_scores, tokenize


def test_tokenize_drops_stopwords_and_case():
    assert tokenize("What ARE the Support-Hours?") == ["support", "hours"]


def test_matching_document_scores_highest():
    docs = ["backups run nightly and are retained for 35 days", "vacation policy for employees", "api rate limit"]
    s = bm25_scores("How long are backups retained?", docs)
    assert s.index(max(s)) == 0 and s[1] == 0 and s[2] == 0


def test_rarer_terms_weigh_more():
    docs = ["common common rare", "common common common", "common other"]
    s = bm25_scores("common rare", docs)
    assert s[0] > s[1] > 0


def test_no_overlap_scores_zero_and_empty_corpus():
    assert bm25_scores("zebra", ["apple banana"]) == [0.0]
    assert bm25_scores("zebra", []) == []
    assert bm25_scores("the of and", ["the of and"]) == [0.0]
