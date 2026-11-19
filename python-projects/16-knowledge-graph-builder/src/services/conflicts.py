"""Facts that cannot both be true.

Code finds the candidates, a person decides. Four shapes of conflict:

  different_object  one subject, a relation that has one object at a time, two objects     "Quillon is headquartered in Dunmere" / "... in Valcross"
  different_value   one subject, one relation, two plain values                            "Acme employs 340 people" / "... 400 people"
  different_holder  one object, a relation that has one holder at a time, two subjects     "Nadia was CEO of Tessel" / "Corin led Tessel"
  reversed          the same relation written both ways round                              "Acme acquired Beta" / "Beta acquired Acme"

Which relations have "one at a time" is a built-in list of common ones (headquartered in, born in, CEO of, chaired, mayor of ...);
for any other relation the model can be asked once and the answer is remembered (it is only ever asked about the word, never
about your documents). A relation nobody classified is treated as "many", so nothing is flagged by guesswork.

Two values read from one sentence are a list, not a contradiction ("tested on 100 patients, 12 providers, and 8 pharmacies"
gives "tested 100 patients" and "tested 12 providers"): facts whose evidence is the same quote, or quotes from the same sentence of
the same document, are never paired as different values, objects or holders. Facts from different sentences, or different documents, still are.

Two facts only conflict if they can have held at the same time (temporal.overlap_status): a handover ("2012 to 2019" and
"2019 to 2022") is not a conflict, "since 2020" and "since 2023" with no end stated is a possible one (probably one replaced the other),
and two facts with dates that surely share time are a certain one. Nothing is ever deleted: choosing one fact leaves the other out of
the graph and the answers until the choice is undone.
"""
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import combinations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from src.models.conflict import Conflict, ConflictStatus, PredicateKind
from src.models.graph import Document, Fact, FactSource
from src.services.llm import LLMBadOutput, LLMClient, LLMError
from src.services.temporal import _not_after, overlap_status

AUX = {"was", "is", "are", "were", "been", "being", "be", "has", "have", "had", "became", "become", "becomes", "served", "serves",
       "serving", "as", "the", "a", "an", "now", "currently", "formerly", "also", "its", "his", "her", "their", "then", "later", "since"}

# (pattern on the normalised relation, family, kind). The family is what makes "led" and "served as chief executive of" the same relation.
LEXICON = [
    (r"\b(ceo|chief executive( officer)?)\b|^(led|leads|lead|leading|headed|heads|head of|ran|runs|running)\b", "leader", "one_subject"),
    (r"\b(cto|chief (technology|technical) officer)\b", "cto", "one_subject"),
    (r"\b(cfo|chief financial officer)\b", "cfo", "one_subject"),
    (r"\b(chair|chaired|chairs|chairman|chairwoman|chairperson)\b", "chair", "one_subject"),
    (r"\bmayor\b", "mayor", "one_subject"),
    (r"\bpresident of\b|\bpresided over\b", "president", "one_subject"),
    (r"headquarter", "headquarters", "one_object"),
    (r"^(based in|based at)$", "headquarters", "one_object"),
    (r"\bborn (in|at)\b", "birthplace", "one_object"),
    (r"\bdied (in|at)\b", "deathplace", "one_object"),
]
SYMMETRIC = re.compile(r"\b(partner|partnered|partners|merged|merge|married|knows|met|competes|competitor|collaborat|sibling|brother|sister|"
                       r"related|allied|ally|friend|colleague|neighbou?r|rival)\w*", re.I)
KINDS = ("one_object", "one_subject", "many")


