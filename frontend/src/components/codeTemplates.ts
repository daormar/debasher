import type { ProgramProcess } from "../models/process";
import type { OptionDataType, ProgramOption } from "../models/option";
import { fanoutBaseLabel, isFanoutOption } from "../models/option";

// Comment text used to mark the point where the user is expected to
// write the process's actual logic. Also used, via isCodeStillTemplate,
// to decide whether existing code is still an unedited template (and
// thus safe to regenerate when the process's options change).
export const TEMPLATE_MARKER = "ADD YOUR CODE HERE";

export function isCodeStillTemplate(code: string): boolean {
  return code.trim() === "" || code.includes(TEMPLATE_MARKER);
}

function toIdentifier(label: string): string {
  const stripped = label.replace(/^-+/, "").replace(/[^a-zA-Z0-9]+/g, "_");
  return stripped === "" || /^[0-9]/.test(stripped) ? `opt_${stripped}` : stripped;
}

function withIdentifiers(options: ProgramOption[]): [ProgramOption, string][] {
  return options.map(option => [option, toIdentifier(option.label)]);
}

// This process's fanout family options (see isFanoutOption) — only
// meaningful on a "standard"-mode process.
function fanoutOptionsOf(process: ProgramProcess): ProgramOption[] {
  return process.optionsHandler.mode === "standard"
    ? process.options.filter(o => isFanoutOption(o.label))
    : [];
}

// A fanout family as a template reads it: the engine passes "<base>0", "<base>1", ... (never the "-outfith"
// label itself), as many as the value of the count source option, which
// the template has already read into the identifier countId. Null when
// the family has no count source configured yet.
interface FanoutRead {
  option: ProgramOption;
  baseLabel: string;
  id: string;
  countId: string;
}

function fanoutRead(process: ProgramProcess, option: ProgramOption): FanoutRead | null {
  const countSource = process.options.find(o => o.id === option.countSourceOptionId);
  if (!countSource) {
    return null;
  }
  const baseLabel = fanoutBaseLabel(option.label);
  return { option, baseLabel, id: toIdentifier(baseLabel), countId: toIdentifier(countSource.label) };
}

// The fanout families of a process that a template can read, and a TODO
// comment for each one that it cannot.
function fanoutReads(process: ProgramProcess, commentPrefix: string): { reads: FanoutRead[]; todoLines: string[] } {
  const reads: FanoutRead[] = [];
  const todoLines: string[] = [];
  for (const option of fanoutOptionsOf(process)) {
    const read = fanoutRead(process, option);
    if (read) {
      reads.push(read);
    } else {
      todoLines.push(`${commentPrefix} TODO: fanout option "${option.label}" has no count source configured yet`);
    }
  }
  return { reads, todoLines };
}

// Bash template lines for one fanout family option (see isFanoutOption):
// a runtime loop, driven by its count-source option's own identifier
// (already declared earlier in the template — fanout blocks are always
// emitted after all plain option reads, see generateBashTemplate),
// reading "<base-label>$i" for each i into an array.
function fanoutReadLines(process: ProgramProcess, option: ProgramOption): string[] {
  const read = fanoutRead(process, option);
  if (!read) {
    return [`    # TODO: fanout option "${option.label}" has no count source configured yet`];
  }

  return [
    `    local ${read.id}=()`,
    `    for ((i=0; i<${read.countId}; i++)); do`,
    `        ${read.id}+=($(read_opt_value_from_func_args "${read.baseLabel}\${i}" "$@"))`,
    `    done`,
  ];
}

