// @vitest-environment node
import { describe, expect, it } from "vitest";
import { z } from "zod";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";

import { LaunchRecordConflict } from "../../src/api/executionApi";
import { createOption } from "../../src/models/option";
import type { ProgramProcess } from "../../src/models/process";
import type { Program } from "../../src/models/program";
import type { Backend } from "./backend";
import type { FakeBackend } from "./fakeBackend";
import { fakeBackend } from "./fakeBackend";
import { createServer } from "./server";
import { RUN_START_WAIT, TOOLS } from "./tools";

const HOME = "/progs/p";

function process(name: string, labels: string[], x = 100): ProgramProcess {
  return {
    id: `id-${name}`,
    name,
    description: "",
    position: { x, y: 100 },
    options: labels.map(label => createOption(`${name}${label}`, label)),
    optionsHandler: { mode: "standard" },
    language: "bash",
    code: `${name}() { :; }`,
    computationalSpecs: { cpus: 1, mem: 256 },
    additionalSpecs: { force: false },
    additionalMethods: {},
  };
}

function program(changes: Partial<Program> = {}): Program {
  return {
    id: "p",
    name: "p",
    programType: "general",
    description: "",
    preamble: "",
    envVars: {},
    homeDir: HOME,
    revision: 1,
    outputDir: "/out/p",
    sourceDir: "",
    executionOptions: { scheduler: "BUILTIN" },
    programOptions: {},
    sharedDirs: [],
    availableSharedDirs: [],
    seqProcesses: [],
    processes: [process("a", ["-outf"]), process("b", ["-in", "-x"], 320)],
    edges: [],
    ...changes,
  };
}

// Calls an MCP tool with its parameters checked by its schema, as the MCP
// library checks them.
async function call(backend: Backend, name: string, args: Record<string, unknown>) {
  const tool = TOOLS.find(candidate => candidate.name === name);
  if (!tool) {
    throw new Error(`no tool ${name}`);
  }
  return tool.run(backend, z.object(tool.input).parse(args));
}

async function text(backend: Backend, name: string, args: Record<string, unknown>) {
  return (await call(backend, name, args)).text;
}

function savedProgram(backend: FakeBackend): Program {
  return backend.saved.get(HOME)!;
}

const A_TO_B = { from: { process: "a", option: "-outf" }, to: { process: "b", option: "-in" } };

describe("reading a program", () => {

  it("shows processes, options and connections by name, never by id", async () => {
    const backend = fakeBackend([program({ edges: [{ id: "e1", sourceProcessId: "id-a", sourceOptionId: "a-outf", targetProcessId: "id-b", targetOptionId: "b-in" }] })]);

    const shown = await text(backend, "get_program", { home_dir: HOME });

    expect(shown).toContain("a (bash)");
    expect(shown).toContain("-outf (output, string)");
    expect(shown).toContain("a -outf -> b -in");
    expect(shown).not.toMatch(/id-a|a-outf|e1/);
  });

  it("shows one process with its code", async () => {
    const backend = fakeBackend([program()]);

    expect(await text(backend, "get_process", { home_dir: HOME, process: "b" })).toContain("b() { :; }");
    await expect(call(backend, "get_process", { home_dir: HOME, process: "nope" })).rejects.toThrow('no process named "nope"');
  });

});

