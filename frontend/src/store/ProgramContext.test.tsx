import type { ReactNode } from "react";
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProgramProvider, useProgram } from "./ProgramContext";
import { DISK_REVISION_POLL_INTERVAL_MS } from "./useDiskRevision";
import { createEmptyProgram } from "../storage/programStorage";
import type { Program } from "../models/program";
import type { ProcessInfo, ProgramProcess } from "../models/process";
import type { ProgramEdge } from "../models/edge";
import type { ProgramOption } from "../models/option";
import { emptyNodeCode } from "../models/node";
import { createSeqProcess } from "../models/seqProcess";

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
  vi.unstubAllGlobals();
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

describe("the sequential processes of a program", () => {

  function general(name: string): ProgramProcess {
    return { ...node(name, undefined), language: "bash" };
  }

  function loadedWithSeq(): Program {
    return {
      ...createEmptyProgram("other"),
      processes: [general("worker")],
      seqProcesses: [createSeqProcess("step")],
    };
  }

  it("replaces the sequential processes", () => {
    const { result } = renderStore(createEmptyProgram("p"));
    const step = createSeqProcess("step");

    act(() => {
      result.current.setSeqProcesses([step]);
    });

    expect(result.current.program.seqProcesses).toEqual([step]);
  });

  it("brings in the sequential processes of an added program in the same group as its processes", () => {
    const { result } = renderStore(createEmptyProgram("p"));

    act(() => result.current.mergeProgram(loadedWithSeq(), "/src"));

    const [worker] = result.current.program.processes;
    const [step] = result.current.program.seqProcesses;
    expect(step.name).toBe("step");
    expect(step.groupSource).toEqual(worker.groupSource);
    expect(worker.groupSource?.groupSize).toBe(2);
  });

  it("refuses an added program whose sequential process has the name of a process", () => {
    const alert = vi.spyOn(window, "alert").mockImplementation(() => {});
    const { result } = renderStore({ ...createEmptyProgram("p"), processes: [general("step")] });

    act(() => result.current.mergeProgram(loadedWithSeq(), "/src"));

    expect(alert).toHaveBeenCalledWith(expect.stringMatching(/"step"/));
    expect(result.current.program.seqProcesses).toEqual([]);
  });

  it("dissolves the whole group when a sequential process of it is removed, once the user agrees", () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { result } = renderStore(createEmptyProgram("p"));
    act(() => result.current.mergeProgram(loadedWithSeq(), "/src"));

    let replaced = false;
    act(() => {
      replaced = result.current.setSeqProcesses([]);
    });

    expect(replaced).toBe(true);
    expect(result.current.program.seqProcesses).toEqual([]);
    expect(result.current.program.processes[0].groupSource).toBeUndefined();
  });

  it("changes nothing when the user declines to dissolve the group", () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const { result } = renderStore(createEmptyProgram("p"));
    act(() => result.current.mergeProgram(loadedWithSeq(), "/src"));
    const before = result.current.program;

    let replaced = true;
    act(() => {
      replaced = result.current.setSeqProcesses([]);
    });

    expect(replaced).toBe(false);
    expect(result.current.program).toEqual(before);
  });

  it("frees the sequential processes of a group when a process of the group changes", () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { result } = renderStore(createEmptyProgram("p"));
    act(() => result.current.mergeProgram(loadedWithSeq(), "/src"));

    const workerId = result.current.program.processes[0].id;
    act(() => result.current.setProcessDescription(workerId, "changed"));

    expect(result.current.program.seqProcesses[0].groupSource).toBeUndefined();
  });

});

