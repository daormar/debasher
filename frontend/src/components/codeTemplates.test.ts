import { describe, expect, it } from "vitest";
import { createOption } from "../models/option";
import type { ProgramOption } from "../models/option";
import type { ProcessLanguage, ProgramProcess } from "../models/process";
import { TEMPLATE_MARKER, generateCodeTemplate } from "./codeTemplates";

function process(language: ProcessLanguage, options: ProgramOption[]): ProgramProcess {
  return { id: "p", name: "dispatch", language, options, optionsHandler: { mode: "standard" } } as unknown as ProgramProcess;
}

// dispatch of debasher_dynamic_fanout_fifos: one output per worker, as
// many as -w says
const fanoutOptions = [
  createOption("w", "-w", { dataType: "int", commandLine: true, mandatory: true }),
  createOption("v", "-v", { dataType: "None" }),
  createOption("outf", "-outfith", { direction: "output", dataType: "file", countSourceOptionId: "w" }),
];

describe("generateCodeTemplate with a fanout family", () => {
  // What each language reads the family with: never the "-outfith" label
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
      const template = generateCodeTemplate(process(language, fanoutOptions));
      for (const line of lines) {
        expect(template).toContain(line);
      }
      expect(template).not.toContain("-outfith");
      expect(template).not.toContain("TODO");
      expect(template).toContain(TEMPLATE_MARKER);
    });

    it(`marks a family without a count source with a TODO in ${language}`, () => {
      const options = fanoutOptions.map(o => (o.id === "outf" ? { ...o, countSourceOptionId: undefined } : o));
      const template = generateCodeTemplate(process(language, options));
      expect(template).toContain('TODO: fanout option "-outfith" has no count source configured yet');
      expect(template).not.toContain("-outf0");
    });
  }
});
