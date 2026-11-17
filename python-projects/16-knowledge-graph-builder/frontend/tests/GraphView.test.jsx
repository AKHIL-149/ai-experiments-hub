import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import GraphView from "../src/components/GraphView";
import { doc, entityDetail, graph } from "./helpers";

vi.mock("../src/api", async () => (await import("./mockapi")).apiMockFactory());
const { api } = await import("../src/api");

const go = vi.fn();
const show = (params = {}) => render(<GraphView params={params} go={go} />);
const nodeButton = (name) => screen.findByRole("button", { name: new RegExp(`^${name},`) });

beforeEach(() => {
  vi.clearAllMocks();
  window.matchMedia = vi.fn().mockReturnValue({ matches: true, addEventListener() {}, removeEventListener() {} });
  api.graph.mockResolvedValue(graph());
  api.documents.mockResolvedValue({ documents: [doc({ id: "d1", title: "Report" }), doc({ id: "d2", title: "Broken", status: "failed" })] });
  api.entity.mockResolvedValue(entityDetail());
  api.entities.mockResolvedValue({ entities: [] });
  api.fact.mockResolvedValue({
    id: "f1", subject_id: "n1", subject: "Acme Corp", predicate: "acquired", object_id: "n2", object: "Beta Systems", object_is_value: false,
    valid_from: "2020-03", valid_to: null, sources: [{ document_id: "d1", document_title: "News", chunk_id: "c1", quote: "Acme acquired Beta", passage: "Acme acquired Beta", verified: true }],
  });
});

