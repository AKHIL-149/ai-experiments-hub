"""Entity resolution: find the entities that are really one thing, merge the safe cases, suggest the rest.

Safe (merged automatically): names that are the same apart from case, accents, punctuation, titles, an article or a
company suffix ("Acme Corp", "ACME", "The Acme Company"); and a surname or first name that appears in the same
document as exactly one matching full name.
Unsure (suggested, a person decides): one name inside another ("Acme" / "Acme Labs"), acronyms ("IBM"), small
spelling differences. A language model may be asked for a second opinion on those.
Never merged: different types, names that differ in a number or letter ("Widget-X" / "Widget-W", "Henric II" /
"Henric III"), or two entities that a fact links to each other.

Every merge is recorded and can be undone. The absorbed name stays as an alias, so later documents land on the same entity.
"""
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from rapidfuzz import fuzz, process
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from src.models.graph import Chunk, Entity, Fact, FactSource
from src.models.resolution import EntityAlias, MergeRecord, MergeSuggestion, SuggestionStatus
from src.services.llm import LLMBadOutput, LLMClient, LLMError
from src.services.text_utils import entity_key, words

TITLES = {"dr", "prof", "professor", "mr", "mrs", "ms", "sir", "king", "queen", "prince", "princess", "lord", "lady",
          "president", "captain", "saint", "st", "dame"}
LEGAL = {"inc", "incorporated", "corp", "corporation", "ltd", "limited", "llc", "co", "company", "gmbh", "plc", "ag",
         "sa", "lp", "llp"}
ARTICLES = {"the", "a", "an"}
SKIP_IN_ACRONYM = {"of", "and", "the", "for", "in", "at", "de", "la"}
_ROMAN = re.compile(r"^(?=[ivxlcdm]{2,}$)m{0,3}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$")

MIN_SUGGESTION_SCORE = 0.5
FUZZY_MIN_RATIO = 90
FUZZY_MIN_LENGTH = 5
AMBIGUITY_PENALTY = 0.25
CONTEXT_BOOST = 0.15
CONTEXT_BOOST_MAX = 0.3
JUDGE_YES_BOOST = 0.2    # the model's 'yes' was right every time in the benchmark
JUDGE_NO_FACTOR = 0.85   # its 'no' was often wrong (it rejected 'IBM' / 'International Business Machines'), so only a mild demotion


def apply_verdict(score: float, verdict: str | None) -> float:
    if verdict == "yes":
        return min(score + JUDGE_YES_BOOST, 0.99)
    if verdict == "no":
        return score * JUDGE_NO_FACTOR
    return score


# ---------------------------------------------------------------- names

def canonical_tokens(name: str, etype: str) -> list[str]:
    """The words that identify a name: no case, accents, punctuation, articles; no titles for people; no company
    suffix for organizations; people lose initials and anything after 'of' ('King Henric III of Vestland')"""
    ws = [w for w in words(name) if w not in ARTICLES]
    if etype == "person":
        if "of" in ws[1:]:
            ws = ws[:ws.index("of", 1)]
        ws = [w for w in ws if w not in TITLES]
        named = [w for w in ws if len(w) > 1]
        ws = named or ws
    elif etype in ("organization", "concept"):
        kept = [w for w in ws if w not in LEGAL]
        ws = kept or ws
    return ws


def qualifier_of(name: str, etype: str) -> tuple[str, ...]:
    """What follows 'of' in a person's name: 'Henric III of Vestland' -> ('vestland',)"""
    if etype != "person":
        return ()
    ws = [w for w in words(name) if w not in ARTICLES]
    return tuple(ws[ws.index("of", 1) + 1:]) if "of" in ws[1:] else ()


def initials_of(name: str, etype: str) -> list[str]:
    """First letters of single-letter tokens: 'Alan M. Turing' -> ['m']"""
    if etype != "person":
        return []
    return [w for w in words(name) if len(w) == 1]


def id_tokens(tokens: list[str], etype: str) -> frozenset[str]:
    """Tokens that tell apart otherwise similar names: numbers, Roman numerals and single letters ('Widget-X')"""
    out = set()
    for t in tokens:
        if any(ch.isdigit() for ch in t) or _ROMAN.match(t) or (len(t) == 1 and etype != "person"):
            out.add(t)
    return frozenset(out)


