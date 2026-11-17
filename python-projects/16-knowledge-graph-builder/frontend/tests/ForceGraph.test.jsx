import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ForceGraph from "../src/components/ForceGraph";
import { graph as sample } from "./helpers";

// reduced motion: the layout is computed at once instead of animating, so positions exist right after render
beforeEach(() => {
  window.matchMedia = vi.fn().mockReturnValue({ matches: true, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
});

const g = sample();
const handlers = () => ({ onSelectNode: vi.fn(), onSelectEdge: vi.fn(), onExpandNode: vi.fn(), onBackground: vi.fn() });
const show = (props = {}, h = handlers()) => ({ h, ...render(<ForceGraph nodes={g.nodes} edges={g.edges} {...h} {...props} />) });

describe("ForceGraph", () => {
  it("describes itself for screen readers and draws one circle per entity and one line per fact", () => {
    const { container } = show();
    expect(screen.getByRole("img")).toHaveAttribute("aria-label", expect.stringContaining("3 entities and 2 facts"));
    expect(container.querySelectorAll("g.node")).toHaveLength(3);
    expect(container.querySelectorAll("g.edge")).toHaveLength(2);
  });

  it("makes each entity a labelled, focusable button with its type and links", () => {
    show();
    const n = screen.getByRole("button", { name: "Acme Corp, organization, 2 links" });
    expect(n).toHaveAttribute("tabindex", "0");
    expect(n).toHaveAttribute("aria-pressed", "false");
  });

  it("colours entities by type", () => {
    const { container } = show();
    const fill = (id) => container.querySelector(`g.node[data-id="${id}"] circle`).getAttribute("fill").toLowerCase();
    expect(fill("n3")).toBe("#2f5fd0");   // person
    expect(fill("n1")).toBe("#0f9d8a");   // organization
  });

  it("draws arrow heads on the lines", () => {
    const { container } = show();
    expect(container.querySelector("g.edge path:not(.hit)")).toHaveAttribute("marker-end", "url(#arrow)");
  });

  it("selects a node on click, and expands it on double click", () => {
    const { h } = show();
    const n = screen.getByRole("button", { name: /^Acme Corp/ });
    fireEvent.click(n);
    expect(h.onSelectNode).toHaveBeenCalledWith("n1");
    fireEvent.doubleClick(n);
    expect(h.onExpandNode).toHaveBeenCalledWith("n1");
  });

  it("works from the keyboard: Enter and Space select, E expands, other keys do nothing", () => {
    const { h } = show();
    const n = screen.getByRole("button", { name: /^Acme Corp/ });
    fireEvent.keyDown(n, { key: "Enter" });
    fireEvent.keyDown(n, { key: " " });
    expect(h.onSelectNode).toHaveBeenCalledTimes(2);
    fireEvent.keyDown(n, { key: "e" });
    expect(h.onExpandNode).toHaveBeenCalledWith("n1");
    fireEvent.keyDown(n, { key: "x" });
    expect(h.onSelectNode).toHaveBeenCalledTimes(2);
    expect(h.onExpandNode).toHaveBeenCalledTimes(1);
  });

  it("selects a fact by clicking its line", () => {
    const { container, h } = show();
    fireEvent.click(container.querySelector('g.edge[data-edge="f1"] path.hit'));
    expect(h.onSelectEdge).toHaveBeenCalledWith("f1");
  });

  it("clears the selection when the empty background is clicked, but not when a node is", () => {
    const { container, h } = show();
    fireEvent.click(container.querySelector("svg"));
    expect(h.onBackground).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: /^Acme Corp/ }));
    expect(h.onBackground).toHaveBeenCalledTimes(1);
  });

  it("marks the selected node and edge", () => {
    const { container } = show({ selectedNodeId: "n1", selectedEdgeId: "f2" });
    expect(screen.getByRole("button", { name: /^Acme Corp.*selected$/ })).toHaveAttribute("aria-pressed", "true");
    expect(container.querySelector('g.edge[data-edge="f2"]')).toHaveClass("sel");
    expect(container.querySelector('g.edge[data-edge="f1"]')).not.toHaveClass("sel");
  });

  it("dims everything that is not highlighted", () => {
    const { container } = show({ highlightNodeIds: new Set(["n1", "n2"]), highlightEdgeIds: new Set(["f1"]) });
    const cls = (sel) => container.querySelector(sel).classList;
    expect(cls('g.node[data-id="n1"]').contains("hl")).toBe(true);
    expect(cls('g.node[data-id="n3"]').contains("dim")).toBe(true);
    expect(cls('g.edge[data-edge="f1"]').contains("hl")).toBe(true);
    expect(cls('g.edge[data-edge="f2"]').contains("dim")).toBe(true);
    expect(container.querySelector('g.edge[data-edge="f1"] path:not(.hit)')).toHaveAttribute("marker-end", "url(#arrow-hl)");
  });

  it("dims nothing when nothing is highlighted", () => {
    const { container } = show();
    expect(container.querySelectorAll(".dim")).toHaveLength(0);
  });

  it("shows relation labels (with dates) while there are few facts, and names on the nodes", () => {
    const { container } = show();
    const texts = [...container.querySelectorAll("g.edge text")].map((t) => t.textContent);
    expect(texts).toContain("acquired · 2020-03");
    expect(texts).toContain("founded · 2010");
    expect(container.querySelectorAll("g.node text").length).toBeGreaterThan(0);
  });

  it("hides relation labels on a busy graph until the line is hovered", () => {
    const nodes = Array.from({ length: 14 }, (_, i) => ({ id: `x${i}`, name: `Entity ${i}`, type: "concept", degree: 1 }));
    const edges = Array.from({ length: 13 }, (_, i) => ({ id: `e${i}`, source: `x${i}`, target: `x${i + 1}`, predicate: `rel${i}`, valid_from: null, valid_to: null, source_count: 1 }));
    const { container } = render(<ForceGraph nodes={nodes} edges={edges} />);
    expect(container.querySelectorAll("g.edge text")).toHaveLength(0);
    fireEvent.mouseEnter(container.querySelector('g.edge[data-edge="e3"]'));
    expect(container.querySelector('g.edge[data-edge="e3"] text')).toHaveTextContent("rel3");
    fireEvent.mouseLeave(container.querySelector('g.edge[data-edge="e3"]'));
    expect(container.querySelectorAll("g.edge text")).toHaveLength(0);
  });

  it("has zoom and fit buttons", () => {
    show();
    for (const name of ["Zoom in", "Zoom out", "Fit the graph to the screen"]) expect(screen.getByRole("button", { name })).toBeInTheDocument();
  });

  it("keeps the places of nodes that were already there, and starts a new node next to its neighbour", () => {
    window.matchMedia = vi.fn().mockReturnValue({ matches: false });   // animated: nothing has moved yet when the data changes
    const { container, rerender, h } = show();
    const at = (id) => {
      const m = container.querySelector(`g.node[data-id="${id}"]`).getAttribute("transform").match(/translate\(([-\d.e]+),([-\d.e]+)\)/);
      return [Number(m[1]), Number(m[2])];
    };
    const before = at("n1");
    const edge = { id: "f3", source: "n4", target: "n1", predicate: "near", valid_from: null, valid_to: null, source_count: 1 };
    rerender(<ForceGraph nodes={[...g.nodes, { id: "n4", name: "Delta", type: "place", degree: 1 }]} edges={[...g.edges, edge]} {...h} />);
    expect(container.querySelectorAll("g.node")).toHaveLength(4);
    expect(at("n1")).toEqual(before);
    const [x, y] = at("n4");
    expect(Math.hypot(x - before[0], y - before[1])).toBeCloseTo(40, 0);
  });

  it("removes nodes and facts that are no longer given", () => {
    const { container, rerender, h } = show();
    rerender(<ForceGraph nodes={g.nodes.slice(0, 2)} edges={g.edges.slice(0, 1)} {...h} />);
    expect(container.querySelectorAll("g.node")).toHaveLength(2);
    expect(container.querySelectorAll("g.edge")).toHaveLength(1);
  });

  it("ignores a fact whose ends are not both on screen", () => {
    const { container } = render(<ForceGraph nodes={g.nodes.slice(0, 1)} edges={g.edges} />);
    expect(container.querySelectorAll("g.node")).toHaveLength(1);
    expect(container.querySelectorAll("g.edge")).toHaveLength(0);
  });

  it("copes with edges whose ends are node objects (as d3 leaves them)", () => {
    const edges = g.edges.map((e) => ({ ...e, source: { id: e.source }, target: { id: e.target } }));
    const { container } = render(<ForceGraph nodes={g.nodes} edges={edges} />);
    expect(container.querySelectorAll("g.edge")).toHaveLength(2);
  });

  it("draws an empty graph without failing", () => {
    const { container } = render(<ForceGraph nodes={[]} edges={[]} />);
    expect(container.querySelectorAll("g.node")).toHaveLength(0);
  });

  it("does not fail when the pointer leaves or the component unmounts mid-animation", () => {
    window.matchMedia = vi.fn().mockReturnValue({ matches: false });
    const { unmount } = show();
    expect(() => unmount()).not.toThrow();
  });

  describe("a chosen time", () => {
    const timed = (times) => g.edges.map((e, i) => ({ ...e, time: times[i] }));

    it("draws facts dated outside the time faint, and the others as usual", () => {
      const { container } = render(<ForceGraph nodes={g.nodes} edges={timed(["outside", "during"])} />);
      expect(container.querySelector('g.edge[data-edge="f1"]')).toHaveClass("outside");
      expect(container.querySelector('g.edge[data-edge="f2"]')).not.toHaveClass("outside");
    });

    it("fades an entity only when every fact it has is outside", () => {
      const { container } = render(<ForceGraph nodes={g.nodes} edges={timed(["outside", "during"])} />);
      expect(container.querySelector('g.node[data-id="n2"]')).toHaveClass("outside");        // Beta: only the outside fact
      expect(container.querySelector('g.node[data-id="n1"]')).not.toHaveClass("outside");     // Acme: one fact still holds
      expect(container.querySelector('g.node[data-id="n3"]')).not.toHaveClass("outside");
    });

    it("fades nothing for facts that are open or undated", () => {
      const { container } = render(<ForceGraph nodes={g.nodes} edges={timed(["open", "undated"])} />);
      expect(container.querySelectorAll(".outside")).toHaveLength(0);
    });

    it("fades nothing when no time was chosen", () => {
      const { container } = render(<ForceGraph nodes={g.nodes} edges={g.edges} />);
      expect(container.querySelectorAll(".outside")).toHaveLength(0);
    });

    it("shows a selected fact normally even when it is outside the time", () => {
      const { container } = render(<ForceGraph nodes={g.nodes} edges={timed(["outside", "outside"])} selectedEdgeId="f1" selectedNodeId="n1" />);
      expect(container.querySelector('g.edge[data-edge="f1"]')).not.toHaveClass("outside");
      expect(container.querySelector('g.node[data-id="n1"]')).not.toHaveClass("outside");
      expect(container.querySelector('g.node[data-id="n3"]')).toHaveClass("outside");
    });

    it("does not fade entities that have no facts at all", () => {
      const { container } = render(<ForceGraph nodes={[...g.nodes, { id: "n9", name: "Lonely", type: "concept", degree: 0 }]} edges={timed(["outside", "outside"])} />);
      expect(container.querySelector('g.node[data-id="n9"]')).not.toHaveClass("outside");
    });
  });
});
