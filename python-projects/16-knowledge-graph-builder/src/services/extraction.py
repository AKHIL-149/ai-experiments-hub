"""Read facts out of a passage with an LLM, then refuse everything the passage does not back up.

The model proposes (subject, predicate, object, dates, quote). Code then checks each proposal:
  * the quote really is in the passage (and is replaced by the exact original text)
  * subject and object really appear in the quote (no pronouns, no invented names)
  * dates really appear in the quote (otherwise the date is dropped, the fact is kept)
  * a word-order check rejects relations written the wrong way round ("Acme founded Maria" for "founded by Maria")
  * an optional second model call confirms the quote supports the statement (catches negations and plans)
"""
import re
from collections import Counter
from dataclasses import dataclass, field

from src.models.graph import ENTITY_TYPES
from src.services.chunker import sentence_spans
from src.services.llm import LLMBadOutput, LLMClient
from src.services.text_utils import core_words, entity_key, locate, name_in_passage, normalize_date, words, words_and_commas

MAX_EVIDENCE_CHARS = 400
MAX_PREDICATE_WORDS = 5
MAX_FACTS_PER_CHUNK = 40

VAGUE_PREDICATES = {
    "is", "are", "was", "were", "be", "has", "have", "had", "related to", "is related to", "relates to",
    "associated with", "is associated with", "mentions", "mentioned", "connected to", "linked to",
}
PRONOUNS = {
    "he", "she", "it", "they", "we", "i", "you", "him", "her", "them", "his", "hers", "their", "its", "this", "that",
    "these", "those", "who", "which", "the company", "the firm", "the organization", "the organisation", "the group",
    "the author", "the man", "the woman",
}

RELATION_SCHEMA = {
    "type": "object",
    "properties": {
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "subject_type": {"type": "string", "enum": list(ENTITY_TYPES)},
                    "predicate": {"type": "string"},
                    "object": {"type": "string"},
                    "object_type": {"type": "string", "enum": list(ENTITY_TYPES) + ["value"]},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                    "evidence": {"type": "string"},
                },
                "required": ["subject", "subject_type", "predicate", "object", "object_type", "start", "end", "evidence"],
            },
        }
    },
    "required": ["relations"],
}

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string", "enum": ["yes", "no"]}},
    "required": ["answer"],
}

EXTRACT_SYSTEM = """You extract facts for a knowledge graph from a passage. Return only facts the passage states.

Rules:
1. One relation per fact. The subject DOES the predicate to the object (active voice). "Acme was founded by Maria" becomes subject Maria, predicate founded, object Acme.
2. Write subject and object exactly as they appear in the passage. Never use a pronoun (he, she, it, they) or a phrase like "the company". If the passage only gives a pronoun, skip that fact.
3. predicate: 1 to 4 lowercase words, a specific verb phrase such as founded, acquired, works at, located in, manufactures, married to. Put a job title in the predicate ("became chief engineer of"), not in the object. Never "is", "has" or "related to".
4. When a sentence links one subject to several objects (or several subjects to one object), give one relation for each pair. Cover every fact between named things: who did what to whom, where things are, what makes or sells what, jobs, memberships, awards, dates and amounts.
5. evidence: copy the shortest exact quote from the passage (one or two sentences, under 400 characters) that states the fact. The quote must contain the subject and the object.
6. start and end: the year or date the passage gives for when the fact began and ended, written as YYYY, YYYY-MM or YYYY-MM-DD. For a one-time event (an acquisition, a founding, a report) put the date in start and leave end empty. "from 2019 to 2022" gives start 2019 and end 2022. "since 2023" gives start 2023. "until 2022" gives end 2022. Leave both empty when the passage gives no date. Never guess a date.
7. Skip anything that is negated ("did not"), only planned or possible ("plans to", "might"), rumoured, or hypothetical.
8. object_type is person, organization, place, product, event or concept. Use value when the object is a plain amount, number or quantity (like 12M or 40 employees).

Example passage:
Lee Park led Foo Labs from 2015 to 2018. Foo Labs, which is based in Oslo, was bought by Quill in 2019. Lee did not join Quill. Kim Soto became chief engineer of Foo Labs in 2016. Foo Labs sells the Gizmo to Quill and to Rho Corp.

Example answer:
{"relations": [
 {"subject": "Lee Park", "subject_type": "person", "predicate": "led", "object": "Foo Labs", "object_type": "organization", "start": "2015", "end": "2018", "evidence": "Lee Park led Foo Labs from 2015 to 2018."},
 {"subject": "Foo Labs", "subject_type": "organization", "predicate": "based in", "object": "Oslo", "object_type": "place", "start": "", "end": "", "evidence": "Foo Labs, which is based in Oslo, was bought by Quill in 2019."},
 {"subject": "Quill", "subject_type": "organization", "predicate": "bought", "object": "Foo Labs", "object_type": "organization", "start": "2019", "end": "", "evidence": "Foo Labs, which is based in Oslo, was bought by Quill in 2019."},
 {"subject": "Kim Soto", "subject_type": "person", "predicate": "became chief engineer of", "object": "Foo Labs", "object_type": "organization", "start": "2016", "end": "", "evidence": "Kim Soto became chief engineer of Foo Labs in 2016."},
 {"subject": "Foo Labs", "subject_type": "organization", "predicate": "sells to", "object": "Quill", "object_type": "organization", "start": "", "end": "", "evidence": "Foo Labs sells the Gizmo to Quill and to Rho Corp."},
 {"subject": "Foo Labs", "subject_type": "organization", "predicate": "sells to", "object": "Rho Corp", "object_type": "organization", "start": "", "end": "", "evidence": "Foo Labs sells the Gizmo to Quill and to Rho Corp."}
]}"""