@dataclass
class EntityInfo:
    id: str
    name: str
    type: str
    tokens: list[str]
    qualifier: tuple = ()  # what follows 'of' in a person's name ('Henric III of Vestland' -> ('vestland',))
    initials: list = field(default_factory=list)  # single letters of a person's name ('Alan M. Turing' -> ['m'])
    n_facts: int = 0
    docs: frozenset = frozenset()
    links: frozenset = frozenset()       # (predicate, direction, other entity id) it takes part in
    neighbors: frozenset = frozenset()   # ids of entities it is directly linked to


@dataclass
class Decision:
    kind: str  # auto | suggest | never | none
    score: float = 0.0
    reasons: list = field(default_factory=list)


def compatible_types(a: str, b: str) -> bool:
    return a == b or "concept" in (a, b)


def acronym_matches(short: EntityInfo, long: EntityInfo) -> bool:
    if len(short.tokens) != 1 or not 2 <= len(short.tokens[0]) <= 6 or len(long.tokens) < 2:
        return False
    sig = [w for w in long.tokens if w not in SKIP_IN_ACRONYM]
    return "".join(w[0] for w in sig) == short.tokens[0]  # (one word gives one letter, never a 2+ letter acronym)


def decide(a: EntityInfo, b: EntityInfo, *, ambiguous_with: int = 0, ambiguity_names: list | None = None,
           same_document_rule: bool = True) -> Decision:
    """How sure are we that a and b are one entity? `ambiguous_with` = other entities the shorter name could also be."""
    if not compatible_types(a.type, b.type):
        return Decision("never", reasons=[f"different types ({a.type} / {b.type})"])
    if a.id in b.neighbors or b.id in a.neighbors:
        return Decision("never", reasons=["a fact links these two, so they are different things"])
    ta, tb = a.tokens, b.tokens
    if not ta or not tb:
        return Decision("none")
    if a.qualifier and b.qualifier and a.qualifier != b.qualifier:
        return Decision("never", reasons=[f"different 'of' parts ({' '.join(a.qualifier)} / {' '.join(b.qualifier)})"])
    ia, ib = id_tokens(ta, a.type), id_tokens(tb, b.type)
    if ia != ib and (set(ta) & set(tb)):
        return Decision("never", reasons=[f"differ in a number or letter ({', '.join(sorted(ia ^ ib))})"])
    if ta == tb or set(ta) == set(tb):
        return Decision("auto", 1.0, ["same name apart from case, accents, punctuation, titles or company suffix"])

    shared = len(a.links & b.links)
    boost = min(CONTEXT_BOOST * shared, CONTEXT_BOOST_MAX)
    boost_reason = [f"{shared} shared link(s) to the same entities"] if shared else []

    short, long_ = (a, b) if len(ta) < len(tb) else (b, a)
    if len(short.tokens) != len(long_.tokens) and set(short.tokens) < set(long_.tokens):
        extra = [t for t in long_.tokens if t not in short.tokens]
        if any(not any(t.startswith(i) for t in extra) for i in short.initials):
            return Decision("never", reasons=[f"the initials in '{short.name}' do not fit '{long_.name}'"])
        reasons = [f"'{short.name}' is part of '{long_.name}'"]
        if a.type == b.type == "person" or "person" in (a.type, b.type):
            score = 0.75
            if ambiguous_with == 0 and same_document_rule and (short.docs & long_.docs) and len(short.tokens) == 1:
                return Decision("auto", 0.9, reasons + ["appears in the same document as the full name and no other person fits"])
        else:
            score = 0.55
        if ambiguous_with:
            score -= AMBIGUITY_PENALTY
            reasons.append(f"could also be: {', '.join((ambiguity_names or [])[:3])}")
        return Decision("suggest" if score + boost >= MIN_SUGGESTION_SCORE else "none", min(score + boost, 0.95), reasons + boost_reason)

    if acronym_matches(a, b) or acronym_matches(b, a):
        return Decision("suggest", min(0.7 + boost, 0.95), ["one is the initials of the other"] + boost_reason)

    ratio = fuzz.ratio(" ".join(ta), " ".join(tb))
    if ratio >= FUZZY_MIN_RATIO:  # 90% alike already needs a name of 10+ letters to differ by one
        return Decision("suggest", min(0.6 + (ratio - FUZZY_MIN_RATIO) * 0.02 + boost, 0.95),
                        [f"spelled almost the same ({ratio:.0f}% alike)"] + boost_reason)
    return Decision("none")


