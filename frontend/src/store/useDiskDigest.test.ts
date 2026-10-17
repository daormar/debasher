import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DISK_DIGEST_POLL_INTERVAL_MS, useDiskDigest } from "./useDiskDigest";
import type { ProgramWrites } from "./useDiskDigest";
import { createEmptyProgram } from "../storage/programStorage";
import type { Program } from "../models/program";

const onDisk = (): Program => ({ ...createEmptyProgram("p"), id: "p", homeDir: "/home/p", digest: "2" });

describe("useDiskDigest", () => {

  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("decides from the program as it is when the digest is read, not when it was asked", async () => {
    let answer: (response: Response) => void = () => {};
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(resolve => { answer = resolve; })));
    const programRef = { current: onDisk() };
    const savedProgramRef = { current: onDisk() };
    const writesRef = { current: { inFlight: 0, answered: 0 } as ProgramWrites };
    const reloadFromDisk = vi.fn(async () => {});
    const { result } = renderHook(() =>
      useDiskDigest({ homeDir: "/home/p", programRef, savedProgramRef, writesRef, reloadFromDisk })
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(DISK_DIGEST_POLL_INTERVAL_MS);
    });
    // An edit while the digest is asked for, with no render after it.
    programRef.current = { ...programRef.current, description: "typed just now" };
    await act(async () => {
      answer(new Response(JSON.stringify({ digest: "3" })));
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(reloadFromDisk).not.toHaveBeenCalled();
    expect(result.current.externalDigest).toBe("3");
  });

});
