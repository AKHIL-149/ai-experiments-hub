// Pure graph helpers: colours, merging, parallel edges, filtering, SVG paths.

export const TYPE_ORDER = ["person", "organization", "place", "product", "event", "concept"];
// Paper Light palette (see styles.css). Kept here too because SVG fills are computed in code.
export const TYPE_COLORS = {
  person: "#2F5FD0",
  organization: "#0F9D8A",
  place: "#D9822B",
  concept: "#C2417C",
  product: "#7B5CC4",
  event: "#7A8088",
};

export function typeColor(type) {
  return TYPE_COLORS[type] || TYPE_COLORS.concept;
}

export function typeLabel(type) {
  return type ? type.charAt(0).toUpperCase() + type.slice(1) : "Thing";
}

export function nodeRadius(degree) {
  return Math.min(7 + Math.sqrt(Math.max(degree || 0, 0)) * 3, 24);
}

/** Union of two graphs ({nodes, edges}): same id = same thing; the newer data wins, the bigger degree is kept */
export function mergeGraph(a, b) {
  const nodes = new Map((a.nodes || []).map((n) => [n.id, n]));
  for (const n of b.nodes || []) {
    const old = nodes.get(n.id);
    nodes.set(n.id, old ? { ...old, ...n, degree: Math.max(old.degree || 0, n.degree || 0) } : n);
  }
  const edges = new Map((a.edges || []).map((e) => [e.id, e]));
  for (const e of b.edges || []) edges.set(e.id, { ...(edges.get(e.id) || {}), ...e });
  // an edge needs both of its ends
  const kept = [...edges.values()].filter((e) => nodes.has(endId(e.source)) && nodes.has(endId(e.target)));
  return { nodes: [...nodes.values()], edges: kept };
}

/** d3-force replaces source/target ids by node objects; both forms are accepted */
export function endId(end) {
  return typeof end === "object" && end !== null ? end.id : end;
}

/** Keep the nodes of the chosen types (an empty set = all) and the edges between kept nodes */
export function filterGraph(graph, { types, hiddenEdgeIds } = {}) {
  const hasTypes = types && types.size > 0;
  const nodes = hasTypes ? graph.nodes.filter((n) => types.has(n.type)) : graph.nodes;
  const ids = new Set(nodes.map((n) => n.id));
  const edges = graph.edges.filter((e) => ids.has(endId(e.source)) && ids.has(endId(e.target)) && !(hiddenEdgeIds && hiddenEdgeIds.has(e.id)));
  return { nodes, edges };
}

export function countByType(nodes) {
  const out = {};
  for (const n of nodes) out[n.type] = (out[n.type] || 0) + 1;
  return out;
}

/** For edges between the same two nodes: { [edgeId]: { index, count, flip } } so they can be drawn as separate arcs */
export function edgeBundles(edges) {
  const groups = new Map();
  for (const e of edges) {
    const a = endId(e.source), b = endId(e.target);
    const key = a < b ? `${a}|${b}` : `${b}|${a}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push({ id: e.id, flip: a > b });
  }
  const out = {};
  for (const list of groups.values()) {
    list.forEach((item, index) => { out[item.id] = { index, count: list.length, flip: item.flip }; });
  }
  return out;
}

/**
 * SVG path from source to target that stops at the node borders (so the arrow head is visible). Parallel edges are
 * curved to different sides; a single straight edge stays straight. Returns { d, labelX, labelY, angle }.
 */
export function linkGeometry(source, target, sourceR, targetR, bundle = { index: 0, count: 1, flip: false }) {
  const dx = target.x - source.x, dy = target.y - source.y;
  const dist = Math.hypot(dx, dy) || 1;
  const ux = dx / dist, uy = dy / dist;
  const sx = source.x + ux * sourceR, sy = source.y + uy * sourceR;
  const tx = target.x - ux * (targetR + 3), ty = target.y - uy * (targetR + 3);
  const spread = bundle.count > 1 ? (bundle.index - (bundle.count - 1) / 2) * 34 * (bundle.flip ? -1 : 1) : 0;
  const mx = (sx + tx) / 2 - uy * spread, my = (sy + ty) / 2 + ux * spread;
  const d = spread === 0 ? `M${sx},${sy}L${tx},${ty}` : `M${sx},${sy}Q${mx},${my} ${tx},${ty}`;
  const labelX = spread === 0 ? (sx + tx) / 2 : 0.25 * sx + 0.5 * mx + 0.25 * tx;
  const labelY = spread === 0 ? (sy + ty) / 2 : 0.25 * sy + 0.5 * my + 0.25 * ty;
  return { d, labelX, labelY, angle: Math.atan2(ty - sy, tx - sx) };
}

/** Ids of the nodes and edges on the given paths (from /api/query/path), for highlighting */
export function pathHighlight(paths, nodes) {
  const byName = new Map(nodes.map((n) => [n.name, n.id]));
  const edgeIds = new Set();
  const nodeIds = new Set();
  for (const path of paths || []) {
    for (const step of path) {
      if (step.fact_id) edgeIds.add(step.fact_id);
      for (const name of [step.from, step.to]) if (byName.has(name)) nodeIds.add(byName.get(name));
    }
  }
  return { nodeIds, edgeIds };
}

/** Which labels to draw: the selected and highlighted ones, and the best connected up to a budget */
export function visibleLabels(nodes, { selectedId, highlightIds = new Set(), budget = 25 } = {}) {
  const ids = new Set(highlightIds);
  if (selectedId) ids.add(selectedId);
  const byDegree = [...nodes].sort((a, b) => (b.degree || 0) - (a.degree || 0));
  for (const n of byDegree.slice(0, budget)) ids.add(n.id);
  return ids;
}

/** Entities matching a typed name, best first (exact start before inside), for the search box */
export function searchNodes(nodes, query, limit = 8) {
  const q = (query || "").trim().toLowerCase();
  if (!q) return [];
  const scored = [];
  for (const n of nodes) {
    const name = n.name.toLowerCase();
    const i = name.indexOf(q);
    if (i < 0) continue;
    scored.push({ n, score: (i === 0 ? 0 : 10) + name.length * 0.01 - (n.degree || 0) * 0.001 });
  }
  return scored.sort((x, y) => x.score - y.score).slice(0, limit).map((s) => s.n);
}
