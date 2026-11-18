import { useState } from "react";
import { api } from "../api";
import { useAsync, useToast } from "../hooks";
import { actionsFor, kindText, periodText } from "../lib/conflicts";
import { plural } from "../lib/format";

function Side({ label, fact }) {
  return (
    <div className="stack" style={{ gap: "0.3rem" }}>
      <div className="small muted">{label}</div>
      <strong style={{ overflowWrap: "anywhere" }}>{fact.text}</strong>
      <div className="small">{periodText(fact.valid_from, fact.valid_to)}</div>
      {fact.sources.map((s, i) => (
        <div className="source" key={i}>
          <div className="small"><strong>{s.document_title}</strong></div>
          <blockquote className="quote">{s.quote}</blockquote>
        </div>
      ))}
    </div>
  );
}

function ConflictCard({ c, busy, onDecide }) {
  return (
    <article className="card stack" aria-label={`${c.a.text} and ${c.b.text}`}>
      <div className="row wrap">
        <strong className="grow">{kindText(c.kind)}</strong>
        <span className={`chip tone-${c.severity === "certain" ? "bad" : "wait"}`} title={c.severity === "certain" ? "Their dates surely share time" : "They might share time, or have no dates"}>{c.severity}</span>
        {c.llm_verdict === "yes" && <span className="chip tone-bad" title="The model was asked and thinks they contradict">model: contradict</span>}
        {c.llm_verdict === "no" && <span className="chip tone-ok" title="The model was asked and thinks both can be true (it is often wrong about this)">model: compatible</span>}
        {c.llm_verdict === "unsure" && <span className="chip tone-muted">model: unsure</span>}
      </div>
      <ul className="small" style={{ margin: 0, paddingLeft: "1.1rem" }}>{c.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
      <div className="pair"><Side label="First" fact={c.a} /><Side label="Second" fact={c.b} /></div>
      <div className="row wrap">
        {actionsFor(c).map((a) => (
          <button key={a.id} className={`btn small ${a.id === "keep_a" || a.id === "keep_b" ? "primary" : ""}`} disabled={busy} onClick={() => onDecide(c, a.id)}>{a.label}</button>
        ))}
      </div>
    </article>
  );
}

const DECIDED = { keep_a: "trusted the first", keep_b: "trusted the second", both: "both are true", succession: "the earlier one ended when the later began" };

export default function Conflicts({ onChange }) {
  const open = useAsync(() => api.conflicts("open"), []);
  const resolved = useAsync(() => api.conflicts("resolved"), []);
  const dismissed = useAsync(() => api.conflicts("dismissed"), []);
  const [busy, setBusy] = useState(false);
  const [useLlm, setUseLlm] = useState(false);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");
  const [toast, notify] = useToast();

  const reloadAll = () => { open.reload(true); resolved.reload(true); dismissed.reload(true); if (onChange) onChange(); };
  async function guarded(fn, ok) {
    setBusy(true);
    setError("");
    try {
      const r = await fn();
      if (ok) notify(ok);
      reloadAll();
      return r;
    } catch (e) {
      setError(e.message);
      return null;
    } finally {
      setBusy(false);
    }
  }
  const run = async () => { const r = await guarded(() => api.runConflicts(useLlm)); if (r) setSummary(r); };
  const decide = (c, resolution) => guarded(() => api.resolveConflict(c.id, resolution), `Settled: ${DECIDED[resolution]}`);

  const list = open.data ? open.data.conflicts : [];
  const settled = [...(resolved.data ? resolved.data.conflicts : []), ...(dismissed.data ? dismissed.data.conflicts : [])];

  return (
    <div className="stack">
      <div className="card row wrap">
        <button className="btn" onClick={run} disabled={busy}>Look for conflicts now</button>
        <label className="row small"><input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} /> Ask the model too (slower)</label>
        {summary && <span className="small" role="status">{plural(summary.new, "new conflict")}{summary.removed > 0 ? `, ${summary.removed} no longer apply` : ""}, {summary.open} open{summary.judged > 0 ? `, ${summary.judged} checked by the model` : ""}.</span>}
      </div>
      <p className="muted small">A conflict is two facts that cannot both be true at the same time. Choosing one leaves the other out of the graph and the answers until you undo it. Nothing is deleted.</p>
      {error && <div className="banner error" role="alert">{error}</div>}
      {open.loading && !open.data && <p className="muted" role="status">Loading…</p>}
      {open.error && <div className="banner error" role="alert">{open.error}</div>}
      {open.data && list.length === 0 && <div className="empty"><h2>No open conflicts</h2><p>No two facts clash right now.</p></div>}
      {list.map((c) => <ConflictCard key={c.id} c={c} busy={busy} onDecide={decide} />)}
      {settled.length > 0 && (
        <details>
          <summary>Settled ({settled.length})</summary>
          <div className="stack" style={{ marginTop: "0.6rem" }}>
            {settled.map((c) => (
              <article key={c.id} className="card row wrap" aria-label={`Settled: ${c.a.text} and ${c.b.text}`}>
                <div className="grow">
                  <div>{c.a.text} <span className="muted">vs</span> {c.b.text}</div>
                  <div className="small muted">{DECIDED[c.resolution] || c.resolution}</div>
                </div>
                <button className="btn small" disabled={busy} onClick={() => guarded(() => api.reopenConflict(c.id), "Reopened")}>Reopen</button>
              </article>
            ))}
          </div>
        </details>
      )}
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}
