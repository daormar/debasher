import { describe, expect, it } from "vitest";
import type { ProgramProcess } from "./process";
import {
  offersRestartNode,
  orderlyStopOutcome,
  residentRunPhase,
  restartNodeWarning,
  restartsWithBothEnds,
  stoppedInOrder,
} from "./residentRun";

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

describe("Restart node", () => {
  function processOf(name: string, nodeKind: ProgramProcess["nodeKind"], mode: "standard" | "array" = "standard"): ProgramProcess {
    return {
      id: name,
      name,
      description: "",
      position: { x: 0, y: 0 },
      options: [],
      optionsHandler: { mode },
      language: "python",
      code: "",
      computationalSpecs: {},
      additionalSpecs: { force: false },
      additionalMethods: {},
      nodeKind,
    } as ProgramProcess;
  }

  const count = processOf("Count", "FBPProcess");
  const sup = processOf("Sup", "Supervisor");

  it("is offered on every node of a program with a Supervisor but the Supervisor", () => {
    const withSupervisor = { programType: "resident" as const, processes: [count, sup] };
    expect(offersRestartNode(withSupervisor, count)).toBe(true);
    expect(offersRestartNode(withSupervisor, sup)).toBe(false);
  });

  it("is not offered where nothing would relaunch the node", () => {
    expect(offersRestartNode({ programType: "resident", processes: [count] }, count)).toBe(false);
    expect(offersRestartNode({ programType: "general", processes: [count, sup] }, count)).toBe(false);
  });

  it("finds a channel whose two ends restart together", () => {
    const loop = { id: "l", sourceProcessId: "Count", sourceOptionId: "o", targetProcessId: "Count", targetOptionId: "i" };
    const out = { id: "e", sourceProcessId: "Count", sourceOptionId: "o", targetProcessId: "Sink", targetOptionId: "i" };
    expect(restartsWithBothEnds([loop, out], "Count")).toBe(true);
    expect(restartsWithBothEnds([out], "Count")).toBe(false);
  });

  it("warns of every task of an array and of -no-hold-fifos only when they apply", () => {
    const plain = restartNodeWarning(count, false).join(" ");
    expect(plain).not.toMatch(/Every task/);
    expect(plain).not.toMatch(/-no-hold-fifos/);
    expect(plain).toMatch(/gives up on it/);

    const array = restartNodeWarning(processOf("Work", "FBPProcess", "array"), true).join(" ");
    expect(array).toMatch(/Every task of the node restarts/);
    expect(array).toMatch(/launched with -no-hold-fifos/);
  });
});
