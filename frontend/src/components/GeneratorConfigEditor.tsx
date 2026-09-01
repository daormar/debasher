import { useState } from "react";

import { useProgram } from "../store/ProgramContext";
import type { ProgramProcess } from "../models/process";

interface Props {
  process: ProgramProcess;
  onClose: () => void;
}

export default function GeneratorConfigEditor({ process, onClose }: Props) {

  const { setOptionsHandler } = useProgram();

  const [generatorSize, setGeneratorSize] =
    useState(process.optionsHandler.generatorSize ?? "");

  function handleSave() {

    setOptionsHandler(process.id, {
      ...process.optionsHandler,
      mode: "generator",
      generatorSize,
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
          width: 360,
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >

        <h3 style={{ margin: 0 }}>
          Generator Configuration
        </h3>

        <label>
          Size
        </label>

        <input

          value={generatorSize}

          onChange={(event) =>
            setGeneratorSize(event.target.value)
          }

          placeholder="e.g. 10 or an expression"

          style={{
            width: "100%",
          }}

        />

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
            marginTop: 8,
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
