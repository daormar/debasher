import { isBusinessOutput, nodeOptionRole } from "./node";
import type { ProgramOption } from "./option";
import type { ProgramProcess } from "./process";
import type { Program } from "./program";

/**
 * The test skeleton that "Add test" writes for a process (see "Adding a
 * test" in doc/design_doc_webui.md): a process test, run with bats, for a
 * process of a general program, and a node test, run with pytest, for a
 * node whose node kind is FBPProcess. The MCP server writes the same one.
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
 * that is when its node kind is FBPProcess.
 */
export function offersAddTest(program: Program, process: ProgramProcess): boolean {
  return program.programType !== "resident" || process.nodeKind === "FBPProcess";
}

/**
 * The path of the test skeleton of `process`, relative to the home
 * directory: test/<process>.bats, or test/test_<process>.py with every
 * dot of a qualified name turned into an underscore, since pytest imports
 * a test file as a module, and a dot would make its name a package path.
 */
export function testFilePath(program: Program, process: ProgramProcess): string {
  if (program.programType === "resident") {
    return `${TEST_DIR}/test_${pythonName(process.name)}.py`;
  }
  return `${TEST_DIR}/${process.name}.bats`;
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

const FAIL_COMMENT = "Write the checks of this test, then remove the line below, which makes a skeleton fail";

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
  lines.push(
    command,
    '    [ "${status}" -eq 0 ]',
    "",
    `    # ${FAIL_COMMENT}`,
    "    false",
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
  const loadCall = `load_node(${JSON.stringify(process.name)}, inputs=${pythonList(inputs)}, outputs=${pythonList(outputs)})`;
  const feed = inputs.length > 0 ? `    under_test.feed(${JSON.stringify(inputs[0])}, "TODO")` : "    # The node has no business input to feed";
  const check = outputs.length > 0 ? `    assert under_test.sent(${JSON.stringify(outputs[0])}) == ["TODO"]` : "    # The node has no business output to check";
  const fail = [`    # ${FAIL_COMMENT}`, '    pytest.fail("write the checks of this test")'];

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
    "def node():",
  ];
  if (configuration.length > 0) {
    lines.push("    # Configuration options that opts could give:", ...optionComments(configuration, "    "));
  }
  lines.push(
    `    return ${loadCall}`,
    "",
    "",
    `def test_${name}_sends_what_it_should():`,
    "    under_test = node()",
    feed,
    check,
    ...fail,
    "",
    "",
    `def test_${name}_goes_on_after_a_restart():`,
    "    under_test = node()",
    feed,
    "    under_test = under_test.restart()",
    feed,
    check,
    ...fail,
    ""
  );
  return lines.join("\n");
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
