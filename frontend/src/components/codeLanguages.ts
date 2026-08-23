import type { Extension } from "@codemirror/state";
import { StreamLanguage } from "@codemirror/language";
import { python } from "@codemirror/lang-python";
import { shell } from "@codemirror/legacy-modes/mode/shell";
import { perl } from "@codemirror/legacy-modes/mode/perl";
import { r } from "@codemirror/legacy-modes/mode/r";
import { groovy } from "@codemirror/legacy-modes/mode/groovy";

import type { ProcessLanguage } from "../models/process";

export const PROCESS_LANGUAGES: { value: ProcessLanguage; label: string }[] = [
  { value: "bash", label: "Bash" },
  { value: "python", label: "Python" },
  { value: "perl", label: "Perl" },
  { value: "r", label: "R" },
  { value: "groovy", label: "Groovy" },
];

export function languageExtension(language: ProcessLanguage): Extension {

  switch (language) {

    case "python":
      return python();

    case "perl":
      return StreamLanguage.define(perl);

    case "r":
      return StreamLanguage.define(r);

    case "groovy":
      return StreamLanguage.define(groovy);

    case "bash":
    default:
      return StreamLanguage.define(shell);

  }

}
