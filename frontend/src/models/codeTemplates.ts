import type { ProcessLanguage, ProgramProcess } from "./process";
import type { OptionDataType, ProgramOption } from "./option";
import { fanoutBaseLabel, isFanoutOption } from "./option";
import type { Program } from "./program";
import { receivesPath } from "./dataTypes";

// Comment text used to mark the point where the user is expected to
// write the process's actual logic. Also used, via isCodeStillTemplate,
// to decide whether existing code is still an unedited template (and
// thus safe to regenerate when the process's options change).
export const TEMPLATE_MARKER = "ADD YOUR CODE HERE";

// The first code of the editor of the code that prints the number of tasks
// of an option generator, which the code prompt takes as no code at all.
export const GENERATOR_SIZE_TEMPLATE = `# TODO: return the number of tasks
`;

export function isCodeStillTemplate(code: string): boolean {
  return code.trim() === "" || code.includes(TEMPLATE_MARKER);
}

// The type of the argument that the process receives for an option, which
// a template parses it as: its data type, unless what it receives is a path
// (a FIFO, a value descriptor or a directory), whose data type is that of
// what the path leads to (see receivesPath).
type ArgumentType = (option: ProgramOption) => OptionDataType;

function argumentTypeOf(program: Program, process: ProgramProcess): ArgumentType {
  return option => (receivesPath(program, process, option) ? "string" : option.dataType);
}

function toIdentifier(label: string): string {
  const stripped = label.replace(/^-+/, "").replace(/[^a-zA-Z0-9]+/g, "_");
  return stripped === "" || /^[0-9]/.test(stripped) ? `opt_${stripped}` : stripped;
}

function withIdentifiers(options: ProgramOption[]): [ProgramOption, string][] {
  return options.map(option => [option, toIdentifier(option.label)]);
}

// The options that a task of the process receives: all but its task
// shaping options, which only its options handler reads.
function taskOptionsOf(process: ProgramProcess): ProgramOption[] {
  return process.options.filter(o => !o.taskShaping);
}

// This process's fanout family options (see isFanoutOption) — only
// meaningful on a "standard"-mode process.
function fanoutOptionsOf(process: ProgramProcess): ProgramOption[] {
  return process.optionsHandler.mode === "standard"
    ? process.options.filter(o => isFanoutOption(o.label))
    : [];
}

// A fanout family as a template reads it: the engine passes "<base>0",
// "<base>1", ... (never the "-outf-ith" label itself). With a count source
// option, as many as its value, which the template has already read into
// the identifier countId; without one, as many as the tasks of the process
// at the other end of its connections (see _fanout_count_process in
// api/script_generation.py), a number that the task does not receive, so
// countId is null and the template counts the options of the family among
// its arguments.
interface FanoutRead {
  option: ProgramOption;
  baseLabel: string;
  id: string;
  countId: string | null;
}

function fanoutReads(process: ProgramProcess): FanoutRead[] {
  return fanoutOptionsOf(process).map(option => {
    const countSource = process.options.find(o => o.id === option.countSourceOptionId);
    const baseLabel = fanoutBaseLabel(option.label);
    return {
      option,
      baseLabel,
      id: toIdentifier(baseLabel),
      countId: countSource ? toIdentifier(countSource.label) : null,
    };
  });
}

// The identifier of the number of options of a family that a template
// counts among its arguments.
function argsCountId(read: FanoutRead): string {
  return `${read.id}_count`;
}

// Bash template lines for one fanout family option (see isFanoutOption):
// a runtime loop, driven by its count-source option's own identifier
// (already declared earlier in the template — fanout blocks are always
// emitted after all plain option reads, see generateBashTemplate), or by
// the number of options of the family found among the arguments, reading
// "<base-label>$i" for each i into an array.
function fanoutReadLines(read: FanoutRead): string[] {
  const lines: string[] = [];
  let countId = read.countId;
  if (countId === null) {
    countId = argsCountId(read);
    lines.push(
      `    local ${countId}=0`,
      `    while [ "$(read_opt_value_from_func_args "${read.baseLabel}\${${countId}}" "$@")" != "\${DEBASHER_OPT_NOT_FOUND}" ]; do`,
      `        ${countId}=$((${countId} + 1))`,
      `    done`,
    );
  }
  lines.push(
    `    local ${read.id}=()`,
    `    for ((i=0; i<${countId}; i++)); do`,
    `        ${read.id}+=($(read_opt_value_from_func_args "${read.baseLabel}\${i}" "$@"))`,
    `    done`,
  );
  return lines;
}

