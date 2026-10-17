import { useMemo, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";

import { useProgram } from "../store/ProgramContext";
import { languageExtensions } from "./codeLanguages";
import type { ProgramProcess } from "../models/process";
import { buildOptionsHandlerPrompt } from "../models/optionsHandlerPrompt";
import { GENERATOR_SIZE_TEMPLATE, GENERATOR_TASKS_PY_TEMPLATE } from "../models/codeTemplates";
import CodePromptPanel, { CodePromptButton } from "./CodePromptPanel";
import FuncLanguageSelect, { useLanguageDrafts } from "./FuncLanguageSelect";

interface Props {
  process: ProgramProcess;
  onClose: () => void;
}


export default function GeneratorConfigEditor({ process, onClose }: Props) {

  const { program, setOptionsHandler } = useProgram();

  const { language, setLanguage, draft, setDraft } = useLanguageDrafts(
    process.optionsHandler.language ?? "bash",
    process.optionsHandler.generatorSizeCode,
    { bash: GENERATOR_SIZE_TEMPLATE, python: GENERATOR_TASKS_PY_TEMPLATE },
  );

  function handleSave() {

    setOptionsHandler(process.id, {
      ...process.optionsHandler,
      mode: "generator",
      generatorSizeCode: draft,
      language,
    });

    onClose();

  }

  // The prompt panel, as in the code editor of a process.
  const [isPromptOpen, setPromptOpen] = useState(false);

  const [codeRequest, setCodeRequest] = useState("");

  const codePrompt = useMemo(
    () => isPromptOpen ? buildOptionsHandlerPrompt(program, process, "generator", draft, codeRequest, language) : "",
    [isPromptOpen, program, process, draft, codeRequest, language]
  );

  return (

    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0, 0, 0, 0.4)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >

      <div
        style={{
          width: isPromptOpen ? "92%" : "70%",
          maxWidth: isPromptOpen ? 1500 : 900,
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >

        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 8,
          }}
        >

          <h3 style={{ margin: 0 }}>
            Generator Configuration: {process.name}
          </h3>

          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <FuncLanguageSelect value={language} onChange={setLanguage} />
            <CodePromptButton isOpen={isPromptOpen} onToggle={() => setPromptOpen(open => !open)} />
          </div>

        </div>

        {language === "python" ? (
        <p style={{ margin: 0, color: "#666", fontSize: 13 }}>
          A Python file that defines <code>tasks(run)</code>, which returns
          the number of tasks, an integer. <code>run.value("-opt")</code>{" "}
          reads an option of the command line, <code>run.process</code> and{" "}
          <code>run.outdir</code> are the name and the output directory of
          the process. Option values can then reference{" "}
          <code>{"${task_idx}"}</code>, the index of the task.
        </p>
        ) : (
        <p style={{ margin: 0, color: "#666", fontSize: 13 }}>
          Bash code returning the number of tasks on stdout. The simplest
          implementation is just a fixed number, e.g. <code>echo 5</code>,
          or a computed one, e.g. <code>echo $n</code>. Taking into account
          that it will be preceded by the following variable
          initialization:
          <br />
          <code>local cmdline=$1</code>
          <br />
          <code>local process_spec=$2</code>
          <br />
          <code>local process_name=$3</code>
          <br />
          <code>local process_outdir=$4</code>
        </p>
        )}

        <div
          style={{
            display: "flex",
            gap: 12,
            alignItems: "stretch",
          }}
        >

          <div
            style={{
              flex: 1,
              minWidth: 0,
              border: "1px solid #ccc",
            }}
          >

            <CodeMirror

              value={draft}

              height="400px"

              extensions={languageExtensions(language)}

              // The setter itself, which keeps its identity: a new function at each

              // render would reconfigure the editor (see languageExtensions).

              onChange={setDraft}

            />

          </div>

          {isPromptOpen && (
            <CodePromptPanel
              prompt={codePrompt}
              request={codeRequest}
              onRequestChange={setCodeRequest}
              pasteHint="Paste the code of the answer into the editor."
            />
          )}

        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
          }}
        >

          <button onClick={onClose}>
            Cancel
          </button>

          <button onClick={handleSave}>
            Save
          </button>

        </div>

      </div>

    </div>

  );

}
