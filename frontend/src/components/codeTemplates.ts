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

// Only generateBashTemplate (see fanoutReadLines) knows how to read a
// fanout option's dynamic-count family — the other languages' templates
// just flag it with a TODO comment instead of registering a bogus
// single flag (e.g. python's argparse would otherwise register
// "-outfith" itself, which is never a real command-line flag; the real
// ones are "-outf0", "-outf1", ...).
function fanoutTodoLines(fanoutOptions: ProgramOption[], commentPrefix: string): string[] {
  return fanoutOptions.map(option => {
    const base = fanoutBaseLabel(option.label);
    return `${commentPrefix} TODO: fanout option "${option.label}" isn't auto-handled for this language yet — read "${base}0".."${base}<N-1>" manually.`;
  });
}

// Bash template lines for one fanout family option (see isFanoutOption):
// a runtime loop, driven by its count-source option's own identifier
// (already declared earlier in the template — fanout blocks are always
// emitted after all plain option reads, see generateBashTemplate),
// reading "<base-label>$i" for each i into an array.
function fanoutReadLines(process: ProgramProcess, option: ProgramOption): string[] {
  const baseLabel = fanoutBaseLabel(option.label);
  const arrId = toIdentifier(baseLabel);

  const countSource = process.options.find(o => o.id === option.countSourceOptionId);
  if (!countSource) {
    return [`    # TODO: fanout option "${option.label}" has no count source configured yet`];
  }

  const countId = toIdentifier(countSource.label);

  return [
    `    local ${arrId}=()`,
    `    for ((i=0; i<${countId}; i++)); do`,
    `        ${arrId}+=($(read_opt_value_from_func_args "${baseLabel}\${i}" "$@"))`,
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

  lines.push("", "args = parser.parse_args()");

  if (optionsWithIds.length > 0) {
    lines.push("");
    for (const [, id] of optionsWithIds) {
      lines.push(`${id} = args.${id}`);
    }
  }

  lines.push(...fanoutTodoLines(fanoutOptions, "#"));

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

  if (optionsWithIds.length > 0) {
    lines.push("");
    for (const [option, id] of optionsWithIds) {
      lines.push(`my $${id} = ${perlDefaultLiteral(option.dataType)};`);
    }

    lines.push("");
    const specs = optionsWithIds.map(([option, id]) => {
      const flagName = option.label.replace(/^-+/, "");
      const suffix = option.dataType === "None" ? "" : getoptLongSuffix(option.dataType);
      return `"${flagName}${suffix}" => \\$${id}`;
    });
    lines.push(`GetOptions(${specs.join(", ")})`);
    lines.push('    or die "Error in command line arguments\\n";');
  }

  lines.push(...fanoutTodoLines(fanoutOptions, "#"));

  lines.push("", `# ${TEMPLATE_MARKER}`);

  return lines.join("\n");
}

function generateRTemplate(process: ProgramProcess): string {
  const fanoutOptions = fanoutOptionsOf(process);
  const plainOptions = process.options.filter(o => !fanoutOptions.includes(o));
  const optionsWithIds = withIdentifiers(plainOptions);

  const lines: string[] = ["args <- commandArgs(trailingOnly = TRUE)"];

  if (optionsWithIds.length > 0) {
    lines.push("", "parse_args <- function(args) {");

    const defaults = optionsWithIds
      .map(([option, id]) => `${id} = ${option.dataType === "None" ? "FALSE" : '""'}`)
      .join(", ");
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
    lines.push("    }", "    i <- i + 1", "  }", "  return(options)", "}");

    lines.push("", "options <- parse_args(args)", "");
    for (const [, id] of optionsWithIds) {
      lines.push(`${id} <- options$${id}`);
    }
  }

  lines.push(...fanoutTodoLines(fanoutOptions, "#"));

  lines.push("", `# ${TEMPLATE_MARKER}`);

  return lines.join("\n");
}

function generateGroovyTemplate(process: ProgramProcess): string {
  const fanoutOptions = fanoutOptionsOf(process);
  const plainOptions = process.options.filter(o => !fanoutOptions.includes(o));
  const optionsWithIds = withIdentifiers(plainOptions);

  const lines: string[] = [];

  if (optionsWithIds.length > 0) {
    lines.push("def parseArgs(args) {");

    const defaults = optionsWithIds
      .map(([option, id]) => `${id}: ${option.dataType === "None" ? "false" : "''"}`)
      .join(", ");
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
    lines.push("        }", "        i++", "    }", "", "    return options", "}");

    lines.push("", "def options = parseArgs(this.args)", "");
    for (const [, id] of optionsWithIds) {
      lines.push(`def ${id} = options.${id}`);
    }
  }

  lines.push(...fanoutTodoLines(fanoutOptions, "//"));

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
