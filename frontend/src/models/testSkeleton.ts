import { isBusinessOutput, nodeOptionRole, observesOutside } from "./node";
import type { ProgramOption } from "./option";
import type { ProgramProcess } from "./process";
import type { Program } from "./program";

/**
 * The test skeleton that "Add test" writes for a process (see "Adding a
 * test" in doc/design_doc_webui.md): a process test, run with bats, for a
 * process of a general program, and a node test, run with pytest, for a
 * node whose node kind is FBPProcess or DirectoryWatcher. The MCP server
 * writes the same one.
 *
 * A skeleton is a starting point, not a test: each of its tests ends with
 * a line that fails on purpose, so that "Run tests" never reports a
 * skeleton as a test that passes.
 */

// The directory of the tests, inside the home directory.
export const TEST_DIR = "test";

/**
 * Whether "Add test" is offered on `process`: on every process of a
 * general program, and on a node only when the node harness builds it,
 * that is when its node kind is FBPProcess or DirectoryWatcher.
 */
export function offersAddTest(program: Program, process: ProgramProcess): boolean {
  return (
    program.programType !== "resident" ||
    process.nodeKind === "FBPProcess" ||
    process.nodeKind === "DirectoryWatcher"
  );
}

// The option of a DirectoryWatcher that gives the directory it watches
// instead of WATCH_DIR (WATCH_DIR_OPTION in the runtime library).
const WATCH_DIR_LABEL = "-watchdir";

/**
 * The name of the test skeleton of `process` that "Add test" proposes, in
 * the test directory: <process>.bats, or test_<process>.py with every dot
 * of a qualified name turned into an underscore, since pytest imports a
 * test file as a module, and a dot would make its name a package path.
 */
export function defaultTestFileName(program: Program, process: ProgramProcess): string {
  return program.programType === "resident" ? `test_${pythonName(process.name)}.py` : `${process.name}.bats`;
}

/**
 * Why `fileName` cannot name a test file of the program, or null when it
 * can: a name of the test directory that debasher_test runs, *.bats in a
 * general program and test_<name>.py in a resident one, with a name that
 * Python can import. A name that debasher_test does not run would hold a
 * test that never runs.
 */
export function testFileNameProblem(program: Program, fileName: string): string | null {
  if (program.programType === "resident") {
    return /^test_\w+\.py$/.test(fileName)
      ? null
      : "A node test is a file test_<name>.py, with letters, digits and underscores in <name>, which debasher_test runs with pytest.";
  }
  return /^[\w-][\w.-]*\.bats$/.test(fileName)
    ? null
    : "A process test is a file <name>.bats, with letters, digits, dots, dashes and underscores, which debasher_test runs with bats.";
}

// The path of a test file, relative to the home directory.
export function testFilePath(fileName: string): string {
  return `${TEST_DIR}/${fileName}`;
}

/**
 * What the test skeleton of `process` is, as "Add test" tells the user
 * before it writes it.
 */
export function testSkeletonSummary(program: Program, process: ProgramProcess): string {
  const what =
    program.programType !== "resident"
      ? `a process test (bats) that runs ${process.name} with placeholders for its options`
      : process.nodeKind === "DirectoryWatcher"
        ? `a node test (pytest) that builds ${process.name} and observes a directory for it to watch`
        : `a node test (pytest) that builds ${process.name}, feeds it a packet${observesOutside(process) ? " and observes" : ""}`;
  return (
    `Writes a first test for ${process.name}: ${what}. Its tests fail on purpose until you fill in its TODOs, ` +
    'real values and checks, and remove the line that makes them fail. "Run tests" runs it with the other ' +
    "tests of the program."
  );
}

export function testSkeleton(program: Program, process: ProgramProcess): string {
  return program.programType === "resident" ? nodeTestSkeleton(program, process) : processTestSkeleton(process);
}

function pythonName(name: string): string {
  return name.replace(/\W/g, "_");
}

