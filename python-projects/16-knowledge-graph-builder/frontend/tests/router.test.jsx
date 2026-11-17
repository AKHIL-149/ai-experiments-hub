import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { buildHash, parseHash, useRoute } from "../src/router";

describe("parseHash", () => {
  it("reads the screen and its parameters", () => {
    expect(parseHash("#/graph?entity=abc&fact=f1")).toEqual({ route: "graph", params: { entity: "abc", fact: "f1" } });
    expect(parseHash("#/documents")).toEqual({ route: "documents", params: {} });
  });
  it("falls back to the graph for an empty or unknown address", () => {
    expect(parseHash("").route).toBe("graph");
    expect(parseHash("#/").route).toBe("graph");
    expect(parseHash("#/admin").route).toBe("graph");
    expect(parseHash(undefined).route).toBe("graph");
  });
  it("decodes encoded values", () => {
    expect(parseHash("#/ask?q=Who%20founded%20Acme%3F").params.q).toBe("Who founded Acme?");
  });
});

describe("buildHash", () => {
  it("leaves out empty parameters and encodes the rest", () => {
    expect(buildHash("graph", { entity: "a b", doc: "", x: null, y: undefined })).toBe("#/graph?entity=a+b");
    expect(buildHash("review")).toBe("#/review");
  });
  it("round-trips with parseHash", () => {
    const p = { entity: "n 1", facts: "f1,f2" };
    expect(parseHash(buildHash("graph", p))).toEqual({ route: "graph", params: p });
  });
});

describe("useRoute", () => {
  beforeEach(() => { window.location.hash = ""; });
  it("follows the address bar and can go elsewhere", () => {
    const { result } = renderHook(() => useRoute());
    expect(result.current.route).toBe("graph");
    act(() => result.current.go("ask", { q: "hi" }));
    expect(window.location.hash).toBe("#/ask?q=hi");
    act(() => { window.dispatchEvent(new HashChangeEvent("hashchange")); });
    expect(result.current.route).toBe("ask");
    expect(result.current.params).toEqual({ q: "hi" });
  });
});
