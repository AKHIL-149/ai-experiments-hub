import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Check from "../src/components/Check";

vi.mock("../src/api", async () => (await import("./mockapi")).apiMockFactory());
const { api } = await import("../src/api");

const go = vi.fn();
const show = (params = {}) => render(<Check params={params} go={go} />);
const result = (over = {}) => ({
  claim: "Veltra acquired Soro in 2018.", parsed: { subject: "Veltra Dynamics", relation: "acquired", object: "Soro Labs", start: "2018", end: null },
  verdict: "supported", summary: "The documents say this: Veltra Dynamics acquired Soro Labs (2018..).",
  evidence: [{ role: "supports", fact_id: "f1", text: "Veltra Dynamics acquired Soro Labs", valid_from: "2018", valid_to: null, quote: "Veltra Dynamics acquired Soro Labs.", document_title: "d01", verified: true }],
  reasoning: ["subject: Veltra Dynamics; object: Soro Labs"], ...over,
});
async function check(text) {
  await userEvent.type(screen.getByLabelText("A claim"), text);
  await userEvent.click(screen.getByRole("button", { name: "Check" }));
}

beforeEach(() => vi.clearAllMocks());

describe("Check", () => {
  it("explains what it does before anything is checked", () => {
    show();
    expect(screen.getByText("Check a statement against what the documents say")).toBeInTheDocument();
    expect(screen.getByText(/not the same as false/)).toBeInTheDocument();
  });

  it("starts with the claim named in the address", () => {
    show({ claim: "Acme acquired Beta." });
    expect(screen.getByLabelText("A claim")).toHaveValue("Acme acquired Beta.");
  });

  it("refuses a claim that is too short without asking the server", async () => {
    show();
    await check("Hi");
    expect(await screen.findByRole("alert")).toHaveTextContent("at least 5 characters");
    expect(api.check).not.toHaveBeenCalled();
  });

  it("shows a supported claim with the quote, how it was read and how it was checked", async () => {
    api.check.mockResolvedValue(result());
    show();
    await check("Veltra acquired Soro in 2018.");
    expect(api.check).toHaveBeenCalledWith("Veltra acquired Soro in 2018.");
    const box = await screen.findByRole("region", { name: "Result" });
    expect(within(box).getByText("Supported")).toBeInTheDocument();
    expect(within(box).getByRole("status")).toHaveTextContent("The documents say this");
    expect(within(box).getByText(/Read as:/)).toHaveTextContent("Read as: Veltra Dynamics — acquired — Soro Labs (since 2018, no end stated)");
    expect(within(box).getByText("1 fact behind this")).toBeInTheDocument();
    expect(within(box).getByText("supports")).toBeInTheDocument();
    expect(within(box).getByText("Veltra Dynamics acquired Soro Labs.", { selector: "blockquote" })).toBeInTheDocument();
    await userEvent.click(within(box).getByText("How this was checked"));
    expect(within(box).getByText("subject: Veltra Dynamics; object: Soro Labs")).toBeInTheDocument();
  });

  it.each([
    ["contradicted", "Contradicted"], ["supported_other_dates", "Supported, but other dates"], ["not_found", "Not in the documents"], ["unclear", "Unclear"],
  ])("shows a %s verdict", async (verdict, label) => {
    api.check.mockResolvedValue(result({ verdict, evidence: [], parsed: null, reasoning: [] }));
    show();
    await check("Something is claimed.");
    expect(await screen.findByText(label)).toBeInTheDocument();
    expect(screen.queryByText(/Read as:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/fact behind this|facts behind this/)).not.toBeInTheDocument();
    expect(screen.queryByText("How this was checked")).not.toBeInTheDocument();
  });

  it("marks contradicting and related evidence differently", async () => {
    api.check.mockResolvedValue(result({ verdict: "contradicted", evidence: [
      { role: "contradicts", fact_id: "f2", text: "Soro Labs acquired Veltra Dynamics", valid_from: "2011", valid_to: "2013", quote: null, document_title: null, verified: false },
      { role: "related", fact_id: "f3", text: "Veltra invested in Soro", valid_from: null, valid_to: null, quote: "Veltra invested in Soro.", document_title: "d02", verified: false }] }));
    show();
    await check("Something is claimed.");
    expect(await screen.findByText("contradicts")).toBeInTheDocument();
    expect(screen.getByText("related")).toBeInTheDocument();
    expect(screen.getByText("2011 – 2013")).toBeInTheDocument();
    expect(screen.getByText("no date")).toBeInTheDocument();
    expect(screen.getByText("2 facts behind this")).toBeInTheDocument();
  });

  it("opens the evidence in the graph", async () => {
    api.check.mockResolvedValue(result());
    show();
    await check("Veltra acquired Soro in 2018.");
    await userEvent.click(await screen.findByRole("button", { name: "Show them in the graph" }));
    expect(go).toHaveBeenCalledWith("graph", { facts: "f1" });
    await userEvent.click(screen.getByRole("button", { name: "Open in the graph" }));
    expect(go).toHaveBeenCalledWith("graph", { fact: "f1" });
  });

  it("shows the server's reason when checking fails, and lets you try again", async () => {
    api.check.mockRejectedValueOnce(new Error("The model is not reachable"));
    api.check.mockResolvedValue(result());
    show();
    await check("Veltra acquired Soro in 2018.");
    expect(await screen.findByRole("alert")).toHaveTextContent("The model is not reachable");
    await userEvent.click(screen.getByRole("button", { name: "Check" }));
    expect(await screen.findByText("Supported")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("is disabled while checking", async () => {
    let finish;
    api.check.mockReturnValue(new Promise((r) => { finish = r; }));
    show();
    await check("Veltra acquired Soro in 2018.");
    expect(screen.getByRole("button", { name: "Checking…" })).toBeDisabled();
    finish(result());
    expect(await screen.findByText("Supported")).toBeInTheDocument();
  });
});

describe("Check: details", () => {
  it("sends the claim without the spaces around it", async () => {
    api.check.mockResolvedValue(result());
    show();
    await userEvent.type(screen.getByLabelText("A claim"), "   Veltra acquired Soro.   ");
    await userEvent.click(screen.getByRole("button", { name: "Check" }));
    expect(api.check).toHaveBeenCalledWith("Veltra acquired Soro.");
  });

  it("says nothing about dates when the claim had none", async () => {
    api.check.mockResolvedValue(result({ parsed: { subject: "A", relation: "knows", object: "B", start: null, end: null } }));
    show();
    await check("A knows B.");
    expect(await screen.findByText(/Read as:/)).toHaveTextContent("Read as: A — knows — B");
    expect(screen.getByText(/Read as:/).textContent).not.toMatch(/\(/);
  });

  it("opens every fact behind the verdict in the graph at once", async () => {
    api.check.mockResolvedValue(result({ evidence: [
      { role: "supports", fact_id: "f2", text: "A", valid_from: null, valid_to: null, quote: null, document_title: null, verified: false },
      { role: "related", fact_id: "f3", text: "B", valid_from: null, valid_to: null, quote: null, document_title: null, verified: false }] }));
    show();
    await check("A knows B.");
    await userEvent.click(await screen.findByRole("button", { name: "Show them in the graph" }));
    expect(go).toHaveBeenCalledWith("graph", { facts: "f2,f3" });
  });

  it("clears the earlier result while the next check runs", async () => {
    api.check.mockResolvedValueOnce(result());
    show();
    await check("Veltra acquired Soro in 2018.");
    await screen.findByText("Supported");
    api.check.mockReturnValue(new Promise(() => {}));
    await userEvent.click(screen.getByRole("button", { name: "Check" }));
    expect(screen.queryByText("Supported")).not.toBeInTheDocument();
    expect(screen.getByText("Looking through your graph…")).toBeInTheDocument();
  });
});
