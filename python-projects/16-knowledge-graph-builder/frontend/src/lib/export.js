// What each download is, in words, and what a download would hold. No React here, so each rule can be tested alone.

export const FORMATS = [
  { id: "json", title: "JSON", file: "knowledge-graph.json",
    blurb: "Everything in one file: entities with their other names, facts with their dates, and the quotes each fact was read from. Best for your own code." },
  { id: "csv", title: "CSV", file: "knowledge-graph.zip",
    blurb: "A zip with three tables (entities, facts, quotes) that open in a spreadsheet or load into a database." },
  { id: "cypher", title: "Cypher", file: "knowledge-graph.cypher",
    blurb: "A script that builds the graph in Neo4j or another Cypher database. Safe to run twice. Loaded and read back unchanged on Neo4j 5.26 Community; not tried on Memgraph or other versions." },
];

/** One line saying what a download would hold: "12 entities, 18 facts (3 with a plain value), 21 quotes".
 *  With the quotes switched off it says so instead of counting them. */
export function holdsText(c, withQuotes = true) {
  if (!c) return "";
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const entities = c.entities === 1 ? "1 entity" : `${c.entities} entities`;
  const values = c.value_facts > 0 ? ` (${c.value_facts} with a plain value)` : "";
  return `${entities}, ${plural(c.facts, "fact")}${values}, ${withQuotes ? plural(c.sources, "quote") : "no quotes (you switched them off)"}`;
}

/** Why some facts are not in the download (empty when none are left out) */
export function leftOutText(c) {
  if (!c || !c.left_out) return "";
  const n = c.left_out;
  return `${n === 1 ? "1 fact is" : `${n} facts are`} left out because you settled a conflict against ${n === 1 ? "it" : "them"}. Reopen the conflict in Review to bring ${n === 1 ? "it" : "them"} back.`;
}
