"""Export: what is in it, that nothing is lost or invented, and that no text in a document can break out of a file.

There is no Neo4j here, so the Cypher script is checked by reading it back with a small reader that understands only the statement
shapes the exporter writes. That proves the script is well formed in those shapes and that every value survives its escaping. It does
not prove that a real database accepts it."""
import csv
import io
import json
import re
import zipfile
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.core.database import get_db
from src.models.resolution import EntityAlias
from src.services import conflicts as cf
from src.services import export as ex
from src.services.text_utils import entity_key

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


# ---------------------------------------------------------------- a small reader for the Cypher the exporter writes

_STR = r"'(?:[^'\\]|\\.)*'"
_UNESC = {"\\": "\\", "'": "'", "n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f"}


def unquote(lit: str) -> str:
    assert lit[0] == lit[-1] == "'", lit
    out, i, body = [], 0, lit[1:-1]
    while i < len(body):
        ch = body[i]
        if ch == "\\":
            nxt = body[i + 1]
            if nxt == "u":
                out.append(chr(int(body[i + 2:i + 6], 16)))
                i += 6
                continue
            out.append(_UNESC[nxt])           # a KeyError here means an escape Cypher does not have
            i += 2
            continue
        assert ch != "'", f"an unescaped quote inside {lit!r}"
        out.append(ch)
        i += 1
    return "".join(out)


def value(src: str, i: int = 0):
    """One literal (string, integer or list of strings) starting at src[i]; returns (value, next index)"""
    if src[i] == "'":
        m = re.compile(_STR).match(src, i)
        return unquote(m.group()), m.end()
    if src[i] == "[":
        items, i = [], i + 1
        while src[i] != "]":
            v, i = value(src, i)
            items.append(v)
            if src[i] == ",":
                i += 2
        return items, i + 1
    m = re.compile(r"\d+").match(src, i)
    return int(m.group()), m.end()


def assignments(text: str, var: str):
    """`n.name = 'x', n.aliases = ['a'], n:Person` -> ({'name': 'x', 'aliases': ['a']}, ['Person'])"""
    props, labels, i = {}, [], 0
    while i < len(text):
        m = re.compile(rf"{var}\.(\w+) = ").match(text, i)
        if m:
            v, i = value(text, m.end())
            props[m.group(1)] = v
        else:
            m = re.compile(rf"{var}:(\w+)").match(text, i)
            assert m, f"cannot read {text[i:i + 40]!r}"
            labels.append(m.group(1))
            i = m.end()
        if i < len(text):
            assert text[i:i + 2] == ", ", text[i:i + 10]
            i += 2
    return props, labels


S = _STR
NODE = re.compile(rf"^MERGE \(n:(Entity|Value) \{{id: ({S})\}}\) SET (.+);$")
REL = re.compile(rf"^MATCH \(a:Entity \{{id: ({S})\}}\), \(b:(Entity|Value) \{{id: ({S})\}}\) MERGE \(a\)-\[r:([A-Z][A-Z0-9_]*) \{{id: ({S})\}}\]->\(b\) SET (.+);$")
SCHEMA = re.compile(r"^CREATE CONSTRAINT \w+ IF NOT EXISTS FOR \(n:(Entity|Value)\) REQUIRE n\.id IS UNIQUE;$")


class Db:
    """What running the script builds: nodes by (label, id) and relationships by id"""

    def __init__(self):
        self.nodes, self.rels, self.constraints = {}, {}, []

    def run(self, script: str):
        for line in script.splitlines():
            if not line or line.startswith("//"):
                continue
            if m := SCHEMA.match(line):
                self.constraints.append(m.group(1))
            elif m := NODE.match(line):
                nid = unquote(m.group(2))
                props, labels = assignments(m.group(3), "n")
                node = self.nodes.setdefault((m.group(1), nid), {"labels": {m.group(1)}, "props": {"id": nid}})
                node["props"].update(props)
                node["labels"] |= set(labels)
            elif m := REL.match(line):
                a, b, rid = unquote(m.group(1)), unquote(m.group(3)), unquote(m.group(5))
                assert ("Entity", a) in self.nodes and (m.group(2), b) in self.nodes, "a relationship to a node that was not created first"
                props, _ = assignments(m.group(6), "r")
                rel = self.rels.setdefault(rid, {"from": a, "to": b, "type": m.group(4), "props": {"id": rid}})
                assert (rel["from"], rel["to"], rel["type"]) == (a, b, m.group(4))
                rel["props"].update(props)
            else:
                raise AssertionError(f"not a statement the exporter writes: {line[:120]!r}")
        return self


