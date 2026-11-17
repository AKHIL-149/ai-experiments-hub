import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useAsync } from "../hooks";
import { plural, prettifyFactText, truncate } from "../lib/format";
import Source from "./Source";

const MODES = [
  ["graph", "Graph", "Follows the chain of facts the question asks for (best for questions that need several documents)"],
  ["subgraph", "Facts around", "Collects the facts around the entities the question names"],
  ["hybrid", "Graph + passages", "The graph facts plus the closest passages"],
  ["vector", "Passages only", "Plain passage search, no graph (for comparison)"],
];

function Reasoning({ r, timings }) {
  const steps = r.steps || [];
  return (
    <details className="reason">
      <summary>How this was answered</summary>
      <div className="stack small" style={{ marginTop: "0.5rem" }}>
        <p><span className="muted">Mode:</span> {r.mode} · {plural(r.facts_considered || 0, "fact")} and {plural(r.passages_considered || 0, "passage")} shown to the model
          {timings && <> · {Math.round(((timings.retrieve || 0) + (timings.answer || 0)) / 100) / 10}s</>}</p>
        {r.seeds && r.seeds.length > 0 && (
          <div><strong>Entities found in the question</strong>
            <ul>{r.seeds.map((s) => <li key={s.entity_id}>{s.name} <span className="muted">({s.how}{s.also_could_be && s.also_could_be.length ? `; could also be ${s.also_could_be.join(", ")}` : ""})</span></li>)}</ul></div>
        )}
        {r.plan && (
          <div><strong>Plan</strong>
            <p>Start at {r.plan.start.join(", ") || "—"}{r.plan.steps.length ? ", then follow: " : "."}
              {r.plan.steps.map((s, i) => <span key={i}>{i > 0 && " → "}<em>{s.relation}</em> ({s.direction === "out" ? "forwards" : "backwards"})</span>)}</p></div>
        )}
        {steps.length > 0 && (
          <div><strong>Steps taken</strong>
            <ol>{steps.map((s) => (
              <li key={s.step}><em>{s.relation}</em>{s.flipped && <span className="chip tone-wait" style={{ marginLeft: "0.3rem" }}>direction reversed</span>}
                <ul>{s.links.slice(0, 6).map((l, i) => <li key={i}>{prettifyFactText(l.fact)}</li>)}</ul></li>
            ))}</ol></div>
        )}
        {r.paths && r.paths.length > 0 && <div><strong>Paths</strong><ul>{r.paths.map((p, i) => <li key={i}>{p.map(prettifyFactText).join("  →  ")}</li>)}</ul></div>}
        {r.fallback && <p className="banner warn">The chain could not be followed ({r.fallback}); the facts around the entities were used instead.</p>}
        {r.evidence_documents && r.evidence_documents.length > 0 && <p><span className="muted">Documents used:</span> {r.evidence_documents.join(", ")}</p>}
      </div>
    </details>
  );
}

