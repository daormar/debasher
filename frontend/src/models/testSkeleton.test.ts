import { describe, expect, it } from "vitest";
import { createOption } from "./option";
import type { ProgramOption } from "./option";
import type { ProgramProcess } from "./process";
import type { Program } from "./program";
import {
  defaultTestFileName,
  offersAddTest,
  testFileNameProblem,
  testFilePath,
  testSkeleton,
  testSkeletonSummary,
} from "./testSkeleton";

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
    expect(offersAddTest(resident, process("Watch", [], { nodeKind: "DirectoryWatcher" }))).toBe(true);
    for (const nodeKind of ["Supervisor", "ProgramLauncher"] as const) {
      expect(offersAddTest(resident, process("X", [], { nodeKind }))).toBe(false);
    }
  });
});

describe("the name of a test file", () => {
  it("names a process test after its process", () => {
    expect(defaultTestFileName(program("general", []), process("org.ns.greet", []))).toBe("org.ns.greet.bats");
  });

  it("names a node test as a Python module", () => {
    expect(defaultTestFileName(program("resident", []), process("org.ns.Acc", []))).toBe("test_org_ns_Acc.py");
  });

  it("puts a test file in the test directory", () => {
    expect(testFilePath("greet.bats")).toBe("test/greet.bats");
  });

  it("accepts only a name that debasher_test runs", () => {
    const general = program("general", []);
    const resident = program("resident", []);
    for (const name of ["greet.bats", "org.ns.greet.bats", "greet-2.bats"]) {
      expect(testFileNameProblem(general, name)).toBeNull();
    }
    for (const name of ["greet.sh", ".greet.bats", "sub/greet.bats", ".bats", "test_greet.py"]) {
      expect(testFileNameProblem(general, name)).toMatch(/<name>\.bats/);
    }
    for (const name of ["test_acc.py", "test_Acc_2.py"]) {
      expect(testFileNameProblem(resident, name)).toBeNull();
    }
    for (const name of ["acc.py", "test_.py", "test_org.ns.acc.py", "test_acc.bats", "sub/test_acc.py"]) {
      expect(testFileNameProblem(resident, name)).toMatch(/test_<name>\.py/);
    }
  });

  it("says what the skeleton is before it is written", () => {
    expect(testSkeletonSummary(program("general", []), process("greet", []))).toMatch(
      /^Writes a first test for greet: a process test \(bats\).*fill in its TODOs/
    );
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

  it("marks with a TODO each thing to fill in", () => {
    expect(skeleton).toContain("    # TODO: replace each TODO value with the value of the test\n    run debasher_process greet");
    expect(skeleton).toContain('    [ "${status}" -eq 0 ]\n    # TODO: check what the process wrote');
  });

  it("fails until the user writes its checks", () => {
    expect(skeleton).toMatch(/ {4}# TODO: once the checks above are written, remove the line below,\n {4}# which makes a skeleton fail\n {4}false\n\}\n$/);
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
    expect(skeleton).toContain('return load_node("Accumulate", opts=opts, inputs=["numbers", "in"], outputs=["outsum"])');
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

  it("has no test of observe for a node that does not observe", () => {
    expect(skeleton).not.toContain("observe()");
  });
});

describe("the skeleton of a node that observes the outside world", () => {
  const out = createOption("outrequests", "-outrequests", { direction: "output", channel: "fifo" });

  it("observes for a node with a body for observe", () => {
    const poll = process("Poll", [out], { nodeKind: "FBPProcess", nodeCode: { observe: "self.inject(1)" } } as Partial<ProgramProcess>);
    const skeleton = testSkeleton(program("resident", [poll]), poll);

    expect(skeleton).toContain("def test_Poll_brings_in_what_it_observes():");
    expect(skeleton).toContain("    injected = under_test.observe()");
    expect(skeleton.match(/pytest\.fail\(/g)).toHaveLength(3);
  });

  describe("a DirectoryWatcher", () => {
    const watchdir = createOption("watchdir", "-watchdir", { commandLine: true });
    const watch = process("Watch", [watchdir, out], { nodeKind: "DirectoryWatcher" });
    const skeleton = testSkeleton(program("resident", [watch]), watch);

    it("has no test that feeds it, since it has no input and needs its directory", () => {
      expect(skeleton).not.toContain("sends_what_it_should");
      expect(skeleton).not.toContain("feed(");
      expect(skeleton).not.toMatch(/under_test = node\(\)/);
    });

    it("puts a file in the directory that it watches, and observes twice", () => {
      expect(skeleton).toContain("def test_Watch_brings_in_what_it_observes(tmp_path):");
      expect(skeleton).toContain('    under_test = node(opts={"watchdir": str(tmp_path)})');
      expect(skeleton).toContain('    # TODO: write in tmp_path the files that the test needs\n    (tmp_path / "TODO").write_text("TODO")');
      expect(skeleton).toMatch(/ {4}under_test\.observe\(\)\n {4}injected = under_test\.observe\(\)/);
    });

    it("checks that after a restart it requests nothing twice", () => {
      expect(skeleton).toContain("def test_Watch_requests_nothing_twice_after_a_restart(tmp_path):");
      expect(skeleton).toContain("    under_test = under_test.restart()");
      expect(skeleton.match(/pytest\.fail\(/g)).toHaveLength(2);
    });

    it("points to WATCH_DIR when it has no option for its directory", () => {
      const bare = process("Watch", [out], { nodeKind: "DirectoryWatcher" });

      expect(testSkeleton(program("resident", [bare]), bare))
        .toContain("# TODO: write in the directory that WATCH_DIR names the files that the test needs");
    });
  });
});
