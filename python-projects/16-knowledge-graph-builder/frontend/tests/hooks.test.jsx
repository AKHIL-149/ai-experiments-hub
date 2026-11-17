import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAsync, useDebounced, usePolling, useToast } from "../src/hooks";

describe("useAsync", () => {
  it("loads, then reports the data", async () => {
    const { result } = renderHook(() => useAsync(() => Promise.resolve(5), []));
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.data).toBe(5));
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBe("");
  });
  it("reports the error message and can try again", async () => {
    const loader = vi.fn().mockRejectedValueOnce(new Error("boom")).mockResolvedValueOnce("ok");
    const { result } = renderHook(() => useAsync(loader, []));
    await waitFor(() => expect(result.current.error).toBe("boom"));
    expect(result.current.data).toBeNull();
    await act(() => result.current.reload());
    expect(result.current.data).toBe("ok");
    expect(result.current.error).toBe("");
  });
  it("a quiet reload keeps the old data on screen and keeps it when it fails", async () => {
    const loader = vi.fn().mockResolvedValueOnce("first").mockRejectedValueOnce(new Error("later"));
    const { result } = renderHook(() => useAsync(loader, []));
    await waitFor(() => expect(result.current.data).toBe("first"));
    await act(() => result.current.reload(true));
    expect(result.current.data).toBe("first");
    expect(result.current.error).toBe("later");
  });
  it("ignores an older answer that arrives after a newer one", async () => {
    let first, second;
    const loader = vi.fn().mockImplementationOnce(() => new Promise((r) => { first = r; })).mockImplementationOnce(() => new Promise((r) => { second = r; }));
    const { result } = renderHook(() => useAsync(loader, []));
    let again;
    act(() => { again = result.current.reload(); });
    await act(async () => { second("new"); await again; });
    await act(async () => { first("old"); });
    expect(result.current.data).toBe("new");
  });
  it("loads again when its dependencies change", async () => {
    const loader = vi.fn((x) => Promise.resolve(x));
    const { result, rerender } = renderHook(({ x }) => useAsync(() => loader(x), [x]), { initialProps: { x: 1 } });
    await waitFor(() => expect(result.current.data).toBe(1));
    rerender({ x: 2 });
    await waitFor(() => expect(result.current.data).toBe(2));
  });
  it("does not update after unmount", async () => {
    let finish;
    const { result, unmount } = renderHook(() => useAsync(() => new Promise((r) => { finish = r; }), []));
    unmount();
    finish("late");
    expect(result.current.data).toBeNull();
  });
});

describe("timers", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("usePolling calls on every tick, uses the latest function, and stops when disabled or unmounted", () => {
    const a = vi.fn(), b = vi.fn();
    const { rerender, unmount } = renderHook(({ fn, on }) => usePolling(fn, 1000, on), { initialProps: { fn: a, on: true } });
    vi.advanceTimersByTime(2000);
    expect(a).toHaveBeenCalledTimes(2);
    rerender({ fn: b, on: true });
    vi.advanceTimersByTime(1000);
    expect(b).toHaveBeenCalledTimes(1);
    rerender({ fn: b, on: false });
    vi.advanceTimersByTime(5000);
    expect(b).toHaveBeenCalledTimes(1);
    rerender({ fn: b, on: true });
    unmount();
    vi.advanceTimersByTime(5000);
    expect(b).toHaveBeenCalledTimes(1);
  });

  it("usePolling changes its pace when the interval changes", () => {
    const fn = vi.fn();
    const { rerender } = renderHook(({ ms }) => usePolling(fn, ms), { initialProps: { ms: 15000 } });
    vi.advanceTimersByTime(14000);
    expect(fn).not.toHaveBeenCalled();
    rerender({ ms: 2000 });
    vi.advanceTimersByTime(2000);
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("useToast clears itself", () => {
    const { result } = renderHook(() => useToast(1000));
    act(() => result.current[1]("Saved"));
    expect(result.current[0]).toBe("Saved");
    act(() => vi.advanceTimersByTime(999));
    expect(result.current[0]).toBe("Saved");
    act(() => vi.advanceTimersByTime(2));
    expect(result.current[0]).toBe("");
  });

  it("useToast restarts the clock when the message changes", () => {
    const { result } = renderHook(() => useToast(1000));
    act(() => result.current[1]("One"));
    act(() => vi.advanceTimersByTime(800));
    act(() => result.current[1]("Two"));
    act(() => vi.advanceTimersByTime(800));
    expect(result.current[0]).toBe("Two");
  });

  it("useDebounced waits until the value stops changing", () => {
    const { result, rerender } = renderHook(({ v }) => useDebounced(v, 250), { initialProps: { v: "a" } });
    rerender({ v: "ab" });
    act(() => vi.advanceTimersByTime(200));
    rerender({ v: "abc" });
    act(() => vi.advanceTimersByTime(200));
    expect(result.current).toBe("a");
    act(() => vi.advanceTimersByTime(60));
    expect(result.current).toBe("abc");
  });
});