// An option label without its leading dashes, as a port or a file is named.
function bareName(label: string): string {
  return label.replace(/^-+/, "");
}

// A description on one line, for a comment.
function oneLine(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

function optionComments(options: ProgramOption[], indent: string): string[] {
  return options.map(option => {
    const description = oneLine(option.description);
    return `${indent}#   ${option.label}${description ? `: ${description}` : ""}`;
  });
}

// The end of every test of a skeleton: a line that fails on purpose, with
// what to do about it
function failLines(failLine: string): string[] {
  return [
    "    # TODO: once the checks above are written, remove the line below,",
    "    # which makes a skeleton fail",
    `    ${failLine}`,
  ];
}

function processTestSkeleton(process: ProgramProcess): string {
  const flags = process.options.filter(option => option.direction === "input" && option.dataType === "None");
  const given = process.options.filter(option => !flags.includes(option));

  // Each option on a line of its own, joined with backslashes: a flag is
  // never one of them, since a line commented out in the middle would end
  // the command there
  const args = given.map(option =>
    option.direction === "output"
      ? `${option.label} "\${BATS_TEST_TMPDIR}/${bareName(option.label)}"`
      : `${option.label} TODO`
  );
  const command = [`    run debasher_process ${process.name}`, ...args.map(arg => `        ${arg}`)].join(" \\\n");

  const lines = [
    `# Process tests of ${process.name}, run with debasher_test`,
    "",
    'load "${DEBASHER_BATS_HELPERS}"',
    "",
    `@test "${process.name} does what it should" {`,
  ];
  if (process.options.length > 0) {
    lines.push(`    # Options of ${process.name}:`, ...optionComments(process.options, "    "));
  }
  if (flags.length > 0) {
    lines.push(`    # Flags, to add to the command if the test needs them: ${flags.map(flag => flag.label).join(" ")}`);
  }
  if (given.some(option => option.direction === "input")) {
    lines.push("    # TODO: replace each TODO value with the value of the test");
  }
  lines.push(
    command,
    '    [ "${status}" -eq 0 ]',
    "    # TODO: check what the process wrote",
    "",
    ...failLines("false"),
    "}",
    ""
  );
  return lines.join("\n");
}

function nodeTestSkeleton(program: Program, process: ProgramProcess): string {
  const inputs = process.options.filter(option => isNodeInput(program, process, option)).map(option => bareName(option.label));
  const outputs = process.options.filter(isBusinessOutput).map(option => bareName(option.label));
  const configuration = process.options.filter(option => nodeOptionRole(option) === "configuration");

  const name = pythonName(process.name);
  const loadCall = `load_node(${JSON.stringify(process.name)}, opts=opts, inputs=${pythonList(inputs)}, outputs=${pythonList(outputs)})`;
  const node: NodeSkeleton = {
    name,
    feed:
      inputs.length > 0
        ? ["    # TODO: the packet of the test", `    under_test.feed(${JSON.stringify(inputs[0])}, "TODO")`]
        : ["    # The node has no business input to feed"],
    sentCheck:
      outputs.length > 0
        ? [`    assert under_test.sent(${JSON.stringify(outputs[0])}) == ["TODO"]`]
        : ["    # The node has no business output to check"],
    fail: failLines('pytest.fail("write the checks of this test")'),
  };

  const lines = [
    `"""`,
    `Node tests of ${process.name}, run with debasher_test.`,
    `"""`,
    "",
    "import pytest",
    "",
    "from debasher_runtime_testing import load_node",
    "",
    "",
    "def node(opts=None):",
  ];
  if (configuration.length > 0) {
    lines.push("    # Configuration options that opts could give:", ...optionComments(configuration, "    "));
  }
  lines.push(`    return ${loadCall}`, "");

  const tests =
    process.nodeKind === "DirectoryWatcher"
      ? watcherTests(process, node)
      : [
          [
            `def test_${name}_sends_what_it_should():`,
            "    under_test = node()",
            ...node.feed,
            "    # TODO: what the node sent for it",
            ...node.sentCheck,
            ...node.fail,
          ],
          [
            `def test_${name}_goes_on_after_a_restart():`,
            "    under_test = node()",
            ...node.feed,
            "    under_test = under_test.restart()",
            ...node.feed,
            "    # TODO: what the restarted node sent, from the node state it got back",
            ...node.sentCheck,
            ...node.fail,
          ],
          ...(observesOutside(process) ? [observeTest(node)] : []),
        ];
  for (const test of tests) {
    lines.push("", ...test);
  }
  lines.push("");
  return lines.join("\n");
}

// What the tests of a node skeleton share: the Python name of the node and
// the lines that feed it, check what it sent and fail on purpose.
interface NodeSkeleton {
  name: string;
  feed: string[];
  sentCheck: string[];
  fail: string[];
}

// The test of what an FBPProcess that observes the outside world brings in:
// what observe() injects, and what process_data then sends.
function observeTest(node: NodeSkeleton): string[] {
  return [
    `def test_${node.name}_brings_in_what_it_observes():`,
    "    under_test = node()",
    "    # TODO: make the outside world show the node something to observe",
    "    injected = under_test.observe()",
    "    # TODO: what observe() brought in, and what the node sent for it",
    '    assert injected == ["TODO"]',
    ...node.sentCheck,
    ...node.fail,
  ];
}

// The tests of a DirectoryWatcher, which has no input to feed and is built
// with the directory it watches: what it brings in when a file arrives
// there, and that after a restart it requests no file twice.
function watcherTests(process: ProgramProcess, node: NodeSkeleton): string[][] {
  const hasWatchDirOption = process.options.some(option => option.label === WATCH_DIR_LABEL);
  const build = hasWatchDirOption
    ? `    under_test = node(opts={${JSON.stringify(bareName(WATCH_DIR_LABEL))}: str(tmp_path)})`
    : "    under_test = node()";
  const files = hasWatchDirOption
    ? ["    # TODO: write in tmp_path the files that the test needs", '    (tmp_path / "TODO").write_text("TODO")']
    : ["    # TODO: write in the directory that WATCH_DIR names the files that the test needs"];
  const signature = hasWatchDirOption ? "(tmp_path)" : "()";
  return [
    [
      `def test_${node.name}_brings_in_what_it_observes${signature}:`,
      build,
      ...files,
      "    # A file is complete once it stayed the same for STABLE_OBSERVATIONS",
      "    # observations in a row (two by default)",
      "    under_test.observe()",
      "    injected = under_test.observe()",
      "    # TODO: what observe() brought in, and what the node sent for it",
      '    assert injected == ["TODO"]',
      ...node.sentCheck,
      ...node.fail,
    ],
    [
      `def test_${node.name}_requests_nothing_twice_after_a_restart${signature}:`,
      build,
      ...files,
      "    under_test.observe()",
      "    under_test.observe()",
      "    under_test = under_test.restart()",
      "    under_test.observe()",
      "    under_test.observe()",
      "    # TODO: after a restart observe() brings the files in again, and",
      "    # process_data drops them: check what the node sent",
      ...node.sentCheck,
      ...node.fail,
    ],
  ];
}

function pythonList(names: string[]): string {
  return `[${names.map(name => JSON.stringify(name)).join(", ")}]`;
}

/**
 * Whether `option` is an input port of the node under test: an external
 * input, or an input that a connection feeds, which makes it a business
 * input. The Supervisor wiring is not in the program model, so no edge
 * stands for it.
 */
function isNodeInput(program: Program, process: ProgramProcess, option: ProgramOption): boolean {
  const role = nodeOptionRole(option);
  if (role === "externalInput") {
    return true;
  }
  return (
    role === "businessInput" &&
    program.edges.some(edge => edge.targetProcessId === process.id && edge.targetOptionId === option.id)
  );
}