describe("saving a program", () => {

  it("keeps the edits made while the save is in flight", async () => {
    let finishSave: (response: Response) => void = () => {};
    vi.stubGlobal("fetch", vi.fn((url: string) =>
      url === "/api/programs/save"
        ? new Promise<Response>(resolve => { finishSave = resolve; })
        : Promise.reject(new Error(`unexpected request to ${url}`))
    ));
    const { result } = renderStore(createEmptyProgram("p"));

    let saving: Promise<void> = Promise.resolve();
    act(() => {
      saving = result.current.save("/home/p");
    });
    act(() => result.current.setDescription("edited while saving"));
    await act(async () => {
      finishSave(new Response(JSON.stringify({ path: "", scriptPath: "", revision: 3 }), { status: 200 }));
      await saving;
    });

    expect(result.current.program.homeDir).toBe("/home/p");
    expect(result.current.program.description).toBe("edited while saving");
    expect(result.current.program.revision).toBe(3);
  });


  function conflictThenLoad(saved: Program) {
    const requests: { url: string; body: unknown }[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      requests.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
      if (url === "/api/programs/save") {
        return new Response(
          JSON.stringify({ detail: { code: "revision", revision: 7, message: "The program changed on disk." } }),
          { status: 409 }
        );
      }
      if (url === "/api/programs/load") {
        return new Response(JSON.stringify(saved), { status: 200 });
      }
      throw new Error(`unexpected request to ${url}`);
    }));
    return requests;
  }

  const loadedProgram = (): Program => ({ ...createEmptyProgram("p"), homeDir: "/home/p", revision: 2 });

  it("sends the home directory it was loaded from, which tells a save from a save as", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const requests = conflictThenLoad(loadedProgram());
    const { result } = renderStore(loadedProgram());

    await act(async () => {
      await result.current.save("/elsewhere").catch(() => {});
    });

    expect(requests[0].body).toMatchObject({ outputDir: "/elsewhere", program: { homeDir: "/home/p", revision: 2 } });
  });

  it("asks the user about the revision that refused a save, keeping the tab's program meanwhile", async () => {
    const confirm = vi.spyOn(window, "confirm");
    conflictThenLoad({ ...loadedProgram(), description: "saved elsewhere", revision: 7 });
    const { result } = renderStore(loadedProgram());
    act(() => result.current.setDescription("this tab's change"));

    let error: unknown = null;
    await act(async () => {
      await result.current.save("/home/p").catch(err => { error = err; });
    });

    expect(confirm).not.toHaveBeenCalled();
    expect(String(error)).toMatch(/changed on disk/);
    expect(result.current.externalRevision).toBe(7);
    expect(result.current.program.description).toBe("this tab's change");
    expect(result.current.program.revision).toBe(2);
  });

  it("loads the revision that refused a save when the user chooses to", async () => {
    conflictThenLoad({ ...loadedProgram(), description: "saved elsewhere", revision: 7 });
    const { result } = renderStore(loadedProgram());
    act(() => result.current.setDescription("this tab's change"));
    await act(async () => {
      await result.current.save("/home/p").catch(() => {});
    });

    await act(async () => {
      await result.current.loadExternal();
    });

    expect(result.current.program.description).toBe("saved elsewhere");
    expect(result.current.program.revision).toBe(7);
    expect(result.current.externalRevision).toBeNull();
    expect(result.current.unsavedChanges).toBe(false);
  });

});

function option(id: string, label: string, changes: Partial<ProgramOption> = {}): ProgramOption {
  return {
    id,
    label,
    direction: label.startsWith("-out") ? "output" : "input",
    dataType: "string",
    channel: "none",
    mirror: false,
    description: "",
    value: "",
    commandLine: false,
    mandatory: false,
    fromProcessSpec: false,
    ...changes,
  };
}

function bashProcess(name: string, options: ProgramOption[] = []): ProgramProcess {
  return { ...node(name, undefined), language: "bash", options };
}

function edge(id: string, source: [string, string], target: [string, string]): ProgramEdge {
  return {
    id,
    sourceProcessId: `id-${source[0]}`,
    sourceOptionId: source[1],
    targetProcessId: `id-${target[0]}`,
    targetOptionId: target[1],
  };
}

function programWith(processes: ProgramProcess[], edges: ProgramEdge[] = []): Program {
  return { ...createEmptyProgram("p"), processes, edges };
}

function processNamed(program: Program, name: string): ProgramProcess {
  return program.processes.find(process => process.name === name)!;
}

function optionValue(program: Program, processName: string, optionId: string): string {
  return processNamed(program, processName).options.find(o => o.id === optionId)!.value;
}