function generateBashTemplate(process: ProgramProcess): string {
  const lines: string[] = [`${process.name}()`, "{"];

  const fanoutOptions = fanoutOptionsOf(process);
  const plainOptions = taskOptionsOf(process).filter(o => !fanoutOptions.includes(o));
  const optionsWithIds = withIdentifiers(plainOptions);
  const reads = fanoutReads(process);

  if (optionsWithIds.length > 0 || reads.length > 0) {
    lines.push("    # Initialize variables");
    for (const [option, id] of optionsWithIds) {
      if (option.dataType === "None") {
        lines.push(`    local ${id}=0`);
        lines.push(`    if read_flag_from_func_args "${option.label}" "$@"; then`);
        lines.push(`        ${id}=1`);
        lines.push("    fi");
      } else {
        lines.push(`    local ${id}=$(read_opt_value_from_func_args "${option.label}" "$@")`);
        if (!option.mandatory) {
          lines.push(`    if [ "\${${id}}" = "\${DEBASHER_OPT_NOT_FOUND}" ]; then`);
          lines.push(`        ${id}=""`);
          lines.push("    fi");
        }
      }
    }
    for (const read of reads) {
      lines.push(...fanoutReadLines(read));
    }
    lines.push("");
  }

  lines.push(`    # ${TEMPLATE_MARKER}`);
  lines.push("}");

  return lines.join("\n");
}

function pythonArgparseType(dataType: OptionDataType): string {
  switch (dataType) {
    case "int":
      return "int";
    case "float":
      return "float";
    default:
      return "str";
  }
}

function pythonDefaultLiteral(dataType: OptionDataType): string {
  switch (dataType) {
    case "int":
    case "float":
      return "None";
    default:
      return "''";
  }
}

// The attribute under which argparse keeps the value of an option: its
// label without the leading dashes, and every other dash an underscore.
function pythonDest(label: string): string {
  return label.replace(/^-+/, "").replace(/-/g, "_");
}

function generatePythonTemplate(process: ProgramProcess, argumentType: ArgumentType): string {
  const fanoutOptions = fanoutOptionsOf(process);
  const plainOptions = taskOptionsOf(process).filter(o => !fanoutOptions.includes(o));
  const optionsWithIds = withIdentifiers(plainOptions);

  const lines: string[] = [
    "import argparse",
    "",
    "parser = argparse.ArgumentParser()",
  ];

  for (const [option] of optionsWithIds) {
    const help = JSON.stringify(option.description ?? "");
    if (option.dataType === "None") {
      lines.push(
        `parser.add_argument('${option.label}', action='store_true', help=${help})`
      );
    } else if (option.mandatory) {
      lines.push(
        `parser.add_argument('${option.label}', type=${pythonArgparseType(argumentType(option))}, required=True, help=${help})`
      );
    } else {
      lines.push(
        `parser.add_argument('${option.label}', type=${pythonArgparseType(argumentType(option))}, default=${pythonDefaultLiteral(argumentType(option))}, help=${help})`
      );
    }
  }

  const reads = fanoutReads(process);

  if (reads.length > 0) {
    // The options of a fanout family are known only once its count is,
    // so they are registered after a first parse of the others, which
    // leaves them among the unknown arguments, where a family without a
    // count source option is counted.
    const countsArgs = reads.some(read => read.countId === null);
    lines.push("", `args, ${countsArgs ? "unknown" : "_"} = parser.parse_known_args()`);
    for (const read of reads) {
      const help = JSON.stringify(read.option.description ?? "");
      let count = `int(args.${read.countId})`;
      if (read.countId === null) {
        count = argsCountId(read);
        lines.push(
          `${count} = sum(1 for arg in unknown if arg.startswith('${read.baseLabel}') and arg[${read.baseLabel.length}:].isdigit())`
        );
      }
      lines.push(`for i in range(${count}):`);
      lines.push(
        `    parser.add_argument(f'${read.baseLabel}{i}', type=${pythonArgparseType(argumentType(read.option))}, required=True, help=${help})`
      );
    }
  }

  lines.push("", "args = parser.parse_args()");

  if (optionsWithIds.length > 0 || reads.length > 0) {
    lines.push("");
    for (const [, id] of optionsWithIds) {
      lines.push(`${id} = args.${id}`);
    }
    for (const read of reads) {
      const count = read.countId === null ? argsCountId(read) : `int(${read.countId})`;
      lines.push(`${read.id} = [getattr(args, f'${pythonDest(read.baseLabel)}{i}') for i in range(${count})]`);
    }
  }

  lines.push("", `# ${TEMPLATE_MARKER}`);

  return lines.join("\n");
}

