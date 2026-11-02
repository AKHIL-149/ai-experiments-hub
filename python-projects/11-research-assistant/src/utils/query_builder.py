"""
Turns a research question into search queries.

The question is typed as a sentence ("What are the main differences between X and Y ...?"). Sent as it
is, a web search matched the everyday word "main" (a dictionary entry and an arcade chain were the top
two results) and ArXiv, which treats a long query loosely, returned papers about image and code
generation for a question about LLM knowledge. Keywords joined with AND found the right papers.
"""

import re
from typing import List

# Words that carry the question's grammar, not its subject
STOPWORDS = frozenset("""
a about above after again against all also am an and any are as at be because been before being below
between both but by can could did do does doing down during each few for from further had has have having
he her here hers him his how i if in into is it its just me more most my no nor not of off on once only or
other our out over own same she should so some such than that the their them then there these they this
those through to too under until up very was we were what when where which while who whom why will with
would you your
main difference differences compare compared comparison versus vs explain describe tell give list
using use used make makes best good better add adding added
""".split())

# Longest keyword query worth sending: past this, each added term only narrows the result to nothing
MAX_KEYWORDS = 6

_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-\+\.#']*[A-Za-z0-9+#]|[A-Za-z0-9]")


def extract_keywords(question: str) -> List[str]:
    """The subject words of a question, in order, without repeats"""
    keywords: List[str] = []
    seen = set()
    for word in _WORD.findall(question or ""):
        word = word.strip("-.'")
        lowered = word.lower()
        if len(lowered) < 2 or lowered in STOPWORDS or lowered in seen:
            continue
        seen.add(lowered)
        keywords.append(word)
    return keywords


def build_web_query(question: str) -> str:
    """Keywords for a web search; the question itself when nothing is left after filtering"""
    keywords = extract_keywords(question)
    return " ".join(keywords[:MAX_KEYWORDS + 2]) if keywords else (question or "").strip()


def build_arxiv_queries(question: str) -> List[str]:
    """
    ArXiv queries from most to least specific: every keyword must appear (`all:a AND all:b`), then
    fewer of them, then the question as typed. The caller stops at the first that returns enough.
    """
    keywords = extract_keywords(question)[:MAX_KEYWORDS]
    queries: List[str] = []
    for count in range(len(keywords), 1, -1):
        # "fine-tuning" and "retrieval-augmented" are phrases, not subtraction
        terms = [f'all:"{k}"' if re.search(r"[\-\s]", k) else f"all:{k}" for k in keywords[:count]]
        query = " AND ".join(terms)
        if query not in queries:
            queries.append(query)
        if count <= 3:
            break
    if len(keywords) == 1:
        queries.append(f"all:{keywords[0]}")
    if (question or "").strip():
        queries.append(question.strip())
    return queries