describe("editing the processes of a program", () => {

  it("adds a process with what the library brings for it", () => {
    const { result } = renderStore(createEmptyProgram("p"));
    const info: ProcessInfo = {
      description: "sorts",
      language: "python",
      code: "print(1)",
      options: [
        { label: "-in", dataType: "file", description: "input", commandLine: true, mandatory: true },
        { label: "-outf", dataType: "file", description: "output", commandLine: false, mandatory: false },
      ],
    };

    act(() => result.current.addProcess("sorter", info));

    const [sorter] = result.current.program.processes;
    expect(sorter.name).toBe("sorter");
    expect(sorter.description).toBe("sorts");
    expect(sorter.language).toBe("python");
    expect(sorter.code).toBe("print(1)");
    expect(sorter.position).toEqual({ x: 100, y: 100 });
    expect(sorter.optionsHandler).toEqual({ mode: "standard" });
    expect(sorter.additionalSpecs).toEqual({ force: false });
    expect(sorter.options.map(o => [o.label, o.direction, o.dataType, o.commandLine, o.mandatory]))
      .toEqual([["-in", "input", "file", true, true], ["-outf", "output", "file", false, false]]);
    expect(sorter.options.every(o => o.channel === "none" && o.value === "")).toBe(true);
  });

  it("adds an empty Bash process when the library brings nothing", () => {
    const { result } = renderStore(createEmptyProgram("p"));

    act(() => result.current.addProcess("blank", null));

    const [blank] = result.current.program.processes;
    expect(blank.language).toBe("bash");
    expect(blank.code).toBe("");
    expect(blank.options).toEqual([]);
    expect(blank.nodeKind).toBeUndefined();
  });

  it("renames a process with what the library brings for the new name", () => {
    const { result } = renderStore(programWith([bashProcess("a", [option("o1", "-x")])]));

    act(() =>
      result.current.renameProcess("id-a", "sorter", {
        description: "new",
        language: "perl",
        code: "print 1;",
        options: [{ label: "-y", dataType: "int", description: "", commandLine: true, mandatory: false }],
      })
    );

    const sorter = processNamed(result.current.program, "sorter");
    expect(sorter.description).toBe("new");
    expect(sorter.language).toBe("perl");
    expect(sorter.code).toBe("print 1;");
    expect(sorter.options.map(o => o.label)).toEqual(["-y"]);
  });

  it("renames a process keeping what it has when the library brings nothing", () => {
    const { result } = renderStore(programWith([bashProcess("a", [option("o1", "-x")])]));

    act(() => result.current.renameProcess("id-a", "b", null));

    const b = processNamed(result.current.program, "b");
    expect(b.options.map(o => o.id)).toEqual(["o1"]);
  });

  it("applies several edits made within one event one after another", () => {
    const { result } = renderStore(programWith([bashProcess("a")]));

    act(() => {
      result.current.setProcessCode("id-a", "echo 1");
      result.current.setProcessDescription("id-a", "described");
    });

    const a = processNamed(result.current.program, "a");
    expect([a.code, a.description]).toEqual(["echo 1", "described"]);
  });

  it("removes a process with the connections that touch it, and unselects it", () => {
    const { result } = renderStore(
      programWith(
        [
          bashProcess("a", [option("ao", "-outf")]),
          bashProcess("b", [option("bi", "-in"), option("bo", "-outf")]),
          bashProcess("c", [option("ci", "-in")]),
        ],
        [edge("e1", ["a", "ao"], ["b", "bi"]), edge("e2", ["b", "bo"], ["c", "ci"])]
      )
    );
    act(() => result.current.selectProcess("id-b"));

    act(() => result.current.removeFromCanvas(["id-b"], []));

    expect(result.current.program.processes.map(p => p.name)).toEqual(["a", "c"]);
    expect(result.current.program.edges).toEqual([]);
    expect(result.current.selectedProcess).toBeNull();
  });

  it("adds an option whose direction comes from its label", () => {
    const { result } = renderStore(programWith([bashProcess("a")]));

    act(() => result.current.addOption("id-a", "-in"));
    act(() => result.current.addOption("id-a", "-outf"));

    const [input, output] = processNamed(result.current.program, "a").options;
    expect([input.label, input.direction]).toEqual(["-in", "input"]);
    expect([output.label, output.direction]).toEqual(["-outf", "output"]);
    expect(input).toMatchObject({
      dataType: "string",
      channel: "none",
      mirror: false,
      value: "",
      commandLine: false,
      mandatory: false,
      fromProcessSpec: false,
    });
  });

  it("changes and removes an option", () => {
    const { result } = renderStore(programWith([bashProcess("a", [option("o1", "-x"), option("o2", "-y")])]));

    act(() => result.current.updateOption("id-a", "o1", { dataType: "int", value: "3" }));
    act(() => result.current.removeOption("id-a", "o2"));

    const options = processNamed(result.current.program, "a").options;
    expect(options.map(o => [o.id, o.dataType, o.value])).toEqual([["o1", "int", "3"]]);
  });

});

