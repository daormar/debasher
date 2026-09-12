import { useState, type ReactNode } from "react";
import CodeMirror from "@uiw/react-codemirror";

import { useProgram } from "../store/ProgramContext";
import { languageExtension } from "./codeLanguages";
import type { AdditionalMethods, ProgramProcess } from "../models/process";

interface Props {
  process: ProgramProcess;
  methodKey: keyof AdditionalMethods;
  methodName: string;
  description: ReactNode;
  onClose: () => void;
}

export default function MethodBodyEditor({
  process,
  methodKey,
  methodName,
  description,
  onClose,
}: Props) {

  const { setAdditionalMethods } = useProgram();

  const [draft, setDraft] = useState(process.additionalMethods[methodKey] ?? "");

  function handleSave() {

    setAdditionalMethods(process.id, {
      ...process.additionalMethods,
      [methodKey]: draft,
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
        zIndex: 1001,
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
          {methodName}: {process.name}
        </h3>

        <p style={{ margin: 0, color: "#666", fontSize: 13 }}>
          {description}
        </p>

        <div
          style={{
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
