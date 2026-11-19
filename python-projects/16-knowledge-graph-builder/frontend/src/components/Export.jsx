import { useState } from "react";
import { api, exportUrl } from "../api";
import { useAsync } from "../hooks";
import { FORMATS, holdsText, leftOutText } from "../lib/export";

export default function Export({ params = {} }) {
  const [documentId, setDocumentId] = useState(params.doc || "");
  const [sources, setSources] = useState(true);
  const [schema, setSchema] = useState(true);
  const docs = useAsync(() => api.documents(), []);
  const summary = useAsync(() => api.exportSummary(documentId), [documentId]);
  const readable = docs.data ? docs.data.documents.filter((d) => d.status === "completed") : [];
  const counts = summary.data;
  const empty = counts && counts.facts === 0;
  const options = { documentId, sources, schema };

  return (
    <div className="page stack">
      <div className="page-head"><h1>Export</h1><span className="muted small">Take the graph with you: as data, as tables, or as a script for a graph database.</span></div>
      <section className="card stack" aria-label="What to export">
        <div className="field">
          <label htmlFor="scope">What to include</label>
          <select id="scope" value={documentId} onChange={(e) => setDocumentId(e.target.value)}>
            <option value="">All documents</option>
            {readable.map((d) => <option key={d.id} value={d.id}>Only facts read from: {d.title}</option>)}
          </select>
        </div>
        <label className="row"><input type="checkbox" checked={sources} onChange={(e) => setSources(e.target.checked)} /> Include the quote each fact was read from</label>
        {summary.error && <div className="banner error" role="alert">{summary.error}</div>}
        {counts && <p role="status" className="small"><strong>This export holds:</strong> {holdsText(counts, sources)}.</p>}
        {counts && leftOutText(counts) && <p className="small muted">{leftOutText(counts)}</p>}
      </section>
      {empty && <div className="empty"><h2>Nothing to export yet</h2><p>Add a document on the Documents screen. Once it is read, its facts can be exported here.</p></div>}
      <div className="stack">
        {FORMATS.map((f) => (
          <article className="card stack" key={f.id} aria-label={f.title}>
            <div className="row wrap"><h2 className="grow">{f.title}</h2><span className="small muted">{f.file}</span></div>
            <p className="small">{f.blurb}</p>
            {f.id === "cypher" && <label className="row small"><input type="checkbox" checked={schema} onChange={(e) => setSchema(e.target.checked)} /> Start with constraint statements (Neo4j 5 syntax; leave them out for other databases)</label>}
            <div className="row">
              {empty || !counts
                ? <button className="btn primary" disabled>Download {f.title}</button>
                : <a className="btn primary" href={exportUrl(f.id, options)} download>Download {f.title}</a>}
            </div>
          </article>
        ))}
      </div>
      <p className="small muted">Facts only appear once. Dates are kept as written in the documents (a year, a month or a day). Exports are made from your account only.</p>
    </div>
  );
}