# ---------------------------------------------------------------- loading and finding pairs

def load_infos(db: Session) -> dict[str, EntityInfo]:
    infos = {e.id: EntityInfo(e.id, e.name, e.type, canonical_tokens(e.name, e.type), qualifier_of(e.name, e.type),
                                    initials_of(e.name, e.type))
             for e in db.execute(select(Entity)).scalars()}
    links, neighbors, nfacts = defaultdict(set), defaultdict(set), defaultdict(int)
    facts = db.execute(select(Fact.id, Fact.subject_id, Fact.predicate, Fact.object_id)).all()
    for fid, s, p, o in facts:
        nfacts[s] += 1
        if o is not None:
            nfacts[o] += 1
            links[s].add((p, "out", o))
            links[o].add((p, "in", s))
            neighbors[s].add(o)
            neighbors[o].add(s)
    fact_docs = defaultdict(set)
    for fid, doc in db.execute(select(FactSource.fact_id, FactSource.document_id)).all():
        fact_docs[fid].add(doc)
    docs = defaultdict(set)
    for fid, s_id, p, o in facts:
        for d in fact_docs.get(fid, ()):
            docs[s_id].add(d)
            if o is not None:
                docs[o].add(d)
    for i, info in infos.items():
        info.n_facts = nfacts.get(i, 0)
        info.links = frozenset(links.get(i, ()))
        info.neighbors = frozenset(neighbors.get(i, ()))
        info.docs = frozenset(docs.get(i, ()))
    return infos


def candidate_pairs(infos: dict[str, EntityInfo]) -> set[tuple[str, str]]:
    """Pairs worth comparing: share a word, are acronyms of each other, or look alike. Not all n*n pairs."""
    pairs: set[tuple[str, str]] = set()
    by_token = defaultdict(list)
    for i, info in infos.items():
        for t in set(info.tokens):
            by_token[t].append(i)
    for ids in by_token.values():
        if len(ids) > 200:  # a word in hundreds of names ("university") says nothing; skip the quadratic blow-up
            continue
        for x in range(len(ids)):
            for y in range(x + 1, len(ids)):
                pairs.add(tuple(sorted((ids[x], ids[y]))))
    shorts = [i for i, e in infos.items() if len(e.tokens) == 1 and 2 <= len(e.tokens[0]) <= 6]
    for s in shorts:
        for j, e in infos.items():
            if j != s and acronym_matches(infos[s], e):
                pairs.add(tuple(sorted((s, j))))
    strings = {i: " ".join(e.tokens) for i, e in infos.items() if len(" ".join(e.tokens)) >= FUZZY_MIN_LENGTH}
    if strings:
        ids, texts = list(strings), list(strings.values())
        for k, text in enumerate(texts):
            for _, score, idx in process.extract(text, texts, scorer=fuzz.ratio, score_cutoff=FUZZY_MIN_RATIO, limit=8):
                if idx != k:
                    pairs.add(tuple(sorted((ids[k], ids[idx]))))
    return pairs


def evaluate(infos: dict[str, EntityInfo], rejected: set[tuple[str, str]] | None = None,
             same_document_rule: bool = True) -> dict[tuple[str, str], Decision]:
    """Decide every candidate pair (rejected pairs are never reconsidered)"""
    rejected = rejected or set()
    pairs = [p for p in candidate_pairs(infos) if p not in rejected]
    contain = defaultdict(list)  # short entity id -> longer entities whose words include all of its words
    for x, y in pairs:
        a, b = infos[x], infos[y]
        if compatible_types(a.type, b.type) and len(a.tokens) != len(b.tokens):
            short, long_ = (a, b) if len(a.tokens) < len(b.tokens) else (b, a)
            if short.tokens and set(short.tokens) < set(long_.tokens):
                contain[short.id].append(long_)
    by_name = defaultdict(list)  # entities that are the same name apart from case, titles, suffixes
    for e in infos.values():
        by_name[(e.type if e.type != "concept" else "", tuple(e.tokens))].append(e)
    out = {}
    for x, y in pairs:
        a, b = infos[x], infos[y]
        short, long_ = (a, b) if len(a.tokens) < len(b.tokens) else (b, a)
        # other *different* names the shorter one could also stand for (spelling variants of one name count once)
        others = {tuple(c.tokens): c for c in contain.get(short.id, []) if tuple(c.tokens) != tuple(long_.tokens)}
        d = decide(a, b, ambiguous_with=len(others), ambiguity_names=[c.name for c in others.values()],
                   same_document_rule=same_document_rule)
        if d.kind == "auto" and bool(a.qualifier) != bool(b.qualifier):
            # 'Henric III' equals 'Henric III of Vestland' only if no 'Henric III of <somewhere else>' exists
            bare, qualified = (a, b) if not a.qualifier else (b, a)
            rivals = [c for c in infos.values() if c.qualifier and c.qualifier != qualified.qualifier and c.tokens == bare.tokens
                      and compatible_types(c.type, bare.type)]
            if rivals:
                d = Decision("suggest", 0.6, [f"'{bare.name}' could also be {', '.join(r.name for r in rivals[:3])}"])
        if d.kind != "none":
            out[(x, y)] = d
    return out