def normalize_predicate(predicate: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", predicate.casefold()) if w not in AUX]
    return " ".join(words)


def lexicon_lookup(predicate: str) -> tuple[str, str] | None:
    """(family, kind) for a relation the built-in list knows"""
    norm = normalize_predicate(predicate)
    for pattern, family, kind in LEXICON:
        if re.search(pattern, norm):
            return family, kind
    return None


# ---------------------------------------------------------------- asking the model what a relation word is (once, then remembered)

CLASSIFY_SYSTEM = """You classify a relation word that links two things in a knowledge graph: "S relation O".
one_object: S can have only ONE such O at a time (born in, headquartered in, capital of, is married to).
one_subject: O can have only ONE such S at a time (CEO of, mayor of, owner of a house: a company has one CEO at a time).
many: several are possible at once (founded, acquired, employs, works with, knows, member of, studied at, located in).
When unsure, answer many."""
CLASSIFY_SCHEMA = {"type": "object", "properties": {"kind": {"type": "string", "enum": list(KINDS)}}, "required": ["kind"]}


def classify_predicate(db: Session, llm: LLMClient, predicate: str) -> str:
    """The kind of a relation word the list does not know: remembered answer, else ask the model (about the word only)"""
    key = normalize_predicate(predicate)[:80]
    row = db.get(PredicateKind, key)
    if row is not None:
        return row.kind
    try:
        data = llm.generate_json(CLASSIFY_SYSTEM, f'Relation: "{predicate}"', CLASSIFY_SCHEMA, max_tokens=48)
    except (LLMBadOutput, LLMError):
        return "many"
    kind = data.get("kind") if data.get("kind") in KINDS else "many"
    db.add(PredicateKind(key=key, kind=kind, model=llm.name))
    db.flush()
    return kind


def predicate_kind(db: Session, predicate: str, llm: LLMClient | None = None) -> tuple[str, str]:
    """(group key, kind): facts conflict only inside one group key. A word nobody classified is 'many' (never flagged)."""
    known = lexicon_lookup(predicate)
    if known:
        return known[0], known[1]
    key = normalize_predicate(predicate)
    row = db.get(PredicateKind, key[:80])
    if row is not None:
        return key, row.kind
    if llm is not None:
        return key, classify_predicate(db, llm, predicate)
    return key, "many"


# ---------------------------------------------------------------- facts as the detector sees them

@dataclass
class Item:
    fact: Fact
    key: str           # the relation's group key
    kind: str          # one_object | one_subject | many
    docs: set = field(default_factory=set)
    sources: list = field(default_factory=list)       # (document id, the quote the fact was read from)

    @property
    def identity(self) -> str:
        """What the object is: its entity, or its normalised plain value"""
        return f"e:{self.fact.object_id}" if self.fact.object_id else f"v:{_value_key(self.fact.object_value)}"


def _value_key(value: str) -> str:
    nums = re.findall(r"\d[\d,.]*", value)
    if nums:
        return nums[0].replace(",", "")
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def overruled_ids(db: Session, owner_id: int | None) -> set[str]:
    """Facts a person left out by choosing the other one of a conflict (undone by reopening the conflict)"""
    rows = db.execute(select(Conflict.fact_a_id, Conflict.fact_b_id, Conflict.resolution)
                      .where(Conflict.owner_id == owner_id, Conflict.status == ConflictStatus.RESOLVED,
                             Conflict.resolution.in_(("keep_a", "keep_b")))).all()
    return {b if res == "keep_a" else a for a, b, res in rows}


def _label(f: Fact) -> str:
    when = f" ({f.valid_from or ''}..{f.valid_to or ''})" if (f.valid_from or f.valid_to) else ""
    return f"{f.subject.name} {f.predicate} {f.object.name if f.object else f.object_value}{when}"


def fact_label(f: Fact) -> str:
    """A fact in words, as answers and conflicts show it: 'Acme employs 340 people (2020..)'"""
    return _label(f)


def _period(f: Fact) -> str:
    if f.valid_from and f.valid_to:
        return f"{f.valid_from} to {f.valid_to}"
    if f.valid_from:
        return f"since {f.valid_from}, no end stated"
    if f.valid_to:
        return f"until {f.valid_to}"
    return "no date"


def _reason(kind: str, a: Item, b: Item, overlap: str) -> list[str]:
    fa, fb = a.fact, b.fact
    reasons = {
        "different_object": f"Both say where or what {fa.subject.name} is for “{fa.predicate}”, and name different ones",
        "different_value": f"Both give a value for “{fa.predicate}” of {fa.subject.name}, and the values differ ({fa.object_value} / {fb.object_value})",
        "different_holder": f"Both say who “{fa.predicate}” {fa.object.name if fa.object else ''}, and name different people or organisations" if fa.object
        else "Both name a holder of the same relation",
        "reversed": f"The same relation is stated both ways round between {fa.subject.name} and {fa.object.name if fa.object else ''}",
    }[kind]
    when = {
        "certain": f"their dates share time ({_period(fa)}; {_period(fb)})",
        "possible": f"they might share time ({_period(fa)}; {_period(fb)})",
        "unknown": "neither has a date, so they may refer to different times",
    }[overlap]
    out = [reasons, when]
    if a.docs and b.docs and a.docs.isdisjoint(b.docs):
        out.append("stated in different documents")
    elif a.docs and a.docs == b.docs:
        out.append("both in the same document (check that it was read correctly)")
    return out


def _load(db: Session, owner_id: int | None, llm: LLMClient | None) -> list[Item]:
    skip = overruled_ids(db, owner_id)
    docs, sources = defaultdict(set), defaultdict(list)
    for fid, did, quote in db.execute(select(FactSource.fact_id, FactSource.document_id, FactSource.evidence)
                                      .join(Fact, Fact.id == FactSource.fact_id).where(Fact.owner_id == owner_id)).all():
        docs[fid].add(did)
        sources[fid].append((did, quote))
    items = []
    for f in db.execute(select(Fact).where(Fact.owner_id == owner_id)).scalars():
        if f.id in skip:
            continue
        key, kind = predicate_kind(db, f.predicate, llm)
        items.append(Item(f, key, kind, docs.get(f.id, set()), sources.get(f.id, [])))
    return items


def _pairs(items: list[Item]):
    """Candidate pairs as (kind, a, b)"""
    by_subject = defaultdict(list)
    by_object = defaultdict(list)
    reverse = defaultdict(list)
    for it in items:
        by_subject[(it.fact.subject_id, it.key)].append(it)
        if it.fact.object_id:
            by_object[(it.fact.object_id, it.key)].append(it)
            reverse[(frozenset((it.fact.subject_id, it.fact.object_id)), it.key)].append(it)
    for group in by_subject.values():
        for a, b in combinations(group, 2):
            if a.identity == b.identity:
                continue
            if not a.fact.object_id and not b.fact.object_id:
                yield "different_value", a, b
            elif a.fact.object_id and b.fact.object_id and a.kind == "one_object" and b.kind == "one_object":
                yield "different_object", a, b
    for group in by_object.values():
        for a, b in combinations(group, 2):
            if a.fact.subject_id != b.fact.subject_id and a.kind == "one_subject" and b.kind == "one_subject":
                yield "different_holder", a, b
    for group in reverse.values():
        for a, b in combinations(group, 2):
            if a.fact.subject_id == b.fact.object_id and a.fact.object_id == b.fact.subject_id and not SYMMETRIC.search(a.fact.predicate + " " + b.fact.predicate):
                yield "reversed", a, b


# ---------------------------------------------------------------- one sentence is not a disagreement

SENTENCE_END = re.compile(r"""[.!?]["')\]]*\s+(?=["'(\[]?[A-Z0-9])|\n\s*\n""")


def _squash(text: str) -> str:
    return " ".join(text.split())


def _locate(text: str, quote: str) -> tuple[int, int] | None:
    """Where the quote stands in the document text (whitespace may differ), or None when it cannot be found"""
    words = quote.split()
    if not words:
        return None
    m = re.search(r"\s+".join(re.escape(w) for w in words), text)
    return (m.start(), m.end()) if m else None


ABBREVIATIONS = {"dr", "mr", "mrs", "ms", "prof", "st", "vs", "fig", "figs", "no", "al", "etc", "e.g", "i.e", "approx", "inc", "ltd", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec"}


def _in_one_sentence(text: str, start: int, end: int) -> bool:
    """No sentence ends between start and end ('Dr. Lee', 'et al. Smith' and '44.4' do not end one)"""
    for m in SENTENCE_END.finditer(text, start, end):
        words = text[start:m.start()].split()
        abbreviation = text[m.start()] == "." and bool(words) and words[-1].casefold().strip("([\"'") in ABBREVIATIONS
        if not abbreviation:
            return False
    return True


class _DocText:
    """Document texts, read only for the pairs that need them"""

    def __init__(self, db: Session):
        self.db, self.cache = db, {}

    def get(self, document_id: str) -> str:
        if document_id not in self.cache:
            self.cache[document_id] = self.db.scalar(select(Document.text).where(Document.id == document_id)) or ""
        return self.cache[document_id]


def same_sentence(a: Item, b: Item, texts: _DocText) -> bool:
    """True when both facts were read from the same place in one document: the very same quote (even a long one: it cannot say
    which part backs which fact), one quote cut shorter than the other, or two different quotes that lie in the same sentence
    of the document text (found by looking the quotes up in it)."""
    for doc_a, quote_a in a.sources:
        for doc_b, quote_b in b.sources:
            if doc_a != doc_b:
                continue
            qa, qb = _squash(quote_a), _squash(quote_b)
            if not qa or not qb:
                continue
            if qa in qb or qb in qa:                     # the same quote, or one cut shorter than the other
                return True
            text = texts.get(doc_a)
            pa, pb = _locate(text, qa), _locate(text, qb)
            if pa and pb and _in_one_sentence(text, min(pa[0], pb[0]), max(pa[1], pb[1])):
                return True
    return False


def find_pairs(db: Session, owner_id: int | None, llm: LLMClient | None = None) -> list[tuple[str, str, Item, Item, str]]:
    """(kind, severity, a, b, overlap) for every pair that looks contradictory. Pair order is fixed (smaller fact id first)."""
    out = []
    texts = _DocText(db)
    for kind, a, b in _pairs(_load(db, owner_id, llm)):
        overlap = overlap_status(a.fact.valid_from, a.fact.valid_to, b.fact.valid_from, b.fact.valid_to)
        if overlap == "none":
            continue
        if kind != "reversed" and same_sentence(a, b, texts):
            continue                                     # a list read from one sentence, not two statements that disagree
        if a.fact.id > b.fact.id:
            a, b = b, a
        out.append((kind, "certain" if overlap == "certain" else "possible", a, b, overlap))
    return out


# ---------------------------------------------------------------- running it

def _now():
    return datetime.now(timezone.utc)


@dataclass
class Summary:
    new: int = 0
    removed: int = 0
    open: int = 0
    judged: int = 0

    def as_dict(self) -> dict:
        return {"new": self.new, "removed": self.removed, "open": self.open, "judged": self.judged}


JUDGE_SYSTEM = """Two statements were read from documents. Decide whether they contradict each other, assuming both talk about the same time.
yes: they cannot both be true. no: both can be true (different roles, different places at different levels, one adds detail to the other). unsure: you cannot tell."""
JUDGE_SCHEMA = {"type": "object", "properties": {"contradict": {"type": "string", "enum": ["yes", "no", "unsure"]}}, "required": ["contradict"]}


def judge_pair(llm: LLMClient, db: Session, a: Fact, b: Fact) -> str | None:
    def line(f: Fact) -> str:
        src = db.execute(select(FactSource.evidence).where(FactSource.fact_id == f.id).limit(1)).scalar()
        return f'{_label(f)}' + (f'   (the text says: "{src[:200]}")' if src else "")
    try:
        data = llm.generate_json(JUDGE_SYSTEM, f"A: {line(a)}\nB: {line(b)}", JUDGE_SCHEMA, max_tokens=48)
    except (LLMBadOutput, LLMError):
        return None
    v = data.get("contradict")
    return v if v in ("yes", "no", "unsure") else None


def run_detection(db: Session, *, owner_id: int | None = None, llm: LLMClient | None = None, judge: bool = False) -> Summary:
    """Find conflicts and record new ones. Open conflicts that no longer apply are removed; decided ones are never touched.
    With `llm` unknown relation words are classified (and remembered); with `judge` each new pair also gets the model's opinion."""
    summary = Summary()
    found = find_pairs(db, owner_id, llm)
    existing = {(c.fact_a_id, c.fact_b_id): c for c in db.execute(select(Conflict).where(Conflict.owner_id == owner_id)).scalars()}
    keep = set()
    for kind, severity, a, b, overlap in found:
        pair = (a.fact.id, b.fact.id)
        keep.add(pair)
        row = existing.get(pair)
        if row is None:
            row = Conflict(owner_id=owner_id, status=ConflictStatus.OPEN, kind=kind, severity=severity, fact_a_id=a.fact.id, fact_b_id=b.fact.id, reasons=_reason(kind, a, b, overlap))
            db.add(row)
            summary.new += 1
        elif row.status == ConflictStatus.OPEN:
            row.kind, row.severity, row.reasons = kind, severity, _reason(kind, a, b, overlap)
        if judge and llm is not None and row.status == ConflictStatus.OPEN and row.llm_verdict is None:
            row.llm_verdict = judge_pair(llm, db, a.fact, b.fact)
            summary.judged += row.llm_verdict is not None
    for pair, row in existing.items():
        if row.status == ConflictStatus.OPEN and pair not in keep:
            db.delete(row)
            summary.removed += 1
    db.flush()
    summary.open = db.scalar(select(func.count()).select_from(Conflict).where(Conflict.owner_id == owner_id, Conflict.status == ConflictStatus.OPEN)) or 0
    return summary


# ---------------------------------------------------------------- deciding

class ConflictError(ValueError):
    pass


RESOLUTIONS = ("keep_a", "keep_b", "both", "succession")


def get_conflict(db: Session, conflict_id: str, owner_id: int | None) -> Conflict:
    c = db.get(Conflict, conflict_id)
    if c is None or c.owner_id != owner_id:
        raise ConflictError("Conflict not found")
    return c


def succession_order(a: Fact, b: Fact) -> tuple[Fact, Fact] | None:
    """(earlier, later) when one began clearly before the other and the earlier one states no end after the later one's start"""
    if not (a.valid_from and b.valid_from):
        return None
    if _not_after(a.valid_from, b.valid_from) and _not_after(b.valid_from, a.valid_from):
        return None                                  # the same start: nothing says which came first
    earlier, later = (a, b) if _not_after(a.valid_from, b.valid_from) else (b, a)
    if earlier.valid_to and not _not_after(later.valid_from, earlier.valid_to):
        return None                                  # it already ends before the other begins: no conflict to settle
    return earlier, later


def resolve(db: Session, conflict_id: str, resolution: str, owner_id: int | None = None) -> Conflict:
    """keep_a / keep_b: trust that fact, leave the other out. both: not a conflict. succession: the earlier one ended when the later began."""
    if resolution not in RESOLUTIONS:
        raise ConflictError(f"resolution must be one of: {', '.join(RESOLUTIONS)}")
    c = get_conflict(db, conflict_id, owner_id)
    if c.status != ConflictStatus.OPEN:
        raise ConflictError("This conflict was already decided; reopen it first")
    a, b = db.get(Fact, c.fact_a_id), db.get(Fact, c.fact_b_id)
    if a is None or b is None:
        raise ConflictError("One of the facts no longer exists")
    data: dict = {}
    if resolution == "succession":
        order = succession_order(a, b)
        if order is None:
            raise ConflictError("These facts do not say which came first, so one cannot be ended at the other's start")
        earlier, later = order
        clash = db.execute(select(Fact.id).where(Fact.subject_id == earlier.subject_id, Fact.predicate == earlier.predicate,
                                                 Fact.object_id == earlier.object_id, Fact.object_value == earlier.object_value,
                                                 Fact.valid_from == earlier.valid_from, Fact.valid_to == later.valid_from, Fact.id != earlier.id)).first()
        if clash:
            raise ConflictError("A fact with those dates already exists")
        data = {"fact_id": earlier.id, "old_valid_to": earlier.valid_to}
        earlier.valid_to = later.valid_from
    c.status = ConflictStatus.DISMISSED if resolution == "both" else ConflictStatus.RESOLVED
    c.resolution, c.data, c.decided_at = resolution, data, _now()
    db.flush()
    return c


def reopen(db: Session, conflict_id: str, owner_id: int | None = None) -> Conflict:
    c = get_conflict(db, conflict_id, owner_id)
    if c.status == ConflictStatus.OPEN:
        raise ConflictError("This conflict is still open")
    if c.resolution == "succession" and c.data:
        f = db.get(Fact, c.data["fact_id"])
        if f is not None:
            clash = db.execute(select(Fact.id).where(Fact.subject_id == f.subject_id, Fact.predicate == f.predicate, Fact.object_id == f.object_id,
                                                     Fact.object_value == f.object_value, Fact.valid_from == f.valid_from,
                                                     Fact.valid_to == c.data["old_valid_to"], Fact.id != f.id)).first()
            if clash:
                raise ConflictError("A fact with the earlier dates exists again, so the dates cannot be restored")
            f.valid_to = c.data["old_valid_to"]
    c.status, c.resolution, c.data, c.decided_at = ConflictStatus.OPEN, None, {}, None
    db.flush()
    return c


def open_conflicts_for(db: Session, fact_ids: list[str], owner_id: int | None) -> list[Conflict]:
    """Open conflicts that involve any of these facts"""
    if not fact_ids:
        return []
    return list(db.execute(select(Conflict).where(Conflict.owner_id == owner_id, Conflict.status == ConflictStatus.OPEN,
                                                  or_(Conflict.fact_a_id.in_(fact_ids), Conflict.fact_b_id.in_(fact_ids)))).scalars())
