"""Read-only views of the stored graph (NetworkX is the working representation)"""
import networkx as nx
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from src.models.graph import Entity, Fact, FactSource


def fact_to_dict(f: Fact, source_count: int | None = None) -> dict:
    return {
        "id": f.id,
        "subject_id": f.subject_id,
        "subject": f.subject.name,
        "predicate": f.predicate,
        "object_id": f.object_id,
        "object": f.object.name if f.object else f.object_value,
        "object_is_value": f.object_id is None,
        "valid_from": f.valid_from or None,
        "valid_to": f.valid_to or None,
        "source_count": source_count if source_count is not None else len(f.sources),
    }


def build_graph(db: Session, document_id: str | None = None, entity_type: str | None = None) -> nx.MultiDiGraph:
    """Entities are nodes, entity-to-entity facts are edges. Facts with a plain value become node attributes."""
    q = select(Fact)
    if document_id:
        q = q.where(Fact.id.in_(select(FactSource.fact_id).where(FactSource.document_id == document_id)))
    g = nx.MultiDiGraph()
    counts = dict(db.execute(select(FactSource.fact_id, func.count()).group_by(FactSource.fact_id)).all())
    for f in db.execute(q).scalars():
        for e in (f.subject, f.object):
            if e is not None and e.id not in g:
                g.add_node(e.id, name=e.name, type=e.type, attributes=[])
        if f.object_id is None:
            g.nodes[f.subject_id]["attributes"].append({"predicate": f.predicate, "value": f.object_value,
                                                        "valid_from": f.valid_from or None, "valid_to": f.valid_to or None})
        else:
            g.add_edge(f.subject_id, f.object_id, key=f.id, id=f.id, predicate=f.predicate,
                       valid_from=f.valid_from or None, valid_to=f.valid_to or None, source_count=counts.get(f.id, 0))
    if entity_type:
        keep = [n for n, d in g.nodes(data=True) if d["type"] == entity_type]
        g = g.subgraph(keep).copy()
    return g


def graph_payload(g: nx.MultiDiGraph, limit: int = 300) -> dict:
    """The most connected `limit` nodes and the edges between them, ready for the UI"""
    ranked = sorted(g.nodes, key=lambda n: (-g.degree(n), g.nodes[n]["name"].casefold()))
    keep = set(ranked[:limit])
    nodes = [{"id": n, "name": g.nodes[n]["name"], "type": g.nodes[n]["type"], "degree": g.degree(n),
              "attributes": g.nodes[n]["attributes"]} for n in ranked[:limit]]
    edges = [{"id": d["id"], "source": u, "target": v, "predicate": d["predicate"], "valid_from": d["valid_from"],
              "valid_to": d["valid_to"], "source_count": d["source_count"]}
             for u, v, d in g.edges(data=True) if u in keep and v in keep]
    return {"nodes": nodes, "edges": edges, "total_nodes": g.number_of_nodes(), "total_edges": g.number_of_edges(),
            "truncated": g.number_of_nodes() > limit}


def neighborhood(g: nx.MultiDiGraph, entity_id: str, depth: int = 1) -> nx.MultiDiGraph:
    """The entity and everything within `depth` links of it (either direction)"""
    if entity_id not in g:
        return nx.MultiDiGraph()
    reach = nx.single_source_shortest_path_length(g.to_undirected(as_view=True), entity_id, cutoff=depth)
    return g.subgraph(reach.keys()).copy()


def stats(db: Session) -> dict:
    by_type = dict(db.execute(select(Entity.type, func.count()).group_by(Entity.type)).all())
    return {
        "entities": sum(by_type.values()),
        "entities_by_type": by_type,
        "facts": db.scalar(select(func.count()).select_from(Fact)) or 0,
        "sources": db.scalar(select(func.count()).select_from(FactSource)) or 0,
        "top_predicates": [{"predicate": p, "count": c} for p, c in db.execute(
            select(Fact.predicate, func.count().label("c")).group_by(Fact.predicate).order_by(func.count().desc()).limit(10))],
    }


def search_entities(db: Session, q: str = "", entity_type: str | None = None, limit: int = 50) -> list[Entity]:
    from src.services.text_utils import entity_key
    stmt = select(Entity)
    if q.strip():
        stmt = stmt.where(or_(Entity.key.contains(entity_key(q)), Entity.name.ilike(f"%{q.strip()}%")))
    if entity_type:
        stmt = stmt.where(Entity.type == entity_type)
    return list(db.execute(stmt.order_by(Entity.name).limit(limit)).scalars())
