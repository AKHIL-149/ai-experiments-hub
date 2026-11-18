import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Conflicts from "../src/components/Conflicts";

vi.mock("../src/api", async () => (await import("./mockapi")).apiMockFactory());
const { api } = await import("../src/api");

const fact = (id, text, over = {}) => ({ id, text, valid_from: "2019", valid_to: "2022", sources: [{ document_title: "News", quote: `${text}.`, verified: true }], ...over });
const conflict = (over = {}) => ({
  id: "c1", kind: "different_holder", severity: "certain", reasons: ["Both say who “was CTO of” Acme", "their dates share time"], llm_verdict: null, status: "open", resolution: null,
  a: fact("f1", "Dana Reyes was CTO of Acme"), b: fact("f2", "Omar Haddad was CTO of Acme", { valid_from: "2021", valid_to: null }), can_end_earlier: false, ...over,
});
const onChange = vi.fn();
const show = () => render(<Conflicts onChange={onChange} />);
function setup({ open = [], resolved = [], dismissed = [] } = {}) {
  api.conflicts.mockImplementation(async (s) => ({ conflicts: { open, resolved, dismissed }[s] }));
}

beforeEach(() => vi.clearAllMocks());

describe("Conflicts", () => {
  it("says when nothing clashes", async () => {
    setup();
    show();
    expect(await screen.findByText("No open conflicts")).toBeInTheDocument();
  });

  it("shows both facts with their dates and quotes, why they clash, and how sure", async () => {
    setup({ open: [conflict()] });
    show();
    const card = await screen.findByRole("article", { name: "Dana Reyes was CTO of Acme and Omar Haddad was CTO of Acme" });
    expect(within(card).getByText("Two holders of a role that has one at a time")).toBeInTheDocument();
    expect(within(card).getByText("certain")).toHaveAttribute("title", "Their dates surely share time");
    expect(within(card).getByText("their dates share time")).toBeInTheDocument();
    expect(within(card).getByText("2019 – 2022")).toBeInTheDocument();
    expect(within(card).getByText("since 2021, no end stated")).toBeInTheDocument();
    expect(within(card).getAllByText("News")).toHaveLength(2);
    expect(within(card).getByText("Omar Haddad was CTO of Acme.")).toBeInTheDocument();
  });

  it("marks a possible conflict differently, and shows what the model thought", async () => {
    setup({ open: [conflict({ severity: "possible", llm_verdict: "no" })] });
    show();
    expect(await screen.findByText("possible")).toHaveAttribute("title", expect.stringMatching(/might share time/));
    expect(screen.getByText("model: compatible")).toBeInTheDocument();
  });

  it.each([["yes", "model: contradict"], ["unsure", "model: unsure"]])("shows a %s opinion", async (v, text) => {
    setup({ open: [conflict({ llm_verdict: v })] });
    show();
    expect(await screen.findByText(text)).toBeInTheDocument();
  });

  it.each([["Trust the first", "keep_a", "Settled: trusted the first"], ["Trust the second", "keep_b", "Settled: trusted the second"], ["Both are true", "both", "Settled: both are true"]])
  ("%s", async (label, resolution, toast) => {
    setup({ open: [conflict()] });
    api.resolveConflict.mockResolvedValue({});
    show();
    await userEvent.click(await screen.findByRole("button", { name: label }));
    expect(api.resolveConflict).toHaveBeenCalledWith("c1", resolution);
    expect(await screen.findByText(toast)).toBeInTheDocument();
    expect(onChange).toHaveBeenCalled();
  });

  it("offers to end the earlier fact only when that is possible", async () => {
    setup({ open: [conflict()] });
    show();
    await screen.findByRole("button", { name: "Both are true" });
    expect(screen.queryByRole("button", { name: /ended when the later began/ })).not.toBeInTheDocument();
  });

  it("ends the earlier fact when the later began", async () => {
    setup({ open: [conflict({ can_end_earlier: true })] });
    api.resolveConflict.mockResolvedValue({});
    show();
    await userEvent.click(await screen.findByRole("button", { name: "The earlier one ended when the later began" }));
    expect(api.resolveConflict).toHaveBeenCalledWith("c1", "succession");
  });

  it("reloads all three lists after a decision", async () => {
    setup({ open: [conflict()] });
    api.resolveConflict.mockResolvedValue({});
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Both are true" }));
    await screen.findByText("Settled: both are true");
    for (const s of ["open", "resolved", "dismissed"]) expect(api.conflicts.mock.calls.filter(([x]) => x === s).length).toBeGreaterThanOrEqual(2);
  });

  it("shows why a decision failed and keeps the card", async () => {
    setup({ open: [conflict()] });
    api.resolveConflict.mockRejectedValue(new Error("A document is being read. Try again when it finishes"));
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Trust the first" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("A document is being read");
    expect(screen.getByRole("article", { name: /Dana Reyes was CTO of Acme and/ })).toBeInTheDocument();
  });

  it("looks for conflicts, with or without the model, and reports the result", async () => {
    setup();
    api.runConflicts.mockResolvedValue({ new: 2, removed: 1, open: 3, judged: 0 });
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Look for conflicts now" }));
    expect(api.runConflicts).toHaveBeenLastCalledWith(false);
    expect(await screen.findByText("2 new conflicts, 1 no longer apply, 3 open.")).toBeInTheDocument();
    api.runConflicts.mockResolvedValue({ new: 1, removed: 0, open: 4, judged: 1 });
    await userEvent.click(screen.getByLabelText(/Ask the model too/));
    await userEvent.click(screen.getByRole("button", { name: "Look for conflicts now" }));
    expect(api.runConflicts).toHaveBeenLastCalledWith(true);
    expect(await screen.findByText("1 new conflict, 4 open, 1 checked by the model.")).toBeInTheDocument();
  });

  it("shows an error when the search fails", async () => {
    setup();
    api.runConflicts.mockRejectedValue(new Error("Model not reachable"));
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Look for conflicts now" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Model not reachable");
  });

  it("lists settled conflicts with how they were settled, and reopens one", async () => {
    setup({ resolved: [conflict({ id: "r1", status: "resolved", resolution: "keep_a" })], dismissed: [conflict({ id: "d1", status: "dismissed", resolution: "both", a: fact("f3", "Acme employs 340 people"), b: fact("f4", "Acme employs 400 people") })] });
    api.reopenConflict.mockResolvedValue({});
    show();
    await userEvent.click(await screen.findByText("Settled (2)"));
    expect(screen.getByText("trusted the first")).toBeInTheDocument();
    expect(screen.getByText("both are true")).toBeInTheDocument();
    const card = screen.getByRole("article", { name: "Settled: Acme employs 340 people and Acme employs 400 people" });
    await userEvent.click(within(card).getByRole("button", { name: "Reopen" }));
    expect(api.reopenConflict).toHaveBeenCalledWith("d1");
    expect(await screen.findByText("Reopened")).toBeInTheDocument();
  });

  it("has no settled section when none are settled", async () => {
    setup({ open: [conflict()] });
    show();
    await screen.findByRole("button", { name: "Both are true" });
    expect(screen.queryByText(/Settled \(/)).not.toBeInTheDocument();
  });

  it("shows an error when the list cannot be loaded", async () => {
    api.conflicts.mockRejectedValue(new Error("Cannot reach the server."));
    show();
    expect((await screen.findAllByRole("alert"))[0]).toHaveTextContent("Cannot reach the server.");
  });
});

describe("Conflicts: tones", () => {
  it("shows a certain conflict as serious and a possible one as a caution", async () => {
    setup({ open: [conflict({ id: "a", severity: "certain" }), conflict({ id: "b", severity: "possible", a: fact("f3", "X employs 1"), b: fact("f4", "X employs 2") })] });
    show();
    expect(await screen.findByText("certain")).toHaveClass("tone-bad");
    expect(screen.getByText("possible")).toHaveClass("tone-wait");
  });
});
