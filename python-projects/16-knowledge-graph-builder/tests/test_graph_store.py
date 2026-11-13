import pytest

from src.models.graph import Document
from src.services import graph_store, pipeline
from src.core.config import Settings
from tests.conftest import FakeLLM, rel

TEXT = ("Ann works at Acme. Acme owns Beta. Beta owns Gamma. Gamma owns Delta. "
        "Acme reported revenue of 12M in 2021. Zed works at Omega.")


def build(db, factory, monkeypatch=None):
    d = Document(title="t", text=TEXT, char_count=len(TEXT))
    db.add(d)
    db.commit()
    o = "organization"
    raws = [
        rel("Ann", "works at", "Acme", "Ann works at Acme.", otype=o),
        rel("Acme", "owns", "Beta", "Acme owns Beta.", otype=o, stype=o),
        rel("Beta", "owns", "Gamma", "Beta owns Gamma.", otype=o, stype=o),
        rel("Gamma", "owns", "Delta", "Gamma owns Delta.", otype=o, stype=o),
        rel("Acme", "reported revenue", "12M", "Acme reported revenue of 12M in 2021.", "2021", otype="value", stype=o),
        rel("Zed", "works at", "Omega", "Zed works at Omega.", otype=o),
    ]
    pipeline.process_document(d.id, FakeLLM(extract=lambda p: {"relations": raws}), Settings(_env_file=None, verify_facts=False, gleaning_passes=0, auto_resolve=False))
    return d.id


def names(g):
    return sorted(d["name"] for _, d in g.nodes(data=True))


def test_entities_are_nodes_facts_are_edges_and_values_are_attributes(db, factory):
    build(db, factory)
    g = graph_store.build_graph(db)
    assert names(g) == ["Acme", "Ann", "Beta", "Delta", "Gamma", "Omega", "Zed"]
    assert g.number_of_edges() == 5
    acme = next(n for n, d in g.nodes(data=True) if d["name"] == "Acme")
    assert g.nodes[acme]["attributes"] == [{"predicate": "reported revenue", "value": "12M", "valid_from": "2021", "valid_to": None}]
    edge = next(d for _, _, d in g.edges(data=True) if d["predicate"] == "owns")
    assert edge["source_count"] == 1 and edge["valid_from"] is None


def test_neighborhood_depth_follows_links_in_both_directions(db, factory):
    build(db, factory)
    g = graph_store.build_graph(db)
    gid = lambda name: next(n for n, d in g.nodes(data=True) if d["name"] == name)  # noqa: E731
    assert names(graph_store.neighborhood(g, gid("Beta"), 1)) == ["Acme", "Beta", "Gamma"]
    assert names(graph_store.neighborhood(g, gid("Beta"), 2)) == ["Acme", "Ann", "Beta", "Delta", "Gamma"]
    assert "Omega" not in names(graph_store.neighborhood(g, gid("Beta"), 3))  # a separate island stays separate
    assert graph_store.neighborhood(g, "missing", 1).number_of_nodes() == 0


def test_payload_keeps_the_most_connected_nodes_and_says_when_truncated(db, factory):
    build(db, factory)
    g = graph_store.build_graph(db)
    p = graph_store.graph_payload(g, limit=3)
    assert p["truncated"] and p["total_nodes"] == 7 and len(p["nodes"]) == 3
    assert {n["name"] for n in p["nodes"]} <= {"Acme", "Beta", "Gamma"}
    ids = {n["id"] for n in p["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in p["edges"])
    assert not graph_store.graph_payload(g, limit=100)["truncated"]


def test_filter_by_document_and_type(db, factory):
    doc_id = build(db, factory)
    assert graph_store.build_graph(db, doc_id).number_of_edges() == 5
    assert graph_store.build_graph(db, "other-doc").number_of_nodes() == 0
    persons = graph_store.build_graph(db, entity_type="person")
    assert names(persons) == ["Ann", "Zed"] and persons.number_of_edges() == 0
    assert graph_store.build_graph(db, entity_type="place").number_of_nodes() == 0


def test_stats_and_search(db, factory):
    build(db, factory)
    s = graph_store.stats(db)
    assert s["facts"] == 6 and s["entities"] == 7 and s["sources"] == 6
    assert {"predicate": "owns", "count": 3} in s["top_predicates"]
    assert [e.name for e in graph_store.search_entities(db, "ac")] == ["Acme"]
    assert [e.name for e in graph_store.search_entities(db, "  BETA ")] == ["Beta"]
    assert len(graph_store.search_entities(db, "")) == 7
    assert graph_store.search_entities(db, "", "place") == []
    assert len(graph_store.search_entities(db, "", limit=2)) == 2