describe("the code prompt", () => {
  it("composes the code prompt of the code of a process, as the editor does", async () => {
    const backend = fakeBackend([program()]);
    const prompt = await text(backend, "get_code_prompt", { home_dir: HOME, process: "b", request: "Echo -x." });
    expect(prompt).toContain("# Write the code of the DeBasher process `b`");
    expect(prompt).toContain("```bash\nb() { :; }\n```");
    expect(prompt).toContain("## What the code has to do\n\nEcho -x.");
  });

  it("composes the code prompt of an options handler, and refuses one with no code", async () => {
    const arrayProcess = { ...process("a", ["-in"]), optionsHandler: { mode: "array" as const, arrayCode: "array=(x y)" } };
    const backend = fakeBackend([program({ processes: [arrayProcess] })]);
    expect(await text(backend, "get_code_prompt", { home_dir: HOME, process: "a", part: "options_handler" }))
      .toContain("It has to build a Bash array named `array`");
    const standard = fakeBackend([program()]);
    await expect(call(standard, "get_code_prompt", { home_dir: HOME, process: "a", part: "options_handler" }))
      .rejects.toThrow("only the code of an array or generator options handler has a code prompt");
  });

  it("composes the code prompt of an additional method, and refuses an unknown part", async () => {
    const backend = fakeBackend([program()]);
    expect(await text(backend, "get_code_prompt", { home_dir: HOME, process: "a", part: "skip" }))
      .toContain("# Write the `skip` method of the DeBasher process `a`");
    await expect(call(backend, "get_code_prompt", { home_dir: HOME, process: "a", part: "nope" }))
      .rejects.toThrow('not "nope"');
  });

  it("composes the code prompt of a node with the reference and the inherited hooks of the library", async () => {
    const node = { ...process("Launch", ["-inreq"]), language: "python" as const, nodeKind: "ProgramLauncher" as const };
    const backend = fakeBackend([program({ programType: "resident", processes: [node] })], {
      getNodeReference: async () => ({ reference: "### FBPProcess\n\nThe base class.", error: null }),
      getInheritedHooks: async () => ({ hooks: { observe: "def observe(self):\n    pass" }, error: null }),
    });
    const prompt = await text(backend, "get_code_prompt", { home_dir: HOME, process: "Launch" });
    expect(prompt).toContain("# Write the code of the DeBasher node `Launch`");
    expect(prompt).toContain("### FBPProcess\n\nThe base class.");
    expect(prompt).toContain("def observe(self):\n    pass");
    await expect(call(backend, "get_code_prompt", { home_dir: HOME, process: "Launch", part: "post" }))
      .rejects.toThrow("A node of a resident program has no additional methods.");
  });
});

