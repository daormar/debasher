import { useState } from "react";
import CodeMirror from "@uiw/react-codemirror";

import { useProgram } from "../store/ProgramContext";
import { languageExtension } from "./codeLanguages";
import type { ProgramProcess } from "../models/process";

interface Props {
  process: ProgramProcess;
  onClose: () => void;
}

export default function ArrayConfigEditor({ process, onClose }: Props) {

  const { setOptionsHandler } = useProgram();

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

        <p style={{ margin: 0, color: "#666", fontSize: 13 }}>
          Add your code below. Bash code that builds an array named{" "}
          <code>array</code>, run once before the per-task loop. Option
          values below can then reference <code>{"${array[$idx]}"}</code>{" "}
          (the current element) or <code>{"${idx}"}</code> (its index).
          Taking into account that it will be preceded by the following
          variable initialization:
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
