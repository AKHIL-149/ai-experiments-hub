import { useState } from "react";
import { api } from "../api";
import { periodText, roleLabel, roleTone, verdictInfo } from "../lib/conflicts";
import { plural } from "../lib/format";
import Source from "./Source";

export default function Check({ params, go }) {
  const [claim, setClaim] = useState(params.claim || "");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(ev) {
    ev.preventDefault();
    const text = claim.trim();
    if (text.length < 5) { setError("Type a claim of at least 5 characters, for example “Acme acquired Beta in 2020”."); return; }
    setBusy(true);
    setError("");
    setResult(null);
    try {
      setResult(await api.check(text));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const v = result ? verdictInfo(result.verdict) : null;
  const ids = result ? result.evidence.map((e) => e.fact_id) : [];
  return (
    <div className="page stack">
      <div className="page-head"><h1>Check</h1><span className="muted small">Is a claim supported, contradicted, or not stated in your documents?</span></div>
      <form className="card stack" onSubmit={submit}>
        <div className="field">
          <label htmlFor="claim">A claim</label>
          <textarea id="claim" rows={2} value={claim} onChange={(e) => setClaim(e.target.value)} placeholder="Veltra Dynamics acquired Soro Labs in 2018." />
        </div>
        <div className="row"><button className="btn primary" disabled={busy}>{busy ? "Checking…" : "Check"}</button>
          <span className="muted small">The model only reads the claim; the check itself is done on your facts. “Not in the documents” is not the same as false.</span></div>
      </form>
      {error && <div className="banner error" role="alert">{error}</div>}
      {busy && <p className="muted" role="status">Looking through your graph…</p>}
      {result && (
        <section className="card stack" aria-label="Result">
          <div className="row wrap"><span className={`chip tone-${v.tone}`}>{v.label}</span><strong className="grow" role="status">{result.summary}</strong></div>
          {result.parsed && (
            <p className="small muted">Read as: <strong>{result.parsed.subject}</strong> — {result.parsed.relation} — <strong>{result.parsed.object}</strong>
              {(result.parsed.start || result.parsed.end) && <> ({periodText(result.parsed.start, result.parsed.end)})</>}</p>
          )}
          {result.evidence.length > 0 && (
            <div>
              <div className="row" style={{ marginBottom: "0.3rem" }}>
                <h3 className="grow">{plural(result.evidence.length, "fact")} behind this</h3>
                <button className="btn small" onClick={() => go("graph", { facts: ids.join(",") })}>Show them in the graph</button>
              </div>
              {result.evidence.map((e) => (
                <div className="cite" key={`${e.role}-${e.fact_id}`}>
                  <span className={`chip tone-${roleTone(e.role)}`}>{roleLabel(e.role)}</span>
                  <div className="stack" style={{ gap: "0.3rem" }}>
                    <div className="row wrap"><strong>{e.text}</strong><button className="linkbtn small" onClick={() => go("graph", { fact: e.fact_id })}>Open in the graph</button></div>
                    <div className="small">{periodText(e.valid_from, e.valid_to)}</div>
                    {e.quote && <Source source={{ document_title: e.document_title, quote: e.quote, verified: e.verified, passage: "" }} />}
                  </div>
                </div>
              ))}
            </div>
          )}
          {result.reasoning.length > 0 && (
            <details className="reason"><summary>How this was checked</summary><ul className="small">{result.reasoning.map((r) => <li key={r}>{r}</li>)}</ul></details>
          )}
        </section>
      )}
      {!result && !busy && <div className="empty"><h2>Check a statement against what the documents say</h2><p>You get the facts and quotes that support it or contradict it. If the documents are silent you get “not in the documents”, never a guess.</p></div>}
    </div>
  );
}
