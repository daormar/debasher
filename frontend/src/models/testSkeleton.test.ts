import { describe, expect, it } from "vitest";
import { createOption } from "./option";
import type { ProgramOption } from "./option";
import type { ProgramProcess } from "./process";
import type { Program } from "./program";
import { offersAddTest, testFilePath, testSkeleton } from "./testSkeleton";

function process(name: string, options: ProgramOption[], fields: Partial<ProgramProcess> = {}): ProgramProcess {
  return { id: name, name, options, ...fields } as ProgramProcess;
}

function program(programType: "general" | "resident", processes: ProgramProcess[], edges: Program["edges"] = []): Program {
  return { programType, processes, edges } as Program;
}

// greet of webui_batch_greet, with a flag of its own
const greet = process("greet", [
  createOption("text", "-text", { description: "whom to greet", commandLine: true }),
  createOption("secs", "-secs", { dataType: "int", description: "how many seconds\nto wait" }),
  createOption("verbose", "-verbose", { dataType: "None", description: "say more" }),
  createOption("outf", "-outf", { direction: "output", dataType: "file", description: "file with the greeting" }),
]);

describe("offersAddTest", () => {
  it("is offered on every process of a general program", () => {
    expect(offersAddTest(program("general", [greet]), greet)).toBe(true);
  });

  it("is offered on a node only when the node harness builds it", () => {
    const resident = program("resident", []);
    expect(offersAddTest(resident, process("Acc", [], { nodeKind: "FBPProcess" }))).toBe(true);
    for (const nodeKind of ["Supervisor", "DirectoryWatcher", "ProgramLauncher"] as const) {
      expect(offersAddTest(resident, process("X", [], { nodeKind }))).toBe(false);
    }
  });
});

describe("testFilePath", () => {
  it("names a process test after its process", () => {
    expect(testFilePath(program("general", []), process("org.ns.greet", []))).toBe("test/org.ns.greet.bats");
  });

  it("names a node test as a Python module", () => {
    expect(testFilePath(program("resident", []), process("org.ns.Acc", []))).toBe("test/test_org_ns_Acc.py");
  });
});

describe("the skeleton of a process test", () => {
  const skeleton = testSkeleton(program("general", [greet]), greet);

  it("runs the process with every option but the flags, one per line", () => {
    expect(skeleton).toContain(
      [
        "    run debasher_process greet \\",
        "        -text TODO \\",
        "        -secs TODO \\",
        '        -outf "${BATS_TEST_TMPDIR}/outf"',
      ].join("\n")
    );
    expect(skeleton).toContain('load "${DEBASHER_BATS_HELPERS}"');
  });

  it("lists the options and the flags in a comment above the command", () => {
    expect(skeleton).toContain("    #   -secs: how many seconds to wait");
    expect(skeleton).toContain("    # Flags, to add to the command if the test needs them: -verbose");
    expect(skeleton.indexOf("-verbose")).toBeLessThan(skeleton.indexOf("run debasher_process"));
  });

  it("fails until the user writes its checks", () => {
    expect(skeleton).toMatch(/\[ "\$\{status\}" -eq 0 \]\n\n {4}# Write the checks.*\n {4}false\n\}\n$/);
  });

  it("runs a process with no options alone", () => {
    expect(testSkeleton(program("general", []), process("bare", []))).toContain("    run debasher_process bare\n");
  });
});

describe("the skeleton of a node test", () => {
  const acc = process("Accumulate", [
    createOption("numbers", "-numbers", { channel: "fifo", fifoTag: "external" }),
    createOption("in", "-in"),
    createOption("unconnected", "-unconnected"),
    createOption("outsum", "-outsum", { direction: "output", channel: "fifo" }),
    createOption("threshold", "-threshold", { commandLine: true, description: "the limit" }),
  ], { nodeKind: "FBPProcess" });
  const source = process("Source", [createOption("out", "-out", { direction: "output", channel: "fifo" })], { nodeKind: "FBPProcess" });
  const edges = [
    { id: "e1", sourceProcessId: "Source", sourceOptionId: "out", targetProcessId: "Accumulate", targetOptionId: "in" },
  ] as Program["edges"];
  const skeleton = testSkeleton(program("resident", [acc, source], edges), acc);

  it("names the external inputs, the connected inputs and the business outputs", () => {
    expect(skeleton).toContain('return load_node("Accumulate", inputs=["numbers", "in"], outputs=["outsum"])');
  });

  it("lists the configuration options in a comment", () => {
    expect(skeleton).toContain("    #   -threshold: the limit");
  });

  it("feeds the first input, checks the first output and restarts", () => {
    expect(skeleton).toContain('    under_test.feed("numbers", "TODO")');
    expect(skeleton).toContain('    assert under_test.sent("outsum") == ["TODO"]');
    expect(skeleton).toContain("    under_test = under_test.restart()");
  });

  it("fails in each test until the user writes its checks", () => {
    expect(skeleton.match(/pytest\.fail\(/g)).toHaveLength(2);
  });
});
