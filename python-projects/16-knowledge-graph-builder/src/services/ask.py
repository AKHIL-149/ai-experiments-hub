"""Answer a question from the graph (and optionally from passages), with citations.

Modes
  vector    passage search only: the closest passages to the question (what a plain RAG assistant does). The baseline.
  subgraph  the facts around the entities the question names, ranked by how well they fit the question.
  graph     a language model turns the question into a chain of relations ("acquired" <- in, "founded" <- in); code walks
            that chain through the graph and keeps the facts on the way; falls back to `subgraph` if the chain breaks.
  hybrid    the `graph` facts plus the closest passages.
  auto      = graph (it was the most reliable in the evaluation, and the best at saying "not found").

Time: a question that names a time ("in 2021", "between 2015 and 2018", "before 2020", "currently") is read by patterns
(temporal.py), not by the model. The words are taken out before planning, facts whose dates put them outside that
time are left out of the walk, and every fact the model sees says what its dates say about the time. Passage search
(`vector`) does not use dates.

Whatever the mode, the model sees numbered facts/passages (F1, P1, ...), must answer only from them, and says which it used.
Citations the model invents (a label that was not offered) are dropped.
"""
import re
import time
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import Settings
from src.models.graph import Chunk, Document, Fact, FactSource
from src.services import conflicts as conflict_service
from src.services import graph_query as gq
from src.services import temporal
from src.services.embedding import Embedder, EmbeddingError, top_chunks
from src.services.llm import LLMBadOutput, LLMClient

MODES = ("auto", "vector", "subgraph", "graph", "hybrid")
MAX_STEPS = 4
QUOTE_CHARS = 220
PASSAGE_CHARS = 700

TIME_RULES = """
The question is about a time: {label}. Each fact is tagged with what its dates say about that time:
- "holds throughout": the stated dates cover it. These answer the question.
- "overlaps": the dates overlap it only partly, or only to the year. Say so when it matters.
- "began earlier, no end date stated": it started before that time and the text never says it ended. It may still have held: give it only as "possibly" and say that no end date is stated, never as certain.
- "no date stated": nothing is known about when. Use it only when no dated fact answers, and say it is undated.
Facts dated outside that time were removed. If no fact fits, set found to false."""

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "start": {"type": "array", "items": {"type": "string"}},
        "steps": {"type": "array", "items": {"type": "object", "properties": {
            "relation": {"type": "string"}, "direction": {"type": "string", "enum": ["out", "in"]}},
            "required": ["relation", "direction"]}},
    },
    "required": ["start", "steps"],
}

PLAN_SYSTEM = """You turn a question into a chain of relations to follow in a knowledge graph of facts "subject relation object".

start: the names of the things the question mentions (as written in the question).
steps: the relations to follow, in order, starting from the start entity. Each step has a relation (a short verb phrase like "founded", "acquired", "works at", "located in", "born in") and a direction:
  out = the current entity is the SUBJECT: current --relation--> next ("Acme acquired ?": next is what Acme acquired)
  in  = the current entity is the OBJECT: next --relation--> current ("? acquired Acme": next is who acquired Acme)
Use as few steps as the question needs. A question about one entity ("What do we know about X?") or the link between two entities has no steps.

Examples
Q: Who founded the company that acquired Tessel AI?
{"start": ["Tessel AI"], "steps": [{"relation": "acquired", "direction": "in"}, {"relation": "founded", "direction": "in"}]}
Q: Which companies did Acme acquire?
{"start": ["Acme"], "steps": [{"relation": "acquired", "direction": "out"}]}
Q: In which city is the university that the founder of Foo Labs attended?
{"start": ["Foo Labs"], "steps": [{"relation": "founded", "direction": "in"}, {"relation": "attended", "direction": "out"}, {"relation": "located in", "direction": "out"}]}
Q: How is Lee connected to Quill?
{"start": ["Lee", "Quill"], "steps": []}
Q: When did Acme acquire Beta?
{"start": ["Acme", "Beta"], "steps": []}"""