VERIFY_SYSTEM = "You check claims against a quote. Answer only from the quote."

@dataclass
class ExtractedFact:
    subject: str
    subject_type: str
    predicate: str
    object: str  # entity name, or the plain value when object_type == "value"
    object_type: str
    valid_from: str
    valid_to: str
    evidence: str
    verified: bool = False

    @property
    def key(self):
        return (entity_key(self.subject), self.predicate, entity_key(self.object), self.valid_from, self.valid_to)


@dataclass
class ChunkResult:
    facts: list[ExtractedFact] = field(default_factory=list)
    candidates: int = 0
    rejected: Counter = field(default_factory=Counter)
    adjusted: Counter = field(default_factory=Counter)
    error: str | None = None  # the model failed to give usable output for this chunk (after one retry)


def normalize_predicate(value: str) -> str:
    value = re.sub(r"[^\w\s'-]", " ", (value or "").casefold())
    return re.sub(r"\s+", " ", value).strip()


_AUX = ("was", "were", "is", "are", "been", "be", "being", "had", "has", "have")


def fix_passive(predicate: str) -> tuple[str, bool]:
    """'was founded by' -> ('founded', True): the caller must swap subject and object"""
    ws = predicate.split()
    while len(ws) > 1 and ws[0] in _AUX:
        ws = ws[1:]
    swap = len(ws) > 1 and ws[-1] == "by"
    if swap:
        ws = ws[:-1]
    return " ".join(ws), swap


def widen_quote(chunk: str, start: int, end: int, names: list[str]) -> tuple[int, int] | None:
    """The quote lacks a name (the sentence says 'The company' or 'She'). If the sentence before has it, include that sentence."""
    spans = sentence_spans(chunk)
    idx = next((i for i, (s, e) in enumerate(spans) if s <= start < e), None)
    if idx is None or idx == 0:
        return None
    wide = (spans[idx - 1][0], end)
    quote = chunk[wide[0]:wide[1]]
    if len(quote) <= MAX_EVIDENCE_CHARS and all(name_in_passage(n, quote, chunk) for n in names):
        return wide
    return None


