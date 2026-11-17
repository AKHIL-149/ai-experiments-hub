import { useCallback, useEffect, useRef, useState } from "react";

/** Run an async loader on mount (and whenever `deps` change): { data, error, loading, reload, setData } */
export function useAsync(loader, deps = []) {
  const [state, setState] = useState({ data: null, error: "", loading: true });
  const alive = useRef(true);
  const seq = useRef(0);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);
  const run = useCallback(async (quiet = false) => {
    const mine = ++seq.current;
    if (!quiet) setState((s) => ({ ...s, loading: true, error: "" }));
    try {
      const data = await loader();
      if (alive.current && mine === seq.current) setState({ data, error: "", loading: false });
    } catch (e) {
      if (alive.current && mine === seq.current) setState((s) => ({ data: quiet ? s.data : null, error: e.message || "Something went wrong", loading: false }));
    }
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { run(); }, [run]);
  const setData = useCallback((data) => setState((s) => ({ ...s, data })), []);
  return { ...state, reload: run, setData };
}

/** Call `fn` every `ms` while `enabled` (used to follow documents being read) */
export function usePolling(fn, ms, enabled = true) {
  const saved = useRef(fn);
  saved.current = fn;
  useEffect(() => {
    if (!enabled) return undefined;
    const id = setInterval(() => saved.current(), ms);
    return () => clearInterval(id);
  }, [ms, enabled]);
}

/** A message that disappears by itself */
export function useToast(ms = 3500) {
  const [message, setMessage] = useState("");
  useEffect(() => {
    if (!message) return undefined;
    const id = setTimeout(() => setMessage(""), ms);
    return () => clearTimeout(id);
  }, [message, ms]);
  return [message, setMessage];
}

/** The value after it stopped changing for `ms` */
export function useDebounced(value, ms = 250) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}
