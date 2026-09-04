import { useState } from "react";
import CodeMirror from "@uiw/react-codemirror";

import { useProgram } from "../store/ProgramContext";
import { languageExtension } from "./codeLanguages";
import type { ProgramProcess } from "../models/process";

interface Props {
  process: ProgramProcess;
  onClose: () => void;
}

const TEMPLATE = `# TODO: return the number of tasks
`;

export default function GeneratorConfigEditor({ process, onClose }: Props) {

  const { setOptionsHandler } = useProgram();

  const [draft, setDraft] =
    useState(process.optionsHandler.generatorSizeCode ?? TEMPLATE);

  function handleSave() {

    setOptionsHandler(process.id, {
      ...process.optionsHandler,
      mode: "generator",
      generatorSizeCode: draft,
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
          Generator Configuration — {process.name}
        </h3>

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
