"""Load the Cypher export of an awkward graph into a real Neo4j, read it back and compare every field.

  NEO4J_PASSWORD=... python3 -m eval.run_neo4j_check [--http http://localhost:7474] [--user neo4j] [--database neo4j]
                                                     [--cypher-shell /path/to/cypher-shell] [--wipe]

The graph has quotes, backslashes, semicolons, "//", backticks, control characters, line separators, emoji, CJK text, a predicate with
no ASCII letters, a quote that tries to inject a statement, a 5,000 character quote and a plain value. It is built in a throwaway
SQLite file, exported by the same code the API uses, loaded by the real `cypher-shell`, and read back over Neo4j's HTTP API.

THIS ERASES THE DATABASE IT POINTS AT. It refuses to run unless that database is empty or you pass --wipe. Use a scratch instance.
Last run: Neo4j Community 5.26.0, no differences (see the README).
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from src.core import database  # noqa: E402
from src.models import *  # noqa: E402,F401,F403
from src.models.resolution import EntityAlias  # noqa: E402
from src.services import export as ex  # noqa: E402
from src.services.text_utils import entity_key  # noqa: E402
from tests.conftest import _graph_world  # noqa: E402

NAMES = ["O'Brien & \"Sons\"; Ltd \\ Co", "Zürich 日本 😀", "Back`tick $param {x: 1} [list] (paren)", "Line Sep Para", "Ctl\x01\x1f\x7f chars",
         "Acme // not a comment /* nor this */"]
QUOTES = ["He said: it's \"fine\"\nline two\tTabbed \\n not a newline; // still text ' ] }", "x'}) DETACH DELETE n; MATCH (m) RETURN m //",
          "ends with backslash \\", "\\'", "emoji 😀 and 日本語 and café", "=cmd|' /C calc'!A0", "a" * 5000]


def build(dir_: str):
    engine = create_engine(f"sqlite:///{dir_}/t.db")
    database.Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    w = _graph_world(db)
    e = [w.ent(n, t) for n, t in zip(NAMES, ["organization", "place", "person", "concept", "product", "event"])]
    w.fact(e[0], "acquired", e[1], frm="2020-03", quote=QUOTES[0], title="News", verified=True)
    w.fact(e[1], "was CTO of", e[2], frm="2012", to="2019", quote=QUOTES[1], title="History")
    w.fact(e[2], "employs", value="340 people; \"approx\" 'x'", quote=QUOTES[2], title="News")
    w.fact(e[3], "是", e[4], quote=QUOTES[3], title="History")
    w.fact(e[4], "2nd owner of", e[5], quote=QUOTES[4], title="News")
    w.fact(e[5], "notes", value="=HYPERLINK(\"http://x\")", quote=QUOTES[5], title="News")
    w.fact(e[0], "headquartered in", e[3], quote=QUOTES[6], title="News")
    w.fact(e[0], "(a)-[:B]->(c) DELETE", e[5], quote="odd predicate", title="News")
    for n in ("Acme Inc.", "ACME", "it's \\ alias"):
        db.add(EntityAlias(entity_id=e[0].id, key=entity_key(n), name=n))
    db.commit()
    return ex.collect(db, None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--http", default="http://localhost:7474")
    ap.add_argument("--user", default="neo4j")
    ap.add_argument("--database", default="neo4j")
    ap.add_argument("--cypher-shell", default="cypher-shell")
    ap.add_argument("--wipe", action="store_true", help="erase the database first, even if it is not empty")
    a = ap.parse_args()
    password = os.environ.get("NEO4J_PASSWORD")
    if not password:
        sys.exit("Set NEO4J_PASSWORD (the password of a scratch Neo4j instance)")
    auth = "Basic " + base64.b64encode(f"{a.user}:{password}".encode()).decode()

    def http(*statements):
        body = json.dumps({"statements": [{"statement": s} for s in statements]}).encode()
        req = urllib.request.Request(f"{a.http}/db/{a.database}/tx/commit", body, {"Content-Type": "application/json", "Authorization": auth})
        out = json.load(urllib.request.urlopen(req))
        if out["errors"]:
            raise RuntimeError(out["errors"])
        return [[r["row"] for r in res["data"]] for res in out["results"]]

    existing = http("MATCH (n) RETURN count(n)")[0][0][0]
    if existing and not a.wipe:
        sys.exit(f"The database already holds {existing} nodes. Use an empty scratch instance, or pass --wipe to erase it.")
    http("MATCH (n) DETACH DELETE n")
    http("DROP CONSTRAINT kg_entity_id IF EXISTS", "DROP CONSTRAINT kg_value_id IF EXISTS")

    tmp = tempfile.mkdtemp()
    ds = build(tmp)
    script = Path(tmp) / "export.cypher"
    script.write_bytes(ex.render(ds, "cypher"))
    print("exported", ds.counts())
    for run in (1, 2):                                   # twice: the script must be safe to run again
        r = subprocess.run([a.cypher_shell, "-u", a.user, "-p", password, "-d", a.database, "-f", str(script)], capture_output=True, text=True)
        print(f"cypher-shell run {run}: exit {r.returncode} {r.stderr.strip()[:300]}")
        if r.returncode:
            sys.exit(1)

    nodes = http("MATCH (n:Entity) RETURN n.id, n.name, n.type, n.aliases, labels(n)")[0]
    vals = dict(http("MATCH (v:Value) RETURN v.id, v.value")[0])
    rels = http("MATCH (a:Entity)-[r]->(b) RETURN r.id, a.id, b.id, type(r), r.predicate, r.valid_from, r.valid_to, r.source_count, r.evidence, r.evidence_documents, labels(b)")[0]
    stray = http("MATCH (n) WHERE NOT n:Entity AND NOT n:Value RETURN count(n)")[0][0][0]
    problems = []
    got_n = {r[0]: r for r in nodes}
    for e in ds.entities:
        g = got_n.get(e["id"])
        if not g:
            problems.append(("missing entity", e["name"]))
            continue
        if (g[1], g[2], g[3] or [], set(g[4])) != (e["name"], e["type"], e["aliases"], {"Entity", e["type"].capitalize()}):
            problems.append(("entity differs", e["name"], g[1:]))
    got_r = {r[0]: r for r in rels}
    for f in ds.facts:
        g = got_r.get(f["id"])
        if not g:
            problems.append(("missing relationship", f["predicate"]))
            continue
        _, s, o, _typ, pred, vf, vt, sc, ev, evd, olabels = g
        want = (f["subject_id"], f["predicate"], f["valid_from"], f["valid_to"], f["source_count"], [x["quote"] for x in f["sources"]], [x["document_title"] for x in f["sources"]])
        if (s, pred, vf, vt, sc, ev, evd) != want:
            problems.append(("relationship differs", f["predicate"]))
        if f["object_is_value"]:
            if "Value" not in olabels or vals.get(f["id"]) != f["object"]:
                problems.append(("value differs", f["object"]))
        elif o != f["object_id"]:
            problems.append(("object differs", f["predicate"]))
    if (len(nodes), len(rels), len(vals), stray) != (len(ds.entities), len(ds.facts), ds.counts()["value_facts"], 0):
        problems.append(("counts differ", len(nodes), len(rels), len(vals), stray))
    print("relationship types:", sorted({r[3] for r in rels}))
    print(f"compared {len(ds.entities)} entities, {len(ds.facts)} facts, {len(vals)} values")
    print("DIFFERENCES:", problems or "none")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