describe("connections between processes", () => {

  function twoProcesses(sourceChanges: Partial<ProgramOption> = {}, targetChanges: Partial<ProgramOption> = {}): Program {
    return programWith([
      bashProcess("a", [option("ao", "-outf", sourceChanges)]),
      bashProcess("b", [option("bi", "-in", targetChanges)]),
    ]);
  }

  it("gives the target of a connection the reference to its source", () => {
    const { result } = renderStore(twoProcesses());

    act(() => result.current.connect(edge("e1", ["a", "ao"], ["b", "bi"])));

    expect(result.current.program.edges.map(e => e.id)).toEqual(["e1"]);
    expect(optionValue(result.current.program, "b", "bi")).toBe("[a;-outf]");
  });

  it("makes the target of a shared directory connection name the same directory", () => {
    const { result } = renderStore(twoProcesses({ channel: "shared_dir", value: "shdir" }));

    act(() => result.current.connect(edge("e1", ["a", "ao"], ["b", "bi"])));

    const target = processNamed(result.current.program, "b").options[0];
    expect([target.channel, target.value]).toEqual(["shared_dir", "shdir"]);
  });

  it("clears the value of the target when the connection is removed", () => {
    const { result } = renderStore(twoProcesses());
    act(() => result.current.connect(edge("e1", ["a", "ao"], ["b", "bi"])));

    act(() => result.current.removeFromCanvas([], ["e1"]));

    expect(result.current.program.edges).toEqual([]);
    expect(optionValue(result.current.program, "b", "bi")).toBe("");
  });

  it("keeps the directory of a shared directory target when the connection is removed", () => {
    const { result } = renderStore(
      twoProcesses({ channel: "shared_dir", value: "shdir" }, { channel: "shared_dir", value: "shdir" })
    );
    act(() => result.current.connect(edge("e1", ["a", "ao"], ["b", "bi"])));

    act(() => result.current.removeFromCanvas([], ["e1"]));

    expect(optionValue(result.current.program, "b", "bi")).toBe("shdir");
  });

  it("follows a renamed source process or source option in the reference", () => {
    const { result } = renderStore(twoProcesses());
    act(() => result.current.connect(edge("e1", ["a", "ao"], ["b", "bi"])));

    act(() => result.current.renameProcess("id-a", "producer"));
    expect(optionValue(result.current.program, "b", "bi")).toBe("[producer;-outf]");

    act(() => result.current.updateOption("id-a", "ao", { label: "-outfile" }));
    expect(optionValue(result.current.program, "b", "bi")).toBe("[producer;-outfile]");
  });

  it("puts the references of a loaded program back in step with its connections", () => {
    const { result } = renderStore(
      programWith(
        [
          bashProcess("a", [option("ao", "-outf")]),
          bashProcess("b", [
            option("bi", "-in", { value: "[old;-outf]" }),
            option("bj", "-stale", { value: "[gone;-outf]" }),
            option("bk", "-literal", { value: "42" }),
          ]),
        ],
        [edge("e1", ["a", "ao"], ["b", "bi"])]
      )
    );

    const program = result.current.program;
    expect(optionValue(program, "b", "bi")).toBe("[a;-outf]");
    expect(optionValue(program, "b", "bj")).toBe("");
    expect(optionValue(program, "b", "bk")).toBe("42");
  });

  it("gives a loaded program without a scheduler the default one", () => {
    const { result } = renderStore({ ...createEmptyProgram("p"), executionOptions: { scheduler: "" } });

    expect(result.current.program.executionOptions.scheduler).toBe("BUILTIN");
  });

});

