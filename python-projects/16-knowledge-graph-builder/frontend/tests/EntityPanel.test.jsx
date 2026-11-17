import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import EntityPanel from "../src/components/EntityPanel";
import { entityDetail } from "./helpers";

vi.mock("../src/api", async () => (await import("./mockapi")).apiMockFactory());
const { api } = await import("../src/api");

const h = { onExpand: vi.fn(), onAsk: vi.fn(), onStartPath: vi.fn(), onSelectFact: vi.fn(), onSelectEntity: vi.fn(), onMerged: vi.fn(), onClose: vi.fn() };
const show = (props = {}) => render(<EntityPanel id="n1" pathFrom={null} {...h} {...props} />);

beforeEach(() => {
  vi.clearAllMocks();
  api.entity.mockResolvedValue(entityDetail());
});

describe("EntityPanel", () => {
  it("groups facts into details, links from this and links to this", async () => {
    show();
    expect(await screen.findByRole("heading", { name: "Acme Corp" })).toBeInTheDocument();
    expect(screen.getByText("3 facts")).toBeInTheDocument();
    expect(screen.getByText("ACME")).toBeInTheDocument();
    const details = screen.getByRole("heading", { name: "Details" }).parentElement;
    expect(within(details).getByText("340 people")).toBeInTheDocument();
    const from = screen.getByRole("heading", { name: "Links from this" }).parentElement;
    expect(within(from).getByRole("button", { name: "Beta Systems" })).toBeInTheDocument();
    expect(within(from).getByText("2020-03")).toBeInTheDocument();
    const to = screen.getByRole("heading", { name: "Links to this" }).parentElement;
    expect(within(to).getByRole("button", { name: "Maria Lopez" })).toBeInTheDocument();
    expect(within(to).getByText("×2")).toBeInTheDocument();
    expect(screen.queryByText("×1")).not.toBeInTheDocument();       // one source says nothing extra
  });

  it("leaves out groups with nothing in them", async () => {
    api.entity.mockResolvedValue(entityDetail({ aliases: [], outgoing: [], incoming: [] }));
    show();
    expect(await screen.findByText("No facts about this entity.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Details" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Also written/)).not.toBeInTheDocument();
  });

  it("follows facts and entities", async () => {
    show();
    await userEvent.click(await screen.findByRole("button", { name: "acquired" }));
    expect(h.onSelectFact).toHaveBeenCalledWith("f1");
    await userEvent.click(screen.getByRole("button", { name: "Beta Systems" }));
    expect(h.onSelectEntity).toHaveBeenCalledWith("n2");
    await userEvent.click(screen.getByRole("button", { name: "Maria Lopez" }));
    expect(h.onSelectEntity).toHaveBeenCalledWith("n3");
  });

  it("expands, asks and starts a path from this entity", async () => {
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Show neighbours" }));
    expect(h.onExpand).toHaveBeenCalledWith("n1");
    await userEvent.click(screen.getByRole("button", { name: "Ask about this" }));
    expect(h.onAsk).toHaveBeenCalledWith(expect.objectContaining({ id: "n1", name: "Acme Corp" }));
    await userEvent.click(screen.getByRole("button", { name: "Find a path to…" }));
    expect(h.onStartPath).toHaveBeenCalledWith("n1");
  });

  it("says a path is being picked", async () => {
    show({ pathFrom: "n1" });
    expect(await screen.findByRole("button", { name: "Pick the other end…" })).toHaveAttribute("aria-pressed", "true");
  });

  it("can be closed", async () => {
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Close the entity panel" }));
    expect(h.onClose).toHaveBeenCalled();
  });

  it("shows an error when the entity is gone", async () => {
    api.entity.mockRejectedValue(new Error("Entity not found"));
    show();
    expect(await screen.findByRole("alert")).toHaveTextContent("Entity not found");
  });
});

