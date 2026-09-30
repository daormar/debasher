import type { ReactNode } from "react";
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProgramProvider, useProgram } from "./ProgramContext";
import { createEmptyProgram } from "../storage/programStorage";
import type { Program } from "../models/program";
import type { ProgramProcess } from "../models/process";
import { emptyNodeCode } from "../models/node";

function renderStore(initialProgram: Program) {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <ProgramProvider initialProgram={initialProgram}>{children}</ProgramProvider>
  );
  return renderHook(() => useProgram(), { wrapper });
}

function node(name: string, nodeKind: ProgramProcess["nodeKind"]): ProgramProcess {
  return {
    id: `id-${name}`,
    name,
    description: "",
    position: { x: 0, y: 0 },
    options: [],
    optionsHandler: { mode: "standard" },
    language: "python",
    code: "",
    computationalSpecs: {},
    additionalSpecs: { force: false },
    additionalMethods: {},
    nodeKind,
    initiator: false,
    nodeCode: nodeKind === "Supervisor" ? undefined : emptyNodeCode(),
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the processes of a resident program", () => {

  it("adds a node of the kind chosen, written in Python, in the parts of a node", () => {
    const { result } = renderStore(createEmptyProgram("p", "resident"));

    act(() => result.current.addProcess("counter", null, "FBPProcess"));
    act(() => result.current.addProcess("sup", null, "Supervisor"));

    const [counter, sup] = result.current.program.processes;
    expect(counter.nodeKind).toBe("FBPProcess");
    expect(counter.language).toBe("python");
    expect(counter.initiator).toBe(false);
    expect(counter.nodeCode).toEqual(emptyNodeCode());
    expect(sup.nodeKind).toBe("Supervisor");
    expect(sup.nodeCode).toBeUndefined();
  });

  it("adds a node that a module of the preamble defines, with what it brings", () => {
    const { result } = renderStore(createEmptyProgram("p", "resident"));
    const nodeCode = { ...emptyNodeCode(), classBody: 'PFILE = "batch.sh"' };
    const options = [{
      id: "o1",
      label: "-requests",
      direction: "input" as const,
      dataType: "string" as const,
      channel: "fifo" as const,
      fifoTag: "external" as const,
      mirror: false,
      description: "requests",
      value: "launch_requests",
      commandLine: false,
      mandatory: false,
      fromProcessSpec: false,
    }];

    act(() =>
      result.current.addProcess("launch", null, "ProgramLauncher", {
        description: "launches",
        nodeKind: "ProgramLauncher",
        nodeCode,
        options,
        optionsHandler: { mode: "standard" },
      })
    );

    const [launch] = result.current.program.processes;
    expect(launch.nodeKind).toBe("ProgramLauncher");
    expect(launch.nodeCode).toEqual(nodeCode);
    expect(launch.description).toBe("launches");
    expect(launch.options).toEqual(options);
    expect(launch.initiator).toBe(false);
  });

  it("adds a process of a general program as before", () => {
    const { result } = renderStore(createEmptyProgram("p"));

    act(() => result.current.addProcess("count", null));

    const [count] = result.current.program.processes;
    expect(count.nodeKind).toBeUndefined();
    expect(count.language).toBe("bash");
  });

  it("keeps the code of a node and whether it is an initiator", () => {
    const { result } = renderStore(createEmptyProgram("p", "resident"));
    act(() => result.current.addProcess("counter", null, "FBPProcess"));
    const id = result.current.program.processes[0].id;
    const code = { ...emptyNodeCode(), processData: "self.send_data('outf', packet)" };

    act(() => result.current.setNodeCode(id, code));
    act(() => result.current.setInitiator(id, true));

    const [counter] = result.current.program.processes;
    expect(counter.nodeCode).toEqual(code);
    expect(counter.initiator).toBe(true);
  });

});

describe("Add program in a resident program", () => {

  function loaded(programType: Program["programType"], processes: ProgramProcess[]): Program {
    return { ...createEmptyProgram("other", programType), processes };
  }

  it("refuses a program of the other type", () => {
    const alert = vi.spyOn(window, "alert").mockImplementation(() => {});
    const { result } = renderStore(createEmptyProgram("p", "resident"));

    act(() => result.current.mergeProgram(loaded("general", [node("count", undefined)]), "/src"));

    expect(alert).toHaveBeenCalledWith(expect.stringMatching(/same type/));
    expect(result.current.program.processes).toEqual([]);
  });

  it("refuses a second Supervisor", () => {
    const alert = vi.spyOn(window, "alert").mockImplementation(() => {});
    const { result } = renderStore({
      ...createEmptyProgram("p", "resident"),
      processes: [node("sup", "Supervisor")],
    });

    act(() => result.current.mergeProgram(loaded("resident", [node("monitor", "Supervisor")]), "/src"));

    expect(alert).toHaveBeenCalledWith(expect.stringMatching(/at most one Supervisor/));
    expect(result.current.program.processes.map(p => p.name)).toEqual(["sup"]);
  });

  it("brings in the nodes one by one, never as a group, and loads nothing from where they came from", () => {
    const { result } = renderStore(createEmptyProgram("p", "resident"));

    act(() =>
      result.current.mergeProgram(
        loaded("resident", [node("counter", "FBPProcess"), node("sup", "Supervisor")]),
        "/src"
      )
    );

    const processes = result.current.program.processes;
    expect(processes.map(p => p.name)).toEqual(["counter", "sup"]);
    expect(processes.every(p => p.groupSource === undefined)).toBe(true);
    expect(result.current.program.envVars.DEBASHER_MOD_DIR).toBeUndefined();
  });

});