describe("reordering the options of a process", () => {

  const options = [
    option("i1", "-a"),
    option("o1", "-outa"),
    option("i2", "-b"),
    option("i3", "-c"),
  ];

  it("reorders the options of one row, leaving the other row in place", () => {
    const { result } = renderStore(programWith([bashProcess("a", options)]));

    act(() => result.current.reorderOptionGroup("id-a", "top", ["i3", "i1", "i2"]));

    expect(processNamed(result.current.program, "a").options.map(o => o.id))
      .toEqual(["i3", "o1", "i1", "i2"]);
  });

  it("ignores an order that does not list the whole row", () => {
    const { result } = renderStore(programWith([bashProcess("a", options)]));

    act(() => result.current.reorderOptionGroup("id-a", "top", ["i3", "i1"]));

    expect(processNamed(result.current.program, "a").options.map(o => o.id))
      .toEqual(["i1", "o1", "i2", "i3"]);
  });

});

describe("editing a process added with another program", () => {

  const groupSource = { programName: "other", groupId: "g1", groupSize: 3, sourceDir: "/src" };

  function grouped(): Program {
    return {
      ...programWith([
        { ...bashProcess("a", [option("ao", "-outf")]), groupSource },
        { ...bashProcess("b", [option("bi", "-in")]), groupSource },
        bashProcess("c", [option("ci", "-in"), option("co", "-outf")]),
      ]),
      seqProcesses: [{ ...createSeqProcess("step"), groupSource }],
    };
  }

  it("frees the whole group and applies the change once the user agrees", () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const { result } = renderStore(grouped());

    act(() => result.current.setProcessCode("id-a", "echo changed"));

    const program = result.current.program;
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(processNamed(program, "a").code).toBe("echo changed");
    expect(program.processes.every(p => p.groupSource === undefined)).toBe(true);
    expect(program.seqProcesses[0].groupSource).toBeUndefined();
  });

  it("changes nothing when the user declines", () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const { result } = renderStore(grouped());
    const before = result.current.program;

    act(() => result.current.renameProcess("id-a", "renamed"));
    act(() => result.current.removeFromCanvas(["id-b"], []));

    expect(result.current.program).toEqual(before);
  });

  it("moves a process of the group without asking", () => {
    const confirm = vi.spyOn(window, "confirm");
    const { result } = renderStore(grouped());

    act(() => result.current.moveProcess("id-a", { x: 5, y: 7 }));

    expect(confirm).not.toHaveBeenCalled();
    expect(processNamed(result.current.program, "a").position).toEqual({ x: 5, y: 7 });
    expect(processNamed(result.current.program, "a").groupSource).toEqual(groupSource);
  });

  it("asks only when the target of a connection is in the group", () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const { result } = renderStore(grouped());

    act(() => result.current.connect(edge("e1", ["a", "ao"], ["c", "ci"])));
    expect(confirm).not.toHaveBeenCalled();
    expect(processNamed(result.current.program, "a").groupSource).toEqual(groupSource);

    act(() => result.current.connect(edge("e2", ["c", "co"], ["b", "bi"])));
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(processNamed(result.current.program, "b").groupSource).toBeUndefined();
  });

  it("asks once for all the processes and edges deleted together", () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const { result } = renderStore({
      ...grouped(),
      edges: [edge("e1", ["c", "co"], ["b", "bi"])],
    });

    let removed = false;
    act(() => {
      removed = result.current.removeFromCanvas(["id-a", "id-b"], ["e1"]);
    });

    expect(removed).toBe(true);
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(result.current.program.processes.map(p => p.name)).toEqual(["c"]);
    expect(result.current.program.edges).toEqual([]);
    expect(result.current.program.seqProcesses[0].groupSource).toBeUndefined();
  });

  it("keeps everything deleted together when the user declines", () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const { result } = renderStore(grouped());
    const before = result.current.program;

    let removed = true;
    act(() => {
      removed = result.current.removeFromCanvas(["id-a", "id-c"], []);
    });

    expect(removed).toBe(false);
    expect(result.current.program).toEqual(before);
  });

  it("asks no more once a first edit within the same event has freed the group", () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const { result } = renderStore(grouped());

    act(() => {
      result.current.setProcessCode("id-a", "echo changed");
      result.current.setProcessCode("id-b", "echo changed too");
    });

    expect(confirm).toHaveBeenCalledTimes(1);
    expect(result.current.program.processes.map(p => p.code)).toEqual(["echo changed", "echo changed too", ""]);
  });

  it("asks once when a process is renamed with what the library brings", () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const { result } = renderStore(grouped());

    act(() =>
      result.current.renameProcess("id-a", "renamed", { description: "d", language: "bash", code: "", options: [] })
    );

    expect(confirm).toHaveBeenCalledTimes(1);
    expect(processNamed(result.current.program, "renamed").description).toBe("d");
  });

});