# ---------------------------------------------------------------- a graph with every awkward case

TRICKY_NAME = "O'Brien & \"Sons\"; Ltd \\ Co"
TRICKY_QUOTE = "He said: it's \"fine\"\nline two\tTabbed \\n not a newline; // not a comment ' ] }"


@pytest.fixture
def rich(world):
    w, db = world, world.db
    w.acme, w.beta = w.ent("Acme Corp"), w.ent(TRICKY_NAME)
    w.zur, w.dana = w.ent("Zürich 日本", "place"), w.ent("Dana Reyes", "person")
    w.f1 = w.fact(w.acme, "acquired", w.beta, frm="2020-03", quote=TRICKY_QUOTE, title="News", verified=True)
    w.f2 = w.fact(w.dana, "was CTO of", w.acme, frm="2012", to="2019", title="History")
    w.f3 = w.fact(w.acme, "employs", value="340 people", title="News")
    w.f4 = w.fact(w.acme, "headquartered in", w.zur, title="News")
    w.f5 = w.fact(w.dana, "是", w.zur, title="History")                           # a predicate with nothing Cypher can use as a type
    w.f6 = w.fact(w.acme, "notes", value="=HYPERLINK(\"http://evil.example\",\"x\")", quote="=cmd|' /C calc'!A0", title="News")
    db.add(EntityAlias(entity_id=w.acme.id, key=entity_key("Acme Inc."), name="Acme Inc."))     # added out of order: the export sorts them
    db.add(EntityAlias(entity_id=w.acme.id, key=entity_key("ACME"), name="ACME"))
    db.commit()
    return w


def facts_by_id(ds):
    return {f["id"]: f for f in ds.facts}


# ---------------------------------------------------------------- what is collected

def test_collects_every_fact_with_its_quotes_and_only_the_entities_in_them(rich, db):
    ds = ex.collect(db, None)
    assert len(ds.facts) == 6 and ds.left_out == 0
    assert {e["name"] for e in ds.entities} == {"Acme Corp", TRICKY_NAME, "Zürich 日本", "Dana Reyes"}
    f = facts_by_id(ds)[rich.f1.id]
    assert f["subject"] == "Acme Corp" and f["object"] == TRICKY_NAME and f["object_id"] == rich.beta.id and not f["object_is_value"]
    assert f["valid_from"] == "2020-03" and f["valid_to"] is None and f["source_count"] == 1
    assert f["sources"] == [{"document_id": rich.docs["News"][0], "document_title": "News", "quote": TRICKY_QUOTE, "verified": True}]
    v = facts_by_id(ds)[rich.f3.id]
    assert v["object_is_value"] and v["object"] == "340 people" and v["object_id"] is None


def test_aliases_come_with_their_entity_sorted_and_each_entity_is_listed_once(rich, db):
    ds = ex.collect(db, None)
    acme = [e for e in ds.entities if e["id"] == rich.acme.id]
    assert len(acme) == 1 and acme[0]["aliases"] == ["ACME", "Acme Inc."]
    assert [e["aliases"] for e in ds.entities if e["id"] != rich.acme.id] == [[], [], []]


def test_an_entity_with_no_exported_fact_is_not_exported(rich, db):
    rich.ent("Lonely Co")
    db.commit()
    assert "Lonely Co" not in {e["name"] for e in ex.collect(db, None).entities}


def test_the_same_graph_always_exports_the_same_bytes(rich, db):
    a, b = ex.collect(db, None), ex.collect(db, None)
    assert ex.render(a, "json", now=NOW) == ex.render(b, "json", now=NOW)
    assert ex.render(a, "cypher", now=NOW) == ex.render(b, "cypher", now=NOW)
    assert ex.render(a, "csv") == ex.render(b, "csv")
    names = [e["name"].casefold() for e in a.entities]
    assert names == sorted(names)
    keys = [(f["subject"].casefold(), f["predicate"].casefold()) for f in a.facts]
    assert keys == sorted(keys)