describe("editing a program", () => {

  it("connects two processes and saves the program with a new revision", async () => {
    const backend = fakeBackend([program()]);

    const answer = await text(backend, "connect", { home_dir: HOME, ...A_TO_B });

    expect(answer).toContain("Saved (revision 2)");
    expect(answer).toContain("+ Connection a -outf -> b -in");
    const saved = savedProgram(backend);
    expect(saved.edges).toHaveLength(1);
    expect(saved.processes[1].options[0].value).toBe("[a;-outf]");
  });

  it("draws a connection as a label edge, when asked, and shows it so", async () => {
    const backend = fakeBackend([program()]);

    const answer = await text(backend, "connect", { home_dir: HOME, ...A_TO_B, display: "label" });

    expect(answer).toContain("+ Connection a -outf -> b -in (drawn as a label edge)");
    expect(savedProgram(backend).edges[0].display).toBe("label");
  });

  it("switches how an existing connection is drawn", async () => {
    const backend = fakeBackend([program()]);
    await call(backend, "connect", { home_dir: HOME, ...A_TO_B });

    const answer = await text(backend, "set_connection_display", { home_dir: HOME, ...A_TO_B, display: "label" });

    expect(answer).toContain("- Connection a -outf -> b -in\n+ Connection a -outf -> b -in (drawn as a label edge)");
    expect(savedProgram(backend).edges[0].display).toBe("label");
    await expect(
      call(backend, "set_connection_display", { home_dir: HOME, ...A_TO_B, to: { process: "a", option: "-outf" }, display: "line" })
    ).rejects.toThrow("There is no connection");
  });

  it("applies a list of edits whole, each naming what an earlier one added", async () => {
    const backend = fakeBackend([program()]);

    await call(backend, "apply_edits", {
      home_dir: HOME,
      edits: [
        { op: "addProcess", name: "c", options: [{ label: "-in" }] },
        { op: "connect", from: { process: "a", option: "-outf" }, to: { process: "c", option: "-in" } },
        { op: "updateProcess", process: "c", changes: { computationalSpecs: { cpus: 4 } } },
      ],
    });

    const c = savedProgram(backend).processes.find(p => p.name === "c")!;
    expect(c.computationalSpecs).toEqual({ cpus: 4, mem: 256, time: "01:00:00" });
    expect(c.options[0].value).toBe("[a;-outf]");
  });

  it("marks an option as a task shaping option, and shows it so", async () => {
    const backend = fakeBackend([program()]);

    await call(backend, "add_option", {
      home_dir: HOME,
      process: "b",
      label: "-w",
      fields: { dataType: "int", commandLine: true, mandatory: true, taskShaping: true },
    });

    const w = savedProgram(backend).processes[1].options.find(option => option.label === "-w")!;
    expect(w.taskShaping).toBe(true);
    expect(await text(backend, "get_program", { home_dir: HOME })).toContain("-w (input, int, command line, task shaping, mandatory)");
  });

  it("saves nothing when one edit breaks a rule, and says which", async () => {
    const backend = fakeBackend([program()]);

    await expect(call(backend, "apply_edits", {
      home_dir: HOME,
      edits: [
        { op: "addOption", process: "a", label: "-y" },
        { op: "addOption", process: "b", label: "-x" },
      ],
    })).rejects.toThrow('Process "b" already has an option labeled -x.');
    expect(backend.saves).toBe(0);
  });

  it("refuses a name that matches nothing, naming the edit", async () => {
    const backend = fakeBackend([program()]);

    await expect(call(backend, "update_option", {
      home_dir: HOME, process: "a", option: "-nope", changes: { mandatory: true },
    })).rejects.toThrow("Edit 1 (updateOption): Process \"a\" has no option labeled -nope.");
  });

  it("refuses a name that the engine does not accept", async () => {
    const backend = fakeBackend([program()]);

    await expect(call(backend, "update_process", {
      home_dir: HOME, process: "a", changes: { name: "bad name" },
    })).rejects.toThrow('"bad name" is not a valid process name');
  });

  it("answers a dry run with a proposal and saves nothing", async () => {
    const backend = fakeBackend([program()]);

    const answer = await call(backend, "connect", { home_dir: HOME, ...A_TO_B, dry_run: true });

    expect(answer.text).toContain("Proposal, nothing saved");
    expect(answer.text).toContain("+ Connection a -outf -> b -in");
    expect(answer.text).toContain('+ Process b option -in (input, string, value "[a;-outf]")');
    expect((answer.structured!.edits as { op: string }[]).map(edit => edit.op)).toEqual(["connect"]);
    expect(backend.saves).toBe(0);
  });

  it("refuses to change a group added with another program unless told to dissolve it", async () => {
    const groupSource = { programName: "other", groupId: "g1", groupSize: 1, sourceDir: "/progs/other" };
    const grouped = program();
    grouped.processes[1] = { ...grouped.processes[1], groupSource };
    const backend = fakeBackend([grouped]);

    await expect(call(backend, "connect", { home_dir: HOME, ...A_TO_B })).rejects.toThrow(
      'processes added with program "other"'
    );

    const answer = await text(backend, "connect", { home_dir: HOME, ...A_TO_B, detach_groups: true });
    expect(answer).toContain('Dissolves the groups of program "other"');
    expect(savedProgram(backend).processes[1].groupSource).toBeUndefined();
  });

  it("refuses to save over a program saved elsewhere since it was loaded", async () => {
    const backend = fakeBackend([program()]);
    const load = backend.loadProgram;
    // Someone saves the program between the load and the save of the call.
    backend.loadProgram = async homeDir => {
      const loaded = await load(homeDir);
      backend.saved.set(HOME, { ...loaded, description: "changed elsewhere", revision: 2 });
      return loaded;
    };

    await expect(call(backend, "connect", { home_dir: HOME, ...A_TO_B })).rejects.toThrow(
      "Read the program again with get_program"
    );
    expect(savedProgram(backend).edges).toEqual([]);
  });

  it("adds a process of the library with its options, to the right of the others", async () => {
    const backend = fakeBackend([program()], {
      suggestProcessNames: async () => ["lib_proc"],
      getProcessInfo: async () => ({
        description: "from the library",
        language: "bash",
        code: "lib_proc() { :; }",
        options: [{ label: "-in", dataType: "file", description: "", commandLine: false, mandatory: true }],
      }),
    });

    await call(backend, "add_process", { home_dir: HOME, name: "lib_proc" });

    const added = savedProgram(backend).processes[2];
    expect(added.description).toBe("from the library");
    expect(added.options.map(o => [o.label, o.dataType, o.mandatory])).toEqual([["-in", "file", true]]);
    expect(added.position).toEqual({ x: 540, y: 100 });
  });

  it("places several added processes apart from each other", async () => {
    const backend = fakeBackend([program()]);

    await call(backend, "apply_edits", {
      home_dir: HOME,
      edits: [{ op: "addProcess", name: "c" }, { op: "addProcess", name: "d" }],
    });

    expect(savedProgram(backend).processes.slice(2).map(p => p.position.x)).toEqual([540, 760]);
  });

  it("needs the node kind of a node that no module defines", async () => {
    const backend = fakeBackend([program({ programType: "resident", processes: [] })]);

    await expect(call(backend, "add_process", { home_dir: HOME, name: "counter" })).rejects.toThrow(
      "give the node kind"
    );

    await call(backend, "add_process", { home_dir: HOME, name: "counter", nodeKind: "FBPProcess" });
    expect(savedProgram(backend).processes[0].nodeKind).toBe("FBPProcess");
  });

  it("adds, changes and removes sequential processes by name", async () => {
    const backend = fakeBackend([program()]);

    await call(backend, "set_seq_processes", { home_dir: HOME, seq_processes: [{ name: "step" }] });
    expect(savedProgram(backend).seqProcesses.map(s => s.code)).toEqual(["step()\n{\n    :\n}"]);

    await call(backend, "set_seq_processes", { home_dir: HOME, seq_processes: [{ name: "step", newName: "step2" }] });
    expect(savedProgram(backend).seqProcesses.map(s => [s.name, s.code])).toEqual([["step2", "step2()\n{\n    :\n}"]]);

    await call(backend, "set_seq_processes", { home_dir: HOME, seq_processes: [{ name: "step2", remove: true }] });
    expect(savedProgram(backend).seqProcesses).toEqual([]);
  });

  it("lays out every process again in layers", async () => {
    const backend = fakeBackend([program({ edges: [{ id: "e1", sourceProcessId: "id-a", sourceOptionId: "a-outf", targetProcessId: "id-b", targetOptionId: "b-in" }] })]);

    await call(backend, "move_process", { home_dir: HOME, layout: true });

    expect(savedProgram(backend).processes.map(p => p.position)).toEqual([{ x: 100, y: 100 }, { x: 100, y: 260 }]);
  });

  it("sets the settings, keeping the execution options it is not given", async () => {
    const backend = fakeBackend([program({ executionOptions: { scheduler: "BUILTIN", condaSupport: true } })]);

    await call(backend, "set_program_settings", {
      home_dir: HOME,
      changes: { executionOptions: { builtinSchedCpus: "4" } },
      env_vars: { DEBASHER_MOD_DIR: "/mods" },
    });

    const saved = savedProgram(backend);
    expect(saved.executionOptions).toEqual({ scheduler: "BUILTIN", condaSupport: true, builtinSchedCpus: "4" });
    expect(saved.envVars).toEqual({ DEBASHER_MOD_DIR: "/mods" });
  });

});

