"""Export the graph: JSON (everything), CSV (three tables in a zip) and Cypher (a script for Neo4j or any Cypher database).

What is exported is what the app shows: facts left out because a conflict was settled against them are not exported (their count is
reported), and an entity is exported when it takes part in an exported fact. Nothing here talks to a database server; the Cypher
output follows the documented syntax but has not been run against a live Neo4j or Memgraph (see the README).

Shape of the graph in Cypher
  every entity           (:Entity:Person {id, name, type, aliases})          label by type: Person, Organization, Place, ...
  fact about two things  (a)-[:LED {id, predicate, valid_from, valid_to, source_count, evidence, evidence_documents}]->(b)
  fact with a value      (a)-[:EMPLOYS {...}]->(:Value {id, value})          one Value node per fact, so dates and quotes are kept
Dates stay text ("2019", "2019-03"): a period may be only a year, which no Cypher date type can say.
"""
import csv
import io
import json
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.graph import Document, Entity, Fact, FactSource
from src.models.resolution import EntityAlias
from src.services.conflicts import overruled_ids

FORMATS = ("json", "cypher", "csv")
VERSION = 1


@dataclass
class Dataset:
    entities: list[dict] = field(default_factory=list)
    facts: list[dict] = field(default_factory=list)
    left_out: int = 0                       # facts not exported because a settled conflict ruled them out
    document: dict | None = None            # {"id", "title"} when only one document's facts were asked for

    def counts(self) -> dict:
        values = sum(1 for f in self.facts if f["object_is_value"])
        return {"entities": len(self.entities), "facts": len(self.facts), "value_facts": values, "entity_facts": len(self.facts) - values,
                "sources": sum(f["source_count"] for f in self.facts), "left_out": self.left_out}


def collect(db: Session, owner_id: int | None, *, document_id: str | None = None, with_sources: bool = True) -> Dataset:
    """The owner's facts (all, or those read from one document) with their quotes, and the entities in them. Order is fixed
    (by name, then id) so the same graph always exports the same bytes."""
    left_out = overruled_ids(db, owner_id)
    q = select(Fact).where(Fact.owner_id == owner_id)
    if document_id:
        q = q.where(Fact.id.in_(select(FactSource.fact_id).where(FactSource.document_id == document_id)))
    all_facts = list(db.execute(q).scalars())
    facts = [f for f in all_facts if f.id not in left_out]
    ds = Dataset(left_out=len(all_facts) - len(facts))
    if document_id:
        doc = db.get(Document, document_id)
        ds.document = {"id": document_id, "title": doc.title if doc else ""}

    by_fact: dict[str, list[dict]] = {}
    rows = db.execute(select(FactSource, Document.title).join(Document, Document.id == FactSource.document_id)
                      .where(FactSource.fact_id.in_([f.id for f in facts]) if facts else False)).all()
    for s, title in rows:
        if document_id and s.document_id != document_id:
            continue
        by_fact.setdefault(s.fact_id, []).append({"document_id": s.document_id, "document_title": title, "quote": s.evidence, "verified": bool(s.verified)})
    for lst in by_fact.values():
        lst.sort(key=lambda s: (s["document_title"].casefold(), s["document_id"], s["quote"]))

    used: dict[str, Entity] = {}
    for f in facts:
        for e in (f.subject, f.object):
            if e is not None:
                used[e.id] = e
        srcs = by_fact.get(f.id, [])
        d = {"id": f.id, "subject_id": f.subject_id, "subject": f.subject.name, "predicate": f.predicate,
             "object_id": f.object_id, "object": f.object.name if f.object else f.object_value, "object_is_value": f.object_id is None,
             "valid_from": f.valid_from or None, "valid_to": f.valid_to or None, "source_count": len(srcs)}
        if with_sources:
            d["sources"] = srcs
        ds.facts.append(d)
    ds.facts.sort(key=lambda d: (d["subject"].casefold(), d["predicate"].casefold(), str(d["object"]).casefold(), d["id"]))

    aliases: dict[str, list[str]] = {}
    if used:
        for eid, name in db.execute(select(EntityAlias.entity_id, EntityAlias.name).where(EntityAlias.entity_id.in_(list(used)))):
            aliases.setdefault(eid, []).append(name)
    ds.entities = sorted(({"id": e.id, "name": e.name, "type": e.type, "aliases": sorted(set(aliases.get(e.id, [])), key=str.casefold)}
                          for e in used.values()), key=lambda d: (d["name"].casefold(), d["id"]))
    return ds


