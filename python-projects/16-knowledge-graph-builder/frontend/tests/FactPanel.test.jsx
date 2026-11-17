import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../src/api";
import FactPanel from "../src/components/FactPanel";

vi.mock("../src/api", async () => (await import("./mockapi")).apiMockFactory());
const { api } = await import("../src/api");

const fact = (over = {}) => ({
  id: "f1", subject_id: "n1", subject: "Acme Corp", predicate: "acquired", object_id: "n2", object: "Beta Systems", object_is_value: false,
  valid_from: "2020-03", valid_to: null,
  sources: [{ document_id: "d1", document_title: "News", chunk_id: "c1", quote: "Acme acquired Beta Systems", passage: "Last year, Acme acquired Beta Systems for cash.", verified: true }], ...over,
});
const handlers = { onSelectEntity: vi.fn(), onClose: vi.fn() };
const show = () => render(<FactPanel id="f1" {...handlers} />);

beforeEach(() => vi.clearAllMocks());

describe("FactPanel", () => {
  it("shows the fact, when it held, and where it was read", async () => {
    api.fact.mockResolvedValue(fact());
    show();
    expect(await screen.findByRole("button", { name: "Acme Corp" })).toBeInTheDocument();
    expect(screen.getByText("acquired")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Beta Systems" })).toBeInTheDocument();
    expect(screen.getByText("2020-03")).toBeInTheDocument();
    expect(screen.getByText("1 source")).toBeInTheDocument();
    expect(screen.getByText("News")).toBeInTheDocument();
    expect(screen.getByText("Acme acquired Beta Systems", { selector: "blockquote" })).toBeInTheDocument();
    expect(screen.getByText("checked")).toBeInTheDocument();
  });

  it("highlights the quote inside its passage, as text and not as HTML", async () => {
    api.fact.mockResolvedValue(fact({ sources: [{ document_id: "d1", document_title: "<b>T</b>", chunk_id: "c1", quote: "Acme acquired Beta Systems", passage: "Last year, Acme acquired Beta Systems for <script>x</script> cash.", verified: false }] }));
    const { container } = show();
    await userEvent.click(await screen.findByText("Show the passage"));
    expect(container.querySelector("mark")).toHaveTextContent("Acme acquired Beta Systems");
    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByText("<b>T</b>")).toBeInTheDocument();
    expect(screen.queryByText("checked")).not.toBeInTheDocument();
  });

  it("shows a plain value without a link and omits a missing date", async () => {
    api.fact.mockResolvedValue(fact({ object_id: null, object: "340 people", object_is_value: true, valid_from: null }));
    show();
    expect(await screen.findByText("340 people")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "340 people" })).not.toBeInTheDocument();
    expect(screen.queryByText("When:")).not.toBeInTheDocument();
  });

  it("counts several sources", async () => {
    const s = fact().sources[0];
    api.fact.mockResolvedValue(fact({ sources: [s, { ...s, chunk_id: "c2", quote: "Beta was bought by Acme" }] }));
    show();
    expect(await screen.findByText("2 sources")).toBeInTheDocument();
  });

  it("goes to either end of the fact and can be closed", async () => {
    api.fact.mockResolvedValue(fact());
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Beta Systems" }));
    expect(handlers.onSelectEntity).toHaveBeenCalledWith("n2");
    await userEvent.click(screen.getByRole("button", { name: "Acme Corp" }));
    expect(handlers.onSelectEntity).toHaveBeenCalledWith("n1");
    await userEvent.click(screen.getByRole("button", { name: "Close the fact panel" }));
    expect(handlers.onClose).toHaveBeenCalled();
  });

  it("shows an error when the fact cannot be loaded", async () => {
    api.fact.mockRejectedValue(new ApiError(404, "Fact not found"));
    show();
    expect(await screen.findByRole("alert")).toHaveTextContent("Fact not found");
  });
});