def check_candidate(raw, chunk: str, rejected: Counter, use_context: bool = True,
                    adjusted: Counter | None = None) -> ExtractedFact | None:
    """Turn one model proposal into a checked fact, or return None and count why it was refused.
    Things we repaired but kept (swapped passive, widened quote, dropped a date) are counted in `adjusted`."""
    adjusted = adjusted if adjusted is not None else Counter()
    if not isinstance(raw, dict):
        rejected["malformed"] += 1
        return None
    get = lambda k: str(raw.get(k) or "").strip()  # noqa: E731
    subject, obj, predicate = get("subject"), get("object"), normalize_predicate(get("predicate"))
    if not subject or not obj or not predicate:
        rejected["malformed"] += 1
        return None
    swap = False
    predicate, swap = fix_passive(predicate)
    if len(predicate.split()) > MAX_PREDICATE_WORDS or len(predicate) > 60:
        rejected["predicate_too_long"] += 1
        return None
    if predicate in VAGUE_PREDICATES:
        rejected["vague_predicate"] += 1
        return None
    if entity_key(subject) in PRONOUNS or (get("object_type") != "value" and entity_key(obj) in PRONOUNS):
        rejected["pronoun_or_generic_name"] += 1
        return None
    if len(subject) > 120 or len(obj) > 200:
        rejected["malformed"] += 1
        return None

    is_value = get("object_type") == "value"
    stype_raw, otype_raw = get("subject_type"), get("object_type")
    if swap:
        if is_value:
            rejected["passive_with_value"] += 1
            return None
        subject, obj, stype_raw, otype_raw = obj, subject, otype_raw, stype_raw
        adjusted["passive_swapped"] += 1

    quote = get("evidence")
    if not quote:
        rejected["no_evidence"] += 1
        return None
    span = locate(quote, chunk)
    if span is None:
        rejected["evidence_not_in_text"] += 1
        return None
    evidence = chunk[span[0]:span[1]]
    if len(evidence) > MAX_EVIDENCE_CHARS:
        rejected["evidence_too_long"] += 1
        return None

    names = [subject] + ([] if is_value else [obj])
    if not all(name_in_passage(n, evidence, chunk) for n in names):
        wide = widen_quote(chunk, span[0], span[1], names) if use_context else None
        if wide is None:
            rejected["subject_not_in_evidence" if not name_in_passage(subject, evidence, chunk) else "object_not_in_evidence"] += 1
            return None
        evidence = chunk[wide[0]:wide[1]]
        adjusted["quote_widened_to_previous_sentence"] += 1
    if is_value:
        if entity_key(obj) not in entity_key(evidence):
            rejected["value_not_in_evidence"] += 1
            return None
    elif entity_key(subject) == entity_key(obj):
        rejected["subject_equals_object"] += 1
        return None

    start, end = normalize_date(get("start")), normalize_date(get("end"))
    evidence_words = set(words(evidence))
    for label, value in (("start", start), ("end", end)):
        if value and value[:4] not in evidence_words:
            adjusted["date_dropped_not_in_evidence"] += 1
            if label == "start":
                start = ""
            else:
                end = ""
    if start and end and start > end:
        adjusted["date_dropped_start_after_end"] += 1
        start = end = ""

    stype = stype_raw if stype_raw in ENTITY_TYPES else "concept"
    otype = "value" if is_value else (otype_raw if otype_raw in ENTITY_TYPES else "concept")
    return ExtractedFact(subject, stype, predicate, obj, otype, start, end, evidence)


def _find(ws: list[str], name: str) -> int | None:
    """Word position of the name in the quote (its longest leading run of words that occurs in a row)"""
    core = core_words(name)
    for k in range(len(core), 0, -1):
        part = core[:k]
        for i in range(len(ws) - k + 1):
            if ws[i:i + k] == part:
                return i
    return None


def word_order_ok(subject: str, obj: str, evidence: str) -> bool:
    """Cheap direction check that needs no model, applied to the sentence that holds both names.
    Active wording puts the subject first ("Acme acquired Beta"); passive wording puts the object first and has
    'by' before the subject ("Beta was acquired by Acme"). A claim that fits neither is reversed.
    Returns True when the order fits or cannot be judged."""
    for lo, hi in sentence_spans(evidence):
        ws = words_and_commas(evidence[lo:hi])
        s, o = _find(ws, subject), _find(ws, obj)
        if s is None or o is None or s == o:
            continue
        if s < o:
            # 'Acme was founded by Maria' must not be read as Acme founded Maria: the object sits right after 'by'.
            # (A 'by' that belongs to an inserted clause - 'Acme, founded by Maria, bought Beta' - is not followed by the object.)
            before = [w for w in ws[max(o - 2, 0):o] if w not in ("the", "a", "an")]
            return not (before and before[-1] == "by")
        return "by" in ws[o:s]
    return True


