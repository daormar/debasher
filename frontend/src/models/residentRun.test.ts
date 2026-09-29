import { describe, expect, it } from "vitest";
import { orderlyStopOutcome, residentRunPhase, stoppedInOrder } from "./residentRun";

describe("residentRunPhase", () => {
  it("is new with no program state and nothing in progress", () => {
    expect(residentRunPhase({}, false, null)).toBe("new");
    expect(residentRunPhase({ A: "FINISHED" }, false, null)).toBe("new");
  });

  it("is live while some process is in progress, whoever launched it", () => {
    expect(residentRunPhase({ A: "IN-PROGRESS", B: "UNFINISHED" }, true, null)).toBe("live");
    expect(residentRunPhase({ A: "IN-PROGRESS" }, false, null)).toBe("live");
  });

  it("is stopped with program state and nothing in progress", () => {
    expect(residentRunPhase({ A: "FINISHED" }, true, null)).toBe("stopped");
    expect(residentRunPhase({ A: "UNFINISHED" }, true, null)).toBe("stopped");
  });

  it("follows a request of this tab until it is answered", () => {
    expect(residentRunPhase({}, false, "launching")).toBe("launching");
    expect(residentRunPhase({ A: "IN-PROGRESS" }, true, "stopping")).toBe("stopping");
  });
});

describe("stoppedInOrder", () => {
  it("holds only when every process finished", () => {
    expect(stoppedInOrder({ A: "FINISHED", B: "FINISHED" })).toBe(true);
    expect(stoppedInOrder({ A: "FINISHED", B: "UNFINISHED" })).toBe(false);
    expect(stoppedInOrder({ A: "FINISHED", B: "UNFINISHED_BUT_RUNNABLE" })).toBe(false);
    expect(stoppedInOrder({})).toBe(false);
  });
});

describe("orderlyStopOutcome", () => {
  it("never takes a hard kill for an orderly stop", () => {
    expect(orderlyStopOutcome(0)).toMatch(/^Stopped in order/);
    expect(orderlyStopOutcome(2)).toMatch(/fell back to the hard kill/);
    expect(orderlyStopOutcome(2)).not.toMatch(/^Stopped in order/);
    expect(orderlyStopOutcome(1)).toMatch(/error of usage or setup/);
    expect(orderlyStopOutcome(7)).toMatch(/exit code 7/);
  });
});
