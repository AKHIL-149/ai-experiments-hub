"""Questions on the graph without a language model: find the entities a question names, follow chains of
relations ("who founded the company that acquired X"), find how two entities are connected, collect the facts around
an entity. The language model only plans and phrases; this module does the traversal, so every step is checkable.
"""
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field

import networkx as nx
import numpy as np
from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.graph import Entity, Fact, FactSource
from src.models.resolution import EntityAlias
from src.services.embedding import Embedder, cosine_top, fact_text, normalize
from src.services.conflicts import overruled_ids
from src.services.resolution import canonical_tokens
from src.services.temporal import Window, classify
from src.services.text_utils import entity_key, words

QUESTION_WORDS = {
    "who", "whom", "whose", "what", "which", "where", "when", "why", "how", "did", "does", "do", "is", "are", "was", "were",
    "the", "a", "an", "of", "in", "on", "at", "to", "for", "by", "with", "from", "and", "or", "that", "this", "these", "those",
    "has", "have", "had", "be", "been", "it", "its", "his", "her", "their", "they", "he", "she", "many", "much", "name", "tell",
    "me", "about", "list", "any", "all", "also", "other", "than", "then", "there", "year", "city", "country", "company", "person",
    "person", "people", "organization", "university", "place", "product",
}
FUZZY_LINK_RATIO = 92
MAX_SEEDS = 5


@dataclass
class FactView:
    id: str
    s_id: str
    s_name: str
    predicate: str
    o_id: str | None
    o_name: str          # the object entity's name, or the plain value
    valid_from: str
    valid_to: str
    docs: frozenset = frozenset()
    time: str = ""      # what its dates say about the question's period (temporal.STATUSES); "" when no period was asked

    @property
    def is_value(self) -> bool:
        return self.o_id is None

    def text(self) -> str:
        when = f" ({self.valid_from or ''}..{self.valid_to or ''})" if (self.valid_from or self.valid_to) else ""
        return f"{self.s_name} {self.predicate} {self.o_name}{when}"


@dataclass
class Seed:
    entity_id: str
    name: str
    how: str            # exact | alias | part_of_name | spelling
    matched: str        # the words of the question that matched
    confidence: float
    alternatives: list = field(default_factory=list)  # other entities the same words could mean


