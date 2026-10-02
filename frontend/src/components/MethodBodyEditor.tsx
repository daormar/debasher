import { Fragment, useMemo, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";

import { useProgram } from "../store/ProgramContext";
import { languageExtension } from "./codeLanguages";
import type { AdditionalMethods, ProgramProcess } from "../models/process";
import { processMethod } from "../models/processMethods";
import { buildMethodPrompt } from "../models/methodPrompt";
import CodePromptPanel, { CodePromptButton } from "./CodePromptPanel";

interface Props {
  process: ProgramProcess;
  methodKey: keyof AdditionalMethods;
  onClose: () => void;
}

export default function MethodBodyEditor({
  process,
  methodKey,
  onClose,
}: Props) {

  const { program, setAdditionalMethods } = useProgram();

  const method = processMethod(methodKey);

  const [draft, setDraft] = useState(process.additionalMethods[methodKey] ?? "");

  function handleSave() {

    setAdditionalMethods(process.id, {
      ...process.additionalMethods,
      [methodKey]: draft,
    });

    onClose();

  }

  // The prompt panel, as in the code editor of a process.
  const [isPromptOpen, setPromptOpen] = useState(false);

  const [codeRequest, setCodeRequest] = useState("");

  const codePrompt = useMemo(
    () => isPromptOpen ? buildMethodPrompt(program, process, methodKey, draft, codeRequest) : "",
    [isPromptOpen, program, process, methodKey, draft, codeRequest]
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
        zIndex: 1001,
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
            {method.name}: {process.name}
          </h3>

          <CodePromptButton isOpen={isPromptOpen} onToggle={() => setPromptOpen(open => !open)} />

        </div>

        <p style={{ margin: 0, color: "#666", fontSize: 13 }}>
          {withCodeSpans(method.summary)}
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

// A text whose code spans are written between backquotes, with each span
// shown as code.
function withCodeSpans(text: string) {
  return text.split("`").map((piece, i) => (
    i % 2 === 1 ? <code key={i}>{piece}</code> : <Fragment key={i}>{piece}</Fragment>
  ));
}
