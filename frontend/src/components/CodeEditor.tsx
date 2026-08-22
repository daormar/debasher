import { useState } from "react";
import CodeMirror from "@uiw/react-codemirror";

import { useWorkflow } from "../store/WorkflowContext";
import { languageExtension } from "./codeLanguages";
import type { WorkflowNode } from "../models/node";

interface Props {
  node: WorkflowNode;
  onClose: () => void;
}

export default function CodeEditor({ node, onClose }: Props) {

  const { setNodeCode } = useWorkflow();

  const [draft, setDraft] =
    useState(node.code);

  function handleSave() {
    setNodeCode(node.id, draft);
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
          Code — {node.name} ({node.language})
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
              languageExtension(node.language),
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
