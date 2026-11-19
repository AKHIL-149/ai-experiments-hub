import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Export from "../src/components/Export";
import { doc } from "./helpers";

vi.mock("../src/api", async () => (await import("./mockapi")).apiMockFactory());
const { api } = await import("../src/api");

const counts = (over = {}) => ({ entities: 12, facts: 18, value_facts: 3, entity_facts: 15, sources: 21, left_out: 0, document: null, ...over });
const show = (params = {}) => render(<Export params={params} />);
const card = (name) => screen.getByRole("article", { name });

beforeEach(() => {
  vi.clearAllMocks();
  api.documents.mockResolvedValue({ documents: [doc({ id: "d1", title: "Annual report" }), doc({ id: "d2", title: "Still reading", status: "processing" }), doc({ id: "d3", title: "Broken", status: "failed" })] });
  api.exportSummary.mockResolvedValue(counts());
});

describe("Export", () => {
  it("offers the three formats, each downloading from the right address", async () => {
    show();
    expect(await screen.findByRole("link", { name: "Download JSON" })).toHaveAttribute("href", "/api/export?format=json");
    expect(screen.getByRole("link", { name: "Download CSV" })).toHaveAttribute("href", "/api/export?format=csv");
    expect(screen.getByRole("link", { name: "Download Cypher" })).toHaveAttribute("href", "/api/export?format=cypher");
    for (const name of ["JSON", "CSV", "Cypher"]) expect(within(card(name)).getByRole("link")).toHaveAttribute("download");
  });

  it("says what the download holds", async () => {
    show();
    expect(await screen.findByRole("status")).toHaveTextContent("This export holds: 12 entities, 18 facts (3 with a plain value), 21 quotes.");
  });

  it("names the file each card gives and what the Cypher script was tried on", async () => {
    show();
    await screen.findByRole("link", { name: "Download JSON" });
    expect(within(card("CSV")).getByText("knowledge-graph.zip")).toBeInTheDocument();
    expect(within(card("Cypher")).getByText(/not tried on Memgraph or other versions/)).toBeInTheDocument();
  });

  it("limits the export to a document that has been read, and only those", async () => {
    show();
    const select = await screen.findByLabelText("What to include");
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["All documents", "Only facts read from: Annual report"]);
    api.exportSummary.mockResolvedValue(counts({ facts: 4, document: { id: "d1", title: "Annual report" } }));
    await userEvent.selectOptions(select, "d1");
    expect(api.exportSummary).toHaveBeenLastCalledWith("d1");
    expect(await screen.findByRole("link", { name: "Download JSON" })).toHaveAttribute("href", "/api/export?format=json&document_id=d1");
    expect(screen.getByRole("status")).toHaveTextContent("4 facts");
  });

  it("goes back to everything when All documents is chosen again", async () => {
    show();
    const select = await screen.findByLabelText("What to include");
    await userEvent.selectOptions(select, "d1");
    await userEvent.selectOptions(select, "All documents");
    expect(select).toHaveValue("");
    expect(api.exportSummary).toHaveBeenLastCalledWith("");
    expect(await screen.findByRole("link", { name: "Download JSON" })).toHaveAttribute("href", "/api/export?format=json");
  });

  it("starts with the document named in the address", async () => {
    show({ doc: "d1" });
    expect(await screen.findByLabelText("What to include")).toHaveValue("d1");
    expect(api.exportSummary).toHaveBeenCalledWith("d1");
    expect(await screen.findByRole("link", { name: "Download CSV" })).toHaveAttribute("href", "/api/export?format=csv&document_id=d1");
  });

  it("stops counting quotes when they are switched off, and counts them again when they are switched on", async () => {
    show();
    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("21 quotes");
    await userEvent.click(screen.getByLabelText("Include the quote each fact was read from"));
    expect(status).toHaveTextContent("This export holds: 12 entities, 18 facts (3 with a plain value), no quotes (you switched them off).");
    expect(status).not.toHaveTextContent("21 quotes");
    await userEvent.click(screen.getByLabelText("Include the quote each fact was read from"));
    expect(status).toHaveTextContent("12 entities, 18 facts (3 with a plain value), 21 quotes.");
  });

  it("can leave the quotes out", async () => {
    show();
    await userEvent.click(await screen.findByLabelText("Include the quote each fact was read from"));
    for (const [name, base] of [["JSON", "json"], ["CSV", "csv"], ["Cypher", "cypher"]]) {
      expect(screen.getByRole("link", { name: `Download ${name}` })).toHaveAttribute("href", `/api/export?format=${base}&sources=false`);
    }
  });

  it("offers the constraint statements for Cypher only, on by default, and can drop them", async () => {
    show();
    const box = await screen.findByLabelText(/Start with constraint statements/);
    expect(box).toBeChecked();
    expect(within(card("JSON")).queryByRole("checkbox")).toBeNull();
    expect(within(card("CSV")).queryByRole("checkbox")).toBeNull();
    await userEvent.click(box);
    expect(screen.getByRole("link", { name: "Download Cypher" })).toHaveAttribute("href", "/api/export?format=cypher&schema=false");
    expect(screen.getByRole("link", { name: "Download JSON" })).toHaveAttribute("href", "/api/export?format=json");
  });

  it("says when facts are left out by settled conflicts, and does not when none are", async () => {
    api.exportSummary.mockResolvedValue(counts({ left_out: 2 }));
    show();
    expect(await screen.findByText(/2 facts are left out because you settled a conflict against them/)).toBeInTheDocument();
  });

  it("does not mention left-out facts when there are none", async () => {
    show();
    await screen.findByRole("status");
    expect(screen.queryByText(/left out/)).toBeNull();
  });

  it("offers nothing to download for an empty graph and says what to do", async () => {
    api.exportSummary.mockResolvedValue(counts({ entities: 0, facts: 0, value_facts: 0, entity_facts: 0, sources: 0 }));
    show();
    expect(await screen.findByText("Nothing to export yet")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Download/ })).toBeNull();
    for (const name of ["Download JSON", "Download CSV", "Download Cypher"]) expect(screen.getByRole("button", { name })).toBeDisabled();
  });

  it("does not offer downloads before the counts are known", () => {
    api.exportSummary.mockReturnValue(new Promise(() => {}));
    show();
    expect(screen.queryByRole("link", { name: /Download/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Download JSON" })).toBeDisabled();
  });

  it("shows why the counts could not be read", async () => {
    api.exportSummary.mockRejectedValue(new Error("The server had a problem. Try again in a moment."));
    show();
    expect(await screen.findByRole("alert")).toHaveTextContent("The server had a problem");
    expect(screen.queryByRole("link", { name: /Download/ })).toBeNull();
  });
});
