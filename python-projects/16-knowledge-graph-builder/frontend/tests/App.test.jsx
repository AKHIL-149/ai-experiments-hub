import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, setUnauthorizedHandler } from "../src/api";
import App from "../src/App";
import { CONFIG, USER } from "./helpers";

vi.mock("../src/api", async () => {
  const actual = await vi.importActual("../src/api");
  const api = Object.fromEntries(Object.keys(actual.api).map((k) => [k, vi.fn()]));
  let handler = () => {};
  return { ...actual, api, setUnauthorizedHandler: (fn) => { handler = fn || (() => {}); }, __fire401: () => handler() };
});
const { api, __fire401 } = await import("../src/api");

function signedIn(user = USER, extra = {}) {
  api.authConfig.mockResolvedValue(CONFIG);
  api.me.mockResolvedValue(user);
  api.jobs.mockResolvedValue({ jobs: extra.jobs || [] });
  api.suggestions.mockResolvedValue({ suggestions: extra.suggestions || [] });
  api.conflicts.mockResolvedValue({ conflicts: extra.conflicts || [] });
  api.health.mockResolvedValue({ status: "ok", llm: extra.llm || { ready: true, detail: "ok" } });
  api.graph.mockResolvedValue({ nodes: [], edges: [], total_nodes: 0, total_edges: 0, truncated: false });
  api.documents.mockResolvedValue({ documents: [] });
}

beforeEach(() => {
  window.location.hash = "";
  api.logout.mockResolvedValue({ success: true });
});

describe("App", () => {
  it("shows the sign-in screen when nobody is signed in", async () => {
    api.authConfig.mockResolvedValue(CONFIG);
    api.me.mockRejectedValue(new ApiError(401, "Not signed in"));
    render(<App />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("shows the app with navigation, the account and the model state when signed in", async () => {
    signedIn();
    render(<App />);
    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(within(nav).getAllByRole("link").map((a) => a.textContent)).toEqual(["Graph", "Documents", "Ask", "Check", "Review", "Export"]);
    expect(within(nav).getByRole("link", { name: "Graph" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: /ann/ })).toBeInTheDocument();
    expect(await screen.findByText("Model ready")).toBeInTheDocument();
  });

  it("moves between screens with the address bar", async () => {
    signedIn();
    render(<App />);
    await screen.findByRole("navigation", { name: "Main" });
    await userEvent.click(screen.getByRole("link", { name: "Documents" }));
    expect(await screen.findByRole("heading", { name: "Documents" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Documents" })).toHaveAttribute("aria-current", "page");
    act(() => { window.location.hash = "#/review"; });
    expect(await screen.findByRole("heading", { name: "Review" })).toBeInTheDocument();
    act(() => { window.location.hash = "#/nonsense"; });
    expect(await screen.findByRole("toolbar", { name: "Graph controls" })).toBeInTheDocument();      // unknown route: the graph
  });

  it("starts on the screen named in the address", async () => {
    signedIn();
    window.location.hash = "#/ask";
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Ask" })).toBeInTheDocument();
  });

  it("badges documents in progress and suggestions waiting for review", async () => {
    signedIn(USER, { jobs: [{ id: "a" }, { id: "b" }], suggestions: [{ id: "s" }], conflicts: [{ id: "c1" }, { id: "c2" }] });
    render(<App />);
    expect(await screen.findByLabelText("2 in progress")).toBeInTheDocument();
    expect(screen.getByLabelText("3 to review")).toBeInTheDocument();          // 1 suggestion + 2 conflicts
  });

  it("keeps the badges and the model state fresh every 8 seconds", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      signedIn();
      render(<App />);
      await screen.findByRole("navigation", { name: "Main" });
      await waitFor(() => expect(api.jobs).toHaveBeenCalled());
      const before = api.jobs.mock.calls.length;
      await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
      expect(api.jobs.mock.calls.length).toBe(before);                 // not yet (the pace is 8 s; some real time passes too)
      await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
      expect(api.jobs.mock.calls.length).toBeGreaterThan(before);
    } finally {
      vi.useRealTimers();
    }
  });

  it("says when the model is not ready", async () => {
    signedIn(USER, { llm: { ready: false, detail: "Cannot reach Ollama" } });
    render(<App />);
    expect(await screen.findByText("Model not ready")).toBeInTheDocument();
  });

  it("signs out", async () => {
    signedIn();
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /ann/ }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Sign out" }));
    expect(api.logout).toHaveBeenCalled();
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("goes back to the sign-in screen with a message when the session ends", async () => {
    signedIn();
    render(<App />);
    await screen.findByRole("navigation", { name: "Main" });
    act(() => __fire401());
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByText("Your session ended. Please sign in again.")).toBeInTheDocument();
  });

  it("has no sign-out in single-user mode", async () => {
    signedIn({ id: null, username: "local", display_name: "Local user", is_guest: false, local_mode: true });
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /Local user/ }));
    expect(screen.getByText(/Single-user mode/)).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Sign out" })).not.toBeInTheDocument();
  });

  it("warns a guest and lets them keep their documents by creating an account", async () => {
    const created = new Date(Date.now() - 3600000).toISOString();
    signedIn({ ...USER, id: 5, username: "guest-ab12", display_name: "Guest", is_guest: true, created_at: created, guest_ttl_hours: 24 });
    api.register.mockResolvedValue({ ...USER, username: "ann" });
    render(<App />);
    const banner = await screen.findByText(/You are a guest: this account and its documents are deleted in 23 hours/);
    expect(banner).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Keep it: create an account" }));
    await userEvent.type(screen.getByPlaceholderText("Username"), "ann");
    await userEvent.type(screen.getByPlaceholderText(/Password/), "correct horse");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(api.register).toHaveBeenCalledWith("ann", "correct horse", undefined);
    await waitFor(() => expect(screen.queryByText(/You are a guest/)).not.toBeInTheDocument());
  });

  it("shows the reason when creating the account from a guest fails", async () => {
    signedIn({ ...USER, is_guest: true, created_at: new Date().toISOString(), guest_ttl_hours: 24 });
    api.register.mockRejectedValue(new ApiError(409, "That username is taken"));
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: "Keep it: create an account" }));
    await userEvent.type(screen.getByPlaceholderText("Username"), "ann");
    await userEvent.type(screen.getByPlaceholderText(/Password/), "correct horse");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("That username is taken")).toBeInTheDocument();
  });

  it("says so when the server cannot be reached at all", async () => {
    api.authConfig.mockRejectedValue(new ApiError(0, "Cannot reach the server. Check that it is running."));
    render(<App />);
    expect(await screen.findByText("Cannot reach the server. Check that it is running.")).toBeInTheDocument();
  });
});

