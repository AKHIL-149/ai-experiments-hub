"""Check a claim against the documents.

The model only turns the claim into "subject relation object (dates)". Code does the checking, so every verdict comes with the
facts and quotes it rests on:

  supported              a stored fact says the same (same relation, same two things, dates that do not clash)
  supported_other_dates  a stored fact says the same, but its dates do not fit the claim's
  contradicted           the documents say the opposite: the relation the other way round, a different value, or a different
                         object / holder for a relation that has only one at a time
  not_found              the documents do not say. This is never "false": the documents may simply be silent.
  unclear                the claim could not be read, or its subject is not in the documents
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.core.config import Settings
from src.services import graph_query as gq
from src.services.conflicts import SYMMETRIC, _value_key, predicate_kind
from src.services.embedding import Embedder, EmbeddingError
from src.services.llm import LLMBadOutput, LLMClient
from src.services.extraction import fix_passive
from src.services.text_utils import normalize_date
from src.services.temporal import _not_after, overlap_status

CLAIM_SYSTEM = """You turn ONE claim into a statement: subject, relation, object, and the dates it gives.
relation: a short verb phrase ("acquired", "was CTO of", "headquartered in", "employs"). object: the thing or value the relation points to.
start / end: the year or date the claim gives for when it began / ended, as YYYY, YYYY-MM or YYYY-MM-DD; "in 2019" for a one-time event or a
state at that time puts 2019 in start and leaves end empty; "from 2015 to 2018" gives both; leave both empty when the claim has no date.
Copy names exactly as written in the claim. Never add facts that are not in the claim.

Examples
Claim: Veltra Dynamics acquired Soro Labs in 2018.
{"subject": "Veltra Dynamics", "relation": "acquired", "object": "Soro Labs", "start": "2018", "end": ""}
Claim: Maria Lopez was the CTO of Acme from 2012 to 2019.
{"subject": "Maria Lopez", "relation": "was CTO of", "object": "Acme", "start": "2012", "end": "2019"}
Claim: Acme employs 340 people.
{"subject": "Acme", "relation": "employs", "object": "340 people", "start": "", "end": ""}"""
CLAIM_SCHEMA = {"type": "object", "properties": {k: {"type": "string"} for k in ("subject", "relation", "object", "start", "end")},
                "required": ["subject", "relation", "object", "start", "end"]}

VERDICTS = ("supported", "supported_other_dates", "contradicted", "not_found", "unclear")


@dataclass
class Claim:
    subject: str
    relation: str
    object: str
    start: str
    end: str

    def as_dict(self) -> dict:
        return {"subject": self.subject, "relation": self.relation, "object": self.object, "start": self.start or None, "end": self.end or None}


def parse_claim(llm: LLMClient, text: str) -> Claim | None:
    """The model's reading of the claim; None when it gave nothing usable (bad output is retried once)"""
    for _ in range(2):
        try:
            data = llm.generate_json(CLAIM_SYSTEM, f"Claim: {text}", CLAIM_SCHEMA, max_tokens=256)
        except LLMBadOutput:
            continue
        get = lambda k: data.get(k).strip() if isinstance(data.get(k), str) else ""  # noqa: E731
        if get("subject") and get("relation") and get("object"):
            # a date the claim does not literally contain is not trusted (the model may invent one)
            keep = lambda d: d if d and d in normalized_text(text) else ""  # noqa: E731
            subject, relation, obj = get("subject"), get("relation"), get("object")
            active, swap = fix_passive(relation)          # "X was founded by Y" is stored as "Y founded X"
            if swap:
                subject, relation, obj = obj, active, subject
            return Claim(subject, relation, obj, keep(normalize_date(get("start"))), keep(normalize_date(get("end"))))
    return None


def normalized_text(text: str) -> str:
    """Every date the text contains, written the way facts store them, joined (so a parsed date can be checked against it)"""
    import re
    from src.services.temporal import _MONTH_NAMES
    found = []
    for m in re.finditer(rf"\b(?:\d{{1,2}}(?:st|nd|rd|th)?\s+)?(?:(?:{_MONTH_NAMES})\.?,?\s+)?(?:\d{{1,2}}(?:st|nd|rd|th)?,?\s+)?\d{{4}}(?:-\d{{2}}(?:-\d{{2}})?)?", text, re.I):
        d = normalize_date(m.group(0).replace(",", " "))
        if d:
            found.append(d)
            found.append(d[:4])
    return " ".join(found)


