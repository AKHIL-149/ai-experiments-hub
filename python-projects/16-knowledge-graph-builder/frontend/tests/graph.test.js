import { describe, expect, it } from "vitest";
import { countByType, edgeBundles, endId, filterGraph, linkGeometry, mergeGraph, nodeRadius, pathHighlight, searchNodes, typeColor, typeLabel, visibleLabels } from "../src/lib/graph";

const n = (id, name, type = "organization", degree = 1) => ({ id, name, type, degree });
const e = (id, source, target, predicate = "owns") => ({ id, source, target, predicate });

describe("types", () => {
  it("has a colour per type and a fallback", () => {
    expect(typeColor("person")).toBe("#2F5FD0");
    expect(typeColor("organization")).toBe("#0F9D8A");
    expect(typeColor("place")).toBe("#D9822B");
    expect(typeColor("concept")).toBe("#C2417C");
    expect(typeColor("something new")).toBe(typeColor("concept"));
    expect(typeLabel("person")).toBe("Person");
    expect(typeLabel("")).toBe("Thing");
  });
  it("sizes nodes by degree, within limits", () => {
    expect(nodeRadius(0)).toBe(7);
    expect(nodeRadius(4)).toBe(13);
    expect(nodeRadius(10000)).toBe(24);
    expect(nodeRadius(-5)).toBe(7);
    expect(nodeRadius(undefined)).toBe(7);
  });
  it("counts nodes by type", () => {
    expect(countByType([n("1", "a", "person"), n("2", "b", "person"), n("3", "c", "place")])).toEqual({ person: 2, place: 1 });
  });
});

describe("mergeGraph", () => {
  it("unites nodes and edges by id and keeps the larger degree", () => {
    const a = { nodes: [n("1", "Acme", "organization", 2), n("2", "Beta")], edges: [e("f1", "1", "2")] };
    const b = { nodes: [n("1", "Acme", "organization", 5), n("3", "Gamma")], edges: [e("f1", "1", "2", "acquired"), e("f2", "1", "3")] };
    const m = mergeGraph(a, b);
    expect(m.nodes.map((x) => x.id).sort()).toEqual(["1", "2", "3"]);
    expect(m.nodes.find((x) => x.id === "1").degree).toBe(5);
    expect(m.edges.map((x) => x.id).sort()).toEqual(["f1", "f2"]);
    expect(m.edges.find((x) => x.id === "f1").predicate).toBe("acquired");
  });
  it("keeps the larger degree whichever side has it (a smaller neighbourhood does not shrink a node)", () => {
    const m = mergeGraph({ nodes: [n("1", "Acme", "organization", 9)], edges: [] }, { nodes: [n("1", "Acme", "organization", 2)], edges: [] });
    expect(m.nodes[0].degree).toBe(9);
  });
  it("drops edges whose end is missing and accepts nothing", () => {
    expect(mergeGraph({ nodes: [n("1", "A")], edges: [] }, { nodes: [], edges: [e("f", "1", "9")] }).edges).toEqual([]);
    expect(mergeGraph({}, {})).toEqual({ nodes: [], edges: [] });
  });
  it("understands edges whose ends were replaced by node objects (after d3-force ran)", () => {
    const a = { nodes: [n("1", "A"), n("2", "B")], edges: [{ id: "f", source: { id: "1" }, target: { id: "2" } }] };
    expect(mergeGraph(a, { nodes: [], edges: [] }).edges).toHaveLength(1);
    expect(endId({ id: "x" })).toBe("x");
    expect(endId("y")).toBe("y");
  });
});

describe("filterGraph", () => {
  const g = { nodes: [n("1", "Ann", "person"), n("2", "Acme", "organization"), n("3", "Oslo", "place")], edges: [e("a", "1", "2"), e("b", "2", "3")] };
  it("keeps everything when no type is chosen", () => {
    expect(filterGraph(g, { types: new Set() })).toEqual(g);
    expect(filterGraph(g)).toEqual(g);
  });
  it("keeps the chosen types and the edges between them", () => {
    const f = filterGraph(g, { types: new Set(["person", "organization"]) });
    expect(f.nodes.map((x) => x.id)).toEqual(["1", "2"]);
    expect(f.edges.map((x) => x.id)).toEqual(["a"]);
  });
  it("can hide single edges", () => {
    expect(filterGraph(g, { hiddenEdgeIds: new Set(["a"]) }).edges.map((x) => x.id)).toEqual(["b"]);
  });
});