describe("creating and importing a program", () => {

  it("refuses a directory that already holds a program", async () => {
    const backend = fakeBackend([program()]);

    await expect(call(backend, "create_program", { home_dir: HOME, name: "q" })).rejects.toThrow("already holds a program");
    await expect(call(backend, "import_module", { home_dir: HOME, script_path: "/m.sh" })).rejects.toThrow("already holds a program");
  });

  it("imports a module into a new home directory", async () => {
    const backend = fakeBackend([], { importProgram: async () => program({ homeDir: "", revision: 0 }) });

    const answer = await text(backend, "import_module", { home_dir: "/progs/new", script_path: "/m.sh" });

    expect(answer).toContain("Home directory: /progs/new");
    expect(backend.saved.get("/progs/new")?.revision).toBe(1);
  });

  it("creates an empty program", async () => {
    const backend = fakeBackend();

    await call(backend, "create_program", { home_dir: "/progs/new", name: "q", program_type: "resident" });

    expect(backend.saved.get("/progs/new")).toMatchObject({ name: "q", programType: "resident", processes: [] });
  });

});

describe("running a program", () => {

  it("refuses to launch a second run on the output directory", async () => {
    const backend = fakeBackend([program()], {
      fetchProgramStatus: async () => ({ state: "in-progress", output: "" }),
    });

    await expect(call(backend, "run_program", { home_dir: HOME })).rejects.toThrow("already in progress");
  });

  it("answers a launch once the statuses show the new run, not the run before", async () => {
    RUN_START_WAIT.everyMs = 1;
    const readings = [{ a: "FINISHED" }, { a: "FINISHED" }, { a: "FINISHED" }, { a: "IN-PROGRESS" }];
    const backend = fakeBackend([program()], {
      fetchProgramStatus: async () => ({ state: "finished", output: "" }),
      getProcessStatuses: async () => ({ statuses: readings.shift()!, hasProgramState: false, output: "", notices: [] }),
      runProgram: async () => ({ started: true, exitCode: null, output: null, revision: 1 }),
    });

    expect(await text(backend, "run_program", { home_dir: HOME })).toContain("a: IN-PROGRESS");
  });

  it("says how to go on when the program state comes from another program", async () => {
    const backend = fakeBackend([program({ programType: "resident" })], {
      fetchProgramStatus: async () => ({ state: "finished", output: "" }),
      runProgram: async () => {
        throw new LaunchRecordConflict(true);
      },
    });

    await expect(call(backend, "run_program", { home_dir: HOME })).rejects.toThrow("resume_changed_program");
  });

  it("needs an output directory", async () => {
    const backend = fakeBackend([program({ outputDir: "" })]);

    await expect(call(backend, "get_status", { home_dir: HOME })).rejects.toThrow("no output directory");
  });

  it("cuts the output of a process to its last lines", async () => {
    const backend = fakeBackend([program()], {
      getProcessStdout: async () => Array.from({ length: 100 }, (_, i) => `line ${i}`).join("\n"),
    });

    const shown = await text(backend, "get_process_output", { home_dir: HOME, process: "a", lines: 2 });

    expect(shown).toBe("(the last 2 of 100 lines)\nline 98\nline 99");
  });

  it("deletes what a run left only when confirmed", async () => {
    let resets = 0;
    const backend = fakeBackend([program()], {
      resetOutputDir: async () => {
        resets += 1;
        return true;
      },
    });

    await expect(call(backend, "reset_output_dir", { home_dir: HOME })).rejects.toThrow("call again with confirm");
    expect(resets).toBe(0);
    await call(backend, "reset_output_dir", { home_dir: HOME, confirm: true });
    expect(resets).toBe(1);
  });

});

