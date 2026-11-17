import { render } from "@testing-library/react";
import { vi } from "vitest";
import { AuthProvider } from "../src/auth";

/** Replace every api method by a vi.fn(); the test sets what each returns */
export async function mockedApi() {
  const mod = await import("../src/api");
  return mod.api;
}

export function withAuth(ui) {
  return render(<AuthProvider>{ui}</AuthProvider>);
}

export const USER = { id: 1, username: "ann", display_name: "ann", is_guest: false, created_at: "2026-01-01T00:00:00Z" };
export const CONFIG = { require_login: true, registration: true, guests: true, guest_ttl_hours: 24, guest_max_documents: 3, min_password: 8 };

export function doc(over = {}) {
  return {
    id: "d1", title: "Report", filename: "report.txt", status: "completed", error: null, char_count: 1200, chunk_count: 2, chunks_done: 2,
    stats: { accepted: 5, rejected: {} }, model: "ollama:llama3.1:8b", job: { id: "j1", status: "completed", attempts: 1, position: null, cancel_requested: false }, ...over,
  };
}

export function graph(over = {}) {
  return {
    nodes: [
      { id: "n1", name: "Acme Corp", type: "organization", degree: 2, attributes: [] },
      { id: "n2", name: "Beta Systems", type: "organization", degree: 1, attributes: [] },
      { id: "n3", name: "Maria Lopez", type: "person", degree: 1, attributes: [] },
    ],
    edges: [
      { id: "f1", source: "n1", target: "n2", predicate: "acquired", valid_from: "2020-03", valid_to: null, source_count: 1 },
      { id: "f2", source: "n3", target: "n1", predicate: "founded", valid_from: "2010", valid_to: null, source_count: 2 },
    ],
    total_nodes: 3, total_edges: 2, truncated: false, ...over,
  };
}

export function entityDetail(over = {}) {
  return {
    id: "n1", name: "Acme Corp", type: "organization", aliases: ["ACME"],
    outgoing: [
      { id: "f1", subject_id: "n1", subject: "Acme Corp", predicate: "acquired", object_id: "n2", object: "Beta Systems", object_is_value: false, valid_from: "2020-03", valid_to: null, source_count: 1 },
      { id: "f9", subject_id: "n1", subject: "Acme Corp", predicate: "employs", object_id: null, object: "340 people", object_is_value: true, valid_from: null, valid_to: null, source_count: 1 },
    ],
    incoming: [
      { id: "f2", subject_id: "n3", subject: "Maria Lopez", predicate: "founded", object_id: "n1", object: "Acme Corp", object_is_value: false, valid_from: "2010", valid_to: null, source_count: 2 },
    ],
    ...over,
  };
}

export { vi };
