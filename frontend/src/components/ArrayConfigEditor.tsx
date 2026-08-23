import { useState } from "react";
import CodeMirror from "@uiw/react-codemirror";

import { useWorkflow } from "../store/WorkflowContext";
import { languageExtension } from "./codeLanguages";
import type { WorkflowProcess } from "../models/process";

interface Props {
  process: WorkflowProcess;
  onClose: () => void;
}

export default function ArrayConfigEditor({ process, onClose }: Props) {

  const { setOptionsHandler } = useWorkflow();

  const [draft, setDraft] =
    useState(process.optionsHandler.arrayCode ?? "");

  function handleSave() {

    setOptionsHandler(process.id, {
      ...process.optionsHandler,
      mode: "array",
      arrayCode: draft,
    });

    onClose();

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
          width: "70%",
          maxWidth: 900,
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >

        <h3 style={{ margin: 0 }}>
          Array Configuration — {process.name}
        </h3>

        <div
          style={{
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
