import { useMemo, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";

import { useProgram } from "../store/ProgramContext";
import { languageExtension } from "./codeLanguages";
import type { ProgramProcess } from "../models/process";
import { buildOptionsHandlerPrompt } from "../models/optionsHandlerPrompt";
import { GENERATOR_SIZE_TEMPLATE } from "../models/codeTemplates";
import CodePromptPanel, { CodePromptButton } from "./CodePromptPanel";

interface Props {
  process: ProgramProcess;
  onClose: () => void;
}


export default function GeneratorConfigEditor({ process, onClose }: Props) {

  const { program, setOptionsHandler } = useProgram();

  const [draft, setDraft] =
    useState(process.optionsHandler.generatorSizeCode ?? GENERATOR_SIZE_TEMPLATE);

  function handleSave() {

    setOptionsHandler(process.id, {
      ...process.optionsHandler,
      mode: "generator",
      generatorSizeCode: draft,
    });

    onClose();

  }

  // The prompt panel, as in the code editor of a process.
  const [isPromptOpen, setPromptOpen] = useState(false);

  const [codeRequest, setCodeRequest] = useState("");

  const codePrompt = useMemo(
    () => isPromptOpen ? buildOptionsHandlerPrompt(program, process, "generator", draft, codeRequest) : "",
    [isPromptOpen, program, process, draft, codeRequest]
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

          <CodePromptButton isOpen={isPromptOpen} onToggle={() => setPromptOpen(open => !open)} />

        </div>

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

              extensions={[
                languageExtension("bash"),
              ]}

              onChange={value => setDraft(value)}

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
