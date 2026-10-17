import { useCallback, useState } from "react";

import type { FuncLanguage } from "../models/process";

interface Props {
  value: FuncLanguage;
  onChange: (language: FuncLanguage) => void;
}

// The language of the code that shapes the tasks of a process or decides
// whether a task is skipped: a Bash body, or a Python function file that
// the engine runs (see "Python function files" in
// doc/design_doc_engine.md).
export default function FuncLanguageSelect({ value, onChange }: Props) {

  return (

    <label style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 4 }}>

      Language

      <select
        value={value}
        onChange={event => onChange(event.target.value as FuncLanguage)}
      >
        <option value="bash">Bash</option>
        <option value="python">Python</option>
      </select>

    </label>

  );

}

// The drafts of an editor whose code may be in either language: one per
// language, so that switching back and forth loses nothing until Save,
// each starting from the saved code in its own language or from the
// template of the language.
export function useLanguageDrafts(
  savedLanguage: FuncLanguage,
  savedCode: string | undefined,
  templates: Record<FuncLanguage, string>,
) {

  const [language, setLanguage] = useState<FuncLanguage>(savedLanguage);

  const [drafts, setDrafts] = useState<Record<FuncLanguage, string>>(() => ({
    ...templates,
    [savedLanguage]: savedCode ?? templates[savedLanguage],
  }));

  // A setter that keeps its identity while the language stays the same: a
  // new function at each render would reconfigure the code editor (see
  // languageExtensions).
  const setDraft = useCallback(
    (code: string) => setDrafts(current => ({ ...current, [language]: code })),
    [language],
  );

  return { language, setLanguage, draft: drafts[language], setDraft };

}
