import { describe, expect, it } from "vitest";
import type { GeneralRunTracking } from "./generalRun";
import {
  INITIAL_GENERAL_TRACKING,
  LAUNCHED_GENERAL_TRACKING,
  generalRunPhase,
  nextGeneralTracking,
  runGoesOnMessage,
  stoppedGeneralTracking,
  showsGeneralIndicator,
} from "./generalRun";

function readAll(start: GeneralRunTracking, readings: Record<string, string>[]): GeneralRunTracking {
  return readings.reduce(nextGeneralTracking, start);
}

const RUNNING = { A: "FINISHED", B: "IN-PROGRESS" };
const GAP = { A: "FINISHED", B: "TO-DO" };
const DONE = { A: "FINISHED", B: "FINISHED" };
const FAILED = { A: "FINISHED", B: "UNFINISHED" };

describe("nextGeneralTracking", () => {
  it("is idle with nothing to report, and running while a process is in progress", () => {
    expect(readAll(INITIAL_GENERAL_TRACKING, [{}, {}]).phase).toBe("idle");
    expect(readAll(INITIAL_GENERAL_TRACKING, [RUNNING]).phase).toBe("running");
  });

  it("does not take the gap between two processes for a run that did not finish", () => {
    const tracking = readAll(INITIAL_GENERAL_TRACKING, [RUNNING, GAP, RUNNING]);
    expect(tracking.phase).toBe("running");
  });

  it("says unfinished after two readings in a row, and finished at once", () => {
    expect(readAll(INITIAL_GENERAL_TRACKING, [RUNNING, FAILED]).phase).toBe("running");
    expect(readAll(INITIAL_GENERAL_TRACKING, [RUNNING, FAILED, FAILED]).phase).toBe("unfinished");
    expect(readAll(INITIAL_GENERAL_TRACKING, [RUNNING, DONE]).phase).toBe("finished");
  });

  it("waits, after a launch, for a process in progress or two quiet readings", () => {
    // The first reading may still show the run before.
    expect(readAll(LAUNCHED_GENERAL_TRACKING, [DONE]).phase).toBe("launching");
    expect(readAll(LAUNCHED_GENERAL_TRACKING, [DONE, RUNNING]).phase).toBe("running");
    // A run that ended, or failed, at once.
    expect(readAll(LAUNCHED_GENERAL_TRACKING, [DONE, DONE]).phase).toBe("finished");
    expect(readAll(LAUNCHED_GENERAL_TRACKING, [{}, FAILED]).phase).toBe("unfinished");
  });

  it("settles at the first quiet reading after a stop of the tab", () => {
    const running = readAll(INITIAL_GENERAL_TRACKING, [RUNNING]);
    const stopped = nextGeneralTracking(stoppedGeneralTracking(running), FAILED);
    expect(stopped.phase).toBe("unfinished");
    expect(stopped.sawEnd).toBe(true);
  });

  it("remembers that the tab saw the run end, and only then", () => {
    expect(readAll(INITIAL_GENERAL_TRACKING, [RUNNING, DONE]).sawEnd).toBe(true);
    expect(readAll(INITIAL_GENERAL_TRACKING, [RUNNING, DONE, DONE]).sawEnd).toBe(true);
    expect(readAll(LAUNCHED_GENERAL_TRACKING, [DONE, DONE]).sawEnd).toBe(true);
    // A program opened with the results of an old run.
    expect(readAll(INITIAL_GENERAL_TRACKING, [DONE, DONE]).sawEnd).toBe(false);
    expect(readAll(INITIAL_GENERAL_TRACKING, [FAILED, FAILED]).sawEnd).toBe(false);
    // The output directory emptied after the end.
    expect(readAll(INITIAL_GENERAL_TRACKING, [RUNNING, DONE, {}]).sawEnd).toBe(false);
  });
});

describe("generalRunPhase and showsGeneralIndicator", () => {
  it("shows a request of the tab first", () => {
    const running = readAll(INITIAL_GENERAL_TRACKING, [RUNNING]);
    expect(generalRunPhase(running, "stopping")).toBe("stopping");
    expect(generalRunPhase(running, null)).toBe("running");
  });

  it("shows the end of a run only when the tab saw it", () => {
    expect(showsGeneralIndicator("running", false)).toBe(true);
    expect(showsGeneralIndicator("stopping", false)).toBe(true);
    expect(showsGeneralIndicator("finished", false)).toBe(false);
    expect(showsGeneralIndicator("unfinished", true)).toBe(true);
    expect(showsGeneralIndicator("idle", true)).toBe(false);
  });
});

describe("runGoesOnMessage", () => {
  const program = { name: "sum", outputDir: "/tmp/out", programType: "general" as const };

  it("says where a run in progress goes on, for each type of program", () => {
    expect(runGoesOnMessage(program, true)).toBe(
      "The run of sum goes on in /tmp/out. Load the program again to follow it or stop it."
    );
    expect(runGoesOnMessage({ ...program, programType: "resident" }, true)).toMatch(/^sum is live in \/tmp\/out/);
  });

  it("says nothing with no run in progress", () => {
    expect(runGoesOnMessage(program, false)).toBeNull();
  });
});
