import { describe, expect, it } from "vitest";
import { documentStatus, factLabel, formatPeriod, isActive, percent, plural, progressOf, splitAroundQuote, timeUntil, truncate } from "../src/lib/format";

describe("formatPeriod", () => {
  it.each([
    ["2019", "2022", "2019 – 2022"],
    ["2020-03", "", "2020-03"],
    ["", "2022", "– 2022"],
    ["", "", ""],
    [null, null, ""],
    [undefined, "2010", "– 2010"],
  ])("%s / %s -> %s", (from, to, expected) => expect(formatPeriod(from, to)).toBe(expected));
});

describe("documentStatus", () => {
  it("says where a waiting document is in the queue", () => {
    expect(documentStatus({ status: "pending", job: { position: 3 } })).toEqual({ label: "Waiting", tone: "wait", detail: "Waiting to be read · place 3 in the queue" });
    expect(documentStatus({ status: "pending", job: null }).detail).toBe("Waiting to be read");
  });
  it("shows progress and a pending stop", () => {
    expect(documentStatus({ status: "processing", chunks_done: 2, chunk_count: 5, job: {} }).detail).toBe("Reading: 2/5 passages");
    expect(documentStatus({ status: "processing", chunks_done: 0, chunk_count: 0, job: {} }).detail).toBe("Reading: starting");
    expect(documentStatus({ status: "processing", chunks_done: 1, chunk_count: 3, job: { cancel_requested: true } }).detail).toContain("stopping after this passage");
  });
  it("counts facts of a finished document with the right plural", () => {
    expect(documentStatus({ status: "completed", stats: { accepted: 1 } }).detail).toBe("1 fact found");
    expect(documentStatus({ status: "completed", stats: { accepted: 12 } }).detail).toBe("12 facts found");
    expect(documentStatus({ status: "completed", stats: {} }).detail).toBe("0 facts found");
  });
  it("tells a cancelled document from a failed one", () => {
    expect(documentStatus({ status: "failed", error: "Cancelled" })).toMatchObject({ label: "Cancelled", tone: "muted" });
    expect(documentStatus({ status: "failed", error: "Cannot reach Ollama" })).toMatchObject({ label: "Failed", tone: "bad", detail: "Cannot reach Ollama" });
    expect(documentStatus({ status: "failed", error: null }).detail).toBe("The document could not be read");
  });
});

describe("document helpers", () => {
  it("knows which documents are still being worked on", () => {
    expect(isActive({ status: "pending" })).toBe(true);
    expect(isActive({ status: "processing" })).toBe(true);
    expect(isActive({ status: "completed" })).toBe(false);
    expect(isActive({ status: "failed" })).toBe(false);
  });
  it("computes progress between 0 and 1", () => {
    expect(progressOf({ status: "completed" })).toBe(1);
    expect(progressOf({ status: "processing", chunks_done: 1, chunk_count: 4 })).toBe(0.25);
    expect(progressOf({ status: "processing", chunks_done: 0, chunk_count: 0 })).toBe(0);
    expect(progressOf({ status: "processing", chunks_done: 9, chunk_count: 4 })).toBe(1);
  });
});

describe("text helpers", () => {
  it("truncates on one line", () => {
    expect(truncate("  a   b\n c ", 50)).toBe("a b c");
    expect(truncate("x".repeat(30), 10)).toBe("xxxxxxxxx…");
    expect(truncate(null)).toBe("");
  });
  it("splits a passage around a quote without html", () => {
    expect(splitAroundQuote("Acme bought Beta. Then more.", "Acme bought Beta.")).toEqual([
      { text: "Acme bought Beta.", hit: true }, { text: " Then more.", hit: false }]);
    expect(splitAroundQuote("Intro. Acme bought Beta.", "Acme bought Beta.")).toEqual([
      { text: "Intro. ", hit: false }, { text: "Acme bought Beta.", hit: true }]);
    expect(splitAroundQuote("A quote in the middle here", "quote")).toHaveLength(3);
    expect(splitAroundQuote("no match", "zzz")).toEqual([{ text: "no match", hit: false }]);
    expect(splitAroundQuote("only text", "")).toEqual([{ text: "only text", hit: false }]);
    expect(splitAroundQuote("", "q")).toEqual([]);
    expect(splitAroundQuote("<b>x</b> hit", "hit")[0].text).toBe("<b>x</b> ");   // markup stays plain text
  });
  it("writes a fact as a sentence with its period", () => {
    expect(factLabel({ subject: "Acme", predicate: "acquired", object: "Beta", valid_from: "2020-03", valid_to: null })).toBe("Acme acquired Beta (2020-03)");
    expect(factLabel({ subject: "Acme", predicate: "led", object: "Beta", valid_from: "2015", valid_to: "2018" })).toBe("Acme led Beta (2015 – 2018)");
    expect(factLabel({ subject: "A", predicate: "p", object: "B" })).toBe("A p B");
  });
  it("pluralises and formats percentages", () => {
    expect(plural(1, "fact")).toBe("1 fact");
    expect(plural(2, "fact")).toBe("2 facts");
    expect(plural(0, "entity", "entities")).toBe("0 entities");
    expect(percent(0.744)).toBe("74%");
    expect(percent(null)).toBe("0%");
  });
  it("says how long a guest has left", () => {
    const now = new Date("2026-01-01T00:00:00Z").getTime();
    expect(timeUntil("2026-01-01T00:20:00Z", now)).toBe("20 minutes");
    expect(timeUntil("2026-01-01T00:00:10Z", now)).toBe("1 minute");
    expect(timeUntil("2026-01-01T05:00:00Z", now)).toBe("5 hours");
    expect(timeUntil("2025-12-31T00:00:00Z", now)).toBe("now");
    expect(timeUntil("garbage", now)).toBe("");
  });
});

import { prettifyFactText } from "../src/lib/format";
describe("prettifyFactText", () => {
  it.each([
    ["Acme acquired Beta (2020-03..)", "Acme acquired Beta (2020-03)"],
    ["Imani studied at Tamsen (..2006)", "Imani studied at Tamsen (– 2006)"],
    ["Dana led Acme (2015..2018)", "Dana led Acme (2015 – 2018)"],
    ["Acme employs 40 people", "Acme employs 40 people"],
    ["Acme (the company) acquired Beta", "Acme (the company) acquired Beta"],
    ["X did Y (..)", "X did Y"],
    [null, ""],
  ])("%s", (input, expected) => expect(prettifyFactText(input)).toBe(expected));
});