function generateBashTemplate(process: ProgramProcess): string {
  const lines: string[] = [`${process.name}()`, "{"];

  const fanoutOptions = fanoutOptionsOf(process);
  const plainOptions = process.options.filter(o => !fanoutOptions.includes(o));
  const optionsWithIds = withIdentifiers(plainOptions);

  if (optionsWithIds.length > 0 || fanoutOptions.length > 0) {
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
    for (const fanoutOption of fanoutOptions) {
      lines.push(...fanoutReadLines(process, fanoutOption));
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

function generatePythonTemplate(process: ProgramProcess): string {
  const fanoutOptions = fanoutOptionsOf(process);
  const plainOptions = process.options.filter(o => !fanoutOptions.includes(o));
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
        `parser.add_argument('${option.label}', type=${pythonArgparseType(option.dataType)}, required=True, help=${help})`
      );
    } else {
      lines.push(
        `parser.add_argument('${option.label}', type=${pythonArgparseType(option.dataType)}, default=${pythonDefaultLiteral(option.dataType)}, help=${help})`
      );
    }
  }

  const { reads, todoLines } = fanoutReads(process, "#");

  if (reads.length > 0) {
    // The options of a fanout family are known only once its count is,
    // so they are registered after a first parse of the others.
    lines.push("", "args, _ = parser.parse_known_args()");
    for (const read of reads) {
      const help = JSON.stringify(read.option.description ?? "");
      lines.push(`for i in range(int(args.${read.countId})):`);
      lines.push(
        `    parser.add_argument(f'${read.baseLabel}{i}', type=${pythonArgparseType(read.option.dataType)}, required=True, help=${help})`
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
      lines.push(`${read.id} = [getattr(args, f'${pythonDest(read.baseLabel)}{i}') for i in range(int(${read.countId}))]`);
    }
  }

  lines.push(...todoLines);

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

function generatePerlTemplate(process: ProgramProcess): string {
  const fanoutOptions = fanoutOptionsOf(process);
  const plainOptions = process.options.filter(o => !fanoutOptions.includes(o));
  const optionsWithIds = withIdentifiers(plainOptions);

  const lines: string[] = [
    "use strict;",
    "use warnings;",
    "use Getopt::Long;",
  ];

  // A fanout family always has a count source among the other options,
  // so there is something to parse whenever there is a family to read.
  const { reads, todoLines } = fanoutReads(process, "#");

  if (optionsWithIds.length > 0) {
    lines.push("");
    for (const [option, id] of optionsWithIds) {
      lines.push(`my $${id} = ${perlDefaultLiteral(option.dataType)};`);
    }
    for (const read of reads) {
      lines.push(`my @${read.id};`);
    }

    lines.push("");
    if (reads.length > 0) {
      // The options of a fanout family are known only once its count is:
      // the first parse leaves them in @ARGV for the second.
      lines.push('Getopt::Long::Configure("pass_through");');
    }
    const specs = optionsWithIds.map(([option, id]) => {
      const flagName = option.label.replace(/^-+/, "");
      const suffix = option.dataType === "None" ? "" : getoptLongSuffix(option.dataType);
      return `"${flagName}${suffix}" => \\$${id}`;
    });
    lines.push(`GetOptions(${specs.join(", ")})`);
    lines.push('    or die "Error in command line arguments\\n";');

    if (reads.length > 0) {
      lines.push('Getopt::Long::Configure("no_pass_through");');
      const fanoutSpecs = reads.map(read => {
        const flagName = read.baseLabel.replace(/^-+/, "");
        const suffix = getoptLongSuffix(read.option.dataType);
        return `(map { my $i = $_; ("${flagName}$i${suffix}" => \\$${read.id}[$i]) } 0 .. $${read.countId} - 1)`;
      });
      lines.push(`GetOptions(${fanoutSpecs.join(", ")})`);
      lines.push('    or die "Error in command line arguments\\n";');
    }
  }

  lines.push(...todoLines);

  lines.push("", `# ${TEMPLATE_MARKER}`);

  return lines.join("\n");
}

function generateRTemplate(process: ProgramProcess): string {
  const fanoutOptions = fanoutOptionsOf(process);
  const plainOptions = process.options.filter(o => !fanoutOptions.includes(o));
  const optionsWithIds = withIdentifiers(plainOptions);

  const lines: string[] = ["args <- commandArgs(trailingOnly = TRUE)"];

  // A fanout family always has a count source among the other options,
  // so there is a parser whenever there is a family to read. Its values
  // are kept by label, and taken in order once the count is known.
  const { reads, todoLines } = fanoutReads(process, "#");

  if (optionsWithIds.length > 0) {
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
    for (const read of reads) {
      lines.push(`    } else if (startsWith(args[i], "${read.baseLabel}") && grepl("^[0-9]+$", substring(args[i], ${read.baseLabel.length + 1}))) {`);
      lines.push(`      options$${read.id}[[args[i]]] <- args[i + 1]`);
      lines.push("      i <- i + 1");
    }
    lines.push("    }", "    i <- i + 1", "  }", "  return(options)", "}");

    lines.push("", "options <- parse_args(args)", "");
    for (const [, id] of optionsWithIds) {
      lines.push(`${id} <- options$${id}`);
    }
    for (const read of reads) {
      lines.push(`${read.id} <- unlist(lapply(seq_len(as.integer(${read.countId})) - 1, function(k) options$${read.id}[[paste0("${read.baseLabel}", k)]]))`);
    }
  }

  lines.push(...todoLines);

  lines.push("", `# ${TEMPLATE_MARKER}`);

  return lines.join("\n");
}

function generateGroovyTemplate(process: ProgramProcess): string {
  const fanoutOptions = fanoutOptionsOf(process);
  const plainOptions = process.options.filter(o => !fanoutOptions.includes(o));
  const optionsWithIds = withIdentifiers(plainOptions);

  const lines: string[] = [];

  // As in R: a parser whenever there is a family to read, whose values
  // are kept by label and taken in order once the count is known.
  const { reads, todoLines } = fanoutReads(process, "//");

  if (optionsWithIds.length > 0) {
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
    for (const read of reads) {
      lines.push(`        } else if (args[i].startsWith('${read.baseLabel}') && args[i].substring(${read.baseLabel.length}).isInteger() && i + 1 < args.size()) {`);
      lines.push(`            options.${read.id}[args[i]] = args[i + 1]`);
      lines.push("            i++");
    }
    lines.push("        }", "        i++", "    }", "", "    return options", "}");

    lines.push("", "def options = parseArgs(this.args)", "");
    for (const [, id] of optionsWithIds) {
      lines.push(`def ${id} = options.${id}`);
    }
    for (const read of reads) {
      lines.push(`def ${read.id} = (0..<(${read.countId} as String).toInteger()).collect { options.${read.id}['${read.baseLabel}' + it] }`);
    }
  }

  lines.push(...todoLines);

  lines.push("", `// ${TEMPLATE_MARKER}`);

  return lines.join("\n");
}

export function generateCodeTemplate(process: ProgramProcess): string {
  switch (process.language) {
    case "python":
      return generatePythonTemplate(process);
    case "perl":
      return generatePerlTemplate(process);
    case "r":
      return generateRTemplate(process);
    case "groovy":
      return generateGroovyTemplate(process);
    case "bash":
    default:
      return generateBashTemplate(process);
  }
}