# ---------------------------------------------------------------- merging

def _now():
    return datetime.now(timezone.utc)


class MergeError(ValueError):
    """A merge or undo that cannot be done (message is safe to show)"""


def choose_keep(a: EntityInfo, b: EntityInfo) -> tuple[EntityInfo, EntityInfo]:
    """The fuller name survives ('Alan Turing' over 'Turing'), then the one with more facts, then not-all-caps"""
    def rank(e):
        return (len(e.tokens), e.n_facts, not e.name.isupper(), len(e.name))
    return (a, b) if rank(a) >= rank(b) else (b, a)


def _fact_row(f: Fact) -> dict:
    return {"id": f.id, "subject_id": f.subject_id, "predicate": f.predicate, "object_id": f.object_id,
            "object_value": f.object_value, "valid_from": f.valid_from, "valid_to": f.valid_to}


def _same_statement(db: Session, entity_id: str) -> list[list[Fact]]:
    """Groups of the entity's facts that now say the same thing (after a merge brought two copies together)"""
    facts = db.execute(select(Fact).where(or_(Fact.subject_id == entity_id, Fact.object_id == entity_id))).scalars().all()
    groups = defaultdict(list)
    for f in facts:
        groups[(f.subject_id, f.predicate, f.object_id, f.object_value)].append(f)
    return [g for g in groups.values() if len(g) > 1]


def _fold(db: Session, f: Fact, twin: Fact, data: dict) -> None:
    """Fact `f` says what `twin` says: give `twin` f's sources and delete f (remembering both for undo)"""
    moved, dropped = [], []
    for src in list(f.sources):
        clash = db.execute(select(FactSource.id).where(FactSource.fact_id == twin.id, FactSource.chunk_id == src.chunk_id,
                                                       FactSource.evidence == src.evidence)).first()
        if clash:  # the twin already has this exact quote; remember it so undo can put it back
            dropped.append({"id": src.id, "document_id": src.document_id, "chunk_id": src.chunk_id,
                            "evidence": src.evidence, "verified": src.verified})
            continue
        src.fact_id = twin.id
        moved.append(src.id)
    db.flush()
    data["collapsed"].append({"fact": _fact_row(f), "into": twin.id, "source_ids": moved, "dropped_sources": dropped})
    db.expire(f)
    db.execute(delete(Fact).where(Fact.id == f.id))