ANSWER_SYSTEM = """You answer a question using ONLY the numbered facts and passages you are given.
- If they contain the answer, set found to true and answer briefly and exactly (names, places, years). If the question asks for several things, list them all.
- If they do not contain the answer, set found to false and answer "not found". Never use outside knowledge and never guess.
- A fact about a different entity or a different relation does not answer the question: "invested in" is not "acquired"; the head of a parent company is not the head of its subsidiary; "A acquired B" does not say "B acquired A".
- cited: the labels (like F2 or P1) of the facts and passages you used."""

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"found": {"type": "boolean"}, "answer": {"type": "string"}, "cited": {"type": "array", "items": {"type": "string"}}},
    "required": ["found", "answer", "cited"],
}


@dataclass
class Plan:
    start: list[str]
    steps: list[dict]


CONNECTION = re.compile(r"\b(connect(ed|ion|ions)|relat(ed|ion|ionship)|link(ed|s)?|ties|tied)\b|\bhow are\b.*\band\b", re.I)


def is_connection_question(question: str) -> bool:
    """'How is A connected to B?' / 'What is the connection between A and B?': answered by the path between them,
    whatever chain of relations a model might make up for it"""
    return bool(CONNECTION.search(question))


@dataclass
class Evidence:
    note: str = ""                                    # something the model should know about how the evidence was found
    facts: list = field(default_factory=list)         # FactViews, in the order they are shown to the model
    passages: list = field(default_factory=list)      # (Chunk, score)
    reasoning: dict = field(default_factory=dict)
    window: temporal.Window | None = None             # the time the question asks about, when it names one
    conflicts: list = field(default_factory=list)     # open conflicts between facts shown to the model


def plan_question(llm: LLMClient, question: str) -> Plan | None:
    """The model's chain of relations for the question; None when it did not give a usable one (bad output is retried once)"""
    for _ in range(2):
        try:
            data = llm.generate_json(PLAN_SYSTEM, f"Q: {question}", PLAN_SCHEMA, max_tokens=384)
        except LLMBadOutput:
            continue
        start = [str(x).strip() for x in data.get("start", []) if isinstance(x, str) and x.strip()][:3]
        steps = []
        for st in data.get("steps", []):
            if isinstance(st, dict) and isinstance(st.get("relation"), str) and st["relation"].strip() and st.get("direction") in ("out", "in"):
                steps.append({"relation": st["relation"].strip(), "direction": st["direction"]})
        return Plan(start, steps[:MAX_STEPS])
    return None


def _quotes(db: Session, fact_ids: list[str]) -> dict[str, dict]:
    """One source per fact (a double-checked one if there is one): its quote, passage and document"""
    if not fact_ids:
        return {}
    rows = db.execute(select(FactSource, Document.title, Chunk.text).join(Document, Document.id == FactSource.document_id)
                      .join(Chunk, Chunk.id == FactSource.chunk_id).where(FactSource.fact_id.in_(fact_ids))).all()
    best: dict[str, dict] = {}
    for src, title, passage in rows:
        cur = best.get(src.fact_id)
        if cur is None or (src.verified and not cur["verified"]):
            best[src.fact_id] = {"quote": src.evidence, "document_id": src.document_id, "document_title": title,
                                 "chunk_id": src.chunk_id, "passage": passage, "verified": src.verified}
    return best


def _step_report(index: gq.GraphIndex, walk: gq.WalkResult) -> list[dict]:
    out = []
    for sr in walk.steps:
        out.append({"step": sr.step, "relation": sr.relation, "direction": sr.direction, "flipped": sr.flipped,
                    "links": [{"from": index.name(e), "fact": f.text(), "to": index.name(t) if t else v} for e, f, t, v in sr.links[:12]]})
    return out


