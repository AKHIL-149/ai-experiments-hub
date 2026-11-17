import { useState } from "react";
import { api } from "../api";
import { useAsync, useDebounced } from "../hooks";
import { formatPeriod, plural } from "../lib/format";
import TypeChip from "./TypeChip";

function FactRow({ f, side, onSelectFact, onSelectEntity }) {
  const when = formatPeriod(f.valid_from, f.valid_to);
  const other = side === "out" ? { id: f.object_id, name: f.object } : { id: f.subject_id, name: f.subject };
  return (
    <li>
      {side === "in" && (f.object_is_value ? <span>{other.name}</span> : <button className="linkbtn" onClick={() => onSelectEntity(other.id)}>{other.name}</button>)}
      <button className="linkbtn pred" onClick={() => onSelectFact(f.id)} title="Show where this was read">{f.predicate}</button>
      {side === "out" && (f.object_is_value ? <strong>{f.object}</strong> : <button className="linkbtn" onClick={() => onSelectEntity(other.id)}>{other.name}</button>)}
      {when && <span className="chip" title="When the text says this held">{when}</span>}
      {f.source_count > 1 && <span className="muted small" title={`${f.source_count} places in your documents say this`}>×{f.source_count}</span>}
    </li>
  );
}

function MergeBox({ entity, onMerged, onClose }) {
  const [q, setQ] = useState("");
  const dq = useDebounced(q, 200);
  const found = useAsync(() => (dq.trim().length >= 2 ? api.entities(dq.trim(), undefined, 8) : Promise.resolve({ entities: [] })), [dq]);
  const [other, setOther] = useState(null);
  const [keepThis, setKeepThis] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const options = (found.data ? found.data.entities : []).filter((e) => e.id !== entity.id);

  async function merge() {
    setBusy(true);
    setError("");
    try {
      const keep = keepThis ? entity : other, absorb = keepThis ? other : entity;
      await api.merge(keep.id, absorb.id);
      onMerged(keep.id, keep.name);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card stack" style={{ background: "#fcfbf8" }}>
      <div className="row"><h3 className="grow">Merge with another entity</h3><button className="btn small ghost" onClick={onClose} aria-label="Cancel merging">✕</button></div>
      {!other && (
        <>
          <div className="field">
            <label htmlFor="merge-search">Find the other name</label>
            <input id="merge-search" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Type at least 2 letters" />
          </div>
          <ul className="suggest" style={{ position: "static", boxShadow: "none" }} aria-label="Matches">
            {options.map((o) => (
              <li key={o.id}><button onClick={() => setOther(o)}><TypeChip type={o.type} /> {o.name}</button></li>
            ))}
            {dq.trim().length >= 2 && !found.loading && options.length === 0 && <li className="muted small" style={{ padding: "0.4rem" }}>No other entity matches.</li>}
          </ul>
        </>
      )}
      {other && (
        <div className="stack">
          <p>“{entity.name}” and “{other.name}” become one entity; every fact and source is kept. You can undo it in Review.</p>
          <fieldset style={{ border: "none", padding: 0, margin: 0 }}>
            <legend className="label">Keep this name</legend>
            <label className="row"><input type="radio" name="keep" checked={keepThis} onChange={() => setKeepThis(true)} /> {entity.name}</label>
            <label className="row"><input type="radio" name="keep" checked={!keepThis} onChange={() => setKeepThis(false)} /> {other.name}</label>
          </fieldset>
          {error && <div className="banner error" role="alert">{error}</div>}
          <div className="row"><button className="btn primary" disabled={busy} onClick={merge}>{busy ? "Merging…" : "Merge"}</button><button className="btn" onClick={() => setOther(null)}>Back</button></div>
        </div>
      )}
    </div>
  );
}

export default function EntityPanel({ id, pathFrom, onExpand, onAsk, onStartPath, onSelectFact, onSelectEntity, onMerged, onClose }) {
  const entity = useAsync(() => api.entity(id), [id]);
  const [merging, setMerging] = useState(false);
  const e = entity.data;
  const attrs = e ? e.outgoing.filter((f) => f.object_is_value) : [];
  const out = e ? e.outgoing.filter((f) => !f.object_is_value) : [];

  return (
    <aside className="side" aria-label="Entity details">
      <div className="row" style={{ marginBottom: "0.5rem" }}>
        <h2 className="grow">{e ? e.name : "Entity"}</h2>
        <button className="btn small ghost" onClick={onClose} aria-label="Close the entity panel">✕</button>
      </div>
      {entity.loading && <p className="muted" role="status">Loading…</p>}
      {entity.error && <div className="banner error" role="alert">{entity.error}</div>}
      {e && (
        <div className="stack">
          <div className="row wrap">
            <TypeChip type={e.type} />
            <span className="muted small">{plural(e.outgoing.length + e.incoming.length, "fact")}</span>
          </div>
          {e.aliases.length > 0 && <p className="small"><span className="muted">Also written: </span>{e.aliases.join(", ")}</p>}
          <div className="row wrap">
            <button className="btn small" onClick={() => onExpand(e.id)}>Show neighbours</button>
            <button className="btn small" onClick={() => onAsk(e)}>Ask about this</button>
            <button className="btn small" onClick={() => onStartPath(e.id)} aria-pressed={pathFrom === e.id}>{pathFrom === e.id ? "Pick the other end…" : "Find a path to…"}</button>
            <button className="btn small" onClick={() => setMerging((m) => !m)} aria-expanded={merging}>Merge…</button>
          </div>
          {merging && <MergeBox entity={e} onClose={() => setMerging(false)} onMerged={(keepId, name) => { setMerging(false); onMerged(keepId, name); }} />}
          {attrs.length > 0 && (
            <div className="sect"><h3>Details</h3>
              <ul className="facts">{attrs.map((f) => <FactRow key={f.id} f={f} side="out" onSelectFact={onSelectFact} onSelectEntity={onSelectEntity} />)}</ul>
            </div>
          )}
          {out.length > 0 && (
            <div className="sect"><h3>Links from this</h3>
              <ul className="facts">{out.map((f) => <FactRow key={f.id} f={f} side="out" onSelectFact={onSelectFact} onSelectEntity={onSelectEntity} />)}</ul>
            </div>
          )}
          {e.incoming.length > 0 && (
            <div className="sect"><h3>Links to this</h3>
              <ul className="facts">{e.incoming.map((f) => <FactRow key={f.id} f={f} side="in" onSelectFact={onSelectFact} onSelectEntity={onSelectEntity} />)}</ul>
            </div>
          )}
          {e.outgoing.length + e.incoming.length === 0 && <p className="muted">No facts about this entity.</p>}
        </div>
      )}
    </aside>
  );
}
