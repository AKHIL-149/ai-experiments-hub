import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Review from "../src/components/Review";

vi.mock("../src/api", async () => (await import("./mockapi")).apiMockFactory());
const { api } = await import("../src/api");

const ent = (id, name, extra = {}) => ({ id, name, type: "person", fact_count: 2, aliases: [], sample_facts: [`${name} founded Acme`], ...extra });
const suggestion = (over = {}) => ({
  id: "s1", score: 0.82, llm_verdict: null, reasons: ["Same surname and first initial"],
  a: ent("a1", "Maria Lopez"), b: ent("b1", "M. Lopez", { aliases: ["Mari"] }), ...over,
});
const merge = (over = {}) => ({ id: "m1", absorbed: "M. Lopez", kept: "Maria Lopez", how: "auto", reasons: ["Same name"], undone: false, ...over });

function setup({ pending = [], rejected = [], merges = [] } = {}) {
  api.suggestions.mockImplementation(async (status) => ({ suggestions: status === "rejected" ? rejected : pending }));
  api.merges.mockResolvedValue({ merges });
}
const onChange = vi.fn();
const show = () => render(<Review onChange={onChange} />);

beforeEach(() => vi.clearAllMocks());

describe("Review: suggestions", () => {
  it("says when there is nothing to review", async () => {
    setup();
    show();
    expect(await screen.findByText("Nothing to review")).toBeInTheDocument();
  });

  it("shows both names, how sure, the reasons and the facts behind each", async () => {
    setup({ pending: [suggestion({ llm_verdict: "yes" })] });
    show();
    const card = await screen.findByRole("article", { name: "Maria Lopez and M. Lopez" });
    expect(within(card).getByText("82% sure")).toBeInTheDocument();
    expect(within(card).getByRole("meter")).toHaveAttribute("aria-valuenow", "82");
    expect(within(card).getByText("Same surname and first initial")).toBeInTheDocument();
    expect(within(card).getByText("model agrees")).toBeInTheDocument();
    expect(within(card).getByText("M. Lopez founded Acme")).toBeInTheDocument();
    expect(within(card).getByText(/also written Mari/)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Suggestions (1)" })).toBeInTheDocument();
  });

  it("shows a model disagreement as a warning, not as a decision", async () => {
    setup({ pending: [suggestion({ llm_verdict: "no" })] });
    show();
    expect(await screen.findByText("model disagrees")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Merge, keep “Maria Lopez”/ })).toBeEnabled();
  });

  it("merges keeping the name you choose", async () => {
    setup({ pending: [suggestion()] });
    api.accept.mockResolvedValue({ absorbed: "M. Lopez", kept: "Maria Lopez" });
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Merge, keep “Maria Lopez”" }));
    expect(api.accept).toHaveBeenCalledWith("s1", "a1");
    expect(await screen.findByText("Merged “M. Lopez” into “Maria Lopez”")).toBeInTheDocument();
    expect(onChange).toHaveBeenCalled();
  });

  it("can keep the other name", async () => {
    setup({ pending: [suggestion()] });
    api.accept.mockResolvedValue({ absorbed: "Maria Lopez", kept: "M. Lopez" });
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Merge, keep “M. Lopez”" }));
    expect(api.accept).toHaveBeenCalledWith("s1", "b1");
  });

  it("marks a pair as different things", async () => {
    setup({ pending: [suggestion()] });
    api.reject.mockResolvedValue({});
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Different things" }));
    expect(api.reject).toHaveBeenCalledWith("s1");
    expect(await screen.findByRole("status")).toHaveTextContent("Kept apart");
  });

  it("reloads the lists after a decision", async () => {
    setup({ pending: [suggestion()] });
    api.reject.mockResolvedValue({});
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Different things" }));
    await screen.findByRole("status");
    expect(api.suggestions.mock.calls.filter(([s]) => s === "pending").length).toBeGreaterThanOrEqual(2);
  });

  it("shows why a decision failed and leaves the card in place", async () => {
    setup({ pending: [suggestion()] });
    api.accept.mockRejectedValue(new Error("Those two are already merged"));
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Merge, keep “Maria Lopez”" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Those two are already merged");
    expect(screen.getByRole("article", { name: "Maria Lopez and M. Lopez" })).toBeInTheDocument();
  });

  it("runs the duplicate search, with or without the model, and reports the result", async () => {
    setup();
    api.runResolution.mockResolvedValue({ auto_merged: 2, suggestions_new: 1, judged: 0 });
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Look for duplicates now" }));
    expect(api.runResolution).toHaveBeenLastCalledWith(false);
    expect(await screen.findByText("2 merges made, 1 new suggestion.")).toBeInTheDocument();

    api.runResolution.mockResolvedValue({ auto_merged: 0, suggestions_new: 3, judged: 3 });
    await userEvent.click(screen.getByLabelText(/Ask the model for a second opinion/));
    await userEvent.click(screen.getByRole("button", { name: "Look for duplicates now" }));
    expect(api.runResolution).toHaveBeenLastCalledWith(true);
    expect(await screen.findByText("0 merges made, 3 new suggestions, 3 checked by the model.")).toBeInTheDocument();
  });

  it("shows an error when the search fails", async () => {
    setup();
    api.runResolution.mockRejectedValue(new Error("Model not reachable"));
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Look for duplicates now" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Model not reachable");
  });
});