function getoptLongSuffix(dataType: OptionDataType): string {
  switch (dataType) {
    case "int":
      return "=i";
    case "float":
      return "=f";
    default:
      return "=s";
  }
}

function perlDefaultLiteral(dataType: OptionDataType): string {
  switch (dataType) {
    case "None":
      return "0";
    case "int":
    case "float":
      return "0";
    default:
      return '""';
  }
}

function generatePerlTemplate(process: ProgramProcess, argumentType: ArgumentType): string {
  const fanoutOptions = fanoutOptionsOf(process);
  const plainOptions = taskOptionsOf(process).filter(o => !fanoutOptions.includes(o));
  const optionsWithIds = withIdentifiers(plainOptions);

  const lines: string[] = [
    "use strict;",
    "use warnings;",
    "use Getopt::Long;",
  ];

  const reads = fanoutReads(process);

  if (optionsWithIds.length > 0 || reads.length > 0) {
    lines.push("");
    for (const [option, id] of optionsWithIds) {
      lines.push(`my $${id} = ${perlDefaultLiteral(argumentType(option))};`);
    }
    for (const read of reads) {
      lines.push(`my @${read.id};`);
    }

    lines.push("");
    if (optionsWithIds.length > 0) {
      if (reads.length > 0) {
        // The options of a fanout family are known only once its count
        // is: the first parse leaves them in @ARGV for the second.
        lines.push('Getopt::Long::Configure("pass_through");');
      }
      const specs = optionsWithIds.map(([option, id]) => {
        const flagName = option.label.replace(/^-+/, "");
        const suffix = option.dataType === "None" ? "" : getoptLongSuffix(argumentType(option));
        return `"${flagName}${suffix}" => \\$${id}`;
      });
      lines.push(`GetOptions(${specs.join(", ")})`);
      lines.push('    or die "Error in command line arguments\\n";');
    }

    if (reads.length > 0) {
      if (optionsWithIds.length > 0) {
        lines.push('Getopt::Long::Configure("no_pass_through");');
      }
      // A family without a count source option is counted among the
      // arguments that are left
      for (const read of reads.filter(read => read.countId === null)) {
        const flagName = read.baseLabel.replace(/^-+/, "");
        lines.push(`my $${argsCountId(read)} = grep { /^--?\\Q${flagName}\\E[0-9]+$/ } @ARGV;`);
      }
      const fanoutSpecs = reads.map(read => {
        const flagName = read.baseLabel.replace(/^-+/, "");
        const suffix = getoptLongSuffix(argumentType(read.option));
        return `(map { my $i = $_; ("${flagName}$i${suffix}" => \\$${read.id}[$i]) } 0 .. $${read.countId ?? argsCountId(read)} - 1)`;
      });
      lines.push(`GetOptions(${fanoutSpecs.join(", ")})`);
      lines.push('    or die "Error in command line arguments\\n";');
    }
  }

  lines.push("", `# ${TEMPLATE_MARKER}`);

  return lines.join("\n");
}