class GraphIndex:
    """The whole graph in memory for one question: entities, facts, who points at whom, and a name lookup"""

    def __init__(self, db: Session, document_id: str | None = None, *, owner_id: int | None = None, window: Window | None = None):
        """With a `window` (the period a question asks about) facts dated outside it are left out of every walk, path and
        search, but their entities can still be named in a question; the others carry what their dates say (`time`)"""
        self.owner_id = owner_id
        self.window = window
        self.excluded: list[str] = []          # texts of the facts left out because of their dates
        self.excluded_facts: list[FactView] = []
        linkable: set[str] = set()
        self.entities: dict[str, Entity] = {e.id: e for e in db.execute(select(Entity).where(Entity.owner_id == owner_id)).scalars()}
        doc_of = defaultdict(set)
        for fid, did in db.execute(select(FactSource.fact_id, FactSource.document_id).join(Fact, Fact.id == FactSource.fact_id)
                                   .where(Fact.owner_id == owner_id)).all():
            doc_of[fid].add(did)
        self.facts: dict[str, FactView] = {}
        self.out: dict[str, list[FactView]] = defaultdict(list)
        self.inn: dict[str, list[FactView]] = defaultdict(list)
        left_out = overruled_ids(db, owner_id)          # facts a person gave up on when settling a conflict
        for f in db.execute(select(Fact).where(Fact.owner_id == owner_id)).scalars():
            if f.id in left_out:
                continue
            docs = frozenset(doc_of.get(f.id, ()))
            if document_id and document_id not in docs:
                continue
            s = self.entities.get(f.subject_id)
            if s is None:
                continue
            o = self.entities.get(f.object_id) if f.object_id else None
            fv = FactView(f.id, f.subject_id, s.name, f.predicate, f.object_id, o.name if o else f.object_value,
                          f.valid_from, f.valid_to, docs)
            if window is not None:
                fv.time = classify(f.valid_from, f.valid_to, window)
                if fv.time == "outside":
                    self.excluded.append(fv.text())
                    self.excluded_facts.append(fv)
                    linkable.add(f.subject_id)
                    if f.object_id:
                        linkable.add(f.object_id)
                    continue
            self.facts[f.id] = fv
            self.out[f.subject_id].append(fv)
            if f.object_id:
                self.inn[f.object_id].append(fv)
        self.used = {i for i in self.entities if self.out.get(i) or self.inn.get(i)} | (linkable & set(self.entities))
        self.surface: dict[str, set[str]] = defaultdict(set)   # normalised name -> entity ids
        self.token_index: dict[str, set[str]] = defaultdict(set)
        for e in self.entities.values():
            if e.id in self.used:
                self.surface[e.key].add(e.id)
                for t in set(canonical_tokens(e.name, e.type)):
                    self.token_index[t].add(e.id)
        for a in db.execute(select(EntityAlias).where(EntityAlias.owner_id == owner_id)).scalars():
            if a.entity_id in self.used:
                self.surface[a.key].add(a.entity_id)
        self._graph: nx.Graph | None = None

    def name(self, entity_id: str) -> str:
        return self.entities[entity_id].name

    def undirected(self) -> nx.Graph:
        if self._graph is None:
            g = nx.Graph()
            g.add_nodes_from(self.used)
            for f in self.facts.values():
                if f.o_id:
                    g.add_edge(f.s_id, f.o_id)
            self._graph = g
        return self._graph

    # ---- finding the entities a question names

    def link(self, text: str) -> list[Seed]:
        """Entities named in `text`: longest exact matches first, then a part of a name ('Turing'), then near spellings"""
        tokens = words(text)
        taken = [False] * len(tokens)
        seeds: dict[str, Seed] = {}

        def add(eid, how, matched, conf, alts=()):
            if eid not in seeds or seeds[eid].confidence < conf:
                seeds[eid] = Seed(eid, self.name(eid), how, matched, conf, [self.name(a) for a in alts])

        for n in range(min(6, len(tokens)), 0, -1):
            for i in range(len(tokens) - n + 1):
                if any(taken[i:i + n]):
                    continue
                gram = " ".join(tokens[i:i + n])
                if n == 1 and (tokens[i] in QUESTION_WORDS or len(tokens[i]) < 3):
                    continue
                ids = self.surface.get(gram)
                if ids:
                    for eid in ids:
                        add(eid, "exact" if self.entities[eid].key == gram else "alias", gram, 1.0, [x for x in ids if x != eid])
                    for j in range(i, i + n):
                        taken[j] = True
        for i, tok in enumerate(tokens):
            if taken[i] or tok in QUESTION_WORDS or len(tok) < 4:
                continue
            ids = self.token_index.get(tok)
            if ids and len(ids) <= 3:
                for eid in ids:
                    add(eid, "part_of_name", tok, 0.6 if len(ids) == 1 else 0.4, [x for x in ids if x != eid])
                taken[i] = True
        keys = list(self.surface)
        for n in (3, 2, 1):
            for i in range(len(tokens) - n + 1):
                if any(taken[i:i + n]):
                    continue
                gram = " ".join(tokens[i:i + n])
                if len(gram) < 4 or all(t in QUESTION_WORDS for t in tokens[i:i + n]):
                    continue  # 'who' or 'up' would match an entity of that name exactly, which is not what the question means
                hit = process.extractOne(gram, keys, scorer=fuzz.ratio, score_cutoff=FUZZY_LINK_RATIO)
                if hit:
                    for eid in self.surface[hit[0]]:
                        add(eid, "spelling", gram, 0.5)
                    for j in range(i, i + n):
                        taken[j] = True
        return sorted(seeds.values(), key=lambda s: -s.confidence)[:MAX_SEEDS]

    # ---- looking around an entity

    def around(self, entity_ids, hops: int) -> dict[str, int]:
        """Entities within `hops` links (either direction) of the given ones, with their distance"""
        dist = {e: 0 for e in entity_ids if e in self.used}
        queue = deque(dist)
        g = self.undirected()
        while queue:
            e = queue.popleft()
            if dist[e] >= hops:
                continue
            for n in g.neighbors(e):
                if n not in dist:
                    dist[n] = dist[e] + 1
                    queue.append(n)
        return dist

    def facts_within(self, dist: dict[str, int]) -> list[tuple[FactView, int]]:
        """Facts whose subject is within reach (value facts too), with how far the nearest end is"""
        seen, out = set(), []
        for e, d in dist.items():
            for f in self.out.get(e, []) + self.inn.get(e, []):
                if f.id in seen:
                    continue
                if f.o_id is not None and (f.s_id not in dist or f.o_id not in dist):
                    continue
                seen.add(f.id)
                out.append((f, min(dist.get(f.s_id, 99), dist.get(f.o_id, 99) if f.o_id else 99)))
        return out

    # ---- how are two entities connected

    def paths(self, a: str, b: str, max_hops: int = 4, limit: int = 3) -> list[list[FactView]]:
        """Shortest chains of facts between two entities, each a list of facts in walking order"""
        g = self.undirected()
        if a not in g or b not in g or a == b:
            return []
        try:
            node_paths = []
            for p in nx.shortest_simple_paths(g, a, b):
                if len(p) - 1 > max_hops:
                    break
                node_paths.append(p)
                if len(node_paths) >= limit:
                    break
        except nx.NetworkXNoPath:
            return []
        out = []
        for p in node_paths:
            chain = []
            for x, y in zip(p, p[1:]):
                f = next((f for f in self.out.get(x, []) if f.o_id == y), None) or next((f for f in self.out.get(y, []) if f.o_id == x), None)
                chain.append(f)
            out.append(chain)
        return out