describe("App: the Check and Review addresses", () => {
  it("shows the Check screen at its address", async () => {
    signedIn();
    window.location.hash = "#/check";
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Check" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Check" })).toHaveAttribute("aria-current", "page");
  });

  it("shows the Export screen at its address", async () => {
    signedIn();
    api.exportSummary.mockResolvedValue({ entities: 1, facts: 1, value_facts: 0, entity_facts: 1, sources: 1, left_out: 0, document: null });
    window.location.hash = "#/export";
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Export" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Export" })).toHaveAttribute("aria-current", "page");
  });

  it("opens Export limited to the document named in the address", async () => {
    signedIn();
    api.documents.mockResolvedValue({ documents: [{ id: "d1", title: "Annual report", status: "completed", char_count: 10, chunk_count: 1, chunks_done: 1, stats: {}, job: null }] });
    api.exportSummary.mockResolvedValue({ entities: 1, facts: 1, value_facts: 0, entity_facts: 1, sources: 1, left_out: 0, document: null });
    window.location.hash = "#/export?doc=d1";
    render(<App />);
    const select = await screen.findByLabelText("What to include");
    await waitFor(() => expect(select).toHaveValue("d1"));          // once the document list has arrived the option exists
    expect(api.exportSummary).toHaveBeenCalledWith("d1");
  });

  it("opens Review on the tab named in the address", async () => {
    signedIn();
    window.location.hash = "#/review?tab=conflicts";
    render(<App />);
    expect(await screen.findByRole("tab", { name: "Conflicts" })).toHaveAttribute("aria-selected", "true");
  });
});
