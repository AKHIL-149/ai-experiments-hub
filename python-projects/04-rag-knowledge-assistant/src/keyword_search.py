"""Small BM25 keyword scorer used alongside vector search.

Embeddings blur exact terms ("retained", "hours", part numbers); keyword
matching catches them. Combining both ranks results better than either alone.
"""

import math
import re
from typing import List, Sequence

_STOPWORDS = frozenset(
    "the a an of to in is are was were what how who when where which does do did for and or on at by "
    "with be can i it this that these those as from about into than then there their its has have had".split()
)


def tokenize(text: str) -> List[str]:
    """Lowercase alphanumeric tokens without common stopwords."""
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOPWORDS]


def bm25_scores(query: str, documents: Sequence[str], k1: float = 1.5, b: float = 0.75) -> List[float]:
    """BM25 score of every document for the query (0.0 when no query term appears)."""
    tokenized = [tokenize(d) for d in documents]
    count = len(tokenized)
    if count == 0:
        return []

    average = sum(len(t) for t in tokenized) / count or 1.0
    document_frequency = {}
    for tokens in tokenized:
        for term in set(tokens):
            document_frequency[term] = document_frequency.get(term, 0) + 1

    query_terms = set(tokenize(query))
    scores = []
    for tokens in tokenized:
        score = 0.0
        for term in query_terms:
            frequency = tokens.count(term)
            if frequency:
                df = document_frequency[term]
                idf = math.log(1 + (count - df + 0.5) / (df + 0.5))
                score += idf * frequency * (k1 + 1) / (
                    frequency + k1 * (1 - b + b * len(tokens) / average)
                )
        scores.append(score)
    return scores