def test_one_documents_facts_and_only_its_quotes(rich, db):
    news = rich.docs["News"][0]
    ds = ex.collect(db, None, document_id=news)
    assert ds.document == {"id": news, "title": "News"}
    assert {f["id"] for f in ds.facts} == {rich.f1.id, rich.f3.id, rich.f4.id, rich.f6.id}
    assert all(s["document_id"] == news for f in ds.facts for s in f["sources"])
    assert "Dana Reyes" not in {e["name"] for e in ds.entities}           # only in the other document's facts


def test_a_fact_read_from_two_documents_keeps_only_the_chosen_documents_quote_when_scoped(rich, db):
    from src.models.graph import FactSource
    hist_doc, hist_chunk = rich.docs["History"]
    db.add(FactSource(fact_id=rich.f1.id, document_id=hist_doc, chunk_id=hist_chunk, evidence="Also in history"))
    db.commit()
    whole = facts_by_id(ex.collect(db, None))[rich.f1.id]
    assert whole["source_count"] == 2 and {s["document_title"] for s in whole["sources"]} == {"News", "History"}
    scoped = facts_by_id(ex.collect(db, None, document_id=rich.docs["News"][0]))[rich.f1.id]
    assert scoped["source_count"] == 1 and [s["quote"] for s in scoped["sources"]] == [TRICKY_QUOTE]


def test_quotes_come_in_a_fixed_order_by_document_title_then_text(world, db):
    from src.models.graph import FactSource
    w = world
    a, b = w.ent("Acme"), w.ent("Beta")
    f = w.fact(a, "acquired", b, quote="Zulu quote", title="Zeta")
    for title, quote in (("alpha", "Second quote"), ("alpha", "First quote"), ("Mid", "Mid quote")):
        did, cid = w.new_doc(title)
        db.add(FactSource(fact_id=f.id, document_id=did, chunk_id=cid, evidence=quote))
    db.commit()
    got = facts_by_id(ex.collect(db, None))[f.id]
    assert [(s["document_title"], s["quote"]) for s in got["sources"]] == [("alpha", "First quote"), ("alpha", "Second quote"), ("Mid", "Mid quote"), ("Zeta", "Zulu quote")]
    assert got["source_count"] == 4 and ex.collect(db, None).counts()["sources"] == 4


def test_aliases_are_sorted_ignoring_case(world, db):
    w = world
    a, b = w.ent("Acme"), w.ent("Beta")
    w.fact(a, "acquired", b)
    for name in ("Beta Co", "acme co", "Cee"):
        db.add(EntityAlias(entity_id=a.id, key=entity_key(name), name=name))
    db.commit()
    assert next(e for e in ex.collect(db, None).entities if e["id"] == a.id)["aliases"] == ["acme co", "Beta Co", "Cee"]


def test_without_sources_the_quotes_are_left_out_but_the_count_stays(rich, db):
    ds = ex.collect(db, None, with_sources=False)
    assert all("sources" not in f for f in ds.facts) and facts_by_id(ds)[rich.f1.id]["source_count"] == 1
    assert "evidence" not in ex.to_cypher(ds, now=NOW) and TRICKY_QUOTE not in ex.to_json(ds, NOW)
    z = zipfile.ZipFile(io.BytesIO(ex.to_csv_zip(ds)))
    assert z.read("sources.csv").decode("utf-8-sig").strip() == "fact_id,document_id,document_title,quote,verified"


def test_a_fact_ruled_out_by_a_settled_conflict_is_not_exported_and_is_counted(world, db):
    w = world
    q, d1, d2 = w.ent("Quillon Systems"), w.ent("Dunmere", "place"), w.ent("Valcross", "place")
    a = w.fact(q, "headquartered in", d1, frm="2004", to="2012")
    b = w.fact(q, "headquartered in", d2, frm="2010", to="2015")
    db.commit()
    cf.run_detection(db, owner_id=None)
    db.commit()
    conflict = db.query(cf.Conflict).one()
    keep = "keep_a" if conflict.fact_a_id == a.id else "keep_b"       # trust Dunmere: Valcross is left out
    cf.resolve(db, conflict.id, keep)
    db.commit()
    ds = ex.collect(db, None)
    assert [f["id"] for f in ds.facts] == [a.id] and ds.left_out == 1
    assert "Valcross" not in {e["name"] for e in ds.entities}
    assert "1 fact(s) are left out" in ex.to_cypher(ds, now=NOW) and json.loads(ex.to_json(ds, NOW))["scope"]["left_out_facts"] == 1
    cf.reopen(db, conflict.id)
    db.commit()
    assert len(ex.collect(db, None).facts) == 2 and ex.collect(db, None).left_out == 0     # undoing the choice puts it back