# ------------------------------------------------------------------ following a chain of relations

STOP_FOR_STEMS = {"of", "at", "by", "in", "to", "the", "a", "an", "for", "with", "from", "on", "as", "is", "was"}


def stem(word: str) -> str:
    w = word.lower()
    for suffix in ("ations", "ation", "ings", "ing", "ers", "er", "ed", "es", "s", "d"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[:-len(suffix)]
    return w


def stems(text: str) -> set[str]:
    return {stem(w) for w in words(text) if w not in STOP_FOR_STEMS}


def lexical_match(hint: str, predicate: str) -> float:
    a, b = stems(hint), stems(predicate)
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a), len(b))


class PredicateMatcher:
    """How alike are a relation word from the question ('bought') and a stored predicate ('acquired')?
    Word stems catch 'founded'/'founder'; embeddings catch 'bought'/'acquired'."""

    def __init__(self, embedder: Embedder | None, predicates: list[str]):
        self.embedder = embedder
        self.predicates = sorted(set(predicates))
        self._vectors: np.ndarray | None = None
        self._hint_cache: dict[str, np.ndarray] = {}

    def _predicate_vectors(self) -> np.ndarray:
        if self._vectors is None:
            self._vectors = normalize(np.asarray(self.embedder.embed(self.predicates, "query"), dtype=np.float32)) if self.predicates else np.zeros((0, 1))
        return self._vectors

    def scores(self, hint: str) -> dict[str, float]:
        out = {p: lexical_match(hint, p) for p in self.predicates}
        if self.embedder is not None and self.predicates:
            if hint not in self._hint_cache:
                self._hint_cache[hint] = normalize(np.asarray(self.embedder.embed([hint], "query")[0], dtype=np.float32).reshape(1, -1))[0]
            sims = self._predicate_vectors() @ self._hint_cache[hint]
            for p, s in zip(self.predicates, sims):
                out[p] = max(out[p], float(s))
        return out


@dataclass
class StepResult:
    step: int
    relation: str
    direction: str       # the direction that was used ('out': subject -> object, 'in': object -> subject)
    flipped: bool        # the asked-for direction found nothing, so the other one was used
    links: list = field(default_factory=list)   # (from entity id, FactView, to entity id | None, value | None)


@dataclass
class WalkResult:
    ok: bool
    reason: str = ""
    final_entities: list = field(default_factory=list)   # entity ids at the end of the chain
    final_values: list = field(default_factory=list)     # plain values at the end ('340 people'), if the last fact has one
    facts: list = field(default_factory=list)            # FactViews on chains that reach the end, in order of use
    steps: list = field(default_factory=list)