# ---------------------------------------------------------------- JSON

def to_json(ds: Dataset, now: datetime | None = None) -> str:
    out = {"format": "knowledge-graph-export", "version": VERSION, "exported_at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
           "scope": {"document": ds.document, "left_out_facts": ds.left_out}, "counts": ds.counts(), "entities": ds.entities, "facts": ds.facts}
    return json.dumps(out, ensure_ascii=False, indent=2) + "\n"


# ---------------------------------------------------------------- Cypher

_ESCAPES = {"\\": "\\\\", "'": "\\'", "\n": "\\n", "\r": "\\r", "\t": "\\t", "\b": "\\b", "\f": "\\f"}


def cypher_string(text: str) -> str:
    """A Cypher string literal in single quotes. Backslash, quote and every control character are escaped, so the literal is one
    line and nothing inside it can end the string or the statement."""
    out = []
    for ch in str(text):
        if ch in _ESCAPES:
            out.append(_ESCAPES[ch])
        elif ord(ch) < 0x20 or ord(ch) == 0x7F or unicodedata.category(ch) in ("Zl", "Zp"):
            out.append(f"\\u{ord(ch):04X}")
        else:
            out.append(ch)
    return "'" + "".join(out) + "'"


def cypher_list(items: list[str]) -> str:
    return "[" + ", ".join(cypher_string(i) for i in items) + "]"


def relationship_type(predicate: str) -> str:
    """'was CTO of' -> WAS_CTO_OF. Only A-Z, 0-9 and _ (so it needs no quoting); never empty, never starting with a digit.
    The original wording is kept in the relationship's `predicate` property."""
    ascii_text = unicodedata.normalize("NFKD", predicate).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9]+", "_", ascii_text).strip("_").upper()[:60].strip("_")
    if not t:
        return "RELATED_TO"
    return f"R_{t}" if t[0].isdigit() else t


_TYPE_LABEL = {"person": "Person", "organization": "Organization", "place": "Place", "product": "Product", "event": "Event", "concept": "Concept"}


def to_cypher(ds: Dataset, *, schema: bool = True, now: datetime | None = None) -> str:
    """A script of single-line statements ending in ';' (a statement never spans lines, so a line-by-line loader works too).
    Running it twice changes nothing: nodes and relationships are MERGEd on their id."""
    c = ds.counts()
    when = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    lines = ["// Knowledge Graph Builder export, Cypher", f"// {when}",
             f"// {c['entities']} entities, {c['entity_facts']} facts between entities, {c['value_facts']} facts with a value (Value nodes)",
             "// Safe to run again: everything is MERGEd on its id. Dates are text (a year, a month or a day).",
             "// Not run against a live Neo4j or Memgraph by the tool that wrote it; see the README."]
    if ds.document:
        lines.append(f"// Only facts read from the document: {ds.document['title'].splitlines()[0] if ds.document['title'] else ds.document['id']}")
    if ds.left_out:
        lines.append(f"// {ds.left_out} fact(s) are left out because a settled conflict ruled them out")
    if schema:
        lines += ["CREATE CONSTRAINT kg_entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE;",
                  "CREATE CONSTRAINT kg_value_id IF NOT EXISTS FOR (n:Value) REQUIRE n.id IS UNIQUE;"]
    for e in ds.entities:
        label = _TYPE_LABEL.get(e["type"])
        sets = [f"n.name = {cypher_string(e['name'])}", f"n.type = {cypher_string(e['type'])}"]
        if e["aliases"]:
            sets.append(f"n.aliases = {cypher_list(e['aliases'])}")
        lines.append(f"MERGE (n:Entity {{id: {cypher_string(e['id'])}}}) SET {', '.join(sets)}" + (f", n:{label}" if label else "") + ";")
    for f in ds.facts:
        if f["object_is_value"]:
            lines.append(f"MERGE (n:Value {{id: {cypher_string(f['id'])}}}) SET n.value = {cypher_string(f['object'])};")
    for f in ds.facts:
        target = "Value" if f["object_is_value"] else "Entity"
        target_id = f["id"] if f["object_is_value"] else f["object_id"]
        sets = [f"r.predicate = {cypher_string(f['predicate'])}", f"r.source_count = {f['source_count']}"]
        for key in ("valid_from", "valid_to"):
            if f[key]:
                sets.append(f"r.{key} = {cypher_string(f[key])}")
        if f.get("sources"):
            sets.append(f"r.evidence = {cypher_list([s['quote'] for s in f['sources']])}")
            sets.append(f"r.evidence_documents = {cypher_list([s['document_title'] for s in f['sources']])}")
        lines.append(f"MATCH (a:Entity {{id: {cypher_string(f['subject_id'])}}}), (b:{target} {{id: {cypher_string(target_id)}}}) "
                     f"MERGE (a)-[r:{relationship_type(f['predicate'])} {{id: {cypher_string(f['id'])}}}]->(b) SET {', '.join(sets)};")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- CSV