def test_an_empty_graph_exports_valid_empty_files(db):
    ds = ex.collect(db, None)
    assert json.loads(ex.to_json(ds, NOW))["counts"] == {"entities": 0, "facts": 0, "value_facts": 0, "entity_facts": 0, "sources": 0, "left_out": 0}
    assert Db().run(ex.to_cypher(ds, now=NOW)).nodes == {}
    assert zipfile.ZipFile(io.BytesIO(ex.to_csv_zip(ds))).namelist() == ["README.txt", "entities.csv", "facts.csv", "sources.csv"]


def test_counts(rich, db):
    c = ex.collect(db, None).counts()
    assert c == {"entities": 4, "facts": 6, "value_facts": 2, "entity_facts": 4, "sources": 6, "left_out": 0}


# ---------------------------------------------------------------- JSON

def test_json_holds_everything_and_keeps_unicode_readable(rich, db):
    raw = ex.to_json(ex.collect(db, None), NOW)
    assert "Zürich 日本" in raw and "\\u" not in raw                       # not escaped to \uXXXX
    j = json.loads(raw)
    assert j["format"] == "knowledge-graph-export" and j["version"] == 1 and j["exported_at"] == "2026-01-02T03:04:05+00:00"
    assert j["scope"] == {"document": None, "left_out_facts": 0}
    assert len(j["entities"]) == 4 and len(j["facts"]) == 6 and j["counts"]["facts"] == 6
    f = next(f for f in j["facts"] if f["id"] == rich.f1.id)
    assert f["sources"][0]["quote"] == TRICKY_QUOTE and f["valid_from"] == "2020-03" and f["valid_to"] is None
    assert next(e for e in j["entities"] if e["id"] == rich.acme.id)["aliases"] == ["ACME", "Acme Inc."]


def test_render_passes_the_time_and_the_schema_choice_through(rich, db):
    ds = ex.collect(db, None)
    assert json.loads(ex.render(ds, "json", now=NOW))["exported_at"] == "2026-01-02T03:04:05+00:00"
    cy = ex.render(ds, "cypher", now=NOW).decode()
    assert "// 2026-01-02T03:04:05+00:00" in cy and "CONSTRAINT" in cy
    assert "CONSTRAINT" not in ex.render(ds, "cypher", schema=False, now=NOW).decode()


def test_json_names_the_document_when_scoped(rich, db):
    j = json.loads(ex.to_json(ex.collect(db, None, document_id=rich.docs["News"][0]), NOW))
    assert j["scope"]["document"] == {"id": rich.docs["News"][0], "title": "News"}


# ---------------------------------------------------------------- Cypher text

@pytest.mark.parametrize("text", ["plain", "", "it's", "back\\slash", "new\nline", "carriage\rreturn", "tab\there", "\x00\x1f\x7f", "a b c",
                                   "emoji 😀", "quote \" double", "end with backslash\\", "\\'", "'; MATCH (n) DETACH DELETE n; //"])
def test_every_string_survives_escaping_and_stays_on_one_line(text):
    lit = ex.cypher_string(text)
    assert unquote(lit) == text
    assert "\n" not in lit and "\r" not in lit and " " not in lit and " " not in lit
    assert re.fullmatch(_STR, lit)                    # the literal is one string: nothing inside can end it early
    assert not any(ord(c) < 0x20 or ord(c) == 0x7F for c in lit), "a raw control character is left in the literal"


def test_the_usual_escapes_are_the_readable_ones_and_the_rest_are_uppercase_unicode_escapes():
    assert ex.cypher_string("a\nb\rc\td\be\ff\\g'h") == "'a\\nb\\rc\\td\\be\\ff\\\\g\\'h'"
    assert ex.cypher_string("\x01\x1f\x7f\u2028") == "'\\u0001\\u001F\\u007F\\u2028'"
    assert ex.cypher_string("é日😀") == "'é日😀'"                # readable text is left as it is


def test_a_hostile_quote_cannot_add_a_statement(rich, db):
    ds = ex.collect(db, None)
    ds.facts[0]["sources"] = [{"document_id": "d", "document_title": "t", "quote": "x'}) DETACH DELETE n; MATCH (m) RETURN m //", "verified": False}]
    script = ex.to_cypher(ds, now=NOW)
    statements = [ln for ln in script.splitlines() if ln and not ln.startswith("//")]
    assert all(NODE.match(s) or REL.match(s) or SCHEMA.match(s) for s in statements)
    assert not any(s.startswith("MATCH (m)") or "DETACH" in s.split("'")[0] for s in statements)
    Db().run(script)