def merge_entities(db: Session, keep_id: str, absorb_id: str, how: str = "manual", reasons: list | None = None,
                   new_name: str | None = None) -> MergeRecord:
    """Fold `absorb` into `keep`: its facts move over, copies of the same fact become one (sources joined), its name
    becomes an alias. Raises MergeError when the two are linked by a fact or are of different types."""
    if keep_id == absorb_id:
        raise MergeError("Cannot merge an entity with itself")
    keep, absorbed = db.get(Entity, keep_id), db.get(Entity, absorb_id)
    if keep is None or absorbed is None:
        raise MergeError("Entity not found")
    if keep.type != absorbed.type and "concept" not in (keep.type, absorbed.type):
        raise MergeError(f"Different types ({keep.type} / {absorbed.type}); these are probably different things")
    linked = db.execute(select(Fact.id).where(or_(
        (Fact.subject_id == keep.id) & (Fact.object_id == absorbed.id),
        (Fact.subject_id == absorbed.id) & (Fact.object_id == keep.id))).limit(1)).first()
    if linked:
        raise MergeError("A fact links these two entities, so they are probably different things")

    data = {"absorbed": {"id": absorbed.id, "name": absorbed.name, "key": absorbed.key, "type": absorbed.type},
            "keep_before": {"name": keep.name, "type": keep.type},
            "subject_moves": [], "object_moves": [], "collapsed": [], "aliases_added": [], "aliases_moved": []}

    for f in db.execute(select(Fact).where(or_(Fact.subject_id == absorbed.id, Fact.object_id == absorbed.id))).scalars().all():
        new_subject = keep.id if f.subject_id == absorbed.id else f.subject_id
        new_object = keep.id if f.object_id == absorbed.id else f.object_id
        same_object = Fact.object_id.is_(None) if new_object is None else Fact.object_id == new_object
        twin = db.execute(select(Fact).where(Fact.id != f.id, Fact.subject_id == new_subject, Fact.predicate == f.predicate,
                                             Fact.object_value == f.object_value, Fact.valid_from == f.valid_from,
                                             Fact.valid_to == f.valid_to, same_object)).scalars().first()
        if twin is not None:  # keep already has this exact fact: fold this one into it instead of moving it
            _fold(db, f, twin, data)
            continue
        if f.subject_id == absorbed.id:
            data["subject_moves"].append(f.id)
            f.subject_id = keep.id
        if f.object_id == absorbed.id:
            data["object_moves"].append(f.id)
            f.object_id = keep.id
    db.flush()

    for group in _same_statement(db, keep.id):
        # the dated copy wins over an undated one; otherwise the first one stays
        group.sort(key=lambda f: (not (f.valid_from or f.valid_to), f.id))
        survivors: list[Fact] = []
        for f in group:
            twin = next((s for s in survivors if (s.valid_from, s.valid_to) == (f.valid_from, f.valid_to)
                         or not (f.valid_from or f.valid_to)), None)
            if twin is None:
                survivors.append(f)
            else:
                _fold(db, f, twin, data)
    db.flush()

    for alias in db.execute(select(EntityAlias).where(EntityAlias.entity_id == absorbed.id)).scalars():
        data["aliases_moved"].append(alias.id)
        alias.entity_id = keep.id
    db.flush()
    if absorbed.key != keep.key and not db.execute(select(EntityAlias.id).where(EntityAlias.key == absorbed.key)).first():
        alias = EntityAlias(entity_id=keep.id, key=absorbed.key, name=absorbed.name)
        db.add(alias)
        db.flush()
        data["aliases_added"].append(alias.id)
    if keep.type == "concept" and absorbed.type != "concept":
        keep.type = absorbed.type
    if new_name and new_name != keep.name:
        keep.name = new_name

    record = MergeRecord(keep_id=keep.id, absorbed_id=absorbed.id, keep_name=keep.name, absorbed_name=absorbed.name,
                         how=how, reasons=reasons or [], data=data)
    db.add(record)
    db.execute(delete(MergeSuggestion).where(or_(MergeSuggestion.entity_a_id == absorbed.id, MergeSuggestion.entity_b_id == absorbed.id)))
    db.execute(delete(Entity).where(Entity.id == absorbed.id))
    db.flush()
    return record