describe("the requests of a run that save the program", () => {

  const runnable = (): Program => ({
    ...createEmptyProgram("p"),
    homeDir: "/home/p",
    outputDir: "/out/p",
    revision: 2,
  });

  function backend(answers: Record<string, () => Response>) {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url === "/api/execution/process-statuses") {
        return new Response(JSON.stringify({ statuses: {}, hasProgramState: false, output: "", notices: [] }));
      }
      if (url === "/api/execution/status") {
        return new Response(JSON.stringify({ state: "unfinished", output: "" }));
      }
      const answer = answers[url];
      if (!answer) {
        throw new Error(`unexpected request to ${url}`);
      }
      return answer();
    }));
  }

  it("take the revision that validating wrote", async () => {
    backend({ "/api/execution/validate": () => new Response(JSON.stringify({ output: "valid", revision: 5 })) });
    const { result } = renderStore(runnable());

    let output = "";
    await act(async () => {
      output = await result.current.validateProgram();
    });

    expect(output).toBe("valid");
    expect(result.current.program.revision).toBe(5);
  });

  it("ask the user about the revision that refused a launch", async () => {
    const confirm = vi.spyOn(window, "confirm");
    backend({
      "/api/execution/run": () => new Response(
        JSON.stringify({ detail: { code: "revision", revision: 9, message: "The program changed on disk." } }),
        { status: 409 }
      ),
    });
    const { result } = renderStore(runnable());

    let error: unknown = null;
    await act(async () => {
      await result.current.startProgramRun().catch(err => { error = err; });
    });

    expect(confirm).not.toHaveBeenCalled();
    expect(String(error)).toMatch(/changed on disk/);
    expect(result.current.externalRevision).toBe(9);
    expect(result.current.program.revision).toBe(2);
  });

});