def verify_fact(llm: LLMClient, fact: ExtractedFact) -> str:
    """Second opinion on one fact from the model: 'supported' or 'unsupported' (anything odd counts as unsupported)"""
    prompt = (
        f"Quote: {fact.evidence}\n\n"
        f"Statement: {fact.subject} {fact.predicate} {fact.object}\n\n"
        "Is the statement true according to the quote? It is NOT true if the quote says it the opposite way round, "
        "denies it, or only says it might or will happen. Answer yes or no."
    )
    for attempt in (1, 2):
        try:
            answer = llm.generate_json(VERIFY_SYSTEM, prompt, VERIFY_SCHEMA).get("answer")
            return "supported" if answer == "yes" else "unsupported"
        except LLMBadOutput:
            if attempt == 2:
                return "unsupported"
    return "unsupported"


def _ask(llm: LLMClient, prompt: str) -> tuple[list | None, str | None]:
    """One extraction call (bad JSON is retried once). Returns (raw relations, error message)."""
    err = None
    for _ in (1, 2):
        try:
            data = llm.generate_json(EXTRACT_SYSTEM, prompt, RELATION_SCHEMA)
        except LLMBadOutput as exc:
            err = str(exc)
            continue
        raw = data.get("relations") if isinstance(data, dict) else None
        if isinstance(raw, list):
            return raw, None
        err = "The model answer had no list of relations"
    return None, err


def _found_list(facts: list[ExtractedFact]) -> str:
    return "\n".join(f"- {f.subject} | {f.predicate} | {f.object}" + (f" | {f.valid_from}..{f.valid_to}" if f.valid_from or f.valid_to else "")
                     for f in facts) or "(none)"


def extract_chunk(llm: LLMClient, chunk: str, verify: bool = True, use_context: bool = True,
                  gleaning_passes: int = 0) -> ChunkResult:
    """Extract checked facts from one passage.
    Connection failures raise LLMError; bad output is retried once. A 'gleaning' pass shows the model what it
    found and asks for what it missed (small local models stop early)."""
    result = ChunkResult()
    candidates: list[ExtractedFact] = []
    seen = set()

    def take(raw_list):
        for raw in raw_list:
            result.candidates += 1
            fact = check_candidate(raw, chunk, result.rejected, use_context, result.adjusted)
            if fact is None:
                continue
            if fact.key in seen:
                result.rejected["duplicate_in_chunk"] += 1
                continue
            same = [i for i, c in enumerate(candidates) if c.key[:3] == fact.key[:3]]  # same statement, other dates
            if same:
                dated = bool(fact.valid_from or fact.valid_to)
                undated = [i for i in same if not (candidates[i].valid_from or candidates[i].valid_to)]
                if not dated:
                    result.rejected["duplicate_in_chunk"] += 1  # already have it, with or without dates
                    continue
                if undated:  # the same statement found again, now with its dates: keep the dated one
                    candidates[undated[0]] = fact
                    seen.add(fact.key)
                    result.adjusted["undated_merged_into_dated"] += 1
                    continue
            seen.add(fact.key)
            if len(candidates) >= MAX_FACTS_PER_CHUNK:
                result.rejected["too_many_facts"] += 1
                continue
            candidates.append(fact)

    prompt = f"Passage:\n<<<\n{chunk}\n>>>"
    raw_list, err = _ask(llm, prompt)
    if raw_list is None:
        result.error = err
        return result
    take(raw_list)
    for _ in range(gleaning_passes):
        more, err = _ask(llm, prompt + f"\n\nFacts already found:\n{_found_list(candidates)}\n\n"
                         "Facts are often missed. List ONLY additional facts the passage states that are not in the list above "
                         "(same rules). If nothing is missing, return an empty list.")
        if more is None:  # a failed extra pass costs nothing already found
            result.rejected["gleaning_call_failed"] += 1
            break
        before = len(candidates)
        take(more)
        result.adjusted["found_by_gleaning"] += len(candidates) - before
        if len(candidates) == before:
            break

    for fact in candidates:
        if fact.object_type != "value" and not word_order_ok(fact.subject, fact.object, fact.evidence):
            result.rejected["reversed_word_order"] += 1  # always on: it costs nothing and needs no model
            continue
        if verify:
            if verify_fact(llm, fact) != "supported":
                result.rejected["verify_unsupported"] += 1
                continue
            fact.verified = True
        result.facts.append(fact)
    return result
