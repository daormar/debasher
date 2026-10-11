import { describe, expect, it } from "vitest";
import { createOption } from "./option";
import type { ProgramOption } from "./option";
import type { ProcessLanguage, ProgramProcess } from "./process";
import type { Program } from "./program";
import { TEMPLATE_MARKER, generateCodeTemplate } from "./codeTemplates";

function process(language: ProcessLanguage, options: ProgramOption[]): ProgramProcess {
  return { id: "p", name: "dispatch", language, options, optionsHandler: { mode: "standard" } } as unknown as ProgramProcess;
}

// The template of a process alone in its program, with no connection.
function templateOf(p: ProgramProcess): string {
  return generateCodeTemplate({ processes: [p], edges: [] } as unknown as Program, p);
}

// dispatch of debasher_dynamic_fanout_fifos: one output per worker, as
// many as -w says
const fanoutOptions = [
  createOption("w", "-w", { dataType: "int", commandLine: true, mandatory: true }),
  createOption("v", "-v", { dataType: "None" }),
  createOption("outf", "-outf-ith", { direction: "output", dataType: "file", countSourceOptionId: "w" }),
];

describe("generateCodeTemplate with a fanout family", () => {
  // What each language reads the family with: never the "-outf-ith" label
  // itself, always "-outf<i>" for each i below the count.
  const reads: Record<ProcessLanguage, string[]> = {
    bash: [
      "local outf=()",
      "for ((i=0; i<w; i++)); do",
      'outf+=($(read_opt_value_from_func_args "-outf${i}" "$@"))',
    ],
    python: [
      "args, _ = parser.parse_known_args()",
      "for i in range(int(args.w)):",
      "parser.add_argument(f'-outf{i}', type=str, required=True",
      "outf = [getattr(args, f'outf{i}') for i in range(int(w))]",
    ],
    perl: [
      "my @outf;",
      'Getopt::Long::Configure("pass_through");',
      'Getopt::Long::Configure("no_pass_through");',
      'GetOptions((map { my $i = $_; ("outf$i=s" => \\$outf[$i]) } 0 .. $w - 1))',
    ],
    r: [
      "outf = list()",
      '} else if (startsWith(args[i], "-outf") && grepl("^[0-9]+$", substring(args[i], 6))) {',
      "options$outf[[args[i]]] <- args[i + 1]",
      'outf <- unlist(lapply(seq_len(as.integer(w)) - 1, function(k) options$outf[[paste0("-outf", k)]]))',
    ],
    groovy: [
      "outf: [:]",
      "} else if (args[i].startsWith('-outf') && args[i].substring(5).isInteger() && i + 1 < args.size()) {",
      "options.outf[args[i]] = args[i + 1]",
      "def outf = (0..<(w as String).toInteger()).collect { options.outf['-outf' + it] }",
    ],
  };

  for (const [language, lines] of Object.entries(reads) as [ProcessLanguage, string[]][]) {
    it(`reads the family in ${language}`, () => {
      const template = templateOf(process(language, fanoutOptions));
      for (const line of lines) {
        expect(template).toContain(line);
      }
      expect(template).not.toContain("-outf-ith");
      expect(template).not.toContain("TODO");
      expect(template).toContain(TEMPLATE_MARKER);
    });

    it(`marks a family without a count source with a TODO in ${language}`, () => {
      const options = fanoutOptions.map(o => (o.id === "outf" ? { ...o, countSourceOptionId: undefined } : o));
      const template = templateOf(process(language, options));
      expect(template).toContain('TODO: fanout option "-outf-ith" has no count source configured yet');
      expect(template).not.toContain("-outf0");
    });
  }
});

describe("generateCodeTemplate with a task shaping option", () => {
  const options = [
    createOption("w", "-w", { dataType: "int", commandLine: true, mandatory: true, taskShaping: true }),
    createOption("inf", "-inf", { dataType: "file" }),
  ];

  for (const language of ["bash", "python", "perl", "r", "groovy"] as ProcessLanguage[]) {
    it(`does not read an option that no task receives in ${language}`, () => {
      const template = templateOf(process(language, options));
      expect(template).toMatch(/inf/);
      expect(template).not.toMatch(/\bw\b/);
    });
  }
});


describe("generateCodeTemplate with an option that receives a path", () => {
  // A counter that writes ints into a FIFO, and an adder that reads them
  // through a connection: each line is an int, but what the adder receives
  // is the path of the FIFO
  const counter = {
    ...process("python", [createOption("outf", "-outf", { dataType: "int", channel: "fifo" })]),
    id: "c",
    name: "counter",
  } as ProgramProcess;

  function adder(language: ProcessLanguage): ProgramProcess {
    return {
      ...process(language, [
        createOption("inf", "-inf", { dataType: "int" }),
        createOption("n", "-n", { dataType: "int" }),
      ]),
      id: "a",
      name: "adder",
    } as ProgramProcess;
  }

  function connectedTemplate(language: ProcessLanguage): string {
    const p = adder(language);
    const program = {
      processes: [counter, p],
      edges: [{ id: "e", sourceProcessId: "c", sourceOptionId: "outf", targetProcessId: "a", targetOptionId: "inf" }],
    } as unknown as Program;
    return generateCodeTemplate(program, p);
  }

  it("parses the path of a FIFO as a string, and a direct value as its data type, in python", () => {
    expect(templateOf(counter)).toContain("parser.add_argument('-outf', type=str");
    const template = connectedTemplate("python");
    expect(template).toContain("parser.add_argument('-inf', type=str");
    expect(template).toContain("parser.add_argument('-n', type=int");
  });

  it("parses the path of a FIFO as a string, and a direct value as its data type, in perl", () => {
    const template = connectedTemplate("perl");
    expect(template).toContain('"inf=s" => \\$inf');
    expect(template).toContain('"n=i" => \\$n');
  });
});
