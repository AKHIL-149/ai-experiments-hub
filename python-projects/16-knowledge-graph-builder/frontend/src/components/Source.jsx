import { splitAroundQuote } from "../lib/format";

/** One place a fact was read: the document, the exact quote, and the passage around it with the quote highlighted */
export default function Source({ source }) {
  const parts = splitAroundQuote(source.passage, source.quote);
  return (
    <div className="source">
      <div className="small">
        <strong>{source.document_title}</strong>
        {source.verified && <span className="chip tone-ok" style={{ marginLeft: "0.4rem" }} title="Confirmed by the quote's own wording or by the double-check">checked</span>}
      </div>
      <blockquote className="quote">{source.quote}</blockquote>
      {parts.length > 1 && (
        <details>
          <summary className="small muted">Show the passage</summary>
          <p className="passage">{parts.map((p, i) => (p.hit ? <mark key={i}>{p.text}</mark> : <span key={i}>{p.text}</span>))}</p>
        </details>
      )}
    </div>
  );
}
