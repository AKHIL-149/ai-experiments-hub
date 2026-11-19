// What a fact's dates say about a chosen time (the server decides: during, overlaps, open, outside, undated).

const WORDS = {
  during: { label: "holds", tone: "ok", sentence: (w) => `its dates cover ${w}` },
  overlaps: { label: "overlaps", tone: "work", sentence: (w) => `its dates overlap ${w}` },
  open: { label: "no end stated", tone: "wait", sentence: () => "it began earlier and no end date is stated, so it may still have held" },
  undated: { label: "no date", tone: "muted", sentence: () => "the text gives no date" },
  outside: { label: "outside", tone: "muted", sentence: (w) => `its dates put it outside ${w}` },
};

export const TIME_STATUSES = Object.keys(WORDS);

export function timeLabel(status) {
  return (WORDS[status] || { label: "" }).label;
}

export function timeTone(status) {
  return (WORDS[status] || { tone: "muted" }).tone;
}

export function timeSentence(status, windowLabel = "that time") {
  return WORDS[status] ? WORDS[status].sentence(windowLabel) : "";
}

/** "3 hold · 1 no end stated · 2 outside": the counts the server gives, in a fixed order, zero counts left out */
export function timeSummary(counts) {
  return TIME_STATUSES.filter((s) => counts && counts[s] > 0).map((s) => `${counts[s]} ${timeLabel(s)}`).join(" · ");
}

/** The year of an `at` value ("2021", "2021-03", "2021-03-15"), or null */
export function yearOf(at) {
  const m = /^(\d{4})/.exec(at || "");
  return m ? Number(m[1]) : null;
}

/** Keep a year inside what the documents reach */
export function clampYear(year, span) {
  if (!span || span.first_year == null) return year;
  return Math.min(span.last_year, Math.max(span.first_year, year));
}

/** An `at` value the Graph screen can use from the address: "now" or YYYY[-MM[-DD]] */
export function validAt(at) {
  return at === "now" || /^\d{4}(-\d{2}(-\d{2})?)?$/.test(at || "") ? at : "";
}

/** The `at` to open the graph with for an answer's time: only a single moment or period ("in 2021") fits the slider */
export function atForAnswer(time) {
  return time && time.kind === "in" && validAt(time.label) ? time.label : "";
}