def undo_merge(db: Session, record_id: str) -> MergeRecord:
    """Give the absorbed entity back its own facts and name. Facts or documents deleted since are simply not restored."""
    record = db.get(MergeRecord, record_id)
    if record is None:
        raise MergeError("Merge not found")
    if record.undone_at is not None:
        raise MergeError("This merge was already undone")
    keep = db.get(Entity, record.keep_id)
    if keep is None:
        raise MergeError("The entity this was merged into no longer exists")
    d = record.data
    a = d["absorbed"]
    if db.get(Entity, a["id"]) is not None or db.execute(select(Entity.id).where(Entity.key == a["key"])).first():
        raise MergeError("An entity with the original name exists again; cannot restore it")
    db.add(Entity(id=a["id"], name=a["name"], key=a["key"], type=a["type"]))
    db.flush()
    for fid in d["subject_moves"]:
        f = db.get(Fact, fid)
        if f is not None and f.subject_id == keep.id:
            f.subject_id = a["id"]
    for fid in d["object_moves"]:
        f = db.get(Fact, fid)
        if f is not None and f.object_id == keep.id:
            f.object_id = a["id"]
    db.flush()
    for c in d["collapsed"]:
        twin = db.get(Fact, c["into"])
        if twin is None:
            continue
        row = dict(c["fact"])
        if row["id"] in d["subject_moves"]:
            row["subject_id"] = a["id"]
        if row["id"] in d["object_moves"]:
            row["object_id"] = a["id"]
        if db.get(Fact, row["id"]) is None:
            db.add(Fact(**row))
            db.flush()
        for sid in c["source_ids"]:
            src = db.get(FactSource, sid)
            if src is not None and src.fact_id == twin.id:
                src.fact_id = row["id"]
        for ds in c.get("dropped_sources", []):
            if db.get(FactSource, ds["id"]) is None and db.get(Chunk, ds["chunk_id"]) is not None:
                db.add(FactSource(fact_id=row["id"], **ds))
    db.flush()
    for aid in d["aliases_moved"]:
        al = db.get(EntityAlias, aid)
        if al is not None:
            al.entity_id = a["id"]
    for aid in d["aliases_added"]:
        al = db.get(EntityAlias, aid)
        if al is not None:
            db.delete(al)
    if d["keep_before"]["name"] != keep.name:
        keep.name = d["keep_before"]["name"]
    keep.type = d["keep_before"]["type"]
    record.undone_at = _now()
    db.flush()
    return record


# ---------------------------------------------------------------- the run

JUDGE_SYSTEM = "You decide whether two names in a knowledge graph refer to the same real-world thing. Use only what is given."
JUDGE_SCHEMA = {"type": "object", "properties": {"same": {"type": "string", "enum": ["yes", "no"]}}, "required": ["same"]}


def _facts_text(db: Session, entity_id: str, limit: int = 5) -> str:
    rows = db.execute(select(Fact).where(or_(Fact.subject_id == entity_id, Fact.object_id == entity_id)).limit(limit)).scalars().all()
    lines = []
    for f in rows:
        obj = f.object.name if f.object else f.object_value
        lines.append(f"- {f.subject.name} {f.predicate} {obj}")
    return "\n".join(lines) or "(no facts)"


def judge_text(llm: LLMClient, a_name: str, a_type: str, a_facts: str, b_name: str, b_type: str, b_facts: str) -> str | None:
    """'yes', 'no', or None when the model could not answer"""
    prompt = (f"Entity 1: {a_name} (type: {a_type})\nWhat is known about it:\n{a_facts}\n\n"
              f"Entity 2: {b_name} (type: {b_type})\nWhat is known about it:\n{b_facts}\n\n"
              "Do Entity 1 and Entity 2 refer to the same real-world thing? Different people, companies or products that "
              "merely share a word are NOT the same. Answer yes or no.")
    try:
        answer = llm.generate_json(JUDGE_SYSTEM, prompt, JUDGE_SCHEMA).get("same")
    except (LLMBadOutput, LLMError):
        return None
    return answer if answer in ("yes", "no") else None


def judge_pair(llm: LLMClient, db: Session, a: Entity, b: Entity) -> str | None:
    return judge_text(llm, a.name, a.type, _facts_text(db, a.id), b.name, b.type, _facts_text(db, b.id))


@dataclass
class RunSummary:
    auto_merged: int = 0
    suggestions_new: int = 0
    suggestions_updated: int = 0
    suggestions_dropped: int = 0
    judged: int = 0
    blocked: int = 0
    merges: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in ("auto_merged", "suggestions_new", "suggestions_updated", "suggestions_dropped",
                                              "judged", "blocked", "merges")}


