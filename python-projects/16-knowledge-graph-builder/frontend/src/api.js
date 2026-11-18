// The only place that talks to the server. Everything returns parsed JSON (or null for 204) or throws ApiError.

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail || `Request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

let onUnauthorized = () => {};
/** The app registers a function that is called when a signed-in session turns out to be over (HTTP 401) */
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn || (() => {});
}

function messageOf(body, status) {
  const detail = body && body.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => (d.msg ? d.msg.replace(/^Value error, /, "") : String(d))).join("; ");
  if (status === 429) return "Too many attempts, try again later";
  if (status >= 500) return "The server had a problem. Try again in a moment.";
  return `Request failed (${status})`;
}

function query(params) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params || {})) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

const NO_REDIRECT_ON_401 = new Set(["/api/auth/login", "/api/auth/register", "/api/auth/guest", "/api/auth/me", "/api/auth/config", "/api/health"]);

async function request(method, path, { body, params, form } = {}) {
  const init = { method, credentials: "same-origin", headers: {} };
  if (form) init.body = form;
  else if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path + query(params), init);
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check that it is running.");
  }
  if (res.status === 204) return null;
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* not JSON */
  }
  if (!res.ok) {
    if (res.status === 401 && !NO_REDIRECT_ON_401.has(path)) onUnauthorized();
    throw new ApiError(res.status, messageOf(data, res.status));
  }
  return data;
}

/** The address of a download: a plain link, so the browser saves the file and the signed-in cookie goes with it */
export function exportUrl(format, { documentId, sources = true, schema = true } = {}) {
  return "/api/export" + query({ format, document_id: documentId || undefined, sources: sources ? undefined : "false", schema: format === "cypher" && !schema ? "false" : undefined });
}

const get = (path, params) => request("GET", path, { params });
const post = (path, body, params) => request("POST", path, { body, params });

export const api = {
  health: () => get("/api/health"),
  authConfig: () => get("/api/auth/config"),
  me: () => get("/api/auth/me"),
  login: (username, password) => post("/api/auth/login", { username, password }),
  register: (username, password, display_name) => post("/api/auth/register", { username, password, display_name: display_name || undefined }),
  guest: () => post("/api/auth/guest"),
  logout: () => post("/api/auth/logout"),

  documents: () => get("/api/documents"),
  document: (id) => get(`/api/documents/${id}`),
  uploadFile: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("POST", "/api/documents", { form });
  },
  addText: (title, text) => post("/api/documents/text", { title, text }),
  reprocess: (id) => post(`/api/documents/${id}/reprocess`),
  deleteDocument: (id) => request("DELETE", `/api/documents/${id}`),
  jobs: (status) => get("/api/jobs", { status }),
  cancelJob: (id) => post(`/api/jobs/${id}/cancel`),

  graph: ({ documentId, type, limit, at } = {}) => get("/api/graph", { document_id: documentId, type, limit, at: at || undefined }),
  stats: () => get("/api/graph/stats"),
  entities: (q, type, limit) => get("/api/entities", { q, type, limit }),
  entity: (id) => get(`/api/entities/${id}`),
  neighborhood: (id, depth = 1, limit, at) => get(`/api/entities/${id}/neighborhood`, { depth, limit, at: at || undefined }),
  timeline: (id, at) => get(`/api/entities/${id}/timeline`, { at: at || undefined }),
  fact: (id) => get(`/api/facts/${id}`),
  path: (from, to, maxHops) => get("/api/query/path", { from, to, max_hops: maxHops }),
  link: (q) => get("/api/query/link", { q }),

  conflicts: (status = "open") => get("/api/conflicts", { status }),
  runConflicts: (useLlm) => post("/api/conflicts/run", { use_llm: !!useLlm }),
  resolveConflict: (id, resolution) => post(`/api/conflicts/${id}/resolve`, { resolution }),
  reopenConflict: (id) => post(`/api/conflicts/${id}/reopen`),
  check: (claim) => post("/api/check", { claim }),

  exportSummary: (documentId) => get("/api/export/summary", { document_id: documentId || undefined }),

  ask: (question, mode, documentId) => post("/api/ask", { question, mode, document_id: documentId || undefined }),

  suggestions: (status = "pending") => get("/api/resolution/suggestions", { status }),
  runResolution: (useLlm) => post("/api/resolution/run", { use_llm: !!useLlm }),
  accept: (id, keepId) => post(`/api/resolution/suggestions/${id}/accept`, keepId ? { keep_id: keepId } : undefined),
  reject: (id) => post(`/api/resolution/suggestions/${id}/reject`),
  merge: (keepId, absorbId) => post("/api/entities/merge", { keep_id: keepId, absorb_id: absorbId }),
  merges: (includeUndone = false) => get("/api/resolution/merges", { include_undone: includeUndone ? "true" : undefined }),
  undo: (id) => post(`/api/resolution/merges/${id}/undo`),
};