describe("talking to a resident program", () => {

  function resident(): Program {
    const node = process("n", []);
    node.nodeKind = "FBPProcess";
    node.options = [
      createOption("n-in", "-in", { channel: "fifo", fifoTag: "external", value: "in_fifo" }),
      createOption("n-out", "-outd", { channel: "fifo", value: "out_fifo" }),
    ];
    return program({ programType: "resident", processes: [node] });
  }

  it("writes only into an external input, by the name of its FIFO", async () => {
    const writes: string[] = [];
    const backend = fakeBackend([resident()], {
      writeResidentFifo: async (_program, processName, fifoName, message) => {
        writes.push(`${processName} ${fifoName} ${message}`);
        return { ok: true };
      },
    });

    await call(backend, "write_fifo", { home_dir: HOME, process: "n", option: "-in", message: "{\"a\": 1}" });
    await expect(call(backend, "write_fifo", { home_dir: HOME, process: "n", option: "-outd", message: "1" }))
      .rejects.toThrow("not an external input");

    expect(writes).toEqual(['n in_fifo {"a": 1}']);
  });

  it("shows what it reads from an output", async () => {
    const backend = fakeBackend([resident()], {
      readResidentFifo: async () => ({ envelope: { type: "DATA", seq: 3, payload: { a: 1 } } }),
    });

    expect(await text(backend, "read_fifo", { home_dir: HOME, process: "n", option: "-outd" })).toBe('< n -outd #3: {"a":1}');
  });

});