function generateRTemplate(process: ProgramProcess): string {
  const fanoutOptions = fanoutOptionsOf(process);
  const plainOptions = taskOptionsOf(process).filter(o => !fanoutOptions.includes(o));
  const optionsWithIds = withIdentifiers(plainOptions);

  const lines: string[] = ["args <- commandArgs(trailingOnly = TRUE)"];

  // The values of a fanout family are kept by label, and taken in order
  // once the count is known: that of its count source option, or, without
  // one, the number of values kept.
  const reads = fanoutReads(process);

  if (optionsWithIds.length > 0 || reads.length > 0) {
    lines.push("", "parse_args <- function(args) {");

    const defaults = [
      ...optionsWithIds.map(([option, id]) => `${id} = ${option.dataType === "None" ? "FALSE" : '""'}`),
      ...reads.map(read => `${read.id} = list()`),
    ].join(", ");
    lines.push(`  options <- list(${defaults})`);

    lines.push("  i <- 1", "  while (i <= length(args)) {");
    optionsWithIds.forEach(([option, id], index) => {
      const branch = index === 0 ? "if" : "} else if";
      if (option.dataType === "None") {
        lines.push(`    ${branch} (args[i] == "${option.label}") {`);
        lines.push(`      options$${id} <- TRUE`);
      } else {
        lines.push(`    ${branch} (args[i] == "${option.label}") {`);
        lines.push(`      options$${id} <- args[i + 1]`);
        lines.push("      i <- i + 1");
      }
    });
    reads.forEach((read, index) => {
      const branch = optionsWithIds.length + index === 0 ? "if" : "} else if";
      lines.push(`    ${branch} (startsWith(args[i], "${read.baseLabel}") && grepl("^[0-9]+$", substring(args[i], ${read.baseLabel.length + 1}))) {`);
      lines.push(`      options$${read.id}[[args[i]]] <- args[i + 1]`);
      lines.push("      i <- i + 1");
    });
    lines.push("    }", "    i <- i + 1", "  }", "  return(options)", "}");

    lines.push("", "options <- parse_args(args)", "");
    for (const [, id] of optionsWithIds) {
      lines.push(`${id} <- options$${id}`);
    }
    for (const read of reads) {
      const count = read.countId === null ? `length(options$${read.id})` : `as.integer(${read.countId})`;
      lines.push(`${read.id} <- unlist(lapply(seq_len(${count}) - 1, function(k) options$${read.id}[[paste0("${read.baseLabel}", k)]]))`);
    }
  }

  lines.push("", `# ${TEMPLATE_MARKER}`);

  return lines.join("\n");
}

function generateGroovyTemplate(process: ProgramProcess): string {
  const fanoutOptions = fanoutOptionsOf(process);
  const plainOptions = taskOptionsOf(process).filter(o => !fanoutOptions.includes(o));
  const optionsWithIds = withIdentifiers(plainOptions);

  const lines: string[] = [];

  // As in R: the values of a fanout family are kept by label and taken in
  // order once the count is known.
  const reads = fanoutReads(process);

  if (optionsWithIds.length > 0 || reads.length > 0) {
    lines.push("def parseArgs(args) {");

    const defaults = [
      ...optionsWithIds.map(([option, id]) => `${id}: ${option.dataType === "None" ? "false" : "''"}`),
      ...reads.map(read => `${read.id}: [:]`),
    ].join(", ");
    lines.push(`    def options = [${defaults}]`, "", "    def i = 0");
    lines.push("    while (i < args.size()) {");
    optionsWithIds.forEach(([option, id], index) => {
      const branch = index === 0 ? "if" : "} else if";
      if (option.dataType === "None") {
        lines.push(`        ${branch} (args[i] == '${option.label}') {`);
        lines.push(`            options.${id} = true`);
      } else {
        lines.push(`        ${branch} (args[i] == '${option.label}' && i + 1 < args.size()) {`);
        lines.push(`            options.${id} = args[i + 1]`);
        lines.push("            i++");
      }
    });
    reads.forEach((read, index) => {
      const branch = optionsWithIds.length + index === 0 ? "if" : "} else if";
      lines.push(`        ${branch} (args[i].startsWith('${read.baseLabel}') && args[i].substring(${read.baseLabel.length}).isInteger() && i + 1 < args.size()) {`);
      lines.push(`            options.${read.id}[args[i]] = args[i + 1]`);
      lines.push("            i++");
    });
    lines.push("        }", "        i++", "    }", "", "    return options", "}");

    lines.push("", "def options = parseArgs(this.args)", "");
    for (const [, id] of optionsWithIds) {
      lines.push(`def ${id} = options.${id}`);
    }
    for (const read of reads) {
      const count = read.countId === null ? `options.${read.id}.size()` : `(${read.countId} as String).toInteger()`;
      lines.push(`def ${read.id} = (0..<${count}).collect { options.${read.id}['${read.baseLabel}' + it] }`);
    }
  }

  lines.push("", `// ${TEMPLATE_MARKER}`);

  return lines.join("\n");
}

