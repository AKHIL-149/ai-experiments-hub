import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Documents from "../src/components/Documents";
import { doc } from "./helpers";

vi.mock("../src/api", async () => (await import("./mockapi")).apiMockFactory());
const { api } = await import("../src/api");

const go = vi.fn();
const onChange = vi.fn();
const show = () => render(<Documents go={go} onChange={onChange} />);
const list = (...documents) => api.documents.mockResolvedValue({ documents });

beforeEach(() => { vi.clearAllMocks(); });
afterEach(() => vi.useRealTimers());

describe("Documents", () => {
  it("invites you to add a first document", async () => {
    list();
    show();
    expect(await screen.findByText("No documents yet")).toBeInTheDocument();
    expect(screen.getByText(".txt, .md, .pdf or .docx")).toBeInTheDocument();
  });

  it("shows each document with its state", async () => {
    list(
      doc({ id: "a", title: "Done doc" }),
      doc({ id: "b", title: "Waiting doc", status: "pending", chunks_done: 0, job: { id: "jb", status: "pending", position: 2, cancel_requested: false } }),
      doc({ id: "c", title: "Busy doc", status: "processing", chunks_done: 1, chunk_count: 4, job: { id: "jc", status: "running", cancel_requested: false } }),
      doc({ id: "d", title: "Broken doc", status: "failed", error: "No text could be read" }),
      doc({ id: "e", title: "Stopped doc", status: "failed", error: "Cancelled" }),
    );
    show();
    const done = await screen.findByRole("article", { name: "Done doc" });
    expect(within(done).getByText("Read")).toBeInTheDocument();
    expect(within(done).getByText("5 facts found")).toBeInTheDocument();
    expect(within(screen.getByRole("article", { name: "Waiting doc" })).getByText(/place 2 in the queue/)).toBeInTheDocument();
    const busy = screen.getByRole("article", { name: "Busy doc" });
    expect(within(busy).getByText("Reading: 1/4 passages")).toBeInTheDocument();
    expect(within(busy).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "25");
    expect(within(screen.getByRole("article", { name: "Broken doc" })).getByText("No text could be read")).toBeInTheDocument();
    expect(within(screen.getByRole("article", { name: "Stopped doc" })).getAllByText("Cancelled")).toHaveLength(2); // the chip and the detail line
    expect(screen.getByRole("status")).toHaveTextContent("1 being read · 1 waiting");
  });

  it("offers only what makes sense for each state", async () => {
    list(doc({ id: "a", title: "Done doc" }), doc({ id: "c", title: "Busy doc", status: "processing", chunks_done: 1, chunk_count: 4, job: { id: "jc", cancel_requested: false } }));
    show();
    const done = await screen.findByRole("article", { name: "Done doc" });
    expect(within(done).getAllByRole("button").map((b) => b.textContent)).toEqual(["View graph", "Read again", "Delete"]);
    const busy = screen.getByRole("article", { name: "Busy doc" });
    expect(within(busy).getAllByRole("button").map((b) => b.textContent)).toEqual(["Cancel"]);
  });

  it("opens the graph limited to that document", async () => {
    list(doc());
    show();
    await userEvent.click(await screen.findByRole("button", { name: "View graph" }));
    expect(go).toHaveBeenCalledWith("graph", { doc: "d1" });
  });

  it("cancels a running document, and shows that it is stopping", async () => {
    list(doc({ status: "processing", chunks_done: 1, chunk_count: 4, job: { id: "j9", cancel_requested: false } }));
    api.cancelJob.mockResolvedValue({});
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(api.cancelJob).toHaveBeenCalledWith("j9");
    expect(await screen.findByText("Cancelling…")).toBeInTheDocument();
  });

  it("disables Cancel once a stop was asked for", async () => {
    list(doc({ status: "processing", chunks_done: 1, chunk_count: 4, job: { id: "j9", cancel_requested: true } }));
    show();
    expect(await screen.findByRole("button", { name: "Stopping…" })).toBeDisabled();
    expect(screen.getByText(/stopping after this passage/)).toBeInTheDocument();
  });

  it("reads a document again", async () => {
    list(doc());
    api.reprocess.mockResolvedValue({});
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Read again" }));
    expect(api.reprocess).toHaveBeenCalledWith("d1");
    expect(await screen.findByText("Queued to be read again")).toBeInTheDocument();
    expect(onChange).toHaveBeenCalled();
  });

  it("deletes only after you confirm", async () => {
    list(doc());
    api.deleteDocument.mockResolvedValue({});
    const confirm = vi.spyOn(window, "confirm");
    show();
    const del = await screen.findByRole("button", { name: "Delete" });
    confirm.mockReturnValueOnce(false);
    await userEvent.click(del);
    expect(api.deleteDocument).not.toHaveBeenCalled();
    confirm.mockReturnValueOnce(true);
    await userEvent.click(del);
    expect(confirm).toHaveBeenLastCalledWith("Delete “Report” and the facts only it supports?");
    expect(api.deleteDocument).toHaveBeenCalledWith("d1");
    confirm.mockRestore();
  });

  it("shows why an action failed", async () => {
    list(doc());
    api.reprocess.mockRejectedValue(new Error("A document is being read"));
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Read again" }));
    expect(await screen.findByText("A document is being read")).toBeInTheDocument();
  });

  it("explains refused candidates, merged names and an index problem", async () => {
    list(doc({ stats: { accepted: 3, rejected: { quote_not_found: 2, bad_name: 1 }, resolution: { auto_merged: 2 }, embedding_error: "Ollama is off" } }));
    show();
    const card = await screen.findByRole("article", { name: "Report" });
    expect(card).toHaveTextContent("3 candidates refused by the checks");
    expect(card).toHaveTextContent("2 duplicate names merged");
    expect(card).toHaveTextContent("search index: Ollama is off");
  });

  it("shows an error with a way to try again", async () => {
    api.documents.mockRejectedValueOnce(new Error("Cannot reach the server."));
    list(doc());
    show();
    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot reach the server.");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("article", { name: "Report" })).toBeInTheDocument();
  });

  it("uploads chosen files, one after another, and stops at the first failure", async () => {
    list();
    api.uploadFile.mockResolvedValueOnce({}).mockRejectedValueOnce(new Error("Unsupported file type")).mockResolvedValue({});
    show();
    await screen.findByText("No documents yet");
    const input = screen.getByLabelText("Choose files");
    const files = ["a.txt", "b.exe", "c.txt"].map((n) => new File(["hello"], n));
    await userEvent.upload(input, files);
    expect(api.uploadFile).toHaveBeenCalledTimes(2);
    expect(await screen.findByRole("alert")).toHaveTextContent("Unsupported file type");
    expect(screen.queryByText("Added “c.txt”")).not.toBeInTheDocument();
  });

  it("lets you choose the same file again after an upload", async () => {
    list();
    api.uploadFile.mockResolvedValue({});
    show();
    await screen.findByText("No documents yet");
    const input = screen.getByLabelText("Choose files");
    await userEvent.upload(input, new File(["hello"], "a.txt"));
    await waitFor(() => expect(api.uploadFile).toHaveBeenCalled());
    await waitFor(() => expect(input.files).toHaveLength(0));
  });

  it("stops highlighting the zone when a drag leaves it", async () => {
    list();
    show();
    await screen.findByText("No documents yet");
    const zone = screen.getByText("Drop files here").closest(".dropzone");
    fireEvent.dragOver(zone);
    expect(zone).toHaveClass("over");
    fireEvent.dragLeave(zone);
    expect(zone).not.toHaveClass("over");
  });

  it("uploads files dropped on the zone", async () => {
    list();
    api.uploadFile.mockResolvedValue({});
    show();
    await screen.findByText("No documents yet");
    const zone = screen.getByText("Drop files here").closest(".dropzone");
    fireEvent.dragOver(zone);
    expect(zone).toHaveClass("over");
    fireEvent.drop(zone, { dataTransfer: { files: [new File(["x"], "dropped.md")] } });
    await waitFor(() => expect(api.uploadFile).toHaveBeenCalledTimes(1));
    expect(zone).not.toHaveClass("over");
    expect(await screen.findByText("Added “dropped.md”")).toBeInTheDocument();
  });

  it("adds pasted text and clears the form", async () => {
    list();
    api.addText.mockResolvedValue({});
    show();
    await userEvent.click(await screen.findByText("Or paste text"));
    await userEvent.type(screen.getByLabelText("Title"), "Notes");
    await userEvent.type(screen.getByLabelText("Text"), "Acme acquired Beta Systems in 2020.");
    await userEvent.click(screen.getByRole("button", { name: "Add text" }));
    expect(api.addText).toHaveBeenCalledWith("Notes", "Acme acquired Beta Systems in 2020.");
    await waitFor(() => expect(screen.getByLabelText("Title")).toHaveValue(""));
    expect(screen.getByLabelText("Text")).toHaveValue("");
  });

  it("keeps the pasted text when the server refuses it", async () => {
    list();
    api.addText.mockRejectedValue(new Error("You have reached the limit of 3 documents"));
    show();
    await userEvent.click(await screen.findByText("Or paste text"));
    await userEvent.type(screen.getByLabelText("Title"), "Notes");
    await userEvent.type(screen.getByLabelText("Text"), "Acme acquired Beta Systems in 2020.");
    await userEvent.click(screen.getByRole("button", { name: "Add text" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("limit of 3 documents");
    expect(screen.getByLabelText("Title")).toHaveValue("Notes");
  });

  it("follows documents being read every 2 seconds, and checks slowly when nothing is active", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    list(doc({ status: "processing", chunks_done: 0, chunk_count: 4, job: { id: "j", cancel_requested: false } }));
    show();
    await screen.findByRole("article", { name: "Report" });
    const before = api.documents.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(4100); });
    expect(api.documents.mock.calls.length).toBeGreaterThanOrEqual(before + 2);

    api.documents.mockResolvedValue({ documents: [doc()] });
    await act(async () => { await vi.advanceTimersByTimeAsync(2100); });
    await screen.findByText("Read");
    const settled = api.documents.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(6000); });
    expect(api.documents.mock.calls.length).toBe(settled);
    await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
    expect(api.documents.mock.calls.length).toBeGreaterThan(settled);
  });
});