@pytest.mark.parametrize("predicate,expected", [
    ("acquired", "ACQUIRED"), ("was CTO of", "WAS_CTO_OF"), ("  led  ", "LED"), ("headquartered in", "HEADQUARTERED_IN"), ("is-a/part of", "IS_A_PART_OF"),
    ("2nd owner of", "R_2ND_OWNER_OF"), ("café of", "CAFE_OF"), ("是", "RELATED_TO"), ("", "RELATED_TO"), ("!!!", "RELATED_TO"),
    ("x" * 100, "X" * 60), ("!" + "x" * 60, "X" * 60), ("a" * 58 + " b", "A" * 58 + "_B"), ("a" * 59 + " b", "A" * 59), ("(a)-[:B]->(c) DELETE", "A_B_C_DELETE"),
])
def test_relationship_types(predicate, expected):
    t = ex.relationship_type(predicate)
    assert t == expected and re.fullmatch(r"[A-Z][A-Z0-9_]*", t)


def test_header_says_what_it_is_and_that_it_was_not_run_on_a_database(rich, db):
    head = [ln for ln in ex.to_cypher(ex.collect(db, None), now=NOW).splitlines() if ln.startswith("//")]
    assert head[0] == "// Knowledge Graph Builder export, Cypher" and head[1] == "// 2026-01-02T03:04:05+00:00"
    assert "4 entities, 4 facts between entities, 2 facts with a value" in head[2]
    assert any("Not run against a live Neo4j or Memgraph" in ln for ln in head) and any("Safe to run again" in ln for ln in head)


def test_a_document_title_cannot_break_out_of_the_header_comment(rich, db):
    ds = ex.collect(db, None, document_id=rich.docs["News"][0])
    ds.document["title"] = "Report\nMATCH (n) DETACH DELETE n;"
    script = ex.to_cypher(ds, now=NOW)
    assert not any(ln.startswith("MATCH (n) DETACH") for ln in script.splitlines())
    ds.document["title"] = "Report MATCH (n) DETACH DELETE n;"
    assert not any("DETACH" in ln and not ln.startswith("//") for ln in ex.to_cypher(ds, now=NOW).splitlines())


# ---------------------------------------------------------------- Cypher, read back

def test_the_script_rebuilds_the_graph_exactly(rich, db):
    ds = ex.collect(db, None)
    g = Db().run(ex.to_cypher(ds, now=NOW))
    assert g.constraints == ["Entity", "Value"]
    ents = {k[1]: n for k, n in g.nodes.items() if k[0] == "Entity"}
    assert set(ents) == {e["id"] for e in ds.entities}
    for e in ds.entities:
        n = ents[e["id"]]
        assert n["props"]["name"] == e["name"] and n["props"]["type"] == e["type"] and n["props"].get("aliases", []) == e["aliases"]
        assert n["labels"] == {"Entity", e["type"].capitalize()}
    assert "aliases" not in ents[rich.dana.id]["props"]                  # none to write
    assert len(g.rels) == 6
    for f in ds.facts:
        r = g.rels[f["id"]]
        assert r["from"] == f["subject_id"] and r["props"]["predicate"] == f["predicate"] and r["props"]["source_count"] == f["source_count"]
        assert r["props"].get("valid_from") == f["valid_from"] and r["props"].get("valid_to") == f["valid_to"]
        assert r["props"]["evidence"] == [s["quote"] for s in f["sources"]] and r["props"]["evidence_documents"] == [s["document_title"] for s in f["sources"]]
        if f["object_is_value"]:
            assert r["to"] == f["id"] and g.nodes[("Value", f["id"])]["props"]["value"] == f["object"]
        else:
            assert r["to"] == f["object_id"]
    assert g.rels[rich.f2.id]["type"] == "WAS_CTO_OF" and g.rels[rich.f5.id]["type"] == "RELATED_TO"
    assert g.rels[rich.f5.id]["props"]["predicate"] == "是"            # the original wording is never lost


def test_dates_that_are_not_stated_are_left_out_not_written_as_empty(rich, db):
    g = Db().run(ex.to_cypher(ex.collect(db, None), now=NOW))
    r = g.rels[rich.f3.id]["props"]
    assert "valid_from" not in r and "valid_to" not in r
    assert g.rels[rich.f2.id]["props"]["valid_from"] == "2012" and g.rels[rich.f2.id]["props"]["valid_to"] == "2019"