describe("business tests and user files", () => {

  // The user files of the home directory, kept as the program files of the
  // backend keep them, with its refusal of the generated script.
  function withFiles(files: Record<string, string>, changes: Partial<Program> = {}) {
    const writes: { path: string; create: boolean }[] = [];
    const removed: string[] = [];
    const moved: [string, string][] = [];
    const backend = fakeBackend([program(changes)], {
      deleteEntry: async (_homeDir: string, _programName: string, path: string) => {
        removed.push(path);
        return [];
      },
      moveEntry: async (_homeDir: string, _programName: string, from: string, to: string) => {
        moved.push([from, to]);
        return [];
      },
      getFileContent: async (_homeDir: string, path: string) =>
        path in files ? { kind: "file" as const, content: files[path], version: "v" } : { kind: "missing" as const },
      writeFileContent: async (_homeDir: string, programName: string, path: string, content: string, create = false) => {
        if (path === `${programName}.sh`) {
          throw new Error("Cannot edit the program's generated script");
        }
        files[path] = content;
        writes.push({ path, create });
        return [];
      },
      getFileTree: async () => [
        { name: "p.sh", path: "p.sh", type: "file" as const, readonly: true, children: null },
        {
          name: "test", path: "test", type: "dir" as const, readonly: false,
          children: [{ name: "a.bats", path: "test/a.bats", type: "file" as const, readonly: false, children: null }],
        },
      ],
    });
    return { backend, files, writes, removed, moved };
  }

  it("runs the tests after saving the program, and says their outcome", async () => {
    let tested: Program | null = null;
    const backend = fakeBackend([program()], {
      runTests: async (sent: Program) => {
        tested = sent;
        return { outcome: "failed" as const, output: "not ok 1 a works\n", revision: 2 };
      },
    });

    const answer = await text(backend, "run_tests", { home_dir: HOME });

    expect(answer).toContain("Some tests failed.");
    expect(answer).toContain("not ok 1 a works");
    expect(tested!.homeDir).toBe(HOME);
  });

  it("writes the test skeleton of a process", async () => {
    const { backend, files, writes } = withFiles({});

    const answer = await text(backend, "add_test", { home_dir: HOME, process: "a" });

    expect(writes).toEqual([{ path: "test/a.bats", create: true }]);
    expect(files["test/a.bats"]).toContain("run debasher_process a");
    expect(answer).toContain("Wrote test/a.bats");
  });

  it("writes a test skeleton under another name", async () => {
    const { backend, files } = withFiles({ "test/a.bats": "mine" });

    expect(await text(backend, "add_test", { home_dir: HOME, process: "a", file_name: "a-edge-cases.bats" }))
      .toContain("Wrote test/a-edge-cases.bats");
    expect(files["test/a.bats"]).toBe("mine");
  });

  it("refuses a name that debasher_test would not run", async () => {
    const { backend, writes } = withFiles({});

    await expect(call(backend, "add_test", { home_dir: HOME, process: "a", file_name: "a.sh" }))
      .rejects.toThrow("<name>.bats");
    expect(writes).toEqual([]);
  });

  it("never overwrites a test that exists", async () => {
    const { backend, writes } = withFiles({ "test/a.bats": "mine" });

    await expect(call(backend, "add_test", { home_dir: HOME, process: "a" })).rejects.toThrow("test/a.bats exists");
    expect(writes).toEqual([]);
  });

  it("refuses a node that the node harness does not build", async () => {
    const sup = { ...process("Sup", []), nodeKind: "Supervisor" as const };
    const { backend } = withFiles({}, { programType: "resident", processes: [sup] });

    await expect(call(backend, "add_test", { home_dir: HOME, process: "Sup" })).rejects.toThrow("node harness");
  });

  it("lists, reads and writes the user files", async () => {
    const { backend, files } = withFiles({ "test/a.bats": "@test x {}" });

    expect(await text(backend, "list_program_files", { home_dir: HOME }))
      .toBe("p.sh (generated script, read-only)\ntest/\n  a.bats");
    expect(await text(backend, "read_program_file", { home_dir: HOME, path: "test/a.bats" })).toBe("@test x {}");
    await expect(call(backend, "read_program_file", { home_dir: HOME, path: "nope" })).rejects.toThrow("does not exist");

    await text(backend, "write_program_file", { home_dir: HOME, path: "test/data/in.txt", content: "1 2" });
    expect(files["test/data/in.txt"]).toBe("1 2");
  });

  it("deletes a user file only when the call confirms it", async () => {
    const { backend, removed } = withFiles({});

    await expect(call(backend, "delete_program_file", { home_dir: HOME, path: "test/a.bats" }))
      .rejects.toThrow("This deletes test/a.bats, which cannot be undone: call again with confirm.");
    expect(removed).toEqual([]);

    expect(await text(backend, "delete_program_file", { home_dir: HOME, path: "test/a.bats", confirm: true }))
      .toBe("Deleted test/a.bats.");
    expect(removed).toEqual(["test/a.bats"]);
  });

  it("says how many files a directory holds before deleting it", async () => {
    const { backend } = withFiles({});

    await expect(call(backend, "delete_program_file", { home_dir: HOME, path: "test" }))
      .rejects.toThrow("the directory test and the 1 files in it");
    await expect(call(backend, "delete_program_file", { home_dir: HOME, path: "nope" }))
      .rejects.toThrow("nope does not exist");
  });

  it("moves a user file", async () => {
    const { backend, moved } = withFiles({});

    expect(await text(backend, "move_program_file", { home_dir: HOME, path: "test/a.bats", new_path: "test/b.bats" }))
      .toBe("Moved test/a.bats to test/b.bats.");
    expect(moved).toEqual([["test/a.bats", "test/b.bats"]]);
  });

  it("refuses to write the generated script, as the backend does", async () => {
    const { backend } = withFiles({});

    await expect(call(backend, "write_program_file", { home_dir: HOME, path: "p.sh", content: "" }))
      .rejects.toThrow("generated script");
  });

});

