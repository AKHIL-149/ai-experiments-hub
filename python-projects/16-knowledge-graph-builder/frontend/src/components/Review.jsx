import { useState } from "react";
import { api } from "../api";
import { useAsync, useToast } from "../hooks";
import { percent, plural } from "../lib/format";
import TypeChip from "./TypeChip";

function Entity({ e }) {
  return (
    <div>
      <div className="row wrap"><strong style={{ overflowWrap: "anywhere" }}>{e.name}</strong><TypeChip type={e.type} /></div>
      <div className="small muted">{plural(e.fact_count, "fact")}{e.aliases.length > 0 && <> · also written {e.aliases.join(", ")}</>}</div>
      {e.sample_facts.length > 0 && <ul className="small" style={{ margin: "0.3rem 0 0", paddingLeft: "1.1rem" }}>{e.sample_facts.map((f) => <li key={f}>{f}</li>)}</ul>}
    </div>
  );
}

function SuggestionCard({ s, onDecide, busy }) {
  return (
    <article className="card stack" aria-label={`${s.a.name} and ${s.b.name}`}>
      <div className="row wrap">
        <strong>Same thing?</strong>
        <span className="meter" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(s.score * 100)} aria-label="How sure"><span style={{ width: percent(s.score) }} /></span>
        <span className="small muted">{percent(s.score)} sure</span>
        {s.llm_verdict === "yes" && <span className="chip tone-ok" title="The model was asked and agreed">model agrees</span>}
        {s.llm_verdict === "no" && <span className="chip tone-wait" title="The model was asked and disagreed (it is often wrong about this)">model disagrees</span>}
      </div>
      <ul className="small" style={{ margin: 0, paddingLeft: "1.1rem" }}>{s.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
      <div className="pair"><Entity e={s.a} /><Entity e={s.b} /></div>
      <div className="row wrap">
        <button className="btn small primary" disabled={busy} onClick={() => onDecide("accept", s, s.a.id)}>Merge, keep “{s.a.name}”</button>
        <button className="btn small primary" disabled={busy} onClick={() => onDecide("accept", s, s.b.id)}>Merge, keep “{s.b.name}”</button>
        <button className="btn small" disabled={busy} onClick={() => onDecide("reject", s)}>Different things</button>
      </div>
    </article>
  );
}

export default function Review({ onChange }) {
  const [tab, setTab] = useState("pending");
  const pending = useAsync(() => api.suggestions("pending"), []);
  const rejected = useAsync(() => api.suggestions("rejected"), []);
  const merges = useAsync(() => api.merges(true), []);
  const [busy, setBusy] = useState(false);
  const [toast, notify] = useToast();
  const [useLlm, setUseLlm] = useState(false);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");

  const reloadAll = () => { pending.reload(true); rejected.reload(true); merges.reload(true); if (onChange) onChange(); };

  async function guarded(fn, ok) {
    setBusy(true);
    setError("");
    try {
      const r = await fn();
      if (ok) notify(ok(r));
      reloadAll();
      return r;
    } catch (e) {
      setError(e.message);
      return null;
    } finally {
      setBusy(false);
    }
  }

  const decide = (kind, s, keepId) => kind === "accept"
    ? guarded(() => api.accept(s.id, keepId), (r) => `Merged “${r.absorbed}” into “${r.kept}”`)
    : guarded(() => api.reject(s.id), () => "Kept apart");
  const run = async () => {
    const r = await guarded(() => api.runResolution(useLlm), null);
    if (r) setSummary(r);
  };

  const list = pending.data ? pending.data.suggestions : [];
  const history = merges.data ? merges.data.merges : [];
  const tabs = [["pending", `Suggestions${list.length ? ` (${list.length})` : ""}`], ["merged", "Merged"], ["rejected", "Kept apart"]];

  return (
    <div className="page stack">
      <div className="page-head">
        <h1>Review</h1>
        <span className="muted small">The same thing is often written differently. Obvious cases are merged for you; the unsure ones wait here.</span>
      </div>
      <div className="card row wrap">
        <button className="btn" onClick={run} disabled={busy}>Look for duplicates now</button>
        <label className="row small"><input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} /> Ask the model for a second opinion (slower)</label>
        {summary && (
          <span className="small" role="status">
            {plural(summary.auto_merged, "merge")} made, {plural(summary.suggestions_new, "new suggestion")}{summary.judged > 0 ? `, ${summary.judged} checked by the model` : ""}.
          </span>
        )}
      </div>
      {error && <div className="banner error" role="alert">{error}</div>}
      <div className="tabs" role="tablist" aria-label="Review sections">
        {tabs.map(([id, label]) => <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}>{label}</button>)}
      </div>

      {tab === "pending" && (
        <div>
          {pending.loading && !pending.data && <p className="muted" role="status">Loading…</p>}
          {pending.error && <div className="banner error" role="alert">{pending.error}</div>}
          {pending.data && list.length === 0 && <div className="empty"><h2>Nothing to review</h2><p>No unsure duplicates right now.</p></div>}
          {list.map((s) => <SuggestionCard key={s.id} s={s} onDecide={decide} busy={busy} />)}
        </div>
      )}

      {tab === "merged" && (
        <div>
          {merges.data && history.length === 0 && <div className="empty"><h2>No merges yet</h2></div>}
          {history.map((m) => (
            <article key={m.id} className="card row wrap" aria-label={`${m.absorbed} into ${m.kept}`} style={m.undone ? { opacity: 0.6 } : undefined}>
              <div className="grow">
                <div>“{m.absorbed}” → <strong>{m.kept}</strong> {m.undone && <span className="chip tone-muted">undone</span>}</div>
                <div className="small muted">{m.how === "auto" ? "merged automatically" : m.how === "manual" ? "merged by you" : "you accepted a suggestion"}{m.reasons && m.reasons.length > 0 && ` · ${m.reasons[0]}`}</div>
              </div>
              {!m.undone && <button className="btn small" disabled={busy} onClick={() => guarded(() => api.undo(m.id), () => `Undid the merge of “${m.absorbed}”`)}>Undo</button>}
            </article>
          ))}
        </div>
      )}

      {tab === "rejected" && (
        <div>
          {rejected.data && rejected.data.suggestions.length === 0 && <div className="empty"><h2>Nothing kept apart</h2><p>Pairs you mark as different things appear here and are not suggested again.</p></div>}
          {rejected.data && rejected.data.suggestions.map((s) => (
            <article key={s.id} className="card" aria-label={`${s.a.name} and ${s.b.name}`}>
              <strong>{s.a.name}</strong> and <strong>{s.b.name}</strong> <span className="muted small">— kept apart</span>
            </article>
          ))}
        </div>
      )}
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}