def csv_cell(value) -> str:
    """A cell that a spreadsheet will not run as a formula: documents are uploaded text, and a quote that starts with = + - or @
    would be executed by Excel or Sheets. Such a cell gets a leading apostrophe (the usual guard), so it opens as plain text."""
    s = "" if value is None else str(value)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def _csv(header: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)                 # rows end in \r\n, as spreadsheets expect
    w.writerow(header)
    for r in rows:
        w.writerow([csv_cell(v) for v in r])
    return buf.getvalue().encode("utf-8-sig")        # a BOM so Excel reads the accents


CSV_README = """Knowledge Graph Builder export (CSV)

entities.csv   one row per entity: id, name, type, aliases (other names, separated by " | ")
facts.csv      one row per fact: id, subject_id, subject, predicate, object_id, object, object_is_value (true when the object is a plain
               value such as "340 people" and object_id is empty), valid_from, valid_to (text: a year, a month or a day), source_count
sources.csv    one row per quote: fact_id, document_id, document_title, quote, verified (true when the second check confirmed it)

Cells that begin with = + - or @ start with an apostrophe so a spreadsheet does not run them as a formula. Remove it if you load the
files into something else. Facts left out because a settled conflict ruled them out are not exported.
"""


def to_csv_zip(ds: Dataset) -> bytes:
    entities = _csv(["id", "name", "type", "aliases"], [[e["id"], e["name"], e["type"], " | ".join(e["aliases"])] for e in ds.entities])
    facts = _csv(["id", "subject_id", "subject", "predicate", "object_id", "object", "object_is_value", "valid_from", "valid_to", "source_count"],
                 [[f["id"], f["subject_id"], f["subject"], f["predicate"], f["object_id"], f["object"], str(f["object_is_value"]).lower(),
                   f["valid_from"], f["valid_to"], f["source_count"]] for f in ds.facts])
    sources = _csv(["fact_id", "document_id", "document_title", "quote", "verified"],
                   [[f["id"], s["document_id"], s["document_title"], s["quote"], str(s["verified"]).lower()] for f in ds.facts for s in f.get("sources", [])])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in (("README.txt", CSV_README.encode()), ("entities.csv", entities), ("facts.csv", facts), ("sources.csv", sources)):
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))     # fixed time: the same graph gives the same bytes
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    return buf.getvalue()


# ---------------------------------------------------------------- one entry point

MEDIA = {"json": ("application/json", "json"), "cypher": ("text/plain; charset=utf-8", "cypher"), "csv": ("application/zip", "zip")}


def render(ds: Dataset, fmt: str, *, schema: bool = True, now: datetime | None = None) -> bytes:
    if fmt == "json":
        return to_json(ds, now).encode("utf-8")
    if fmt == "cypher":
        return to_cypher(ds, schema=schema, now=now).encode("utf-8")
    if fmt == "csv":
        return to_csv_zip(ds)
    raise ValueError(f"Unknown format {fmt!r}. Use one of: {', '.join(FORMATS)}")


def file_name(fmt: str, document_title: str | None = None) -> str:
    """knowledge-graph.json, or knowledge-graph-<document>.json: ASCII only, safe in a header"""
    base = "knowledge-graph"
    if document_title:
        slug = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", document_title).encode("ascii", "ignore").decode().lower()).strip("-")[:40].strip("-")
        if slug:
            base += f"-{slug}"
    return f"{base}.{MEDIA[fmt][1]}"
