import { api } from "../api";
import { useAsync } from "../hooks";
import { formatPeriod, plural } from "../lib/format";
import Source from "./Source";

export default function FactPanel({ id, onSelectEntity, onClose }) {
  const fact = useAsync(() => api.fact(id), [id]);
  const f = fact.data;
  return (
    <aside className="side" aria-label="Fact details">
      <div className="row" style={{ marginBottom: "0.5rem" }}>
        <h2 className="grow">Fact</h2>
        <button className="btn small ghost" onClick={onClose} aria-label="Close the fact panel">✕</button>
      </div>
      {fact.loading && <p className="muted" role="status">Loading…</p>}
      {fact.error && <div className="banner error" role="alert">{fact.error}</div>}
      {f && (
        <div className="stack">
          <p style={{ fontSize: "1.05rem" }}>
            <button className="linkbtn" onClick={() => onSelectEntity(f.subject_id)}>{f.subject}</button>{" "}
            <span className="muted"><em>{f.predicate}</em></span>{" "}
            {f.object_is_value ? <strong>{f.object}</strong> : <button className="linkbtn" onClick={() => onSelectEntity(f.object_id)}>{f.object}</button>}
          </p>
          {formatPeriod(f.valid_from, f.valid_to) && <p className="small"><span className="muted">When: </span>{formatPeriod(f.valid_from, f.valid_to)}</p>}
          <div className="sect">
            <h3>{plural(f.sources.length, "source")}</h3>
            <div className="stack">{f.sources.map((s) => <Source key={`${s.chunk_id}-${s.quote}`} source={s} />)}</div>
          </div>
        </div>
      )}
    </aside>
  );
}
