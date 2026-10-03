import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { usePolling } from "./usePolling";

describe("usePolling", () => {

  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("polls every interval while enabled", async () => {
    const poll = vi.fn(async () => {});
    const { rerender } = renderHook(({ enabled }) => usePolling(poll, { intervalMs: 100, enabled }), {
      initialProps: { enabled: true },
    });

    await vi.advanceTimersByTimeAsync(300);
    expect(poll).toHaveBeenCalledTimes(3);

    rerender({ enabled: false });
    await vi.advanceTimersByTimeAsync(300);
    expect(poll).toHaveBeenCalledTimes(3);
  });

  it("never starts a poll while the one before is in flight", async () => {
    let finish: () => void = () => {};
    const poll = vi.fn(() => new Promise<void>(resolve => { finish = resolve; }));
    renderHook(() => usePolling(poll, { intervalMs: 100, enabled: true }));

    await vi.advanceTimersByTimeAsync(350);
    expect(poll).toHaveBeenCalledTimes(1);

    finish();
    await vi.advanceTimersByTimeAsync(100);
    expect(poll).toHaveBeenCalledTimes(2);
  });

  it("skips the polls while the page is hidden", async () => {
    const poll = vi.fn(async () => {});
    const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(true);
    renderHook(() => usePolling(poll, { intervalMs: 100, enabled: true }));

    await vi.advanceTimersByTimeAsync(300);
    expect(poll).not.toHaveBeenCalled();

    hidden.mockReturnValue(false);
    await vi.advanceTimersByTimeAsync(100);
    expect(poll).toHaveBeenCalledTimes(1);
  });

  it("tells a poll in flight that polling started over", async () => {
    let finish: () => void = () => {};
    let cancelledAtEnd: boolean | null = null;
    const poll = async (isCancelled: () => boolean) => {
      await new Promise<void>(resolve => { finish = resolve; });
      cancelledAtEnd = isCancelled();
    };
    const { rerender } = renderHook(({ key }) => usePolling(poll, { intervalMs: 100, enabled: true, resetKey: key }), {
      initialProps: { key: "a" },
    });

    await vi.advanceTimersByTimeAsync(100);
    rerender({ key: "b" });
    finish();
    await vi.advanceTimersByTimeAsync(0);

    expect(cancelledAtEnd).toBe(true);
  });

  it("calls the latest poll, without starting over on every render", async () => {
    const first = vi.fn(async () => {});
    const second = vi.fn(async () => {});
    const { rerender } = renderHook(({ poll }) => usePolling(poll, { intervalMs: 100, enabled: true }), {
      initialProps: { poll: first },
    });

    await vi.advanceTimersByTimeAsync(50);
    rerender({ poll: second });
    await vi.advanceTimersByTimeAsync(50);

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });

});