describe("the MCP server", () => {

  async function connected(backend: Backend) {
    const [clientSide, serverSide] = InMemoryTransport.createLinkedPair();
    await createServer(backend, "test").connect(serverSide);
    const client = new Client({ name: "test", version: "test" });
    await client.connect(clientSide);
    return client;
  }

  it("offers every MCP tool and answers a call with text", async () => {
    const backend = fakeBackend([program()]);
    const client = await connected(backend);

    const { tools } = await client.listTools();
    expect(tools.map(tool => tool.name).sort()).toEqual(TOOLS.map(tool => tool.name).sort());

    const result = await client.callTool({ name: "connect", arguments: { home_dir: HOME, ...A_TO_B } });
    expect(result.isError).toBeFalsy();
    expect((result.content as { text: string }[])[0].text).toContain("Saved (revision 2)");
  });

  it("answers a refusal as an error with its reason", async () => {
    const client = await connected(fakeBackend([program()]));

    const result = await client.callTool({ name: "remove_process", arguments: { home_dir: HOME, process: "zzz" } });

    expect(result.isError).toBe(true);
    expect((result.content as { text: string }[])[0].text).toContain('no process named "zzz"');
  });

  it("refuses a field that the model does not have", async () => {
    const client = await connected(fakeBackend([program()]));

    const result = await client.callTool({
      name: "update_process",
      arguments: { home_dir: HOME, process: "a", changes: { position: { x: 0, y: 0 } } },
    });

    expect(result.isError).toBe(true);
  });

});
