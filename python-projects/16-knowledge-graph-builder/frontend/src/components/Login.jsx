import { useState } from "react";
import { useAuth } from "../auth";
import Brand from "./Brand";

export default function Login() {
  const auth = useAuth();
  const cfg = auth.config || {};
  const [mode, setMode] = useState("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [display, setDisplay] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const canRegister = cfg.registration !== false;
  const min = cfg.min_password || 8;

  async function run(call) {
    setError("");
    setBusy(true);
    try {
      await call();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function submit(ev) {
    ev.preventDefault();
    if (mode === "login") run(() => auth.login(username, password));
    else run(() => auth.register(username, password, display));
  }

  return (
    <main className="login">
      <div className="card login-card stack">
        <div>
          <Brand size={34} />
          <p className="muted small" style={{ textAlign: "center" }}>Turn documents into a graph you can explore and question.</p>
        </div>
        {auth.notice && <div className="banner warn" role="status">{auth.notice}</div>}
        <div className="tabs" role="tablist" aria-label="Sign in or create an account">
          <button role="tab" aria-selected={mode === "login"} onClick={() => { setMode("login"); setError(""); }}>Sign in</button>
          {canRegister && <button role="tab" aria-selected={mode === "register"} onClick={() => { setMode("register"); setError(""); }}>Create account</button>}
        </div>
        <form className="stack" onSubmit={submit}>
          <div className="field">
            <label htmlFor="username">Username</label>
            <input id="username" type="text" autoComplete="username" autoCapitalize="none" spellCheck="false" value={username} onChange={(e) => setUsername(e.target.value)} required />
          </div>
          {mode === "register" && (
            <div className="field">
              <label htmlFor="display">Display name <span className="muted">(optional)</span></label>
              <input id="display" type="text" autoComplete="name" value={display} onChange={(e) => setDisplay(e.target.value)} />
            </div>
          )}
          <div className="field">
            <label htmlFor="password">Password</label>
            <input id="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} value={password} onChange={(e) => setPassword(e.target.value)} required />
            {mode === "register" && <span className="muted small">At least {min} characters. Usernames: letters, numbers, dot, dash or underscore.</span>}
          </div>
          {error && <div className="banner error" role="alert">{error}</div>}
          <button className="btn primary" type="submit" disabled={busy}>{busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}</button>
        </form>
        {cfg.guests !== false && (
          <div className="stack" style={{ borderTop: "1px solid var(--border)", paddingTop: "0.9rem" }}>
            <button className="btn" onClick={() => run(auth.guest)} disabled={busy}>Continue as a guest</button>
            <p className="muted small">
              A guest account is temporary{cfg.guest_ttl_hours ? ` (${cfg.guest_ttl_hours} hours)` : ""} and can hold {cfg.guest_max_documents || 3} documents.
              You can turn it into a real account later without losing them.
            </p>
          </div>
        )}
      </div>
    </main>
  );
}
