import { useMemo, useRef, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";

import { useProgram } from "../store/ProgramContext";
import { languageExtension } from "./codeLanguages";
import { generateCodeTemplate, isCodeStillTemplate } from "../models/codeTemplates";
import { buildCodePrompt } from "../models/codePrompt";
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

  const [copyNote, setCopyNote] = useState<string | null>(null);

  const promptRef = useRef<HTMLTextAreaElement>(null);

  const codePrompt = useMemo(
    () => isPromptOpen ? buildCodePrompt(program, process, draft, codeRequest) : "",
    [isPromptOpen, program, process, draft, codeRequest]
  );

  // The clipboard is missing on a page opened from a file, and a browser
  // may refuse it: the prompt is then selected, for the keyboard to copy.
  async function handleCopy() {
    try {
      if (!navigator.clipboard) {
        throw new Error("no clipboard");
      }
      await navigator.clipboard.writeText(codePrompt);
      setCopyNote("Copied. Paste the code of the answer into the editor.");
    } catch {
      promptRef.current?.focus();
      promptRef.current?.select();
      setCopyNote("The browser did not let the page copy: the prompt is selected, copy it with the keyboard.");
    }
  }

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

          <button
            title="Prompt for an AI tool"
            aria-pressed={isPromptOpen}
            onClick={() => { setPromptOpen(open => !open); setCopyNote(null); }}
            style={{
              background: isPromptOpen ? "#ede7f6" : undefined,
            }}
          >
            ✨ AI prompt
          </button>

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

            <div
              style={{
                flex: 1,
                minWidth: 0,
                display: "flex",
                flexDirection: "column",
                gap: 6,
                fontSize: 13,
              }}
            >

              <label htmlFor="code-request">
                What should the code do? (optional)
              </label>

              <textarea
                id="code-request"
                rows={3}
                value={codeRequest}
                placeholder="Blank: the code that the description of the process asks for"
                onChange={event => setCodeRequest(event.target.value)}
                style={{ resize: "vertical", flexShrink: 0 }}
              />

              <label htmlFor="code-prompt">
                Prompt, to copy into an AI tool of your choice
              </label>

              <textarea
                id="code-prompt"
                ref={promptRef}
                readOnly
                value={codePrompt}
                style={{
                  flex: 1,
                  minHeight: 200,
                  fontFamily: "monospace",
                  fontSize: 12,
                  resize: "none",
                }}
              />

              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                }}
              >

                <button onClick={handleCopy}>
                  Copy
                </button>

                <span style={{ color: "#555" }}>
                  {copyNote ?? "Nothing is sent from here: the prompt only leaves through your copy."}
                </span>

              </div>

            </div>

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