describe("changes saved from elsewhere", () => {

  const onDisk = (): Program => ({ ...createEmptyProgram("p"), id: "p", homeDir: "/home/p", revision: 2 });

  // A backend whose program metadata is at `disk.revision`, holding
  // `disk.program`; a save writes the next revision.
  function backend(disk: { revision: number; program: Program }) {
    const requests: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      requests.push(url);
      if (url === "/api/programs/revision") {
        return new Response(JSON.stringify({ revision: disk.revision }));
      }
      if (url === "/api/programs/load") {
        return new Response(JSON.stringify({ ...disk.program, revision: disk.revision }));
      }
      if (url === "/api/programs/save") {
        const { program } = JSON.parse(String(init?.body));
        disk.revision += 1;
        disk.program = program;
        return new Response(JSON.stringify({ path: "", scriptPath: "", revision: disk.revision }));
      }
      throw new Error(`unexpected request to ${url}`);
    }));
    return requests;
  }

  async function poll() {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DISK_REVISION_POLL_INTERVAL_MS);
    });
  }

  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("holds no unsaved changes once loaded or saved, and holds them after an edit", async () => {
    backend({ revision: 2, program: onDisk() });
    const { result } = renderStore(onDisk());
    expect(result.current.unsavedChanges).toBe(false);

    act(() => result.current.setDescription("edited"));
    expect(result.current.unsavedChanges).toBe(true);

    await act(async () => {
      await result.current.save("/home/p");
    });
    expect(result.current.unsavedChanges).toBe(false);
  });

  it("keeps the changes made while a save is in flight as unsaved", async () => {
    let finishSave: (response: Response) => void = () => {};
    vi.stubGlobal("fetch", vi.fn((url: string) =>
      url === "/api/programs/save"
        ? new Promise<Response>(resolve => { finishSave = resolve; })
        : Promise.reject(new Error(`unexpected request to ${url}`))
    ));
    const { result } = renderStore(onDisk());
    act(() => result.current.setDescription("saved"));

    let saving: Promise<void> = Promise.resolve();
    act(() => {
      saving = result.current.save("/home/p");
    });
    act(() => result.current.setDescription("edited while saving"));
    await act(async () => {
      finishSave(new Response(JSON.stringify({ path: "", scriptPath: "", revision: 3 })));
      await saving;
    });

    expect(result.current.unsavedChanges).toBe(true);
  });

  it("loads a revision saved elsewhere on its own when nothing is unsaved", async () => {
    const disk = { revision: 2, program: onDisk() };
    backend(disk);
    const { result } = renderStore(onDisk());

    disk.revision = 3;
    disk.program = { ...onDisk(), description: "saved by an agent" };
    await poll();

    expect(result.current.program.description).toBe("saved by an agent");
    expect(result.current.program.revision).toBe(3);
    expect(result.current.unsavedChanges).toBe(false);
    expect(result.current.externalRevision).toBeNull();
    expect(result.current.diskLoads).toBe(1);
  });

  it("asks before it loses unsaved changes, about the latest revision on disk", async () => {
    const disk = { revision: 2, program: onDisk() };
    const requests = backend(disk);
    const { result } = renderStore(onDisk());
    act(() => result.current.setDescription("this tab's change"));

    disk.revision = 3;
    await poll();

    expect(result.current.externalRevision).toBe(3);
    expect(result.current.program.description).toBe("this tab's change");
    expect(requests).not.toContain("/api/programs/load");

    disk.revision = 4;
    disk.program = { ...onDisk(), description: "saved again" };
    await poll();
    expect(result.current.externalRevision).toBe(4);

    await act(async () => {
      await result.current.loadExternal();
    });
    expect(result.current.program.description).toBe("saved again");
    expect(result.current.externalRevision).toBeNull();
    expect(result.current.unsavedChanges).toBe(false);
  });

  it("saves the tab over the revision on disk when the user chooses to", async () => {
    const disk = { revision: 2, program: onDisk() };
    backend(disk);
    const { result } = renderStore(onDisk());
    act(() => result.current.setDescription("this tab's change"));
    disk.revision = 3;
    disk.program = { ...onDisk(), description: "saved by an agent" };
    await poll();

    await act(async () => {
      await result.current.saveOverExternal();
    });

    expect(disk.revision).toBe(4);
    expect(disk.program.description).toBe("this tab's change");
    expect(result.current.program.revision).toBe(4);
    expect(result.current.externalRevision).toBeNull();
    expect(result.current.unsavedChanges).toBe(false);
  });

  it("never takes its own save for one made elsewhere", async () => {
    // The save has written the next revision, but its answer has not
    // arrived: the tab still holds the revision before, and edits on.
    let finishSave: (response: Response) => void = () => {};
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url === "/api/programs/revision") {
        return Promise.resolve(new Response(JSON.stringify({ revision: 3 })));
      }
      if (url === "/api/programs/save") {
        return new Promise<Response>(resolve => { finishSave = resolve; });
      }
      return Promise.reject(new Error(`unexpected request to ${url}`));
    }));
    const { result } = renderStore(onDisk());
    act(() => result.current.setDescription("mine"));

    let saving: Promise<void> = Promise.resolve();
    act(() => {
      saving = result.current.save("/home/p");
    });
    act(() => result.current.setDescription("edited while saving"));
    await poll();

    expect(result.current.externalRevision).toBeNull();

    await act(async () => {
      finishSave(new Response(JSON.stringify({ path: "", scriptPath: "", revision: 3 })));
      await saving;
    });
    await poll();

    expect(result.current.externalRevision).toBeNull();
    expect(result.current.diskLoads).toBe(0);
    expect(result.current.program.description).toBe("edited while saving");
  });

  it("asks nothing of a program that was never saved", async () => {
    const requests = backend({ revision: 2, program: onDisk() });
    renderStore(createEmptyProgram("p"));

    await poll();

    expect(requests).toEqual([]);
  });

});