function AnswerCard({ title, result, go }) {
  const cited = result.citations || [];
  const factIds = cited.filter((c) => c.kind === "fact").map((c) => c.fact_id);
  return (
    <section className="card stack" aria-label={title || "Answer"}>
      {title && <div className="row"><h2 className="grow">{title}</h2></div>}
      <p className={`answer ${result.found ? "" : "notfound"}`} role="status">
        {result.found ? result.answer : "The documents do not say."}
      </p>
      {!result.found && result.note && <p className="muted small">{result.note}</p>}
      {result.warning && <div className="banner warn" role="alert">{result.warning}</div>}
      {result.dropped_citations && result.dropped_citations.length > 0 && (
        <div className="banner warn">The model cited {result.dropped_citations.join(", ")}, which it was never given; those citations were removed.</div>
      )}
      {cited.length > 0 && (
        <div>
          <div className="row" style={{ marginBottom: "0.3rem" }}>
            <h3 className="grow">{plural(cited.length, "citation")}</h3>
            {factIds.length > 0 && <button className="btn small" onClick={() => go("graph", { facts: factIds.join(",") })}>Show them in the graph</button>}
          </div>
          {cited.map((c) => (
            <div className="cite" key={c.label}>
              <span className="label-chip">{c.label}</span>
              <div className="stack" style={{ gap: "0.3rem" }}>
                {c.kind === "fact" ? (
                  <>
                    <div className="row wrap"><strong>{prettifyFactText(c.text)}</strong>{c.fact_id && <button className="linkbtn small" onClick={() => go("graph", { fact: c.fact_id })}>Open in the graph</button>}</div>
                    {c.quote && <Source source={{ document_title: c.document_title, quote: c.quote, verified: c.verified, passage: "" }} />}
                  </>
                ) : (
                  <>
                    <div className="small"><strong>{c.document_title}</strong> <span className="muted">passage</span></div>
                    <p className="passage">{truncate(c.text, 400)}</p>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
      {result.reasoning && <Reasoning r={result.reasoning} timings={result.timings_ms} />}
    </section>
  );
}

export default function Ask({ params, go }) {
  const [question, setQuestion] = useState(params.q || "");
  const [mode, setMode] = useState("graph");
  const [docId, setDocId] = useState("");
  const [compare, setCompare] = useState(false);
  const [results, setResults] = useState(null);   // [{title, result}]
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState([]);
  const docs = useAsync(() => api.documents(), []);
  const inputRef = useRef(null);
  const completed = ((docs.data && docs.data.documents) || []).filter((d) => d.status === "completed");

  useEffect(() => { if (params.q) setQuestion(params.q); }, [params.q]);

  async function submit(ev) {
    if (ev) ev.preventDefault();
    const q = question.trim();
    if (q.length < 3) { setError("Type a question of at least 3 characters."); return; }
    setBusy(true);
    setError("");
    setResults(null);
    try {
      const modes = compare && mode !== "vector" ? [mode, "vector"] : [mode];
      const out = [];
      for (const m of modes) {
        const result = await api.ask(q, m, docId);
        out.push({ title: modes.length > 1 ? (m === "vector" ? "Passage search" : "Graph answer") : null, result });
      }
      setResults(out);
      setHistory((h) => [{ q, found: out[0].result.found, answer: out[0].result.answer }, ...h.filter((x) => x.q !== q)].slice(0, 8));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page stack">
      <div className="page-head"><h1>Ask</h1><span className="muted small">Answers come only from your documents and cite what they used.</span></div>
      <form className="card stack" onSubmit={submit}>
        <div className="field">
          <label htmlFor="question">Your question</label>
          <textarea id="question" ref={inputRef} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Who founded the company that Veltra Dynamics acquired?"
            onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit(); }} rows={2} />
        </div>
        <div className="row wrap">
          <div className="field">
            <label htmlFor="mode">How</label>
            <select id="mode" value={mode} onChange={(e) => setMode(e.target.value)} style={{ width: "auto" }}>
              {MODES.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="scope">Look in</label>
            <select id="scope" value={docId} onChange={(e) => setDocId(e.target.value)} style={{ width: "auto", maxWidth: 240 }}>
              <option value="">All my documents</option>
              {completed.map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}
            </select>
          </div>
          <label className="row" style={{ alignSelf: "end", paddingBottom: "0.45rem" }}>
            <input type="checkbox" checked={compare} onChange={(e) => setCompare(e.target.checked)} disabled={mode === "vector"} /> Compare with passage search
          </label>
          <span className="spacer" />
          <button className="btn primary" disabled={busy} style={{ alignSelf: "end" }}>{busy ? "Thinking…" : "Ask"}</button>
        </div>
        <p className="muted small">{MODES.find((m) => m[0] === mode)[2]}. Ctrl/⌘ + Enter to send.</p>
      </form>

      {error && <div className="banner error" role="alert">{error}</div>}
      {busy && <p className="muted" role="status">Looking through your graph…</p>}
      {results && (
        <div className={results.length > 1 ? "pair" : ""} style={results.length > 1 ? { alignItems: "start" } : undefined}>
          {results.map((r, i) => <AnswerCard key={i} title={r.title} result={r.result} go={go} />)}
        </div>
      )}
      {!results && !busy && history.length > 0 && (
        <section aria-label="Recent questions">
          <h3 style={{ marginBottom: "0.4rem" }}>Recent questions</h3>
          <ul className="facts">
            {history.map((h) => (
              <li key={h.q}><button className="linkbtn" onClick={() => setQuestion(h.q)}>{h.q}</button> <span className="muted small">{h.found ? `→ ${truncate(h.answer, 60)}` : "→ not found"}</span></li>
            ))}
          </ul>
        </section>
      )}
      {!results && !busy && history.length === 0 && (
        <div className="empty"><h2>Ask about what is in your documents</h2>
          <p>Try a question that needs facts from more than one document, like “Which university did the founder of Soro Labs attend?”. If the documents do not say, you get “not found” rather than a guess.</p></div>
      )}
    </div>
  );
}