def walk(index: GraphIndex, start_ids: list[str], steps: list[dict], matcher: PredicateMatcher, threshold: float) -> WalkResult:
    """Follow the chain step by step from the start entities. A step is {relation, direction}. Only chains that
    get all the way to the end are kept."""
    if not start_ids:
        return WalkResult(False, "no starting entity")
    if not steps:
        return WalkResult(False, "no steps")
    layers: list[dict[str, list]] = []   # per step: next entity (or value) -> list of (previous entity, fact)
    current = list(dict.fromkeys(start_ids))
    results: list[StepResult] = []
    for n, step in enumerate(steps, 1):
        hint, want = step["relation"], step.get("direction", "any")
        scores = matcher.scores(hint)
        # the asked-for direction first; if it finds nothing the other one is tried (a small model often mixes them up)
        attempts = [[want], ["in" if want == "out" else "out"]] if want in ("out", "in") else [["out", "in"]]
        found, flipped = [], False
        for k, dirs in enumerate(attempts):
            for e in current:
                for d in dirs:
                    for f in (index.out.get(e, []) if d == "out" else index.inn.get(e, [])):
                        if scores.get(f.predicate, 0.0) >= threshold:
                            found.append((e, f, d))
            if found:
                flipped = k == 1
                break
        if not found:
            return WalkResult(False, f"step {n}: nothing matches '{hint}'", steps=results)
        layer: dict[str, list] = defaultdict(list)
        sr = StepResult(n, hint, found[0][2] if len({d for *_, d in found}) == 1 else "any", flipped)
        for e, f, d in found:
            key = (f.o_id or f"value:{f.o_name}") if d == "out" else f.s_id
            layer[key].append((e, f))
            sr.links.append((e, f, (f.o_id if d == "out" else f.s_id), (f.o_name if d == "out" and not f.o_id else None)))
        layers.append(layer)
        results.append(sr)
        nxt = [k for k in layer if not k.startswith("value:")]
        if n < len(steps) and not nxt:
            return WalkResult(False, f"step {n}: '{hint}' leads only to plain values", steps=results)
        current = nxt
    last = layers[-1]
    final_entities = [k for k in last if not k.startswith("value:")]
    final_values = [k[len("value:"):] for k in last if k.startswith("value:")]
    # keep only the facts on chains that reach the end
    keep_facts: dict[str, FactView] = {}
    wanted = set(last)
    for layer in reversed(layers):
        needed_prev = set()
        for key in wanted:
            for prev, f in layer.get(key, []):
                keep_facts.setdefault(f.id, f)
                needed_prev.add(prev)
        wanted = needed_prev
    order = {f.id: i for i, f in enumerate(f for sr in results for (_, f, _, _) in sr.links)}
    return WalkResult(True, final_entities=final_entities, final_values=final_values,
                      facts=sorted(keep_facts.values(), key=lambda f: order.get(f.id, 0)), steps=results)


def rank_facts(index: GraphIndex, db: Session, embedder: Embedder | None, question: str, candidates: list[tuple[FactView, int]], limit: int) -> list[FactView]:
    """The `limit` facts that best fit the question: closer to its entities and more alike its wording"""
    if not candidates:
        return []
    if embedder is None:
        return [f for f, _ in sorted(candidates, key=lambda t: (t[1], t[0].text()))[:limit]]
    from src.services.embedding import ensure_fact_embeddings
    facts = [db.get(Fact, f.id) for f, _ in candidates]
    vectors = ensure_fact_embeddings(db, embedder, [f for f in facts if f is not None])
    qv = np.asarray(embedder.embed([question], "query")[0], dtype=np.float32)
    qv = qv / (np.linalg.norm(qv) or 1)
    scored = []
    for (f, dist) in candidates:
        v = vectors.get(f.id)
        sim = float(normalize(v.reshape(1, -1))[0] @ qv) if v is not None else 0.0
        scored.append((sim - 0.04 * dist, f))
    scored.sort(key=lambda t: -t[0])
    return [f for _, f in scored[:limit]]


def global_fact_search(db: Session, embedder: Embedder, question: str, index: GraphIndex, limit: int) -> list[FactView]:
    """When a question names no known entity: the facts whose wording is closest to the question, anywhere in the graph"""
    from src.services.embedding import ensure_fact_embeddings
    rows = [db.get(Fact, fid) for fid in index.facts]
    rows = [r for r in rows if r is not None]
    vectors = ensure_fact_embeddings(db, embedder, rows)
    ids = [r.id for r in rows if r.id in vectors]
    if not ids:
        return []
    matrix = np.vstack([vectors[i] for i in ids])
    qv = np.asarray(embedder.embed([question], "query")[0], dtype=np.float32)
    return [index.facts[ids[i]] for i, _ in cosine_top(qv, matrix, limit)]
