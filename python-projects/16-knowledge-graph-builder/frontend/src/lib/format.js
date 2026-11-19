// Small, pure helpers for showing data. No React here, so each rule can be tested alone.

/** "2019 – 2022", "2020-03", "– 2022" (ended), or "" when the fact states no date */
export function formatPeriod(from, to) {
  if (from && to) return `${from} – ${to}`;
  if (from) return from;
  if (to) return `– ${to}`;
  return "";
}

/** How a document is doing, in words: { label, tone, detail } (tone: wait | work | ok | bad | muted) */
export function documentStatus(doc) {
  const job = doc.job;
  if (doc.status === "pending") {
    const place = job && job.position ? ` · place ${job.position} in the queue` : "";
    return { label: "Waiting", tone: "wait", detail: `Waiting to be read${place}` };
  }
  if (doc.status === "processing") {
    const total = doc.chunk_count || 0;
    const step = total ? `${doc.chunks_done}/${total} passages` : "starting";
    const stopping = job && job.cancel_requested ? " · stopping after this passage" : "";
    return { label: "Reading", tone: "work", detail: `Reading: ${step}${stopping}` };
  }
  if (doc.status === "completed") {
    const n = doc.stats && doc.stats.accepted != null ? doc.stats.accepted : 0;
    return { label: "Read", tone: "ok", detail: `${n} fact${n === 1 ? "" : "s"} found` };
  }
  if (doc.error === "Cancelled") return { label: "Cancelled", tone: "muted", detail: "Cancelled" };
  return { label: "Failed", tone: "bad", detail: doc.error || "The document could not be read" };
}

export function isActive(doc) {
  return doc.status === "pending" || doc.status === "processing";
}

export function progressOf(doc) {
  if (doc.status === "completed") return 1;
  if (!doc.chunk_count) return 0;
  return Math.min(1, doc.chunks_done / doc.chunk_count);
}

/** Cut a long text for a one-line display */
export function truncate(text, max = 120) {
  const t = (text || "").replace(/\s+/g, " ").trim();
  return t.length <= max ? t : t.slice(0, max - 1).trimEnd() + "…";
}

/** Split a passage around a quote so the quote can be highlighted: [{text, hit}] (never uses innerHTML) */
export function splitAroundQuote(passage, quote) {
  if (!passage) return [];
  if (!quote) return [{ text: passage, hit: false }];
  const i = passage.indexOf(quote);
  if (i < 0) return [{ text: passage, hit: false }];
  const parts = [];
  if (i > 0) parts.push({ text: passage.slice(0, i), hit: false });
  parts.push({ text: quote, hit: true });
  if (i + quote.length < passage.length) parts.push({ text: passage.slice(i + quote.length), hit: false });
  return parts;
}

/** "Alan Turing studied at King's College (..1934)" style label for a stored fact */
export function factLabel(f) {
  const when = formatPeriod(f.valid_from, f.valid_to);
  return `${f.subject} ${f.predicate} ${f.object}${when ? ` (${when})` : ""}`;
}

export function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many || one + "s"}`;
}

/** Percent for a 0..1 score */
export function percent(x) {
  return `${Math.round((x || 0) * 100)}%`;
}

/** "3 hours", "12 minutes": time left until an ISO date, for the guest notice */
export function timeUntil(iso, now = Date.now()) {
  const ms = new Date(iso).getTime() - now;
  if (!Number.isFinite(ms)) return "";
  if (ms <= 0) return "now";
  const m = Math.round(ms / 60000);
  if (m < 60) return plural(Math.max(m, 1), "minute");
  return plural(Math.round(m / 60), "hour");
}

/** The server writes a period as "(2019..2022)", "(..2006)" or "(2020-03..)": show it the way people read it */
export function prettifyFactText(text) {
  return (text || "").replace(/ \(([^()]*)\.\.([^()]*)\)$/, (_, from, to) => {
    const period = formatPeriod(from, to);
    return period ? ` (${period})` : "";
  });
}