def dates_fit_fact(c_from: str, c_to: str, f_from: str, f_to: str) -> bool:
    """Can the claim's dates be what the fact says? A claim naming one date ("in 2015") fits a fact that had begun by then and
    had not ended by then (a fact with no stated end is taken to still hold: the text does not say otherwise);
    a claim naming a range fits a fact that overlaps it and had begun by its end. A fact with no date cannot contradict a claim."""
    if not (c_from or c_to) or not (f_from or f_to):
        return True
    if c_from and c_to:
        return overlap_status(c_from, c_to, f_from, f_to) != "none" and (not f_from or _not_after(f_from, c_to))
    day = c_from or c_to
    return (not f_from or _not_after(f_from, day)) and (not f_to or _not_after(day, f_to))


class Checker:
    def __init__(self, db: Session, index: gq.GraphIndex, matcher: gq.PredicateMatcher, threshold: float):
        self.db, self.index, self.matcher, self.threshold = db, index, matcher, threshold

    def same_relation(self, claim_relation: str, stored: str) -> bool:
        a, b = predicate_kind(self.db, claim_relation), predicate_kind(self.db, stored)
        if a[0] == b[0] and a[0]:
            return True
        return self.matcher.scores(claim_relation).get(stored, 0.0) >= self.threshold

    def entity(self, name: str) -> str | None:
        seeds = self.index.link(name)
        good = [s for s in seeds if s.how in ("exact", "alias") or s.confidence >= 0.6]
        return good[0].entity_id if good else None


