import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { useAsync, useDebounced, useToast } from "../hooks";
import { formatPeriod, plural } from "../lib/format";
import { clampYear, timeSummary, validAt, yearOf } from "../lib/time";
import { TYPE_ORDER, countByType, filterGraph, mergeGraph, pathHighlight, searchNodes, typeColor, typeLabel } from "../lib/graph";
import EntityPanel from "./EntityPanel";
import FactPanel from "./FactPanel";
import ForceGraph from "./ForceGraph";
import TypeChip from "./TypeChip";

const LIMIT = 300;
const EMPTY = { nodes: [], edges: [] };

function ListView({ graph, onSelectNode, onSelectEdge }) {
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const name = (end) => (byId.get(typeof end === "object" ? end.id : end) || {}).name || "?";
  return (
    <div className="list-view" style={{ gridColumn: "1" }}>
      <h2 style={{ marginBottom: "0.5rem" }}>Entities ({graph.nodes.length})</h2>
      <table className="data" aria-label="Entities">
        <thead><tr><th>Name</th><th>Type</th><th>Links</th></tr></thead>
        <tbody>
          {[...graph.nodes].sort((a, b) => (b.degree || 0) - (a.degree || 0)).map((n) => (
            <tr key={n.id}><td><button className="linkbtn" onClick={() => onSelectNode(n.id)}>{n.name}</button></td><td><TypeChip type={n.type} /></td><td>{n.degree || 0}</td></tr>
          ))}
        </tbody>
      </table>
      <h2 style={{ margin: "1.2rem 0 0.5rem" }}>Facts ({graph.edges.length})</h2>
      <table className="data" aria-label="Facts">
        <thead><tr><th>Subject</th><th>Relation</th><th>Object</th><th>When</th><th>Sources</th></tr></thead>
        <tbody>
          {graph.edges.map((e) => (
            <tr key={e.id}>
              <td>{name(e.source)}</td>
              <td><button className="linkbtn" onClick={() => onSelectEdge(e.id)}>{e.predicate}</button></td>
              <td>{name(e.target)}</td>
              <td>{formatPeriod(e.valid_from, e.valid_to)}</td>
              <td>{e.source_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** "Any time", or one year to look at: facts dated outside it fade, the rest stay */
function TimeControl({ at, setAt, span }) {
  const has = span && span.first_year != null;
  if (!has) return null;
  const year = yearOf(at);
  const set = (y) => setAt(String(clampYear(y, span)));
  return (
    <div className="row timebox" role="group" aria-label="Time">
      <button className="chip" aria-pressed={at === ""} onClick={() => setAt("")}>Any time</button>
      <button className="chip" aria-pressed={at === "now"} onClick={() => setAt("now")} title="Facts that have not ended">Now</button>
      <button className="btn small ghost" aria-label="Previous year" disabled={at === "" || at === "now" || year <= span.first_year} onClick={() => set(year - 1)}>◀</button>
      <label className="sr-only" htmlFor="graph-year">Year</label>
      <input id="graph-year" type="range" min={span.first_year} max={span.last_year} value={year || span.last_year}
        onChange={(e) => set(Number(e.target.value))} aria-valuetext={year ? String(year) : "no year chosen"} style={{ width: 130 }} />
      <button className="btn small ghost" aria-label="Next year" disabled={at === "" || at === "now" || year >= span.last_year} onClick={() => set(year + 1)}>▶</button>
      <span className="small" aria-live="polite" style={{ minWidth: "3.2rem" }}>{at === "now" ? "now" : year && at ? at : "any"}</span>
    </div>
  );
}

export default function GraphView({ params, go }) {
  const [graph, setGraph] = useState(EMPTY);
  const [meta, setMeta] = useState({ total_nodes: 0, total_edges: 0, truncated: false });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [docId, setDocId] = useState(params.doc || "");
  const [types, setTypes] = useState(new Set());
  const [selected, setSelected] = useState(null);      // { kind: "node" | "edge", id }
  const [highlight, setHighlight] = useState({ nodeIds: new Set(), edgeIds: new Set() });
  const [pathFrom, setPathFrom] = useState(null);
  const [pathNote, setPathNote] = useState(null);
  const [view, setView] = useState("graph");
  const [fitSignal, setFitSignal] = useState(0);
  const [query, setQuery] = useState("");
  const [at, setAt] = useState(validAt(params.at));        // "" = any time; else YYYY[-MM[-DD]] or "now"
  const [timeCounts, setTimeCounts] = useState(null);
  const [toast, notify] = useToast();
  const span = useAsync(() => api.stats().then((s) => s.time), []);
  useEffect(() => { if (params.at !== undefined) setAt(validAt(params.at)); }, [params.at]);   // an address with a new time moves the control
  const atApplied = useDebounced(at, 250);
  const atRef = useRef(atApplied);
  atRef.current = atApplied;
  const graphRef = useRef(graph);
  graphRef.current = graph;
  const docs = useAsync(() => api.documents(), []);

  // ---- load the graph (again) when the document filter changes
  const load = useCallback(async (keepSelection = false) => {
    setLoading(true);
    setError("");
    try {
      const g = await api.graph({ documentId: docId || undefined, limit: LIMIT, at: atRef.current });
      setGraph({ nodes: g.nodes, edges: g.edges });
      setTimeCounts(g.time_counts || null);
      setMeta({ total_nodes: g.total_nodes, total_edges: g.total_edges, truncated: g.truncated });
      if (!keepSelection) { setSelected(null); setHighlight({ nodeIds: new Set(), edgeIds: new Set() }); setPathFrom(null); setPathNote(null); }
      setFitSignal((s) => s + 1);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [docId]);
  useEffect(() => { load(); }, [load]);
  // moving the time reloads the same graph with the facts re-marked; what you selected stays selected
  const firstAt = useRef(true);
  useEffect(() => {
    if (firstAt.current) { firstAt.current = false; return; }
    load(true);
  }, [atApplied]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- bring more of the graph on screen
  const addToGraph = useCallback((more) => setGraph((g) => mergeGraph(g, more)), []);
  const expand = useCallback(async (id, depth = 1) => {
    try {
      const more = await api.neighborhood(id, depth, 200, atRef.current);
      const before = graphRef.current.nodes.length;
      const merged = mergeGraph(graphRef.current, more);
      setGraph(merged);
      notify(merged.nodes.length > before ? `Added ${plural(merged.nodes.length - before, "entity", "entities")}` : "Nothing more to show here");
      return merged;
    } catch (e) {
      notify(e.message);
      return null;
    }
  }, [notify]);

  const focusEntity = useCallback(async (id) => {
    if (!graphRef.current.nodes.some((n) => n.id === id)) await expand(id);
    setSelected({ kind: "node", id });
  }, [expand]);

  // ---- arrive from another screen: ?entity=ID, ?fact=ID, ?facts=ID,ID (the facts an answer cited)
  const handled = useRef("");
  useEffect(() => {
    if (loading) return;
    const key = `${params.entity || ""}|${params.fact || ""}|${params.facts || ""}`;
    if (key === "||" || handled.current === key) return;
    handled.current = key;
    (async () => {
      if (params.entity) { await focusEntity(params.entity); return; }
      const ids = (params.facts || params.fact || "").split(",").filter(Boolean);
      const edgeIds = new Set(), nodeIds = new Set();
      for (const fid of ids) {
        try {
          const f = await api.fact(fid);
          await expandInto(f.subject_id);
          edgeIds.add(fid);
          nodeIds.add(f.subject_id);
          if (f.object_id) nodeIds.add(f.object_id);
        } catch (e) {
          notify(e.message);
        }
      }
      setHighlight({ nodeIds, edgeIds });
      if (ids.length === 1) setSelected({ kind: "edge", id: ids[0] });
      setFitSignal((s) => s + 1);
    })();
    async function expandInto(id) {
      if (graphRef.current.nodes.some((n) => n.id === id)) return;
      const more = await api.neighborhood(id, 1, 200, atRef.current);
      const merged = mergeGraph(graphRef.current, more);
      graphRef.current = merged;
      setGraph(merged);
    }
  }, [params.entity, params.fact, params.facts, loading, focusEntity, notify]);

  // ---- selecting things
  const selectNode = useCallback(async (id) => {
    if (pathFrom && pathFrom !== id) {
      try {
        const r = await api.path(pathFrom, id, 4);
        if (!r.paths.length) { setPathNote({ text: "No connection within 4 links.", steps: [] }); setHighlight({ nodeIds: new Set([pathFrom, id]), edgeIds: new Set() }); }
        else {
          const depth = Math.min(2, Math.ceil(r.paths[0].length / 2));
          const a = await api.neighborhood(pathFrom, depth, 200, atRef.current), b = await api.neighborhood(id, depth, 200, atRef.current);
          const merged = mergeGraph(mergeGraph(graphRef.current, a), b);
          graphRef.current = merged;
          setGraph(merged);
          setHighlight(pathHighlight(r.paths, merged.nodes));
          setPathNote({ text: `${r.from} → ${r.to}: ${plural(r.paths[0].length, "step")}`, steps: r.paths[0] });
        }
      } catch (e) {
        notify(e.message);
      }
      setPathFrom(null);
      return;
    }
    setSelected({ kind: "node", id });
  }, [pathFrom, notify]);

  const clearHighlights = () => { setHighlight({ nodeIds: new Set(), edgeIds: new Set() }); setPathNote(null); setPathFrom(null); };

  // ---- search
  const dq = useDebounced(query, 250);
  const local = useMemo(() => searchNodes(graph.nodes, dq, 6), [graph.nodes, dq]);
  const remote = useAsync(async () => {
    const q = dq.trim();
    if (q.length < 2) return { entities: [] };
    return api.entities(q, undefined, 8);
  }, [dq]);
  const results = useMemo(() => {
    const seen = new Set(local.map((n) => n.id));
    const extra = ((remote.data && remote.data.entities) || []).filter((e) => !seen.has(e.id));
    return [...local.map((n) => ({ id: n.id, name: n.name, type: n.type })), ...extra].slice(0, 8);
  }, [local, remote.data]);

  // ---- derived
  const counts = useMemo(() => countByType(graph.nodes), [graph.nodes]);
  const shown = useMemo(() => filterGraph(graph, { types }), [graph, types]);
  const toggleType = (t) => setTypes((s) => { const n = new Set(s); if (n.has(t)) n.delete(t); else n.add(t); return n; });
  const typeList = TYPE_ORDER.filter((t) => counts[t]).concat(Object.keys(counts).filter((t) => !TYPE_ORDER.includes(t)));
  const completedDocs = ((docs.data && docs.data.documents) || []).filter((d) => d.status === "completed");

  const panel = selected && (selected.kind === "node"
    ? <EntityPanel id={selected.id} at={atApplied} pathFrom={pathFrom} onExpand={(id) => expand(id)} onClose={() => setSelected(null)}
        onAsk={(e) => go("ask", { q: `What do we know about ${e.name}?` })} onStartPath={(id) => { setPathFrom((p) => (p === id ? null : id)); setPathNote(null); }}
        onSelectFact={(id) => setSelected({ kind: "edge", id })} onSelectEntity={focusEntity}
        onMerged={async (keepId, name) => { notify(`Merged into “${name}”`); await load(true); setSelected({ kind: "node", id: keepId }); }} />
    : <FactPanel id={selected.id} onSelectEntity={focusEntity} onClose={() => setSelected(null)} onOpenConflicts={() => go("review", { tab: "conflicts" })} />);

  const empty = !loading && !error && graph.nodes.length === 0;

  return (
    <div className={`graph-page ${panel && view === "graph" ? "" : "no-panel"}`}>
      <div className="toolbar" role="toolbar" aria-label="Graph controls">
        <div className="search-wrap">
          <label className="sr-only" htmlFor="graph-search">Find an entity</label>
          <input id="graph-search" type="search" placeholder="Find an entity…" value={query} onChange={(e) => setQuery(e.target.value)} autoComplete="off" />
          {query.trim().length >= 1 && results.length > 0 && (
            <ul className="suggest" aria-label="Matching entities">
              {results.map((r) => (
                <li key={r.id}><button onClick={() => { setQuery(""); focusEntity(r.id); }}><TypeChip type={r.type} /> {r.name}</button></li>
              ))}
            </ul>
          )}
        </div>
        <label className="sr-only" htmlFor="graph-doc">Document</label>
        <select id="graph-doc" value={docId} onChange={(e) => { setDocId(e.target.value); }} style={{ width: "auto", maxWidth: 220 }}>
          <option value="">All documents</option>
          {completedDocs.map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}
        </select>
        <div className="row wrap" role="group" aria-label="Show these kinds of entity">
          {typeList.map((t) => (
            <button key={t} className="chip" style={{ "--c": typeColor(t) }} aria-pressed={types.has(t)} onClick={() => toggleType(t)}>
              <span className="swatch" aria-hidden="true" />{typeLabel(t)} {counts[t]}
            </button>
          ))}
        </div>
        <TimeControl at={at} setAt={setAt} span={span.data} />
        <span className="spacer" />
        <div className="row" role="group" aria-label="View">
          <button className="btn small" aria-pressed={view === "graph"} onClick={() => setView("graph")} style={view === "graph" ? { borderColor: "var(--accent)", color: "var(--accent)" } : undefined}>Graph</button>
          <button className="btn small" aria-pressed={view === "list"} onClick={() => setView("list")} style={view === "list" ? { borderColor: "var(--accent)", color: "var(--accent)" } : undefined}>List</button>
        </div>
      </div>

      {view === "graph" && (
        <div className="canvas-wrap">
          {loading && <div className="canvas-note" role="status">Loading the graph…</div>}
          {error && <div className="canvas-note banner error" role="alert">{error} <button className="linkbtn" onClick={() => load()}>Try again</button></div>}
          {empty && (
            <div className="empty" style={{ position: "absolute", inset: 0, display: "grid", placeContent: "center" }}>
              <h2>Your graph is empty</h2>
              <p>Add a document and its facts appear here.</p>
              <p style={{ marginTop: "0.8rem" }}><button className="btn primary" onClick={() => go("documents")}>Add documents</button></p>
            </div>
          )}
          {!empty && graph.nodes.length > 0 && (
            <ForceGraph
              nodes={shown.nodes} edges={shown.edges}
              selectedNodeId={selected && selected.kind === "node" ? selected.id : null}
              selectedEdgeId={selected && selected.kind === "edge" ? selected.id : null}
              highlightNodeIds={highlight.nodeIds} highlightEdgeIds={highlight.edgeIds}
              onSelectNode={selectNode} onSelectEdge={(id) => setSelected({ kind: "edge", id })} onExpandNode={(id) => expand(id)}
              onBackground={() => setSelected(null)} fitSignal={fitSignal}
            />
          )}
          {!empty && (
            <div className="canvas-note" role="status">
              <span>{plural(shown.nodes.length, "entity", "entities")} · {plural(shown.edges.length, "fact")}</span>
              {at && timeCounts && <span role="status" aria-label="Facts in the chosen time">In {at === "now" ? "now" : at}: {timeSummary(timeCounts)}{timeCounts.outside ? " (faded: dated outside)" : ""}</span>}
              {meta.truncated && <span className="muted">Showing the {LIMIT} best connected of {meta.total_nodes.toLocaleString()}. Search or open “Show neighbours” to reach the others.</span>}
              {pathFrom && <span className="chip tone-work">Pick the entity to connect to</span>}
              {(highlight.nodeIds.size > 0 || highlight.edgeIds.size > 0 || pathFrom) && <button className="btn small" onClick={clearHighlights}>Clear highlight</button>}
            </div>
          )}
          {pathNote && (
            <div className="card" style={{ position: "absolute", left: "0.75rem", top: "0.75rem", maxWidth: 380 }} role="status" aria-label="Path found">
              <strong>{pathNote.text}</strong>
              <ol className="small" style={{ margin: "0.3rem 0 0", paddingLeft: "1.1rem" }}>
                {pathNote.steps.map((s) => <li key={s.fact_id}>{s.from} <em className="muted">{s.predicate}</em> {s.to}</li>)}
              </ol>
            </div>
          )}
          {!empty && (
            <div className="legend" aria-hidden="true">
              {typeList.map((t) => <span key={t} className="row"><span className="dot" style={{ background: typeColor(t) }} />{typeLabel(t)}</span>)}
            </div>
          )}
        </div>
      )}
      {view === "list" && <ListView graph={shown} onSelectNode={(id) => { setSelected({ kind: "node", id }); setView("graph"); }} onSelectEdge={(id) => { setSelected({ kind: "edge", id }); setView("graph"); }} />}
      {panel && view === "graph" && panel}
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}
