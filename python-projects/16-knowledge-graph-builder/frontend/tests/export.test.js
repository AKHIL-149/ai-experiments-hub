import { describe, expect, it } from "vitest";
import { afterEach, beforeEach, vi } from "vitest";
import { api, exportUrl } from "../src/api";
import { FORMATS, holdsText, leftOutText } from "../src/lib/export";

describe("exportSummary", () => {
  let fetchMock;
  beforeEach(() => { fetchMock = vi.fn(() => Promise.resolve({ status: 200, ok: true, json: () => Promise.resolve({ facts: 1 }) })); vi.stubGlobal("fetch", fetchMock); });
  afterEach(() => vi.unstubAllGlobals());
  it("asks for the whole graph, or for one document", async () => {
    await api.exportSummary();
    await api.exportSummary("d 1");
    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual(["/api/export/summary", "/api/export/summary?document_id=d+1"]);
  });
});

describe("exportUrl", () => {
  it("keeps every choice at its default when none is given", () => {
    expect(exportUrl("cypher")).toBe("/api/export?format=cypher");
    expect(exportUrl("json")).toBe("/api/export?format=json");
  });
  it("is the plain address for the default choices", () => {
    expect(exportUrl("json")).toBe("/api/export?format=json");
    expect(exportUrl("csv", {})).toBe("/api/export?format=csv");
  });
  it("adds only the choices that differ from the default", () => {
    expect(exportUrl("cypher", { documentId: "d 1", sources: false, schema: false })).toBe("/api/export?format=cypher&document_id=d+1&sources=false&schema=false");
    expect(exportUrl("json", { sources: false })).toBe("/api/export?format=json&sources=false");
    expect(exportUrl("cypher", { schema: false })).toBe("/api/export?format=cypher&schema=false");
    expect(exportUrl("json", { documentId: "" })).toBe("/api/export?format=json");
  });
  it("sends the constraint choice for Cypher only, since no other format has constraints", () => {
    expect(exportUrl("json", { schema: false })).toBe("/api/export?format=json");
    expect(exportUrl("csv", { schema: false, sources: false })).toBe("/api/export?format=csv&sources=false");
  });
});

describe("FORMATS", () => {
  it("lists the three formats the server offers, each with a file name that matches", () => {
    expect(FORMATS.map((f) => f.id)).toEqual(["json", "csv", "cypher"]);
    expect(FORMATS.map((f) => f.file)).toEqual(["knowledge-graph.json", "knowledge-graph.zip", "knowledge-graph.cypher"]);
  });
  it("is honest that the Cypher script has not been tried on a live database", () => {
    expect(FORMATS.find((f) => f.id === "cypher").blurb).toMatch(/Not yet tried against a live database/);
  });
});

describe("holdsText", () => {
  const c = (over) => ({ entities: 12, facts: 18, value_facts: 3, entity_facts: 15, sources: 21, left_out: 0, ...over });
  it("says what a download holds", () => {
    expect(holdsText(c())).toBe("12 entities, 18 facts (3 with a plain value), 21 quotes");
  });
  it("uses singular words for one", () => {
    expect(holdsText(c({ entities: 1, facts: 1, value_facts: 0, sources: 1 }))).toBe("1 entity, 1 fact, 1 quote");
  });
  it("leaves out the plain-value part when there are none", () => {
    expect(holdsText(c({ value_facts: 0 }))).toBe("12 entities, 18 facts, 21 quotes");
  });
  it("says zeros and says nothing before the counts arrive", () => {
    expect(holdsText(c({ entities: 0, facts: 0, value_facts: 0, sources: 0 }))).toBe("0 entities, 0 facts, 0 quotes");
    expect(holdsText(null)).toBe("");
  });
});

describe("leftOutText", () => {
  it("is empty when nothing is left out", () => {
    expect(leftOutText({ left_out: 0 })).toBe("");
    expect(leftOutText(null)).toBe("");
  });
  it("says how many facts, why and how to bring them back", () => {
    expect(leftOutText({ left_out: 3 })).toBe("3 facts are left out because you settled a conflict against them. Reopen the conflict in Review to bring them back.");
    expect(leftOutText({ left_out: 1 })).toBe("1 fact is left out because you settled a conflict against it. Reopen the conflict in Review to bring it back.");
  });
});
