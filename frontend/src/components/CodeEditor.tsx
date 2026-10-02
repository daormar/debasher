import { useMemo, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";

import { useProgram } from "../store/ProgramContext";
import { languageExtension } from "./codeLanguages";
import { generateCodeTemplate, isCodeStillTemplate } from "../models/codeTemplates";
import { buildCodePrompt } from "../models/codePrompt";
import CodePromptPanel, { CodePromptButton } from "./CodePromptPanel";
import type { ProgramProcess } from "../models/process";

interface Props {
  process: ProgramProcess;
  onClose: () => void;
}

export default function CodeEditor({ process, onClose }: Props) {

  const { program, setProcessCode } = useProgram();

  const [draft, setDraft] = useState(() =>
    isCodeStillTemplate(process.code)
      ? generateCodeTemplate(process)
      : process.code
  );

  function handleSave() {
    setProcessCode(process.id, draft);
    onClose();
  }

  // The prompt panel: the code prompt, built from the program in the store
  // and the draft, for the user to copy into an AI tool. The code comes
  // back by being pasted into the editor, like any code.
  const [isPromptOpen, setPromptOpen] = useState(false);

  const [codeRequest, setCodeRequest] = useState("");

  const codePrompt = useMemo(
    () => isPromptOpen ? buildCodePrompt(program, process, draft, codeRequest) : "",
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
            Code: {process.name} ({process.language})
          </h3>

          <CodePromptButton isOpen={isPromptOpen} onToggle={() => setPromptOpen(open => !open)} />

        </div>

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
                languageExtension(process.language),
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
