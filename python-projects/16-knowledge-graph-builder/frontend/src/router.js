import { useCallback, useEffect, useState } from "react";

export const ROUTES = ["graph", "documents", "ask", "review"];

/** Parse "#/graph?entity=abc" into { route, params } (unknown routes fall back to the graph) */
export function parseHash(hash) {
  const raw = (hash || "").replace(/^#\/?/, "");
  const [path, qs = ""] = raw.split("?");
  const route = ROUTES.includes(path) ? path : "graph";
  const params = Object.fromEntries(new URLSearchParams(qs));
  return { route, params };
}

export function buildHash(route, params = {}) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const qs = p.toString();
  return `#/${route}${qs ? `?${qs}` : ""}`;
}

/** The current screen from the address bar's #fragment, and a way to go elsewhere (back/forward work) */
export function useRoute() {
  const [state, setState] = useState(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setState(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  const go = useCallback((route, params) => {
    window.location.hash = buildHash(route, params);
  }, []);
  return { ...state, go };
}