def gather_graph(db: Session, index: gq.GraphIndex, question: str, llm: LLMClient | None, embedder: Embedder | None,
                 settings: Settings, use_plan: bool) -> Evidence:
    ev = Evidence()
    r: dict = {"seeds": [], "plan": None, "steps": [], "paths": [], "fallback": None}
    ev.reasoning = r
    seeds = index.link(question)
    if use_plan and is_connection_question(question) and len(seeds) >= 2:
        r["seeds"] = [{"entity_id": x.entity_id, "name": x.name, "how": x.how, "matched": x.matched, "confidence": x.confidence,
                       "also_could_be": x.alternatives} for x in seeds]
        r["connection_question"] = True
        a, b = seeds[0].entity_id, seeds[1].entity_id
        for chain in index.paths(a, b, max_hops=4):
            r["paths"].append([f.text() for f in chain if f])
            for f in chain:
                if f and f not in ev.facts:
                    ev.facts.append(f)
        for f in index.out.get(a, []) + index.out.get(b, []):
            if f.o_id in (a, b) and f not in ev.facts:
                ev.facts.append(f)
        if ev.facts:
            return ev
    plan = None
    if use_plan and llm is not None:
        plan = plan_question(llm, question)
        if plan is None:
            r["fallback"] = "the model did not give a usable plan"
    start_ids: list[str] = []
    if plan and plan.start:
        for name in plan.start:
            linked = index.link(name)
            if linked:
                start_ids.append(linked[0].entity_id)
                if linked[0].entity_id not in {s.entity_id for s in seeds}:
                    seeds.append(linked[0])
        r["plan"] = {"start": plan.start, "steps": plan.steps}
    if not start_ids:
        start_ids = [s.entity_id for s in seeds[:3]]
    r["seeds"] = [{"entity_id": s.entity_id, "name": s.name, "how": s.how, "matched": s.matched, "confidence": s.confidence,
                   "also_could_be": s.alternatives} for s in seeds]

    if plan and plan.steps and start_ids:
        try:
            matcher = gq.PredicateMatcher(embedder, [f.predicate for f in index.facts.values()])
            w = gq.walk(index, start_ids, plan.steps, matcher, settings.predicate_threshold)
        except EmbeddingError as exc:
            r["fallback"] = f"embeddings unavailable ({exc}); matched relations by word stems only"
            matcher = gq.PredicateMatcher(None, [f.predicate for f in index.facts.values()])
            w = gq.walk(index, start_ids, plan.steps, matcher, settings.predicate_threshold)
        r["steps"] = _step_report(index, w)
        if w.ok:
            ev.facts = w.facts
            r["answer_entities"] = [index.name(e) for e in w.final_entities] + list(w.final_values)
            return ev
        r["fallback"] = w.reason
        ev.note = (f"The relations the question asks for could not be followed in the graph ({w.reason}). The facts below are only "
                   "what is stored around the entities of the question: answer only if they state the answer directly.")

    if plan and not plan.steps and len(start_ids) >= 2:
        chains = index.paths(start_ids[0], start_ids[1], max_hops=4)
        for chain in chains:
            r["paths"].append([f.text() for f in chain if f])
            for f in chain:
                if f and f not in ev.facts:
                    ev.facts.append(f)
        direct = [f for f in index.out.get(start_ids[0], []) + index.out.get(start_ids[1], []) if f.o_id in start_ids]
        for f in direct:  # the path shows one fact per hop; any other facts between the two entities belong too
            if f not in ev.facts:
                ev.facts.append(f)
        if ev.facts:
            return ev

    # no chain to follow: the facts around the entities of the question
    if start_ids:
        dist = index.around(start_ids, settings.ask_max_hops)
        ev.facts = gq.rank_facts(index, db, embedder, question, index.facts_within(dist), settings.ask_max_facts)
    elif embedder is not None:
        try:
            ev.facts = gq.global_fact_search(db, embedder, question, index, settings.ask_max_facts)
            r["fallback"] = r["fallback"] or "no entity of the question is in the graph; used the facts closest in wording"
        except EmbeddingError as exc:
            r["fallback"] = f"no entity found and embeddings unavailable ({exc})"
    return ev


def _time_report(tq: temporal.TimeQuery, index: gq.GraphIndex) -> dict:
    counts: dict[str, int] = {}
    for f in index.facts.values():
        counts[f.time] = counts.get(f.time, 0) + 1
    return {"asked": tq.text, **tq.window.to_dict(), "question_used": tq.question, "facts_by_status": counts,
            "left_out": len(index.excluded), "left_out_examples": index.excluded[:5]}


