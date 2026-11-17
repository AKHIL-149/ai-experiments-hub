import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Ask from "../src/components/Ask";
import { doc } from "./helpers";

vi.mock("../src/api", async () => (await import("./mockapi")).apiMockFactory());
const { api } = await import("../src/api");

const go = vi.fn();
const show = (params = {}) => render(<Ask params={params} go={go} />);

const factCite = (over = {}) => ({
  label: "F1", kind: "fact", fact_id: "f1", text: "Soro Labs founded_by Ines Varga (..2006)", document_title: "News", quote: "Ines Varga founded Soro Labs", verified: true, ...over,
});
const answer = (over = {}) => ({
  found: true, answer: "Kellmar", mode: "graph", citations: [factCite(), factCite({ label: "F2", fact_id: "f2" })],
  reasoning: { mode: "graph", facts_considered: 2, passages_considered: 0, seeds: [{ entity_id: "e1", name: "Soro Labs", how: "exact", also_could_be: [] }], steps: [] },
  timings_ms: { retrieve: 400, answer: 1200 }, ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  api.documents.mockResolvedValue({ documents: [doc({ id: "d1", title: "Report" }), doc({ id: "d2", title: "Unread", status: "failed" })] });
});

async function ask(text) {
  await userEvent.type(screen.getByLabelText("Your question"), text);
  await userEvent.click(screen.getByRole("button", { name: "Ask" }));
}

