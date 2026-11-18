import { describe, expect, it } from "vitest";
import { KIND_TEXT, actionsFor, kindText, periodText, roleLabel, roleTone, verdictInfo } from "../src/lib/conflicts";

describe("conflict words", () => {
  it("has a sentence for each kind the server sends, and a fallback", () => {
    for (const k of ["different_object", "different_value", "different_holder", "reversed"]) expect(kindText(k)).toBe(KIND_TEXT[k]);
    expect(kindText("something_new")).toBe("Facts that may not both be true");
  });
  it("names every verdict with a tone, and treats an unknown one as unclear", () => {
    expect(Object.fromEntries(["supported", "supported_other_dates", "contradicted", "not_found", "unclear"].map((v) => [v, verdictInfo(v).tone])))
      .toEqual({ supported: "ok", supported_other_dates: "work", contradicted: "bad", not_found: "muted", unclear: "wait" });
    expect(verdictInfo("not_found").label).toBe("Not in the documents");
    expect(verdictInfo("nonsense")).toEqual(verdictInfo("unclear"));
  });
  it("labels evidence roles", () => {
    expect(roleLabel("supports")).toBe("supports");
    expect(roleLabel("other")).toBe("other");
    expect([roleTone("supports"), roleTone("contradicts"), roleTone("related")]).toEqual(["ok", "bad", "muted"]);
  });
  it("offers to end the earlier fact only when the server says it can", () => {
    expect(actionsFor({ can_end_earlier: false }).map((a) => a.id)).toEqual(["keep_a", "keep_b", "both"]);
    expect(actionsFor({ can_end_earlier: true }).map((a) => a.id)).toEqual(["keep_a", "keep_b", "both", "succession"]);
  });
  it("writes a period in words, saying when no end is stated", () => {
    expect(periodText("2012", "2019")).toBe("2012 – 2019");
    expect(periodText("2020", null)).toBe("since 2020, no end stated");
    expect(periodText(null, "2022")).toBe("until 2022");
    expect(periodText(null, null)).toBe("no date");
  });
});