describe("EntityPanel: merging", () => {
  async function open() {
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Merge…" }));
  }

  it("searches for the other entity, never offering this one", async () => {
    api.entities.mockResolvedValue({ entities: [{ id: "n1", name: "Acme Corp", type: "organization" }, { id: "n9", name: "ACME Corporation", type: "organization" }] });
    await open();
    await userEvent.type(screen.getByLabelText("Find the other name"), "acme");
    const list = await screen.findByRole("list", { name: "Matches" });
    expect(await within(list).findByRole("button", { name: /ACME Corporation/ })).toBeInTheDocument();
    expect(within(list).queryByRole("button", { name: /^.*Acme Corp$/ })).not.toBeInTheDocument();
    expect(api.entities).toHaveBeenCalledWith("acme", undefined, 8);
  });

  it("does not search for fewer than two letters", async () => {
    await open();
    await userEvent.type(screen.getByLabelText("Find the other name"), "a");
    await new Promise((r) => setTimeout(r, 300));
    expect(api.entities).not.toHaveBeenCalled();
  });

  it("says when nothing matches", async () => {
    api.entities.mockResolvedValue({ entities: [] });
    await open();
    await userEvent.type(screen.getByLabelText("Find the other name"), "zzz");
    expect(await screen.findByText("No other entity matches.")).toBeInTheDocument();
  });

  async function choose() {
    api.entities.mockResolvedValue({ entities: [{ id: "n9", name: "ACME Corporation", type: "organization" }] });
    await open();
    await userEvent.type(screen.getByLabelText("Find the other name"), "acme");
    await userEvent.click(await screen.findByRole("button", { name: /ACME Corporation/ }));
  }

  it("merges keeping this name by default", async () => {
    api.merge.mockResolvedValue({});
    await choose();
    expect(screen.getByText(/become one entity/)).toBeInTheDocument();
    expect(screen.getByLabelText("Acme Corp")).toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: "Merge" }));
    expect(api.merge).toHaveBeenCalledWith("n1", "n9");
    expect(h.onMerged).toHaveBeenCalledWith("n1", "Acme Corp");
  });

  it("merges keeping the other name when chosen", async () => {
    api.merge.mockResolvedValue({});
    await choose();
    await userEvent.click(screen.getByLabelText("ACME Corporation"));
    await userEvent.click(screen.getByRole("button", { name: "Merge" }));
    expect(api.merge).toHaveBeenCalledWith("n9", "n1");
    expect(h.onMerged).toHaveBeenCalledWith("n9", "ACME Corporation");
  });

  it("shows why a merge failed and stays open", async () => {
    api.merge.mockRejectedValue(new Error("These entities have different types"));
    await choose();
    await userEvent.click(screen.getByRole("button", { name: "Merge" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("different types");
    expect(h.onMerged).not.toHaveBeenCalled();
  });

  it("goes back to the search, and can be cancelled", async () => {
    await choose();
    await userEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByLabelText("Find the other name")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel merging" }));
    expect(screen.queryByLabelText("Find the other name")).not.toBeInTheDocument();
  });
});

describe("EntityPanel: timeline", () => {
  const tl = (over = {}) => ({
    entity: { id: "n1", name: "Acme Corp", type: "organization" },
    facts: [
      { id: "t1", subject: "Maria Lopez", predicate: "was CTO of", object: "Acme Corp", direction: "in", valid_from: "2012", valid_to: "2019" },
      { id: "t2", subject: "Acme Corp", predicate: "acquired", object: "Beta Systems", direction: "out", valid_from: "2020-03", valid_to: null },
      { id: "t3", subject: "Acme Corp", predicate: "employs", object: "340 people", direction: "out", valid_from: null, valid_to: null },
    ], ...over,
  });

  it("is closed until asked for, then lists the facts in the order the server gives, as sentences", async () => {
    api.timeline.mockResolvedValue(tl());
    show();
    await screen.findByRole("heading", { name: "Acme Corp" });
    expect(api.timeline).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Timeline" }));
    const box = await screen.findByLabelText("Timeline");
    const items = await within(box).findAllByRole("listitem");
    expect(items.map((li) => li.textContent)).toEqual([
      "2012 – 2019Maria Lopez was CTO of Acme Corp", "2020-03Acme Corp acquired Beta Systems", "no dateAcme Corp employs 340 people"]);
    expect(api.timeline).toHaveBeenCalledWith("n1", "");
  });

  it("shows what each fact means for the chosen time, and fades those outside", async () => {
    api.timeline.mockResolvedValue(tl({ window: { label: "2021" }, facts: tl().facts.map((f, i) => ({ ...f, time: ["outside", "open", "undated"][i] })) }));
    show({ at: "2021" });
    await userEvent.click(await screen.findByRole("button", { name: "Timeline" }));
    const box = await screen.findByLabelText("Timeline");
    expect(within(box).getByRole("heading", { name: "Timeline · 2021" })).toBeInTheDocument();
    const items = await within(box).findAllByRole("listitem");
    expect(items[0]).toHaveClass("outside");
    expect(items[1]).not.toHaveClass("outside");
    expect(within(items[1]).getByText("no end stated")).toHaveAttribute("title", expect.stringMatching(/may still have held/));
    expect(within(items[2]).getAllByText("no date")).toHaveLength(1);       // said once, in the date column
    expect(api.timeline).toHaveBeenCalledWith("n1", "2021");
  });

  it("loads the timeline again when the chosen time changes", async () => {
    api.timeline.mockResolvedValue(tl());
    const { rerender } = show({ at: "2015" });
    await userEvent.click(await screen.findByRole("button", { name: "Timeline" }));
    await screen.findByLabelText("Timeline");
    rerender(<EntityPanel id="n1" at="2021" pathFrom={null} {...h} />);
    await waitFor(() => expect(api.timeline).toHaveBeenLastCalledWith("n1", "2021"));
  });

  it("opens a fact from the timeline", async () => {
    api.timeline.mockResolvedValue(tl());
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Timeline" }));
    await userEvent.click(await screen.findByRole("button", { name: "Acme Corp acquired Beta Systems" }));
    expect(h.onSelectFact).toHaveBeenCalledWith("t2");
  });

  it("says when there are no facts, shows errors, and closes again", async () => {
    api.timeline.mockResolvedValueOnce(tl({ facts: [] }));
    show();
    const btn = await screen.findByRole("button", { name: "Timeline" });
    await userEvent.click(btn);
    expect(await screen.findByText("No facts.")).toBeInTheDocument();
    await userEvent.click(btn);
    expect(screen.queryByLabelText("Timeline")).not.toBeInTheDocument();
    api.timeline.mockRejectedValueOnce(new Error("Entity not found"));
    await userEvent.click(btn);
    expect(await screen.findByRole("alert")).toHaveTextContent("Entity not found");
  });
});