describe("Ask", () => {
  it("invites a first question", async () => {
    show();
    expect(screen.getByText("Ask about what is in your documents")).toBeInTheDocument();
  });

  it("starts with the question named in the address", () => {
    show({ q: "Who founded Acme?" });
    expect(screen.getByLabelText("Your question")).toHaveValue("Who founded Acme?");
  });

  it("only offers finished documents as the place to look", async () => {
    show();
    const scope = screen.getByLabelText("Look in");
    await within(scope).findByRole("option", { name: "Report" });
    expect(within(scope).queryByRole("option", { name: "Unread" })).not.toBeInTheDocument();
  });

  it("refuses a question that is too short without asking the server", async () => {
    show();
    await ask("hi");
    expect(await screen.findByRole("alert")).toHaveTextContent("at least 3 characters");
    expect(api.ask).not.toHaveBeenCalled();
  });

  it("shows the answer with its citations and quotes", async () => {
    api.ask.mockResolvedValue(answer());
    show();
    await ask("In which city is the university?");
    expect(api.ask).toHaveBeenCalledWith("In which city is the university?", "graph", "");
    expect(await screen.findByText("Kellmar")).toBeInTheDocument();
    expect(screen.getByText("2 citations")).toBeInTheDocument();
    expect(screen.getAllByText("Soro Labs founded_by Ines Varga (– 2006)")).toHaveLength(2);
    expect(screen.getAllByText("Ines Varga founded Soro Labs")).toHaveLength(2);
  });

  it("says the documents do not say, instead of showing a guess", async () => {
    api.ask.mockResolvedValue({ found: false, answer: "whatever the model said", note: "No fact links these", citations: [], reasoning: null });
    show();
    await ask("Who is the chief executive?");
    expect(await screen.findByText("The documents do not say.")).toBeInTheDocument();
    expect(screen.queryByText("whatever the model said")).not.toBeInTheDocument();
    expect(screen.getByText("No fact links these")).toBeInTheDocument();
  });

  it("shows the cited facts in the graph", async () => {
    api.ask.mockResolvedValue(answer());
    show();
    await ask("In which city is the university?");
    await userEvent.click(await screen.findByRole("button", { name: "Show them in the graph" }));
    expect(go).toHaveBeenCalledWith("graph", { facts: "f1,f2" });
  });

  it("opens one cited fact in the graph", async () => {
    api.ask.mockResolvedValue(answer());
    show();
    await ask("In which city is the university?");
    await userEvent.click((await screen.findAllByRole("button", { name: "Open in the graph" }))[1]);
    expect(go).toHaveBeenCalledWith("graph", { fact: "f2" });
  });

  it("shows a passage citation and offers no graph button when only passages were cited", async () => {
    api.ask.mockResolvedValue(answer({ citations: [{ label: "P1", kind: "passage", text: "Ines Varga founded Soro Labs in 2006. ".repeat(30), document_title: "News" }] }));
    show();
    await ask("Who founded Soro Labs?");
    expect(await screen.findByText("passage")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show them in the graph" })).not.toBeInTheDocument();
    expect(screen.getByText(/…$/)).toBeInTheDocument();
  });

  it("warns about citations that were removed, and about a model warning", async () => {
    api.ask.mockResolvedValue(answer({ dropped_citations: ["F9"], warning: "Some evidence was left out" }));
    show();
    await ask("In which city is the university?");
    expect(await screen.findByText(/cited F9, which it was never given/)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Some evidence was left out");
  });

  it("uses the chosen mode and document", async () => {
    api.ask.mockResolvedValue(answer());
    show();
    await screen.findByRole("option", { name: "Report" });
    await userEvent.selectOptions(screen.getByLabelText("How"), "hybrid");
    await userEvent.selectOptions(screen.getByLabelText("Look in"), "d1");
    await ask("Who founded Soro Labs?");
    expect(api.ask).toHaveBeenCalledWith("Who founded Soro Labs?", "hybrid", "d1");
  });

  it("puts the graph answer next to the passage search when comparing", async () => {
    api.ask.mockImplementation(async (q, mode) => (mode === "vector" ? { found: false, citations: [], note: "" } : answer()));
    show();
    await userEvent.click(screen.getByLabelText(/Compare with passage search/));
    await ask("In which city is the university?");
    const g = await screen.findByRole("region", { name: "Graph answer" });
    const p = screen.getByRole("region", { name: "Passage search" });
    expect(within(g).getByText("Kellmar")).toBeInTheDocument();
    expect(within(p).getByText("The documents do not say.")).toBeInTheDocument();
    expect(api.ask.mock.calls.map((c) => c[1])).toEqual(["graph", "vector"]);
  });

  it("turns compare off when the mode is passages only", async () => {
    show();
    await userEvent.selectOptions(screen.getByLabelText("How"), "vector");
    expect(screen.getByLabelText(/Compare with passage search/)).toBeDisabled();
  });

  it("explains how the answer was reached", async () => {
    api.ask.mockResolvedValue(answer({
      reasoning: {
        mode: "graph", facts_considered: 2, passages_considered: 1,
        seeds: [{ entity_id: "e1", name: "Soro Labs", how: "alias", also_could_be: ["Soro Ltd"] }],
        plan: { start: ["Soro Labs"], steps: [{ relation: "founded_by", direction: "out" }, { relation: "attended", direction: "in" }] },
        steps: [{ step: 1, relation: "founded_by", flipped: true, links: [{ fact: "Soro Labs founded_by Ines Varga (..2006)" }] }],
        paths: [["A knows B", "B knows C"]], fallback: "no fact matches 'attended'", evidence_documents: ["News"],
      },
    }));
    show();
    await ask("In which city is the university?");
    await userEvent.click(await screen.findByText("How this was answered"));
    expect(screen.getByText("Soro Labs", { selector: "li" })).toBeInTheDocument();
    expect(screen.getByText(/could also be Soro Ltd/)).toBeInTheDocument();
    expect(screen.getByText("forwards", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("direction reversed")).toBeInTheDocument();
    expect(screen.getByText("A knows B → B knows C")).toBeInTheDocument();
    expect(screen.getByText(/chain could not be followed/)).toBeInTheDocument();
    expect(screen.getByText(/1.6s/)).toBeInTheDocument();
  });

  it("shows the server's reason when asking fails, and lets you ask again", async () => {
    api.ask.mockRejectedValueOnce(new Error("The model is not reachable"));
    api.ask.mockResolvedValue(answer());
    show();
    await ask("In which city is the university?");
    expect(await screen.findByRole("alert")).toHaveTextContent("The model is not reachable");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText("Kellmar")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("is disabled while thinking", async () => {
    let finish;
    api.ask.mockReturnValue(new Promise((r) => { finish = r; }));
    show();
    await ask("In which city is the university?");
    expect(screen.getByRole("button", { name: "Thinking…" })).toBeDisabled();
    expect(screen.getByText("Looking through your graph…")).toBeInTheDocument();
    finish(answer());
    expect(await screen.findByText("Kellmar")).toBeInTheDocument();
  });

  it("sends on Ctrl+Enter", async () => {
    api.ask.mockResolvedValue(answer());
    show();
    await userEvent.type(screen.getByLabelText("Your question"), "In which city is it?{Control>}{Enter}{/Control}");
    expect(api.ask).toHaveBeenCalledTimes(1);
  });

  it("keeps the last 8 recent questions, newest first, each only once", async () => {
    api.ask.mockResolvedValue({ found: false, citations: [] });
    show();
    const box = () => screen.getByLabelText("Your question");
    const send = async (q) => {
      await userEvent.clear(box());
      await userEvent.type(box(), q);
      await userEvent.click(screen.getByRole("button", { name: "Ask" }));
      await screen.findByText("The documents do not say.");
    };
    for (let i = 1; i <= 9; i += 1) await send(`Question number ${i}`);
    await send("Question number 5");            // asked again: moves to the front, not added twice
    api.ask.mockRejectedValueOnce(new Error("boom"));
    await send2();
    async function send2() {
      await userEvent.clear(box());
      await userEvent.type(box(), "One more question");
      await userEvent.click(screen.getByRole("button", { name: "Ask" }));
      await screen.findByRole("alert");
    }
    const items = within(screen.getByRole("region", { name: "Recent questions" })).getAllByRole("listitem").map((li) => li.querySelector("button").textContent);
    expect(items).toEqual(["Question number 5", "Question number 9", "Question number 8", "Question number 7", "Question number 6", "Question number 4", "Question number 3", "Question number 2"]);
  });

  it("follows a new question from the address", () => {
    const { rerender } = show({ q: "First one" });
    expect(screen.getByLabelText("Your question")).toHaveValue("First one");
    rerender(<Ask params={{ q: "Second one" }} go={go} />);
    expect(screen.getByLabelText("Your question")).toHaveValue("Second one");
  });

  it("lists recent questions once a new one is under way, and brings one back into the box", async () => {
    api.ask.mockResolvedValueOnce(answer()).mockRejectedValueOnce(new Error("The model is not reachable"));
    show();
    await ask("First question here");
    await screen.findByText("Kellmar");
    expect(screen.queryByRole("region", { name: "Recent questions" })).not.toBeInTheDocument(); // hidden while a result is shown
    await userEvent.clear(screen.getByLabelText("Your question"));
    await userEvent.type(screen.getByLabelText("Your question"), "Second question here");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByRole("alert");
    const recent = screen.getByRole("region", { name: "Recent questions" });
    expect(within(recent).getByText("→ Kellmar")).toBeInTheDocument();
    await userEvent.click(within(recent).getByRole("button", { name: "First question here" }));
    expect(screen.getByLabelText("Your question")).toHaveValue("First question here");
  });
});
