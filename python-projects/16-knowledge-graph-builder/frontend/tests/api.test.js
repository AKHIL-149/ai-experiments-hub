import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, setUnauthorizedHandler } from "../src/api";

function reply(status, body) {
  return Promise.resolve({ status, ok: status >= 200 && status < 300, json: () => (body === undefined ? Promise.reject(new Error("no json")) : Promise.resolve(body)) });
}

let fetchMock;
beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  setUnauthorizedHandler(null);
});
afterEach(() => vi.unstubAllGlobals());

describe("requests", () => {
  it("sends the cookie and builds the query string without empty values", async () => {
    fetchMock.mockReturnValue(reply(200, { nodes: [] }));
    await api.graph({ documentId: "d1", type: "", limit: 50 });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/graph?document_id=d1&limit=50");
    expect(init).toMatchObject({ method: "GET", credentials: "same-origin" });
  });
  it("posts JSON", async () => {
    fetchMock.mockReturnValue(reply(200, { id: 1 }));
    await api.login("ann", "correct horse");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/auth/login");
    expect(init.method).toBe("POST");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body)).toEqual({ username: "ann", password: "correct horse" });
  });
  it("leaves a blank display name out of the registration", async () => {
    fetchMock.mockReturnValue(reply(200, {}));
    await api.register("ann", "correct horse", "");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ username: "ann", password: "correct horse" });
  });
  it("uploads a file as a form without forcing a content type", async () => {
    fetchMock.mockReturnValue(reply(202, { id: "d" }));
    const file = new File(["hello"], "a.txt", { type: "text/plain" });
    await api.uploadFile(file);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/documents");
    expect(init.body).toBeInstanceOf(FormData);
    expect(init.body.get("file").name).toBe("a.txt");
    expect(init.headers["Content-Type"]).toBeUndefined();
  });
  it("returns null for 204 (delete)", async () => {
    fetchMock.mockReturnValue(reply(204));
    expect(await api.deleteDocument("d1")).toBeNull();
    expect(fetchMock.mock.calls[0][1].method).toBe("DELETE");
  });
  it("addresses every endpoint the screens use", async () => {
    fetchMock.mockReturnValue(reply(200, {}));
    await api.entity("e1");
    await api.neighborhood("e1", 2, 100);
    await api.fact("f1");
    await api.path("a", "b", 3);
    await api.entities("acme", "organization", 20);
    await api.jobs("active");
    await api.cancelJob("j1");
    await api.reprocess("d1");
    await api.suggestions("rejected");
    await api.accept("s1", "k1");
    await api.accept("s2");
    await api.reject("s3");
    await api.merge("k", "a");
    await api.merges(true);
    await api.undo("m1");
    await api.runResolution(true);
    await api.ask("Who?", "graph", "d1");
    const urls = fetchMock.mock.calls.map((c) => c[0]);
    expect(urls).toEqual([
      "/api/entities/e1", "/api/entities/e1/neighborhood?depth=2&limit=100", "/api/facts/f1", "/api/query/path?from=a&to=b&max_hops=3",
      "/api/entities?q=acme&type=organization&limit=20", "/api/jobs?status=active", "/api/jobs/j1/cancel", "/api/documents/d1/reprocess",
      "/api/resolution/suggestions?status=rejected", "/api/resolution/suggestions/s1/accept", "/api/resolution/suggestions/s2/accept",
      "/api/resolution/suggestions/s3/reject", "/api/entities/merge", "/api/resolution/merges?include_undone=true", "/api/resolution/merges/m1/undo",
      "/api/resolution/run", "/api/ask"]);
    expect(JSON.parse(fetchMock.mock.calls[9][1].body)).toEqual({ keep_id: "k1" });
    expect(fetchMock.mock.calls[10][1].body).toBeUndefined();
    expect(JSON.parse(fetchMock.mock.calls[16][1].body)).toEqual({ question: "Who?", mode: "graph", document_id: "d1" });
  });
});

describe("errors", () => {
  it("shows the server's message", async () => {
    fetchMock.mockReturnValue(reply(409, { detail: "A document is being read." }));
    await expect(api.merge("a", "b")).rejects.toMatchObject({ name: "ApiError", status: 409, message: "A document is being read." });
  });
  it("turns validation errors into one readable line", async () => {
    fetchMock.mockReturnValue(reply(422, { detail: [{ msg: "Value error, Password too short" }, { msg: "Field required" }] }));
    await expect(api.register("a", "b")).rejects.toThrow("Password too short; Field required");
  });
  it("has friendly fallbacks for 429, 500 and unknown errors", async () => {
    fetchMock.mockReturnValueOnce(reply(429, {}));
    await expect(api.documents()).rejects.toThrow("Too many attempts, try again later");
    fetchMock.mockReturnValueOnce(reply(500, undefined));
    await expect(api.documents()).rejects.toThrow("The server had a problem. Try again in a moment.");
    fetchMock.mockReturnValueOnce(reply(418, {}));
    await expect(api.documents()).rejects.toThrow("Request failed (418)");
  });
  it("says so when the server cannot be reached", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(api.documents()).rejects.toMatchObject({ status: 0, message: "Cannot reach the server. Check that it is running." });
  });
  it("tells the app when the sign-in is over, but not for the sign-in calls themselves", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    fetchMock.mockReturnValue(reply(401, { detail: "Not signed in" }));
    await expect(api.documents()).rejects.toBeInstanceOf(ApiError);
    expect(handler).toHaveBeenCalledTimes(1);
    await expect(api.login("a", "b")).rejects.toThrow();
    await expect(api.me()).rejects.toThrow();
    await expect(api.guest()).rejects.toThrow();
    expect(handler).toHaveBeenCalledTimes(1);
  });
});