def test_running_the_script_twice_changes_nothing(rich, db):
    script = ex.to_cypher(ex.collect(db, None), now=NOW)
    once = Db().run(script)
    twice = Db().run(script).run(script)
    assert once.nodes == twice.nodes and once.rels == twice.rels


def test_every_statement_is_one_line_ending_in_a_semicolon(rich, db):
    script = ex.to_cypher(ex.collect(db, None), now=NOW)
    for ln in script.splitlines():
        assert ln.startswith("//") or ln.endswith(";")
    assert script.endswith(";\n") and "\r" not in script
    assert sum(1 for ln in script.splitlines() if not ln.startswith("//")) == 2 + 4 + 2 + 6       # constraints, entities, value nodes, relationships


def test_nodes_are_created_before_the_relationships_that_need_them(rich, db):
    lines = [ln for ln in ex.to_cypher(ex.collect(db, None), now=NOW).splitlines() if not ln.startswith("//")]
    last_node = max(i for i, ln in enumerate(lines) if ln.startswith("MERGE"))
    first_rel = min(i for i, ln in enumerate(lines) if ln.startswith("MATCH"))
    assert last_node < first_rel


def test_without_the_schema_there_are_no_constraint_statements(rich, db):
    script = ex.to_cypher(ex.collect(db, None), schema=False, now=NOW)
    assert "CONSTRAINT" not in script and Db().run(script).constraints == []
    assert "CONSTRAINT" in ex.to_cypher(ex.collect(db, None), now=NOW)


def test_value_facts_with_the_same_text_stay_separate_nodes(world, db):
    w = world
    a, b = w.ent("Acme"), w.ent("Beta")
    f1, f2 = w.fact(a, "employs", value="40 people"), w.fact(b, "employs", value="40 people")
    db.commit()
    g = Db().run(ex.to_cypher(ex.collect(db, None), now=NOW))
    assert g.nodes[("Value", f1.id)]["props"]["value"] == g.nodes[("Value", f2.id)]["props"]["value"] == "40 people"
    assert g.rels[f1.id]["to"] != g.rels[f2.id]["to"]


def test_types_without_a_label_still_export(world, db):
    w = world
    a, b = w.ent("Acme"), w.ent("Gadget", "gizmo")
    w.fact(a, "makes", b)
    db.commit()
    g = Db().run(ex.to_cypher(ex.collect(db, None), now=NOW))
    node = next(n for k, n in g.nodes.items() if n["props"].get("name") == "Gadget")
    assert node["labels"] == {"Entity"} and node["props"]["type"] == "gizmo"


# ---------------------------------------------------------------- CSV

def unzip(data: bytes) -> dict[str, bytes]:
    z = zipfile.ZipFile(io.BytesIO(data))
    assert z.testzip() is None
    return {n: z.read(n) for n in z.namelist()}


def table(raw: bytes):
    assert raw.startswith(b"\xef\xbb\xbf")                                  # a BOM, so Excel reads the accents
    return list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline="")))


def test_csv_is_three_tables_and_a_readme(rich, db):
    files = unzip(ex.to_csv_zip(ex.collect(db, None)))
    assert list(files) == ["README.txt", "entities.csv", "facts.csv", "sources.csv"]
    ents, facts, srcs = table(files["entities.csv"]), table(files["facts.csv"]), table(files["sources.csv"])
    assert ents[0] == ["id", "name", "type", "aliases"] and len(ents) == 5
    assert facts[0] == ["id", "subject_id", "subject", "predicate", "object_id", "object", "object_is_value", "valid_from", "valid_to", "source_count"]
    assert len(facts) == 7 and srcs[0] == ["fact_id", "document_id", "document_title", "quote", "verified"] and len(srcs) == 7
    acme = next(r for r in ents if r[0] == rich.acme.id)
    assert acme[1:] == ["Acme Corp", "organization", "ACME | Acme Inc."]
    f1 = next(r for r in facts if r[0] == rich.f1.id)
    assert f1[2:] == ["Acme Corp", "acquired", rich.beta.id, TRICKY_NAME, "false", "2020-03", "", "1"]
    val = next(r for r in facts if r[0] == rich.f3.id)
    assert val[4] == "" and val[5] == "340 people" and val[6] == "true"
    q = next(r for r in srcs if r[0] == rich.f1.id)
    assert q[3] == TRICKY_QUOTE and q[4] == "true"                          # commas, quotes and newlines survive the CSV quoting