def check(db: Session, claim_text: str, *, llm: LLMClient, embedder: Embedder | None, settings: Settings, owner_id: int | None = None) -> dict:
    from src.services.ask import _quotes
    out: dict = {"claim": claim_text, "parsed": None, "verdict": "unclear", "summary": "", "evidence": [], "reasoning": []}
    claim = parse_claim(llm, claim_text)
    if claim is None:
        out["summary"] = "The claim could not be read as a statement of the form: something relation something. Try a plain sentence."
        return out
    out["parsed"] = claim.as_dict()
    index = gq.GraphIndex(db, owner_id=owner_id)
    try:
        matcher = gq.PredicateMatcher(embedder, [f.predicate for f in index.facts.values()])
        matcher.scores(claim.relation)
    except EmbeddingError:
        matcher = gq.PredicateMatcher(None, [f.predicate for f in index.facts.values()])
    ck = Checker(db, index, matcher, settings.predicate_threshold)
    key, kind = predicate_kind(db, claim.relation)
    subj = ck.entity(claim.subject)
    obj = ck.entity(claim.object)
    why = out["reasoning"]
    if subj is None:
        holders = []
        if obj is not None and kind == "one_subject":
            # a holder the documents do not know, for a role that has one holder at a time: the holders they do name clash with it
            holders = [f for f in index.inn.get(obj, []) if predicate_kind(db, f.predicate)[0] == key and dates_fit_fact(claim.start, claim.end, f.valid_from, f.valid_to)]
        if not holders:
            out["summary"] = f"“{claim.subject}” is not in the documents, so nothing can be checked."
            why.append(f"no entity matches “{claim.subject}”")
            return out
        why.append(f"“{claim.subject}” is not in the documents, but {index.name(obj)} has other holders of this role")
        out["verdict"] = "contradicted"
        out["summary"] = f"The documents name someone else: {holders[0].text()}."
        quotes = _quotes(db, [f.id for f in holders])
        out["evidence"] = [{"role": "contradicts", "fact_id": f.id, "text": f.text(), "valid_from": f.valid_from or None, "valid_to": f.valid_to or None,
                            "quote": quotes.get(f.id, {}).get("quote"), "document_title": quotes.get(f.id, {}).get("document_title"),
                            "verified": quotes.get(f.id, {}).get("verified", False)} for f in holders]
        return out
    sname = index.name(subj)
    why.append(f"subject: {sname}" + (f"; object: {index.name(obj)}" if obj else f"; object read as a value: {claim.object}"))
    c_from, c_to = claim.start, claim.end

    evidence: list[tuple[str, gq.FactView]] = []

    def dates_fit(f: gq.FactView) -> bool:
        if not (c_from or c_to):
            return True
        return dates_fit_fact(c_from, c_to, f.valid_from, f.valid_to)

    verdict, summary = "not_found", ""
    if obj is not None:
        same = [f for f in index.out.get(subj, []) if f.o_id == obj and ck.same_relation(claim.relation, f.predicate)]
        back = [f for f in index.out.get(obj, []) if f.o_id == subj and ck.same_relation(claim.relation, f.predicate)]
        if same:
            fits = [f for f in same if dates_fit(f)]
            if fits:
                verdict, summary = "supported", f"The documents say this: {fits[0].text()}."
                evidence += [("supports", f) for f in fits]
            else:
                verdict = "supported_other_dates"
                summary = f"The documents say this happened, but with other dates: {same[0].text()}."
                evidence += [("supports", f) for f in same]
        elif back and not SYMMETRIC.search(claim.relation):
            verdict, summary = "contradicted", f"The documents say it the other way round: {back[0].text()}."
            evidence += [("contradicts", f) for f in back]
        elif kind == "one_object":
            other = [f for f in index.out.get(subj, []) if f.o_id and f.o_id != obj and predicate_kind(db, f.predicate)[0] == key and dates_fit(f)]
            if other:
                verdict, summary = "contradicted", f"The documents name something else: {other[0].text()}."
                evidence += [("contradicts", f) for f in other]
        elif kind == "one_subject":
            other = [f for f in index.inn.get(obj, []) if f.s_id != subj and predicate_kind(db, f.predicate)[0] == key and dates_fit(f)]
            if other:
                verdict, summary = "contradicted", f"The documents name someone else: {other[0].text()}."
                evidence += [("contradicts", f) for f in other]
        if verdict == "not_found":
            related = [f for f in index.out.get(subj, []) + index.out.get(obj, []) if {f.s_id, f.o_id} == {subj, obj}]
            evidence += [("related", f) for f in related]
            summary = "The documents do not say this."
            if related:
                summary += " They do connect the two in another way (shown below)."
    elif kind == "one_object":
        # the claim names something the documents do not know, for a relation with one object at a time: what they do name differs
        other = [f for f in index.out.get(subj, []) if f.o_id and predicate_kind(db, f.predicate)[0] == key and dates_fit(f)]
        if other:
            verdict, summary = "contradicted", f"The documents name something else: {other[0].text()}."
            evidence += [("contradicts", f) for f in other]
        else:
            summary = "The documents do not say this."
    else:
        same = [f for f in index.out.get(subj, []) if f.is_value and ck.same_relation(claim.relation, f.predicate)]
        agree = [f for f in same if _value_key(f.o_name) == _value_key(claim.object)]
        differ = [f for f in same if _value_key(f.o_name) != _value_key(claim.object) and dates_fit(f)]
        if agree:
            fits = [f for f in agree if dates_fit(f)]
            verdict = "supported" if fits else "supported_other_dates"
            summary = f"The documents say this: {agree[0].text()}." if fits else f"The documents say this, but with other dates: {agree[0].text()}."
            evidence += [("supports", f) for f in agree]
        elif differ:
            verdict, summary = "contradicted", f"The documents give a different value: {differ[0].text()}."
            evidence += [("contradicts", f) for f in differ]
        else:
            summary = "The documents do not say this."
    out["verdict"], out["summary"] = verdict, summary
    quotes = _quotes(db, [f.id for _, f in evidence])
    seen = set()
    for role, f in evidence:
        if (role, f.id) in seen:
            continue
        seen.add((role, f.id))
        q = quotes.get(f.id, {})
        out["evidence"].append({"role": role, "fact_id": f.id, "text": f.text(), "valid_from": f.valid_from or None, "valid_to": f.valid_to or None,
                                "quote": q.get("quote"), "document_title": q.get("document_title"), "verified": q.get("verified", False)})
    return out
