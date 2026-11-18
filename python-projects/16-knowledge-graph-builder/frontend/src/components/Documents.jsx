import { useRef, useState } from "react";
import { api } from "../api";
import { useAsync, usePolling, useToast } from "../hooks";
import { documentStatus, isActive, plural, progressOf } from "../lib/format";

function DocumentCard({ doc, onChanged, go, notify }) {
  const st = documentStatus(doc);
  const active = isActive(doc);
  const [busy, setBusy] = useState(false);
  const act = async (fn, okMessage) => {
    setBusy(true);
    try {
      await fn();
      if (okMessage) notify(okMessage);
    } catch (e) {
      notify(e.message);
    } finally {
      setBusy(false);
      onChanged();
    }
  };
  return (
    <article className="card doc" aria-label={doc.title}>
      <div className="row wrap">
        <span className="doc-title grow">{doc.title}</span>
        <span className={`chip tone-${st.tone}`}>{st.label}</span>
      </div>
      <div className="small muted">{st.detail}</div>
      {(active || doc.status === "completed") && (
        <div className={`progress ${doc.status === "completed" ? "done" : ""}`} role="progressbar" aria-valuemin={0} aria-valuemax={100}
          aria-valuenow={Math.round(progressOf(doc) * 100)} aria-label={`Progress of ${doc.title}`}>
          <span style={{ width: `${progressOf(doc) * 100}%` }} />
        </div>
      )}
      <div className="small muted">
        {doc.char_count.toLocaleString()} characters
        {doc.stats && doc.stats.rejected && Object.keys(doc.stats.rejected).length > 0 && (
          <> · {plural(Object.values(doc.stats.rejected).reduce((a, b) => a + b, 0), "candidate")} refused by the checks</>
        )}
        {doc.stats && doc.stats.resolution && doc.stats.resolution.auto_merged > 0 && <> · {plural(doc.stats.resolution.auto_merged, "duplicate name")} merged</>}
        {doc.stats && doc.stats.embedding_error && <> · search index: {doc.stats.embedding_error}</>}
      </div>
      <div className="row wrap">
        {doc.status === "completed" && <button className="btn small" onClick={() => go("graph", { doc: doc.id })}>View graph</button>}
        {doc.status === "completed" && <button className="btn small" onClick={() => go("export", { doc: doc.id })}>Export</button>}
        {active && doc.job && (
          <button className="btn small" disabled={busy || doc.job.cancel_requested} onClick={() => act(() => api.cancelJob(doc.job.id), "Cancelling…")}>
            {doc.job.cancel_requested ? "Stopping…" : "Cancel"}
          </button>
        )}
        {!active && <button className="btn small" disabled={busy} onClick={() => act(() => api.reprocess(doc.id), "Queued to be read again")}>Read again</button>}
        {!active && (
          <button className="btn small danger" disabled={busy}
            onClick={() => { if (window.confirm(`Delete “${doc.title}” and the facts only it supports?`)) act(() => api.deleteDocument(doc.id), "Deleted"); }}>
            Delete
          </button>
        )}
      </div>
    </article>
  );
}

function AddDocument({ onAdded, notify }) {
  const fileRef = useRef(null);
  const [over, setOver] = useState(false);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function send(call) {
    setError("");
    setBusy(true);
    try {
      await call();
      onAdded();
      return true;
    } catch (e) {
      setError(e.message);
      return false;
    } finally {
      setBusy(false);
    }
  }
  async function files(list) {
    for (const f of Array.from(list || [])) {
      const ok = await send(() => api.uploadFile(f));
      if (!ok) break;
      notify(`Added “${f.name}”`);
    }
    if (fileRef.current) fileRef.current.value = "";
  }

  return (
    <section className="card stack" aria-label="Add documents">
      <div
        className={`dropzone ${over ? "over" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); files(e.dataTransfer.files); }}
      >
        <p><strong>Drop files here</strong> or <button type="button" className="linkbtn" onClick={() => fileRef.current && fileRef.current.click()}>choose files</button></p>
        <p className="muted small">.txt, .md, .pdf or .docx</p>
        <input ref={fileRef} type="file" multiple accept=".txt,.md,.markdown,.pdf,.docx" className="sr-only" aria-label="Choose files" onChange={(e) => files(e.target.files)} />
      </div>
      <details>
        <summary>Or paste text</summary>
        <form className="stack" style={{ marginTop: "0.6rem" }} onSubmit={async (e) => {
          e.preventDefault();
          if (await send(() => api.addText(title, text))) { setTitle(""); setText(""); notify(`Added “${title}”`); }
        }}>
          <div className="field"><label htmlFor="paste-title">Title</label><input id="paste-title" type="text" value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={300} /></div>
          <div className="field"><label htmlFor="paste-text">Text</label><textarea id="paste-text" value={text} onChange={(e) => setText(e.target.value)} required minLength={20} /></div>
          <div><button className="btn primary" disabled={busy}>Add text</button></div>
        </form>
      </details>
      {error && <div className="banner error" role="alert">{error}</div>}
    </section>
  );
}

export default function Documents({ go, onChange }) {
  const docs = useAsync(() => api.documents(), []);
  const [toast, notify] = useToast();
  const list = docs.data ? docs.data.documents : [];
  const active = list.filter(isActive);
  usePolling(() => docs.reload(true), active.length ? 2000 : 15000);
  const refresh = () => { docs.reload(true); if (onChange) onChange(); };

  const waiting = list.filter((d) => d.status === "pending").length;
  const reading = list.filter((d) => d.status === "processing").length;

  return (
    <div className="page stack">
      <div className="page-head">
        <h1>Documents</h1>
        {(waiting > 0 || reading > 0) && <span className="muted small" role="status">{reading > 0 && `${reading} being read`}{reading > 0 && waiting > 0 && " · "}{waiting > 0 && `${waiting} waiting`}</span>}
      </div>
      <AddDocument onAdded={refresh} notify={notify} />
      {docs.error && <div className="banner error" role="alert">{docs.error} <button className="linkbtn" onClick={() => docs.reload()}>Try again</button></div>}
      {docs.loading && !docs.data && <p className="muted" role="status">Loading documents…</p>}
      {docs.data && list.length === 0 && (
        <div className="empty"><h2>No documents yet</h2><p>Add a text, Word or PDF file above. It is read in the background and its facts appear in the graph.</p></div>
      )}
      <div>{list.map((d) => <DocumentCard key={d.id} doc={d} onChanged={refresh} go={go} notify={notify} />)}</div>
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}