def gather(db: Session, question: str, mode: str, llm: LLMClient, embedder: Embedder | None, settings: Settings,
           document_id: str | None, owner_id: int | None = None, today: date | None = None) -> Evidence:
    if mode == "vector":
        if embedder is None:
            raise EmbeddingError("Passage search needs an embedding model")
        chunks = top_chunks(db, embedder, question, settings.ask_top_chunks, document_id, owner_id=owner_id)
        return Evidence(passages=chunks, reasoning={"seeds": [], "plan": None, "steps": [], "paths": [], "fallback": None})
    tq = temporal.parse_time(question, today)
    index = gq.GraphIndex(db, document_id, owner_id=owner_id, window=tq.window if tq else None)
    if tq and any(re.search(r"\d{4}", x.matched) for x in index.link(question) if x.how in ("exact", "alias")):
        tq = None                                    # the year is part of an entity's name ("Expo 2020"), not a time
        index = gq.GraphIndex(db, document_id, owner_id=owner_id)
    ev = gather_graph(db, index, tq.question if tq else question, llm, embedder, settings, use_plan=mode in ("graph", "hybrid"))
    if tq:
        ev.window = tq.window
        ev.reasoning["time"] = _time_report(tq, index)
    if mode == "hybrid" and embedder is not None:
        try:
            ev.passages = top_chunks(db, embedder, question, settings.ask_top_chunks, document_id, owner_id=owner_id)
        except EmbeddingError as exc:
            ev.reasoning["passages_skipped"] = str(exc)
    return ev


def build_prompt(db: Session, question: str, ev: Evidence) -> tuple[str, dict[str, dict]]:
    """The numbered evidence for the model, and what each label stands for"""
    quotes = _quotes(db, [f.id for f in ev.facts])
    labels: dict[str, dict] = {}
    lines = []
    if ev.facts:
        lines.append("Facts:")
    for i, f in enumerate(ev.facts, 1):
        label = f"F{i}"
        q = quotes.get(f.id)
        labels[label] = {"kind": "fact", "fact_id": f.id, "text": f.text(), **({k: q[k] for k in ("quote", "document_id", "document_title", "verified")} if q else {}),
                         **({"time": f.time} if ev.window else {})}
        tag = f"   [{temporal.describe(f.time, ev.window)}]" if ev.window and f.time else ""
        lines.append(f"[{label}] {f.text()}{tag}" + (f'   (source: "{q["quote"][:QUOTE_CHARS]}")' if q else ""))
    if ev.passages:
        lines.append("\nPassages:")
    for i, (chunk, score) in enumerate(ev.passages, 1):
        label = f"P{i}"
        title = db.get(Document, chunk.document_id).title
        labels[label] = {"kind": "passage", "chunk_id": chunk.id, "document_id": chunk.document_id, "document_title": title,
                         "text": chunk.text[:PASSAGE_CHARS], "score": round(score, 3)}
        lines.append(f"[{label}] ({title}) {chunk.text[:PASSAGE_CHARS]}")
    notes = [ev.note] if ev.note else []
    by_fact = {meta["fact_id"]: label for label, meta in labels.items() if meta["kind"] == "fact"}
    for c in ev.conflicts:
        if c.fact_a_id in by_fact and c.fact_b_id in by_fact:
            notes.append(f"[{by_fact[c.fact_a_id]}] and [{by_fact[c.fact_b_id]}] contradict each other. Do not choose between them silently: "
                         "say that the documents disagree and give both, citing both.")
    if ev.reasoning.get("paths"):
        notes.append("The facts form a chain between the entities of the question. Describe the whole chain, naming every entity on it.")
    note = "".join(f"Note: {n}\n\n" for n in notes)
    return f"Question: {question}\n\n{note}" + "\n".join(lines), labels


def answer_from(llm: LLMClient, prompt: str, window: temporal.Window | None = None) -> dict:
    system = ANSWER_SYSTEM + TIME_RULES.format(label=window.label) if window else ANSWER_SYSTEM
    for attempt in (1, 2):
        try:
            data = llm.generate_json(system, prompt, ANSWER_SCHEMA, max_tokens=768)
            break
        except LLMBadOutput:
            if attempt == 2:
                return {"found": False, "answer": "", "cited": [], "error": "the model did not give a usable answer"}
    cited = data.get("cited") if isinstance(data.get("cited"), list) else []
    return {"found": bool(data.get("found")), "answer": str(data.get("answer") or "").strip(),
            "cited": [str(c).strip().upper().strip("[]") for c in cited]}


