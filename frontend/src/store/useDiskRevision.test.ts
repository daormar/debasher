import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DISK_REVISION_POLL_INTERVAL_MS, useDiskRevision } from "./useDiskRevision";
import type { ProgramWrites } from "./useDiskRevision";
import { createEmptyProgram } from "../storage/programStorage";
import type { Program } from "../models/program";

const onDisk = (): Program => ({ ...createEmptyProgram("p"), id: "p", homeDir: "/home/p", revision: 2 });

describe("useDiskRevision", () => {

  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("decides from the program as it is when the revision is read, not when it was asked", async () => {
    let answer: (response: Response) => void = () => {};
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(resolve => { answer = resolve; })));
    const programRef = { current: onDisk() };
    const savedProgramRef = { current: onDisk() };
    const writesRef = { current: { inFlight: 0, answered: 0 } as ProgramWrites };
    const reloadFromDisk = vi.fn(async () => {});
    const { result } = renderHook(() =>
      useDiskRevision({ homeDir: "/home/p", programRef, savedProgramRef, writesRef, reloadFromDisk })
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(DISK_REVISION_POLL_INTERVAL_MS);
    });
    // An edit while the revision is asked for, with no render after it.
    programRef.current = { ...programRef.current, description: "typed just now" };
    await act(async () => {
      answer(new Response(JSON.stringify({ revision: 3 })));
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(reloadFromDisk).not.toHaveBeenCalled();
    expect(result.current.externalRevision).toBe(3);
  });

});