describe("edgeBundles", () => {
  it("numbers edges between the same two nodes, whichever way they point", () => {
    const b = edgeBundles([e("1", "a", "b"), e("2", "b", "a"), e("3", "a", "b"), e("4", "a", "c")]);
    expect(b["1"]).toEqual({ index: 0, count: 3, flip: false });
    expect(b["2"]).toEqual({ index: 1, count: 3, flip: true });
    expect(b["3"]).toEqual({ index: 2, count: 3, flip: false });
    expect(b["4"]).toEqual({ index: 0, count: 1, flip: false });
  });
  it("works with node objects as ends", () => {
    const b = edgeBundles([{ id: "1", source: { id: "a" }, target: { id: "b" } }, { id: "2", source: { id: "b" }, target: { id: "a" } }]);
    expect(b["1"].count).toBe(2);
  });
});

describe("linkGeometry", () => {
  const A = { x: 0, y: 0 }, B = { x: 100, y: 0 };
  it("draws a straight line that stops at the node borders", () => {
    const g = linkGeometry(A, B, 10, 10);
    expect(g.d).toBe("M10,0L87,0");
    expect(g.labelX).toBeCloseTo(48.5);
    expect(g.labelY).toBe(0);
    expect(g.angle).toBe(0);
  });
  it("curves parallel edges to different sides", () => {
    const up = linkGeometry(A, B, 10, 10, { index: 0, count: 2, flip: false });
    const down = linkGeometry(A, B, 10, 10, { index: 1, count: 2, flip: false });
    expect(up.d.startsWith("M10,0Q")).toBe(true);
    expect(up.labelY).toBeLessThan(0);
    expect(down.labelY).toBeGreaterThan(0);
  });
  it("flips the side for an edge that points the other way", () => {
    const same = linkGeometry(A, B, 10, 10, { index: 0, count: 2, flip: false });
    const flipped = linkGeometry(A, B, 10, 10, { index: 0, count: 2, flip: true });
    expect(Math.sign(same.labelY)).toBe(-Math.sign(flipped.labelY));
  });
  it("copes with two nodes in the same place", () => {
    const g = linkGeometry({ x: 5, y: 5 }, { x: 5, y: 5 }, 8, 8);
    expect(Number.isFinite(g.labelX) && Number.isFinite(g.labelY)).toBe(true);
  });
});

describe("pathHighlight", () => {
  it("collects the nodes and facts of a path by name", () => {
    const nodes = [n("1", "Imani"), n("2", "Soro"), n("3", "Veltra")];
    const paths = [[{ fact_id: "f1", from: "Imani", to: "Soro" }, { fact_id: "f2", from: "Veltra", to: "Soro" }]];
    const h = pathHighlight(paths, nodes);
    expect([...h.nodeIds].sort()).toEqual(["1", "2", "3"]);
    expect([...h.edgeIds].sort()).toEqual(["f1", "f2"]);
  });
  it("ignores names that are not on screen and empty input", () => {
    expect([...pathHighlight([[{ fact_id: "f", from: "X", to: "Y" }]], []).nodeIds]).toEqual([]);
    expect(pathHighlight(null, []).edgeIds.size).toBe(0);
  });
});

describe("visibleLabels", () => {
  it("labels the selected, the highlighted and the best connected within a budget", () => {
    const nodes = [n("1", "a", "x", 1), n("2", "b", "x", 9), n("3", "c", "x", 5), n("4", "d", "x", 0)];
    const ids = visibleLabels(nodes, { selectedId: "4", highlightIds: new Set(["1"]), budget: 1 });
    expect([...ids].sort()).toEqual(["1", "2", "4"]);
  });
  it("works without options", () => {
    expect(visibleLabels([n("1", "a")]).has("1")).toBe(true);
  });
});

describe("searchNodes", () => {
  const nodes = [n("1", "Acme Corp", "o", 5), n("2", "Beta Acme", "o", 1), n("3", "Zed", "o", 1), n("4", "Acme", "o", 1)];
  it("finds names that start with the text before names that contain it", () => {
    expect(searchNodes(nodes, "acme").map((x) => x.id)).toEqual(["4", "1", "2"]);
  });
  it("is case-insensitive, trims, and returns nothing for nothing", () => {
    expect(searchNodes(nodes, "  ZED ").map((x) => x.id)).toEqual(["3"]);
    expect(searchNodes(nodes, "")).toEqual([]);
    expect(searchNodes(nodes, "nothing")).toEqual([]);
    expect(searchNodes(nodes, null)).toEqual([]);
  });
  it("limits the list", () => {
    expect(searchNodes(nodes, "a", 2)).toHaveLength(2);
  });
});