def _time_caveat(citations: list[dict], window: temporal.Window) -> str:
    """What the model may not say: when no fact it cited has dates that hold in or overlap the time, the answer rests on
    facts that are undated, or that began earlier with no end stated. Said by code, so it does not depend on the model's wording."""
    used = [c["time"] for c in citations if c.get("kind") == "fact" and c.get("time")]
    if not used or any(t in ("during", "overlaps") for t in used):
        return ""
    if all(t == "undated" for t in used):
        return "The fact behind this answer has no date, so the documents do not show when it held."
    return (f"The facts behind this answer began before {window.label} (or have no date) and none states an end, "
            "so it may still have held, but the documents do not confirm it.")


def _disputes_behind(db: Session, ev: Evidence, citations: list[dict]) -> list[dict]:
    """The open conflicts an answer rests on: those with a fact the answer cited. Conflicts among the other facts the model was
    shown (the closest in wording, say, for a question the documents do not answer) say nothing about this answer. Always both sides:
    the one that was not shown to the model is read from the graph."""
    cited = {c["fact_id"] for c in citations if c.get("kind") == "fact"}
    shown = {f.id: f.text() for f in ev.facts}
    out = []
    for c in ev.conflicts:
        if c.fact_a_id not in cited and c.fact_b_id not in cited:
            continue
        texts = []
        for fid in (c.fact_a_id, c.fact_b_id):
            if fid not in shown:
                fact = db.get(Fact, fid)
                shown[fid] = conflict_service.fact_label(fact) if fact is not None else None
            texts.append(shown[fid])
        if None in texts:
            continue                                    # a fact that no longer exists: never show one side alone
        out.append({"id": c.id, "kind": c.kind, "severity": c.severity, "fact_ids": [c.fact_a_id, c.fact_b_id], "texts": texts})
    return out


def ask(db: Session, question: str, *, mode: str = "auto", llm: LLMClient, embedder: Embedder | None, settings: Settings,
        document_id: str | None = None, owner_id: int | None = None, today: date | None = None) -> dict:
    question = question.strip()
    mode_used = "graph" if mode == "auto" else mode
    t0 = time.time()
    ev = gather(db, question, mode_used, llm, embedder, settings, document_id, owner_id, today)
    t1 = time.time()
    doc_ids = {d for f in ev.facts for d in f.docs} | {c.document_id for c, _ in ev.passages}
    titles = sorted(t for (t,) in db.execute(select(Document.title).where(Document.id.in_(doc_ids)))) if doc_ids else []
    reasoning = {**ev.reasoning, "mode": mode_used, "facts_considered": len(ev.facts), "passages_considered": len(ev.passages),
                 "evidence_documents": titles}
    if not ev.facts and not ev.passages:
        note = "Nothing in the graph or the passages relates to this question."
        if ev.window and reasoning["time"]["left_out"]:
            note = (f"The graph has facts about this, but their dates put them outside {ev.window.label} "
                    f"(for example: {'; '.join(reasoning['time']['left_out_examples'][:3])}).")
        return {"question": question, "found": False, "answer": "not found", "citations": [], "reasoning": reasoning,
                "note": note, "timings_ms": {"retrieve": round((t1 - t0) * 1000)}}
    ev.conflicts = conflict_service.open_conflicts_for(db, [f.id for f in ev.facts], owner_id)
    prompt, labels = build_prompt(db, question, ev)
    result = answer_from(llm, prompt, ev.window)
    t2 = time.time()
    citations, dropped = [], []
    for label in dict.fromkeys(result["cited"]):
        if label in labels:
            citations.append({"label": label, **labels[label]})
        else:
            dropped.append(label)
    out = {"question": question, "found": result["found"] and bool(result["answer"]), "answer": result["answer"] or "not found",
           "citations": citations, "reasoning": reasoning,
           "timings_ms": {"retrieve": round((t1 - t0) * 1000), "answer": round((t2 - t1) * 1000)}}
    disputes = _disputes_behind(db, ev, citations) if out["found"] else []
    if disputes:
        out["conflicts"] = disputes
    if ev.window and out["found"]:
        caveat = _time_caveat(citations, ev.window)
        if caveat:
            out["time_caveat"] = caveat
    if dropped:
        out["dropped_citations"] = dropped            # labels the model cited that it was never given
    if out["found"] and not citations:
        out["warning"] = "The model answered without citing any fact or passage it was given; treat the answer with care."
    if result.get("error"):
        out["warning"] = result["error"]
    return out