describe("Review: history and kept apart", () => {
  it("lists merges and how each came about", async () => {
    setup({ merges: [merge(), merge({ id: "m2", absorbed: "Beta", kept: "Beta Systems", how: "manual", reasons: [] }), merge({ id: "m3", absorbed: "X", kept: "Y", how: "suggestion", reasons: ["r"] })] });
    show();
    await userEvent.click(await screen.findByRole("tab", { name: "Merged" }));
    expect(await screen.findByText(/merged automatically · Same name/)).toBeInTheDocument();
    expect(screen.getByText("merged by you")).toBeInTheDocument();
    expect(screen.getByText(/you accepted a suggestion · r/)).toBeInTheDocument();
  });

  it("undoes a merge", async () => {
    setup({ merges: [merge()] });
    api.undo.mockResolvedValue({});
    show();
    await userEvent.click(await screen.findByRole("tab", { name: "Merged" }));
    await userEvent.click(await screen.findByRole("button", { name: "Undo" }));
    expect(api.undo).toHaveBeenCalledWith("m1");
    expect(await screen.findByText("Undid the merge of “M. Lopez”")).toBeInTheDocument();
  });

  it("asks for undone merges as well, so the history is complete", async () => {
    setup();
    show();
    await screen.findByText("Nothing to review");
    expect(api.merges).toHaveBeenCalledWith(true);
  });

  it("shows an undone merge as undone, without another Undo", async () => {
    setup({ merges: [merge({ undone: true })] });
    show();
    await userEvent.click(await screen.findByRole("tab", { name: "Merged" }));
    expect(await screen.findByText("undone")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Undo" })).not.toBeInTheDocument();
  });

  it("says when nothing was merged", async () => {
    setup();
    show();
    await userEvent.click(await screen.findByRole("tab", { name: "Merged" }));
    expect(await screen.findByText("No merges yet")).toBeInTheDocument();
  });

  it("lists pairs kept apart, or explains the empty list", async () => {
    setup({ rejected: [suggestion({ id: "r1" })] });
    show();
    await userEvent.click(await screen.findByRole("tab", { name: "Kept apart" }));
    expect(await screen.findByText(/kept apart/)).toBeInTheDocument();
    expect(screen.getByRole("article", { name: "Maria Lopez and M. Lopez" })).toBeInTheDocument();
  });

  it("explains an empty kept-apart list", async () => {
    setup();
    show();
    await userEvent.click(await screen.findByRole("tab", { name: "Kept apart" }));
    expect(await screen.findByText("Nothing kept apart")).toBeInTheDocument();
  });

  it("marks the open tab", async () => {
    setup();
    show();
    const tab = await screen.findByRole("tab", { name: "Merged" });
    await userEvent.click(tab);
    expect(tab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Kept apart" })).toHaveAttribute("aria-selected", "false");
  });
});

describe("Review: conflicts tab", () => {
  it("shows how many conflicts are open on the tab and opens it", async () => {
    setup();
    api.conflicts.mockImplementation(async (s) => ({ conflicts: s === "open" ? [{ id: "c1", kind: "reversed", severity: "possible", reasons: [], llm_verdict: null, a: { id: "a", text: "A acquired B", sources: [] }, b: { id: "b", text: "B acquired A", sources: [] }, can_end_earlier: false }] : [] }));
    show();
    const tab = await screen.findByRole("tab", { name: "Conflicts (1)" });
    await userEvent.click(tab);
    expect(await screen.findByRole("button", { name: "Look for conflicts now" })).toBeInTheDocument();
    expect(await screen.findByRole("article", { name: "A acquired B and B acquired A" })).toBeInTheDocument();
  });

  it("has no number on the tab when nothing is open, and opens on the tab named in the address", async () => {
    setup();
    api.conflicts.mockResolvedValue({ conflicts: [] });
    render(<Review onChange={onChange} params={{ tab: "conflicts" }} />);
    expect(await screen.findByRole("tab", { name: "Conflicts" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByText("No open conflicts")).toBeInTheDocument();
  });

  it("ignores a tab name it does not know", async () => {
    setup();
    api.conflicts.mockResolvedValue({ conflicts: [] });
    render(<Review onChange={onChange} params={{ tab: "nonsense" }} />);
    expect(await screen.findByRole("tab", { name: /Suggestions/ })).toHaveAttribute("aria-selected", "true");
  });
});

describe("Review: the conflicts count follows decisions", () => {
  it("drops the number on the tab when the last conflict is settled", async () => {
    setup();
    let open = [{ id: "c1", kind: "reversed", severity: "possible", reasons: [], llm_verdict: null, a: { id: "a", text: "A acquired B", valid_from: null, valid_to: null, sources: [] }, b: { id: "b", text: "B acquired A", valid_from: null, valid_to: null, sources: [] }, can_end_earlier: false }];
    api.conflicts.mockImplementation(async (s) => ({ conflicts: s === "open" ? open : [] }));
    api.resolveConflict.mockImplementation(async () => { open = []; return {}; });
    show();
    await userEvent.click(await screen.findByRole("tab", { name: "Conflicts (1)" }));
    await userEvent.click(await screen.findByRole("button", { name: "Both are true" }));
    expect(await screen.findByRole("tab", { name: "Conflicts" })).toBeInTheDocument();
    expect(onChange).toHaveBeenCalled();
  });
});
