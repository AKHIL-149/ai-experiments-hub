import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { ApiError, api, setUnauthorizedHandler } from "./api";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

/** Who is signed in. status: loading | anon | user. In single-user mode the server answers "local" and there is no sign-in. */
export function AuthProvider({ children }) {
  const [state, setState] = useState({ status: "loading", user: null, config: null, notice: "" });

  const refresh = useCallback(async () => {
    let config = null;
    try {
      config = await api.authConfig();
    } catch (e) {
      setState({ status: "anon", user: null, config: null, notice: e.message });
      return;
    }
    try {
      const user = await api.me();
      setState({ status: "user", user, config, notice: "" });
    } catch (e) {
      setState({ status: "anon", user: null, config, notice: e instanceof ApiError && e.status !== 401 ? e.message : "" });
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    setUnauthorizedHandler(() => setState((s) => (s.status === "user" ? { ...s, status: "anon", user: null, notice: "Your session ended. Please sign in again." } : s)));
    return () => setUnauthorizedHandler(null);
  }, []);

  const enter = useCallback(async (call) => {
    const user = await call();   // errors are shown by the caller (the login form)
    setState((s) => ({ ...s, status: "user", user, notice: "" }));
    return user;
  }, []);

  const value = useMemo(() => ({
    ...state,
    login: (u, p) => enter(() => api.login(u, p)),
    register: (u, p, d) => enter(() => api.register(u, p, d)),
    guest: () => enter(() => api.guest()),
    logout: async () => {
      try {
        await api.logout();
      } finally {
        setState((s) => ({ ...s, status: "anon", user: null, notice: "" }));
      }
    },
    refresh,
  }), [state, enter, refresh]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
