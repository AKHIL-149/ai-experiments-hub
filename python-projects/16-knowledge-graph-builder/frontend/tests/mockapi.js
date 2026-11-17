import { vi } from "vitest";

/** Factory for vi.mock("../src/api", ...): every api method becomes a vi.fn(), the rest stays real */
export async function apiMockFactory() {
  const actual = await vi.importActual("../src/api");
  const api = Object.fromEntries(Object.keys(actual.api).map((k) => [k, vi.fn()]));
  return { ...actual, api };
}