def run_resolution(db: Session, *, auto: bool = True, llm: LLMClient | None = None) -> RunSummary:
    """Merge the safe pairs, and record the unsure ones as suggestions. Safe to run again at any time."""
    summary = RunSummary()
    for _ in range(10):  # merging can create new safe pairs ("Acme" -> "Acme Corp" -> ...); stop when nothing changes
        infos = load_infos(db)
        rejected = {tuple(sorted((s.entity_a_id, s.entity_b_id))) for s in
                    db.execute(select(MergeSuggestion).where(MergeSuggestion.status == SuggestionStatus.REJECTED)).scalars()}
        decisions = evaluate(infos, rejected)
        summary.blocked = sum(1 for d in decisions.values() if d.kind == "never")
        autos = sorted(((p, d) for p, d in decisions.items() if d.kind == "auto"), key=lambda t: -t[1].score)
        if not auto or not autos:
            break
        changed = False
        for (x, y), d in autos:
            keep, absorb = choose_keep(infos[x], infos[y])
            try:
                rec = merge_entities(db, keep.id, absorb.id, "auto", d.reasons)
            except MergeError:  # one of them was merged away earlier in this pass; the next pass pairs up what is left
                continue
            changed = True
            summary.auto_merged += 1
            summary.merges.append({"id": rec.id, "kept": rec.keep_name, "absorbed": rec.absorbed_name, "reasons": d.reasons})
        if not changed:
            break

    infos = load_infos(db)
    rejected = {tuple(sorted((s.entity_a_id, s.entity_b_id))) for s in
                db.execute(select(MergeSuggestion).where(MergeSuggestion.status == SuggestionStatus.REJECTED)).scalars()}
    decisions = {p: d for p, d in evaluate(infos, rejected).items() if d.kind == "suggest"}
    existing = {(s.entity_a_id, s.entity_b_id): s for s in
                db.execute(select(MergeSuggestion).where(MergeSuggestion.status == SuggestionStatus.PENDING)).scalars()}
    for pair, d in decisions.items():
        score, verdict = d.score, None
        row = existing.get(pair)
        if row is not None and row.llm_verdict:
            verdict = row.llm_verdict  # already asked; do not ask the model again for the same pair
        elif llm is not None:
            verdict = judge_pair(llm, db, db.get(Entity, pair[0]), db.get(Entity, pair[1]))
            summary.judged += 1
        score = apply_verdict(score, verdict)
        if score < MIN_SUGGESTION_SCORE:
            if row is not None:
                db.delete(row)
                existing.pop(pair)
                summary.suggestions_dropped += 1
            continue
        if row is None:
            db.add(MergeSuggestion(entity_a_id=pair[0], entity_b_id=pair[1], score=round(score, 3), reasons=d.reasons, llm_verdict=verdict))
            summary.suggestions_new += 1
        else:
            row.score, row.reasons, row.llm_verdict = round(score, 3), d.reasons, verdict
            summary.suggestions_updated += 1
    for pair, row in list(existing.items()):
        if pair not in decisions:  # no longer a candidate (entity renamed, now linked, ...)
            db.delete(row)
            summary.suggestions_dropped += 1
    db.flush()
    return summary


def accept_suggestion(db: Session, suggestion_id: str, keep_id: str | None = None) -> MergeRecord:
    s = db.get(MergeSuggestion, suggestion_id)
    if s is None:
        raise MergeError("Suggestion not found")
    if s.status != SuggestionStatus.PENDING:
        raise MergeError(f"This suggestion was already {s.status.value}")
    if keep_id not in (None, s.entity_a_id, s.entity_b_id):
        raise MergeError("keep_id must be one of the two entities")
    infos = load_infos(db)
    a, b = infos.get(s.entity_a_id), infos.get(s.entity_b_id)
    if a is None or b is None:
        raise MergeError("One of the entities no longer exists")
    keep, absorb = choose_keep(a, b) if keep_id is None else ((a, b) if keep_id == a.id else (b, a))
    rec = merge_entities(db, keep.id, absorb.id, "suggestion", s.reasons)
    s = db.get(MergeSuggestion, suggestion_id)
    if s is not None:  # the merge deleted suggestions of the absorbed entity, including this one
        s.status, s.decided_at = SuggestionStatus.ACCEPTED, _now()
    return rec


def reject_suggestion(db: Session, suggestion_id: str) -> None:
    s = db.get(MergeSuggestion, suggestion_id)
    if s is None:
        raise MergeError("Suggestion not found")
    if s.status != SuggestionStatus.PENDING:
        raise MergeError(f"This suggestion was already {s.status.value}")
    s.status, s.decided_at = SuggestionStatus.REJECTED, _now()
    db.flush()


def find_by_alias(db: Session, key: str) -> Entity | None:
    row = db.execute(select(EntityAlias).where(EntityAlias.key == key)).scalar_one_or_none()
    return db.get(Entity, row.entity_id) if row else None