// The first code of a process of `program`, which reads its options: the
// program tells what reaches the process through its connections.
export function generateCodeTemplate(program: Program, process: ProgramProcess): string {
  switch (process.language) {
    case "python":
      return generatePythonTemplate(process, argumentTypeOf(program, process));
    case "perl":
      return generatePerlTemplate(process, argumentTypeOf(program, process));
    case "r":
      return generateRTemplate(process);
    case "groovy":
      return generateGroovyTemplate(process);
    case "bash":
    default:
      return generateBashTemplate(process);
  }
}

// The name of each language as a code prompt writes it, and the tag of a
// fenced code block of that language.
export const LANGUAGE_NAMES: Record<ProcessLanguage, string> = {
  bash: "Bash",
  python: "Python",
  perl: "Perl",
  r: "R",
  groovy: "Groovy",
};

// The interpreter that the engine runs the code of a language with, and
// the option that hands it the code (DEBASHER_HEREDOC_INTERPRETERS and
// DEBASHER_HEREDOC_INTERPRETER_OPTS in engine/debasher_lib.sh).
const INTERPRETERS: Record<Exclude<ProcessLanguage, "bash">, string> = {
  python: "python3 -c",
  perl: "perl -e",
  r: "Rscript -e",
  groovy: "groovy -e",
};

// The language rules of a code prompt: how the engine runs the code of a
// process of the language, and how the templates above read its options,
// so that a change to either is made here, beside them.
export function languageRules(language: ProcessLanguage, processName: string): string[] {
  const own =
    language === "bash"
      ? [
          `- The process is a Bash function named \`${processName}\`, which the engine calls with the option list of a task as its arguments: each option as its label followed by its value, and a flag as its label alone.`,
          '- Read the value of an option with `read_opt_value_from_func_args "<label>" "$@"`, which prints `${DEBASHER_OPT_NOT_FOUND}` when the option is not given, and test a flag with `read_flag_from_func_args "<label>" "$@"`.',
          "- Declare the variables of the function with `local`, and end it with `return 0` on success and another status on failure.",
        ]
      : [
          `- The process is a whole ${LANGUAGE_NAMES[language]} program, which the engine runs with \`${INTERPRETERS[language]}\` and the option list of a task as its command line arguments: each option as its label followed by its value, and a flag as its label alone.`,
          "- The generated module holds the code in a Bash here-document that ends with a line `EOF`, so no line of the code may be `EOF` alone.",
          "- The program ends with exit status 0 on success and another status on failure.",
        ];
  return [
    ...own,
    "- The value of an output option names where the process writes what it produces: a file, a directory or a FIFO. The process writes there: what it prints to its standard output goes to a file of the task that no other process reads.",
    "- A FIFO is read until its end. An output FIFO is closed once everything is written, since only then does its reader see the end; a process at the other end of a FIFO runs at the same time.",
  ];
}
