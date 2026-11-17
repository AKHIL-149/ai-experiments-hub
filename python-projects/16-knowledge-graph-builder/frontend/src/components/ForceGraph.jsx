import * as d3 from "d3";
import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import { edgeBundles, endId, linkGeometry, nodeRadius, typeColor, visibleLabels } from "../lib/graph";

const FALLBACK = { width: 800, height: 600 };

/**
 * The graph drawn as SVG. d3-force computes the positions, d3-zoom pans and zooms, d3-drag moves nodes; React draws everything
 * (so labels, focus and clicks are ordinary DOM). Nodes keep their place when the data changes, so expanding a node does not
 * rearrange what you were looking at.
 */
export default function ForceGraph({
  nodes, edges, selectedNodeId = null, selectedEdgeId = null, highlightNodeIds, highlightEdgeIds,
  onSelectNode = () => {}, onSelectEdge = () => {}, onExpandNode = () => {}, onBackground = () => {}, fitSignal = 0,
}) {
  const svgRef = useRef(null);
  const gRef = useRef(null);
  const nodesLayerRef = useRef(null);
  const simRef = useRef(null);
  const zoomRef = useRef(null);
  const simNodes = useRef(new Map());
  const simLinks = useRef([]);
  const frame = useRef(0);
  const [, bump] = useReducer((x) => x + 1, 0);
  const [size, setSize] = useState(FALLBACK);
  const [transform, setTransform] = useState(d3.zoomIdentity);
  const [hoverEdge, setHoverEdge] = useState(null);

  const hlNodes = highlightNodeIds || new Set();
  const hlEdges = highlightEdgeIds || new Set();
  const dimming = hlNodes.size > 0 || hlEdges.size > 0;
  // with a chosen time: facts dated outside it are drawn faint, and so are entities that have nothing left in that time
  const outsideNodes = useMemo(() => {
    const live = new Set(), seen = new Set();
    for (const e of edges) {
      const a = endId(e.source), b = endId(e.target);
      seen.add(a); seen.add(b);
      if (e.time !== "outside") { live.add(a); live.add(b); }
    }
    return new Set([...seen].filter((id) => !live.has(id)));
  }, [edges]);

  // ---- the simulation, made once
  useEffect(() => {
    const sim = d3.forceSimulation()
      .alphaDecay(0.045)
      .force("link", d3.forceLink().id((d) => d.id).distance(95).strength(0.55))
      .force("charge", d3.forceManyBody().strength(-300).distanceMax(520))
      .force("collide", d3.forceCollide().radius((d) => d.r + 9))
      .force("x", d3.forceX(0).strength(0.035))
      .force("y", d3.forceY(0).strength(0.035));
    sim.on("tick", () => {
      if (!frame.current) frame.current = requestAnimationFrame(() => { frame.current = 0; bump(); });
    });
    simRef.current = sim;
    return () => {
      sim.stop();
      if (frame.current) cancelAnimationFrame(frame.current);
    };
  }, []);

  // ---- feed the simulation, keeping positions of nodes that were already there
  useEffect(() => {
    const sim = simRef.current;
    if (!sim) return;
    const old = simNodes.current;
    const next = new Map();
    const neighbours = new Map();
    for (const e of edges) {
      const a = endId(e.source), b = endId(e.target);
      (neighbours.get(a) || neighbours.set(a, []).get(a)).push(b);
      (neighbours.get(b) || neighbours.set(b, []).get(b)).push(a);
    }
    let fresh = 0;
    for (const n of nodes) {
      const prev = old.get(n.id);
      const r = nodeRadius(n.degree);
      if (prev) {
        Object.assign(prev, { name: n.name, type: n.type, degree: n.degree, r });
        next.set(n.id, prev);
        continue;
      }
      // a new node starts next to a neighbour that is already placed, so it does not fly in from far away
      const anchor = (neighbours.get(n.id) || []).map((id) => old.get(id)).find(Boolean);
      const angle = Math.random() * Math.PI * 2;
      const dist = anchor ? 40 : 60 + Math.random() * 120;
      next.set(n.id, {
        id: n.id, name: n.name, type: n.type, degree: n.degree, r,
        x: (anchor ? anchor.x : 0) + Math.cos(angle) * dist, y: (anchor ? anchor.y : 0) + Math.sin(angle) * dist,
      });
      fresh += 1;
    }
    simNodes.current = next;
    const list = [...next.values()];
    simLinks.current = edges
      .filter((e) => next.has(endId(e.source)) && next.has(endId(e.target)))
      .map((e) => ({ id: e.id, predicate: e.predicate, valid_from: e.valid_from, valid_to: e.valid_to, time: e.time, source: endId(e.source), target: endId(e.target) }));
    sim.nodes(list);
    sim.force("link").links(simLinks.current);
    const calm = typeof window !== "undefined" && window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (calm) {
      sim.stop();
      for (let i = 0; i < 250; i += 1) sim.tick();
      bump();
    } else {
      sim.alpha(fresh > 0 ? (old.size ? 0.45 : 1) : 0.15).restart();
    }
    bump();
  }, [nodes, edges]);

  // ---- measure the box
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return undefined;
    const measure = () => {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) setSize({ width: r.width, height: r.height });
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // ---- zoom and pan
  useEffect(() => {
    const svg = d3.select(svgRef.current);
    const zoom = d3.zoom().scaleExtent([0.15, 4]).on("zoom", (ev) => setTransform(ev.transform));
    svg.call(zoom).on("dblclick.zoom", null);
    zoomRef.current = zoom;
    return () => { svg.on(".zoom", null); };
  }, []);

  // ---- drag nodes (one behaviour on the layer; it finds the node under the pointer)
  useEffect(() => {
    const layer = nodesLayerRef.current;
    if (!layer || !gRef.current) return undefined;
    const sim = simRef.current;
    const nodeOf = (ev) => {
      const el = ev.sourceEvent && ev.sourceEvent.target && ev.sourceEvent.target.closest && ev.sourceEvent.target.closest("g.node");
      return el ? simNodes.current.get(el.getAttribute("data-id")) : null;
    };
    const drag = d3.drag()
      .container(gRef.current)
      .clickDistance(4)
      .subject((ev) => nodeOf(ev))
      .filter((ev) => !ev.button && !!ev.target.closest("g.node"))
      .on("start", (ev) => { if (!ev.active) sim.alphaTarget(0.2).restart(); ev.subject.fx = ev.subject.x; ev.subject.fy = ev.subject.y; })
      .on("drag", (ev) => { ev.subject.fx = ev.x; ev.subject.fy = ev.y; })
      .on("end", (ev) => { if (!ev.active) sim.alphaTarget(0); ev.subject.fx = null; ev.subject.fy = null; });
    d3.select(layer).call(drag);
    return () => { d3.select(layer).on(".drag", null); };
  }, []);

  // ---- "fit to screen" whenever the parent asks (fitSignal changes) and on the first data
  const fit = () => {
    const list = [...simNodes.current.values()].filter((n) => Number.isFinite(n.x));
    if (!list.length || !zoomRef.current) return;
    const xs = list.map((n) => n.x), ys = list.map((n) => n.y);
    const pad = 60;
    const w = Math.max(...xs) - Math.min(...xs) + pad * 2, h = Math.max(...ys) - Math.min(...ys) + pad * 2;
    const k = Math.min(1.6, Math.max(0.15, Math.min(size.width / w, size.height / h)));
    const cx = (Math.max(...xs) + Math.min(...xs)) / 2, cy = (Math.max(...ys) + Math.min(...ys)) / 2;
    const t = d3.zoomIdentity.scale(k).translate(-cx, -cy);
    d3.select(svgRef.current).transition().duration(350).call(zoomRef.current.transform, t);
  };
  useEffect(() => {
    const id = setTimeout(fit, 700);
    return () => clearTimeout(id);
  }, [fitSignal]); // eslint-disable-line react-hooks/exhaustive-deps

  const zoomBy = (factor) => d3.select(svgRef.current).transition().duration(200).call(zoomRef.current.scaleBy, factor);

  // ---- what to draw
  const bundles = useMemo(() => edgeBundles(simLinks.current), [nodes, edges]); // eslint-disable-line react-hooks/exhaustive-deps
  const labels = visibleLabels([...simNodes.current.values()], { selectedId: selectedNodeId, highlightIds: hlNodes });
  const showEdgeLabels = simLinks.current.length <= 12 || transform.k >= 1.6;   // otherwise labels appear on hover or selection
  const nodeList = [...simNodes.current.values()].sort((a, b) => (a.id === selectedNodeId) - (b.id === selectedNodeId));
  const cx = size.width / 2, cy = size.height / 2;

  return (
    <div className="graph-svg-box" style={{ position: "relative", width: "100%", height: "100%" }}>
      <svg
        ref={svgRef}
        role="img"
        aria-label={`Graph with ${nodes.length} entities and ${edges.length} facts. Use the list view for a text version.`}
        onClick={(e) => { if (e.target === svgRef.current) onBackground(); }}
      >
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0L10,5L0,10z" fill="#9aa0ac" /></marker>
          <marker id="arrow-hl" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0L10,5L0,10z" fill="#2f5fd0" /></marker>
        </defs>
        <g ref={gRef} transform={`translate(${cx + transform.x},${cy + transform.y}) scale(${transform.k})`}>
          <g className="edges">
            {simLinks.current.map((l) => {
              const s = typeof l.source === "object" ? l.source : simNodes.current.get(l.source);
              const t = typeof l.target === "object" ? l.target : simNodes.current.get(l.target);
              if (!s || !t || !Number.isFinite(s.x) || !Number.isFinite(t.x)) return null;
              const g = linkGeometry(s, t, s.r, t.r, bundles[l.id]);
              const hl = hlEdges.has(l.id), sel = selectedEdgeId === l.id;
              const dim = dimming && !hl && !sel;
              const text = l.predicate + (l.valid_from || l.valid_to ? ` · ${l.valid_from || ""}${l.valid_to ? `–${l.valid_to}` : ""}` : "");
              return (
                <g key={l.id} className={`edge ${hl ? "hl" : ""} ${sel ? "sel" : ""} ${dim ? "dim" : ""} ${l.time === "outside" && !sel ? "outside" : ""}`} data-edge={l.id}
                  onMouseEnter={() => setHoverEdge(l.id)} onMouseLeave={() => setHoverEdge((h) => (h === l.id ? null : h))}>
                  <path className="hit" d={g.d} onClick={() => onSelectEdge(l.id)} />
                  <path d={g.d} markerEnd={hl || sel ? "url(#arrow-hl)" : "url(#arrow)"} pointerEvents="none" />
                  {(showEdgeLabels || hl || sel || hoverEdge === l.id) && <text x={g.labelX} y={g.labelY - 3}>{text}</text>}
                </g>
              );
            })}
          </g>
          <g className="nodes" ref={nodesLayerRef}>
            {nodeList.map((n) => {
              if (!Number.isFinite(n.x)) return null;
              const sel = n.id === selectedNodeId, hl = hlNodes.has(n.id);
              const dim = dimming && !hl && !sel;
              return (
                <g
                  key={n.id}
                  className={`node ${sel ? "sel" : ""} ${hl ? "hl" : ""} ${dim ? "dim" : ""} ${outsideNodes.has(n.id) && !sel ? "outside" : ""}`}
                  data-id={n.id}
                  transform={`translate(${n.x},${n.y})`}
                  tabIndex={0}
                  role="button"
                  aria-label={`${n.name}, ${n.type}, ${n.degree || 0} links${sel ? ", selected" : ""}`}
                  aria-pressed={sel}
                  onClick={() => onSelectNode(n.id)}
                  onDoubleClick={() => onExpandNode(n.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelectNode(n.id); }
                    else if (e.key === "e" || e.key === "E") onExpandNode(n.id);
                  }}
                >
                  <circle r={n.r} fill={typeColor(n.type)} />
                  {labels.has(n.id) && <text y={n.r + 13} textAnchor="middle">{n.name}</text>}
                </g>
              );
            })}
          </g>
        </g>
      </svg>
      <div className="zoom-buttons">
        <button className="btn small" aria-label="Zoom in" onClick={() => zoomBy(1.4)}>+</button>
        <button className="btn small" aria-label="Zoom out" onClick={() => zoomBy(1 / 1.4)}>−</button>
        <button className="btn small" aria-label="Fit the graph to the screen" onClick={fit}>Fit</button>
      </div>
    </div>
  );
}
