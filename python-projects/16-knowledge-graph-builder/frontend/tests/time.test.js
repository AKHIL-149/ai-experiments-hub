import { describe, expect, it } from "vitest";
import { TIME_STATUSES, atForAnswer, clampYear, timeLabel, timeSentence, timeSummary, timeTone, validAt, yearOf } from "../src/lib/time";

describe("time words", () => {
  it("has words and a tone for every status the server can send", () => {
    expect(TIME_STATUSES).toEqual(["during", "overlaps", "open", "undated", "outside"]);
    for (const s of TIME_STATUSES) {
      expect(timeLabel(s)).not.toBe("");
      expect(timeSentence(s, "2021")).not.toBe("");
      expect(["ok", "work", "wait", "muted"]).toContain(timeTone(s));
    }
  });
  it("says plainly that an open-ended fact may or may not still hold", () => {
    expect(timeLabel("open")).toBe("no end stated");
    expect(timeSentence("open", "2021")).toMatch(/no end date is stated.*may still have held/);
    expect(timeSentence("during", "2021")).toContain("2021");
    expect(timeSentence("outside", "2021")).toContain("outside 2021");
  });
  it("gives each status its own tone", () => {
    expect(Object.fromEntries(TIME_STATUSES.map((s) => [s, timeTone(s)]))).toEqual({ during: "ok", overlaps: "work", open: "wait", undated: "muted", outside: "muted" });
  });
  it("copes with a status it does not know", () => {
    expect(timeLabel("???")).toBe("");
    expect(timeTone("???")).toBe("muted");
    expect(timeSentence("???")).toBe("");
  });
  it("summarises counts in a fixed order and leaves out zeros", () => {
    expect(timeSummary({ outside: 2, during: 3, open: 1, undated: 0 })).toBe("3 holds · 1 no end stated · 2 outside");
    expect(timeSummary({})).toBe("");
    expect(timeSummary(null)).toBe("");
  });
});

describe("years", () => {
  it("reads the year of an at value", () => {
    expect(yearOf("2021")).toBe(2021);
    expect(yearOf("2021-03-15")).toBe(2021);
    expect(yearOf("now")).toBeNull();
    expect(yearOf("")).toBeNull();
    expect(yearOf(undefined)).toBeNull();
  });
  it("keeps a year inside what the documents reach", () => {
    const span = { first_year: 2010, last_year: 2024 };
    expect(clampYear(2005, span)).toBe(2010);
    expect(clampYear(2030, span)).toBe(2024);
    expect(clampYear(2015, span)).toBe(2015);
    expect(clampYear(2015, { first_year: null })).toBe(2015);
    expect(clampYear(2015, null)).toBe(2015);
  });
  it("accepts only addresses the server accepts", () => {
    for (const ok of ["now", "2021", "2021-03", "2021-03-15"]) expect(validAt(ok)).toBe(ok);
    for (const bad of ["", "soon", "21", "2021-3", "2021-03-1", "2021/03", undefined, "<script>"]) expect(validAt(bad)).toBe("");
  });
  it("opens the graph at an answer's time only when it is one moment or period", () => {
    expect(atForAnswer({ kind: "in", label: "2021" })).toBe("2021");
    expect(atForAnswer({ kind: "in", label: "2021-03" })).toBe("2021-03");
    expect(atForAnswer({ kind: "in", label: "the 1990s" })).toBe("");
    expect(atForAnswer({ kind: "between", label: "2015 to 2018" })).toBe("");
    expect(atForAnswer({ kind: "after", label: "2019" })).toBe("");
    expect(atForAnswer({ kind: "before", label: "2019-03" })).toBe("");
    expect(atForAnswer({ kind: "now", label: "now (2026-11-16)" })).toBe("");
    expect(atForAnswer(null)).toBe("");
    expect(atForAnswer(undefined)).toBe("");
  });
});
