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

// The extensions of a code editor in `language`, one array for each
// language, made once and then shared. @uiw/react-codemirror reconfigures
// the whole editor whenever one of its `extensions`, `onChange`,
// `basicSetup` or `placeholder` props is another value than at the render
// before, and the highlighting of the code vanishes for a moment while it
// does: an array or a function written in the JSX, a new one at each
// render, makes the colors of an open editor blink every time the
// component renders again, as it does at each reading of the run status.
// Every editor takes its extensions from here, and an `onChange` that
// keeps its identity (a state setter, or a function from useCallback).
const LANGUAGE_EXTENSIONS = new Map<ProcessLanguage, Extension[]>();

export function languageExtensions(language: ProcessLanguage): Extension[] {
  let extensions = LANGUAGE_EXTENSIONS.get(language);
  if (!extensions) {
    extensions = [languageExtension(language)];
    LANGUAGE_EXTENSIONS.set(language, extensions);
  }
  return extensions;
}