def test_a_cell_that_would_run_as_a_spreadsheet_formula_is_defused(rich, db):
    files = unzip(ex.to_csv_zip(ex.collect(db, None)))
    facts, srcs = table(files["facts.csv"]), table(files["sources.csv"])
    val = next(r for r in facts if r[0] == rich.f6.id)
    assert val[5].startswith("'=HYPERLINK(")
    assert next(r for r in srcs if r[0] == rich.f6.id)[3] == "'=cmd|' /C calc'!A0"
    for name in ("entities.csv", "facts.csv", "sources.csv"):
        for row in table(files[name]):
            assert not any(c[:1] in ("=", "+", "-", "@") for c in row), (name, row)


@pytest.mark.parametrize("cell,expected", [("=1+1", "'=1+1"), ("+1", "'+1"), ("-1", "'-1"), ("@SUM(A1)", "'@SUM(A1)"), ("\tx", "'\tx"), ("\rx", "'\rx"),
                                           ("safe", "safe"), ("", ""), (None, ""), (5, "5"), ("a=b", "a=b"), (" =x", " =x")])
def test_csv_cell_guard(cell, expected):
    assert ex.csv_cell(cell) == expected


def test_csv_dates_are_text_not_numbers(rich, db):
    facts = table(unzip(ex.to_csv_zip(ex.collect(db, None)))["facts.csv"])
    f2 = next(r for r in facts if r[0] == rich.f2.id)
    assert f2[7:9] == ["2012", "2019"]


def test_the_zip_has_a_fixed_time_and_is_compressed(rich, db):
    z = zipfile.ZipFile(io.BytesIO(ex.to_csv_zip(ex.collect(db, None))))
    assert {i.date_time for i in z.infolist()} == {(2020, 1, 1, 0, 0, 0)}
    assert {i.compress_type for i in z.infolist()} == {zipfile.ZIP_DEFLATED}


def test_csv_rows_end_in_crlf(rich, db):
    raw = zipfile.ZipFile(io.BytesIO(ex.to_csv_zip(ex.collect(db, None)))).read("entities.csv")
    assert raw.endswith(b"\r\n") and raw.count(b"\r\n") == 5


def test_the_readme_in_the_zip_matches_the_columns(rich, db):
    readme = unzip(ex.to_csv_zip(ex.collect(db, None)))["README.txt"].decode()
    for col in ("object_is_value", "source_count", "verified", "aliases"):
        assert col in readme
    assert "apostrophe" in readme


# ---------------------------------------------------------------- file names

@pytest.mark.parametrize("fmt,title,expected", [
    ("json", None, "knowledge-graph.json"), ("cypher", None, "knowledge-graph.cypher"), ("csv", None, "knowledge-graph.zip"),
    ("json", "Q3 Report (final)", "knowledge-graph-q3-report-final.json"), ("json", "(Final) Report", "knowledge-graph-final-report.json"), ("json", "(" + "a" * 40, "knowledge-graph-" + "a" * 40 + ".json"),
    ("json", "a" * 39 + " b", "knowledge-graph-" + "a" * 39 + ".json"), ("json", "Zürich 日本", "knowledge-graph-zurich.json"),
    ("json", "日本", "knowledge-graph.json"), ("json", "", "knowledge-graph.json"), ("json", "a" * 100, "knowledge-graph-" + "a" * 40 + ".json"),
    ("json", 'x"; filename="evil.exe', "knowledge-graph-x-filename-evil-exe.json"), ("json", "../../etc/passwd", "knowledge-graph-etc-passwd.json"),
])
def test_file_names_are_plain_ascii(fmt, title, expected):
    assert ex.file_name(fmt, title) == expected


def test_an_unknown_format_is_refused():
    with pytest.raises(ValueError, match="Use one of: json, cypher, csv"):
        ex.render(ex.Dataset(), "xml")


# ---------------------------------------------------------------- the API

@pytest.fixture
def client(factory, rich):
    import server

    def override():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    server.app.dependency_overrides[get_db] = override
    c = TestClient(server.app)
    c.d = rich
    yield c
    server.app.dependency_overrides.clear()


