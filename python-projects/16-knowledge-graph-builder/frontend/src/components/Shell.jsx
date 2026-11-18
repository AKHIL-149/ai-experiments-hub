import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { usePolling } from "../hooks";
import { timeUntil } from "../lib/format";
import { useRoute } from "../router";
import Ask from "./Ask";
import Brand from "./Brand";
import Check from "./Check";
import Documents from "./Documents";
import GraphView from "./GraphView";
import Review from "./Review";

const TABS = [
  ["graph", "Graph"],
  ["documents", "Documents"],
  ["ask", "Ask"],
  ["check", "Check"],
  ["review", "Review"],
];

function useCounts() {
  const [counts, setCounts] = useState({ active: 0, suggestions: 0, ready: null, detail: "" });
  const load = async () => {
    const [jobs, sugg, clash, health] = await Promise.allSettled([api.jobs("active"), api.suggestions("pending"), api.conflicts("open"), api.health()]);
    setCounts({
      active: jobs.status === "fulfilled" ? jobs.value.jobs.length : 0,
      suggestions: (sugg.status === "fulfilled" ? sugg.value.suggestions.length : 0) + (clash.status === "fulfilled" && clash.value ? clash.value.conflicts.length : 0),
      ready: health.status === "fulfilled" && health.value.llm ? health.value.llm.ready : null,
      detail: health.status === "fulfilled" && health.value.llm ? health.value.llm.detail : "",
    });
  };
  useEffect(() => { load(); }, []);
  usePolling(load, 8000);
  return [counts, load];
}

function GuestBanner({ user }) {
  const auth = useAuth();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const left = user.created_at && user.guest_ttl_hours ? timeUntil(new Date(new Date(user.created_at).getTime() + user.guest_ttl_hours * 3600000).toISOString()) : "";

  async function submit(ev) {
    ev.preventDefault();
    setErr("");
    setBusy(true);
    try {
      await auth.register(name, pw);
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="banner warn" style={{ borderRadius: 0, borderWidth: "0 0 1px 0" }} role="status">
      <div className="row wrap">
        <span>You are a guest{left ? `: this account and its documents are deleted in ${left}` : ""}.</span>
        <button className="btn small" onClick={() => setOpen((o) => !o)} aria-expanded={open}>Keep it: create an account</button>
      </div>
      {open && (
        <form className="row wrap" style={{ marginTop: "0.5rem" }} onSubmit={submit}>
          <label className="sr-only" htmlFor="up-name">Username</label>
          <input id="up-name" type="text" placeholder="Username" value={name} onChange={(e) => setName(e.target.value)} style={{ width: 180 }} required />
          <label className="sr-only" htmlFor="up-pw">Password</label>
          <input id="up-pw" type="password" placeholder="Password (8+ characters)" value={pw} onChange={(e) => setPw(e.target.value)} style={{ width: 220 }} required />
          <button className="btn primary small" disabled={busy}>Create account</button>
          {err && <span role="alert" style={{ color: "var(--danger)" }}>{err}</span>}
        </form>
      )}
    </div>
  );
}

export default function Shell() {
  const auth = useAuth();
  const { route, params, go } = useRoute();
  const [counts, reloadCounts] = useCounts();
  const [menu, setMenu] = useState(false);
  const menuRef = useRef(null);
  const user = auth.user;

  useEffect(() => {
    if (!menu) return undefined;
    const close = (e) => { if (menuRef.current && !menuRef.current.contains(e.target)) setMenu(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menu]);

  const badge = { documents: counts.active, review: counts.suggestions };

  return (
    <div className="app">
      <header className="topbar">
        <Brand />
        <nav className="nav" aria-label="Main">
          {TABS.map(([id, label]) => (
            <a key={id} href={`#/${id}`} aria-current={route === id ? "page" : undefined}>
              {label}
              {badge[id] > 0 && <span className="badge" aria-label={`${badge[id]} ${id === "documents" ? "in progress" : "to review"}`}>{badge[id]}</span>}
            </a>
          ))}
        </nav>
        <span className="spacer" />
        <span className="row small muted" title={counts.detail || ""}>
          <span className={`dot ${counts.ready === true ? "ok" : counts.ready === false ? "bad" : ""}`} aria-hidden="true" />
          {counts.ready === true ? "Model ready" : counts.ready === false ? "Model not ready" : "Model unknown"}
        </span>
        <div className="account" ref={menuRef}>
          <button className="btn small ghost" aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu((m) => !m)}>
            {user.display_name || user.username}{user.is_guest ? " (guest)" : ""} ▾
          </button>
          {menu && (
            <div className="menu" role="menu">
              <div className="small muted" style={{ padding: "0.25rem 0.5rem" }}>{user.local_mode ? "Single-user mode: everything is yours" : `Signed in as ${user.username}`}</div>
              {!user.local_mode && <button className="btn small ghost" role="menuitem" style={{ width: "100%", justifyContent: "flex-start" }} onClick={auth.logout}>Sign out</button>}
            </div>
          )}
        </div>
      </header>
      {user.is_guest && <GuestBanner user={user} />}
      <main className="main" id="main">
        {route === "graph" && <GraphView params={params} go={go} />}
        {route === "documents" && <Documents go={go} onChange={reloadCounts} />}
        {route === "ask" && <Ask params={params} go={go} />}
        {route === "check" && <Check params={params} go={go} />}
        {route === "review" && <Review onChange={reloadCounts} go={go} params={params} />}
      </main>
    </div>
  );
}