// d3-zoom and d3-drag read pointer geometry that jsdom does not have, so clicks on the drawing itself are plain click events here
describe("GraphView: loading and showing", () => {
  it("loads the graph and counts what is on screen", async () => {
    show();
    expect(screen.getByText("Loading the graph…")).toBeInTheDocument();
    await nodeButton("Acme Corp");
    expect(screen.getByText("3 entities · 2 facts")).toBeInTheDocument();
    expect(api.graph).toHaveBeenCalledWith({ documentId: undefined, limit: 300 });
  });

  it("invites you to add documents when the graph is empty", async () => {
    api.graph.mockResolvedValue(graph({ nodes: [], edges: [], total_nodes: 0, total_edges: 0 }));
    show();
    expect(await screen.findByText("Your graph is empty")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add documents" }));
    expect(go).toHaveBeenCalledWith("documents");
  });

  it("shows an error with a way to try again", async () => {
    api.graph.mockRejectedValueOnce(new Error("Cannot reach the server."));
    show();
    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot reach the server.");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await nodeButton("Acme Corp");
  });

  it("says when only the best connected part is shown", async () => {
    api.graph.mockResolvedValue(graph({ truncated: true, total_nodes: 1200 }));
    show();
    expect(await screen.findByText(/Showing the 300 best connected of 1,200/)).toBeInTheDocument();
  });

  it("starts limited to the document named in the address, and changes with the selector", async () => {
    show({ doc: "d1" });
    await nodeButton("Acme Corp");
    expect(api.graph).toHaveBeenCalledWith({ documentId: "d1", limit: 300 });
    await userEvent.selectOptions(screen.getByLabelText("Document"), "");
    await waitFor(() => expect(api.graph).toHaveBeenLastCalledWith({ documentId: undefined, limit: 300 }));
  });

  it("only offers finished documents in the selector", async () => {
    show();
    await within(screen.getByLabelText("Document")).findByRole("option", { name: "Report" });
    expect(screen.queryByRole("option", { name: "Broken" })).not.toBeInTheDocument();
  });
});

describe("GraphView: filters and views", () => {
  it("counts entities per type and hides the types you switch off... or rather, shows only the ones you pick", async () => {
    show();
    await nodeButton("Acme Corp");
    const group = screen.getByRole("group", { name: "Show these kinds of entity" });
    expect(within(group).getByRole("button", { name: /Person 1/ })).toBeInTheDocument();
    expect(within(group).getByRole("button", { name: /Organization 2/ })).toBeInTheDocument();
    await userEvent.click(within(group).getByRole("button", { name: /Person 1/ }));
    expect(screen.getByText("1 entity · 0 facts")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Acme Corp,/ })).not.toBeInTheDocument();
    await userEvent.click(within(group).getByRole("button", { name: /Person 1/ }));
    expect(screen.getByText("3 entities · 2 facts")).toBeInTheDocument();
  });

  it("offers a text version: a list of entities and facts", async () => {
    show();
    await nodeButton("Acme Corp");
    await userEvent.click(screen.getByRole("button", { name: "List" }));
    const entities = screen.getByRole("table", { name: "Entities" });
    expect(within(entities).getAllByRole("row")).toHaveLength(4);
    const facts = screen.getByRole("table", { name: "Facts" });
    const rows = within(facts).getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(within(rows[1]).getByText("Acme Corp")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Beta Systems")).toBeInTheDocument();
    expect(within(rows[1]).getByText("2020-03")).toBeInTheDocument();
  });

  it("lists the best connected entity first", async () => {
    const g = graph();
    api.graph.mockResolvedValue({ ...g, nodes: [g.nodes[2], g.nodes[1], g.nodes[0]] });     // delivered with the best connected last
    show();
    await nodeButton("Acme Corp");
    await userEvent.click(screen.getByRole("button", { name: "List" }));
    const rows = within(screen.getByRole("table", { name: "Entities" })).getAllByRole("row");
    expect(within(rows[1]).getByText("Acme Corp")).toBeInTheDocument();
  });

  it("opens an entity from the list and goes back to the graph with its panel", async () => {
    show();
    await nodeButton("Acme Corp");
    await userEvent.click(screen.getByRole("button", { name: "List" }));
    await userEvent.click(within(screen.getByRole("table", { name: "Entities" })).getByRole("button", { name: "Maria Lopez" }));
    expect(api.entity).toHaveBeenCalledWith("n3");
    expect(await screen.findByRole("complementary", { name: "Entity details" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Graph" })).toHaveAttribute("aria-pressed", "true");
  });

  it("opens a fact from the list", async () => {
    show();
    await nodeButton("Acme Corp");
    await userEvent.click(screen.getByRole("button", { name: "List" }));
    await userEvent.click(within(screen.getByRole("table", { name: "Facts" })).getByRole("button", { name: "acquired" }));
    expect(await screen.findByRole("complementary", { name: "Fact details" })).toBeInTheDocument();
    expect(api.fact).toHaveBeenCalledWith("f1");
  });
});

describe("GraphView: selecting, expanding, asking", () => {
  it("shows the panel for a clicked entity, and closes it", async () => {
    show();
    fireEvent.click(await nodeButton("Acme Corp"));
    const panel = await screen.findByRole("complementary", { name: "Entity details" });
    expect(await within(panel).findByRole("heading", { name: "Acme Corp" })).toBeInTheDocument();
    await userEvent.click(within(panel).getByRole("button", { name: "Close the entity panel" }));
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
  });

  it("shows the panel for a clicked fact line", async () => {
    const { container } = show();
    await nodeButton("Acme Corp");
    fireEvent.click(container.querySelector('g.edge[data-edge="f1"] path.hit'));
    const panel = await screen.findByRole("complementary", { name: "Fact details" });
    expect(await within(panel).findByText("Acme acquired Beta")).toBeInTheDocument();
  });

  it("adds the neighbours of an entity to what is on screen without losing the rest", async () => {
    api.neighborhood.mockResolvedValue({
      nodes: [{ id: "n1", name: "Acme Corp", type: "organization", degree: 3 }, { id: "n4", name: "Delta Works", type: "organization", degree: 1 }],
      edges: [{ id: "f3", source: "n1", target: "n4", predicate: "owns", valid_from: null, valid_to: null, source_count: 1 }],
    });
    show();
    fireEvent.click(await nodeButton("Acme Corp"));
    await userEvent.click(await screen.findByRole("button", { name: "Show neighbours" }));
    expect(await screen.findByText("Added 1 entity")).toBeInTheDocument();
    expect(screen.getByText("4 entities · 3 facts")).toBeInTheDocument();
    expect(api.neighborhood).toHaveBeenCalledWith("n1", 1, 200);
  });

  it("says when there was nothing more to add", async () => {
    api.neighborhood.mockResolvedValue(graph());
    show();
    fireEvent.click(await nodeButton("Acme Corp"));
    await userEvent.click(await screen.findByRole("button", { name: "Show neighbours" }));
    expect(await screen.findByText("Nothing more to show here")).toBeInTheDocument();
  });

  it("shows why expanding failed", async () => {
    api.neighborhood.mockRejectedValue(new Error("Entity not found"));
    show();
    fireEvent.click(await nodeButton("Acme Corp"));
    await userEvent.click(await screen.findByRole("button", { name: "Show neighbours" }));
    expect(await screen.findByText("Entity not found")).toBeInTheDocument();
  });

  it("sends you to Ask with a question about the entity", async () => {
    show();
    fireEvent.click(await nodeButton("Acme Corp"));
    await userEvent.click(await screen.findByRole("button", { name: "Ask about this" }));
    expect(go).toHaveBeenCalledWith("ask", { q: "What do we know about Acme Corp?" });
  });

  it("reloads the graph and selects the kept entity after a merge", async () => {
    api.entities.mockResolvedValue({ entities: [{ id: "n9", name: "ACME Corporation", type: "organization" }] });
    api.merge.mockResolvedValue({});
    show();
    fireEvent.click(await nodeButton("Acme Corp"));
    await userEvent.click(await screen.findByRole("button", { name: "Merge…" }));
    await userEvent.type(screen.getByLabelText("Find the other name"), "acme");
    await userEvent.click(await screen.findByRole("button", { name: /ACME Corporation/ }));
    await userEvent.click(screen.getByRole("button", { name: "Merge" }));
    expect(api.merge).toHaveBeenCalledWith("n1", "n9");
    expect(await screen.findByText("Merged into “Acme Corp”")).toBeInTheDocument();
    await waitFor(() => expect(api.graph).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("complementary", { name: "Entity details" })).toBeInTheDocument();
  });
});

describe("GraphView: search", () => {
  it("finds entities already on screen and in the whole graph, without repeats", async () => {
    api.entities.mockResolvedValue({ entities: [{ id: "n1", name: "Acme Corp", type: "organization" }, { id: "n7", name: "Acme Holdings", type: "organization" }] });
    show();
    await nodeButton("Acme Corp");
    await userEvent.type(screen.getByLabelText("Find an entity"), "acme");
    const list = await screen.findByRole("list", { name: "Matching entities" });
    await within(list).findByRole("button", { name: /Acme Holdings/ });
    expect(within(list).getAllByRole("button")).toHaveLength(2);
  });

  it("brings in an entity that is not on screen and selects it", async () => {
    api.entities.mockResolvedValue({ entities: [{ id: "n7", name: "Acme Holdings", type: "organization" }] });
    api.neighborhood.mockResolvedValue({ nodes: [{ id: "n7", name: "Acme Holdings", type: "organization", degree: 1 }], edges: [] });
    api.entity.mockResolvedValue(entityDetail({ id: "n7", name: "Acme Holdings", outgoing: [], incoming: [] }));
    show();
    await nodeButton("Acme Corp");
    await userEvent.type(screen.getByLabelText("Find an entity"), "holdings");
    await userEvent.click(await screen.findByRole("button", { name: /Acme Holdings/ }));
    expect(api.neighborhood).toHaveBeenCalledWith("n7", 1, 200);
    expect(await screen.findByRole("heading", { name: "Acme Holdings" })).toBeInTheDocument();
    expect(screen.getByLabelText("Find an entity")).toHaveValue("");
  });

  it("does not ask the server for fewer than two letters", async () => {
    show();
    await nodeButton("Acme Corp");
    await userEvent.type(screen.getByLabelText("Find an entity"), "a");
    await new Promise((r) => setTimeout(r, 350));
    expect(api.entities).not.toHaveBeenCalled();
    expect(await screen.findByRole("list", { name: "Matching entities" })).toBeInTheDocument();   // but on-screen matches still show
  });
});

describe("GraphView: arriving from another screen", () => {
  it("opens the entity named in the address", async () => {
    show({ entity: "n1" });
    expect(await screen.findByRole("heading", { name: "Acme Corp" })).toBeInTheDocument();
    expect(api.entity).toHaveBeenCalledWith("n1");
  });

  it("brings in an entity named in the address that is not on screen", async () => {
    api.neighborhood.mockResolvedValue({ nodes: [{ id: "n7", name: "Far Away", type: "place", degree: 1 }], edges: [] });
    show({ entity: "n7" });
    await waitFor(() => expect(api.neighborhood).toHaveBeenCalledWith("n7", 1, 200));
    expect(await screen.findByText("4 entities · 2 facts")).toBeInTheDocument();
  });

  it("highlights the facts an answer cited, and clears them on request", async () => {
    const { container } = show({ facts: "f1,f2" });
    await waitFor(() => expect(api.fact).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(container.querySelectorAll("g.edge.hl")).toHaveLength(2));
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();      // two facts: no single panel
    await userEvent.click(screen.getByRole("button", { name: "Clear highlight" }));
    expect(container.querySelectorAll("g.edge.hl")).toHaveLength(0);
  });

  it("opens the panel for a single cited fact", async () => {
    show({ fact: "f1" });
    expect(await screen.findByRole("complementary", { name: "Fact details" })).toBeInTheDocument();
  });

  it("loads the neighbourhood of a cited fact that is not on screen", async () => {
    api.fact.mockResolvedValue({ id: "f5", subject_id: "n8", subject: "X", predicate: "knows", object_id: "n3", object: "Maria Lopez", object_is_value: false, sources: [] });
    api.neighborhood.mockResolvedValue({ nodes: [{ id: "n8", name: "X Person", type: "person", degree: 1 }], edges: [{ id: "f5", source: "n8", target: "n3", predicate: "knows", valid_from: null, valid_to: null, source_count: 1 }] });
    show({ fact: "f5" });
    await waitFor(() => expect(api.neighborhood).toHaveBeenCalledWith("n8", 1, 200));
    expect(await screen.findByText("4 entities · 3 facts")).toBeInTheDocument();
  });

  it("tells you when a cited fact no longer exists", async () => {
    api.fact.mockRejectedValue(new Error("Fact not found"));
    show({ facts: "gone" });
    expect(await screen.findByText("Fact not found")).toBeInTheDocument();
  });

  it("does not jump back to the entity from the address after you closed it and reloaded the graph", async () => {
    show({ entity: "n1" });
    const panel = await screen.findByRole("complementary", { name: "Entity details" });
    await userEvent.click(within(panel).getByRole("button", { name: "Close the entity panel" }));
    await userEvent.selectOptions(screen.getByLabelText("Document"), "d1");
    await waitFor(() => expect(api.graph).toHaveBeenCalledTimes(2));
    await act(async () => {});
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
  });

  it("keeps the highlighted facts when the graph reloads after a merge", async () => {
    api.entities.mockResolvedValue({ entities: [{ id: "n9", name: "ACME Corporation", type: "organization" }] });
    api.merge.mockResolvedValue({});
    const { container } = show({ facts: "f1,f2" });
    await waitFor(() => expect(container.querySelectorAll("g.edge.hl")).toHaveLength(2));
    fireEvent.click(await nodeButton("Acme Corp"));
    await userEvent.click(await screen.findByRole("button", { name: "Merge…" }));
    await userEvent.type(screen.getByLabelText("Find the other name"), "acme");
    await userEvent.click(await screen.findByRole("button", { name: /ACME Corporation/ }));
    await userEvent.click(screen.getByRole("button", { name: "Merge" }));
    await waitFor(() => expect(api.graph).toHaveBeenCalledTimes(2));
    await screen.findByText("Merged into “Acme Corp”");
    expect(container.querySelectorAll("g.edge.hl")).toHaveLength(2);
  });

  it("handles each address once, not on every re-render", async () => {
    const { rerender } = show({ entity: "n1" });
    await screen.findByRole("heading", { name: "Acme Corp" });
    rerender(<GraphView params={{ entity: "n1" }} go={go} />);
    await act(async () => {});
    expect(api.entity).toHaveBeenCalledTimes(1);
  });
});

describe("GraphView: finding a path", () => {
  const path = {
    from: "Maria Lopez", to: "Beta Systems",
    paths: [[
      { fact_id: "f2", text: "", from: "Maria Lopez", predicate: "founded", to: "Acme Corp" },
      { fact_id: "f1", text: "", from: "Acme Corp", predicate: "acquired", to: "Beta Systems" },
    ]],
  };

  async function startPathFromMaria() {
    api.entity.mockResolvedValue(entityDetail({ id: "n3", name: "Maria Lopez", type: "person", outgoing: [], incoming: [] }));
    fireEvent.click(await nodeButton("Maria Lopez"));
    await userEvent.click(await screen.findByRole("button", { name: "Find a path to…" }));
    expect(screen.getByText("Pick the entity to connect to")).toBeInTheDocument();
  }

  it("highlights the shortest chain and lists its steps", async () => {
    api.path.mockResolvedValue(path);
    api.neighborhood.mockResolvedValue(graph());
    const { container } = show();
    await startPathFromMaria();
    fireEvent.click(screen.getByRole("button", { name: /^Beta Systems,/ }));
    expect(api.path).toHaveBeenCalledWith("n3", "n2", 4);
    const note = await screen.findByRole("status", { name: "Path found" });
    expect(note).toHaveTextContent("Maria Lopez → Beta Systems: 2 steps");
    expect(within(note).getAllByRole("listitem")).toHaveLength(2);
    expect(container.querySelectorAll("g.edge.hl")).toHaveLength(2);
    expect(screen.queryByText("Pick the entity to connect to")).not.toBeInTheDocument();
  });

  it("says when there is no connection", async () => {
    api.path.mockResolvedValue({ from: "Maria Lopez", to: "Beta Systems", paths: [] });
    show();
    await startPathFromMaria();
    fireEvent.click(screen.getByRole("button", { name: /^Beta Systems,/ }));
    expect(await screen.findByText("No connection within 4 links.")).toBeInTheDocument();
  });

  it("shows why a path search failed and stops waiting for a second pick", async () => {
    api.path.mockRejectedValue(new Error("No entity matches 'x'"));
    show();
    await startPathFromMaria();
    fireEvent.click(screen.getByRole("button", { name: /^Beta Systems,/ }));
    expect(await screen.findByText("No entity matches 'x'")).toBeInTheDocument();
    expect(screen.queryByText("Pick the entity to connect to")).not.toBeInTheDocument();
  });

  it("clicking the same entity again does not start a path to itself", async () => {
    show();
    await startPathFromMaria();
    fireEvent.click(screen.getByRole("button", { name: /^Maria Lopez,/ }));
    expect(api.path).not.toHaveBeenCalled();
  });
});