def test_summary_says_what_a_download_would_hold(client):
    r = client.get("/api/export/summary")
    assert r.status_code == 200 and r.json() == {"entities": 4, "facts": 6, "value_facts": 2, "entity_facts": 4, "sources": 6, "left_out": 0, "document": None}
    news = client.d.docs["News"][0]
    s = client.get(f"/api/export/summary?document_id={news}").json()
    assert s["facts"] == 4 and s["document"] == {"id": news, "title": "News"}


@pytest.mark.parametrize("fmt,media,name", [("json", "application/json", "knowledge-graph.json"), ("cypher", "text/plain; charset=utf-8", "knowledge-graph.cypher"),
                                            ("csv", "application/zip", "knowledge-graph.zip")])
def test_each_format_downloads_as_a_file(client, fmt, media, name):
    r = client.get(f"/api/export?format={fmt}")
    assert r.status_code == 200 and r.headers["content-type"] == media
    assert r.headers["content-disposition"] == f'attachment; filename="{name}"'
    assert r.headers["cache-control"] == "no-store" and r.headers["x-content-type-options"] == "nosniff"


def test_json_is_the_default_and_the_content_is_right(client):
    r = client.get("/api/export")
    assert r.headers["content-disposition"].endswith('"knowledge-graph.json"')
    j = r.json()
    assert j["counts"]["facts"] == 6 and any(f["sources"] for f in j["facts"])


def test_the_downloaded_cypher_and_csv_are_the_real_thing(client):
    g = Db().run(client.get("/api/export?format=cypher").text)
    assert len(g.rels) == 6 and g.constraints == ["Entity", "Value"]
    files = unzip(client.get("/api/export?format=csv").content)
    assert len(table(files["facts.csv"])) == 7


def test_options_reach_the_export(client):
    assert "evidence" not in client.get("/api/export?format=cypher&sources=false").text
    assert "CONSTRAINT" not in client.get("/api/export?format=cypher&schema=false").text
    assert "sources" not in client.get("/api/export?sources=false").json()["facts"][0]


def test_a_document_scope_names_the_file_and_limits_the_facts(client):
    r = client.get(f"/api/export?document_id={client.d.docs['News'][0]}")
    assert r.headers["content-disposition"].endswith('"knowledge-graph-news.json"') and len(r.json()["facts"]) == 4


def test_a_bad_format_or_document_is_refused(client):
    r = client.get("/api/export?format=xml")
    assert r.status_code == 422 and "json, cypher, csv" in r.json()["detail"]
    assert client.get(f"/api/export?document_id={'0' * 32}").status_code == 404
    assert client.get(f"/api/export/summary?document_id={'0' * 32}").status_code == 404


def test_it_is_not_cached_or_sniffable(client):
    r = client.get("/api/export?format=cypher")
    assert "no-store" in r.headers["cache-control"] and r.headers["x-content-type-options"] == "nosniff"


# ---------------------------------------------------------------- accounts

from tests.test_accounts import DOCS, RAWS, site  # noqa: E402,F401  (the fixture)


def _add(c, key):
    r = c.post("/api/documents/text", json={"title": f"Doc {key}", "text": DOCS[key]})
    assert r.status_code == 202, r.text
    return r.json()["id"]


def test_accounts_never_see_each_others_export(site):
    ann, bob = site.user("ann"), site.user("bob")
    _add(ann, "A")
    bob_doc = _add(bob, "B")
    for fmt in ("json", "cypher", "csv"):
        a = ann.get(f"/api/export?format={fmt}")
        assert a.status_code == 200
        text = "".join(v.decode("utf-8-sig") for v in unzip(a.content).values()) if fmt == "csv" else a.text
        assert "Acme Corp" in text and "Zed Inc" not in text and "Omega" not in text, fmt
    assert ann.get("/api/export/summary").json()["facts"] == 2 and bob.get("/api/export/summary").json()["facts"] == 2
    missing = ann.get(f"/api/export?document_id={bob_doc}")
    absent = ann.get(f"/api/export?document_id={'0' * 32}")
    assert missing.status_code == absent.status_code == 404 and missing.json() == absent.json()
    assert ann.get(f"/api/export/summary?document_id={bob_doc}").status_code == 404


def test_signed_out_callers_get_401_for_every_export_url(site):
    anon = site.client()
    for url in ("/api/export", "/api/export?format=cypher", "/api/export?format=csv", "/api/export/summary"):
        assert anon.get(url).status_code == 401, url
