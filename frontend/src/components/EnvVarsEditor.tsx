import { useState } from "react";

import { useProgram } from "../store/ProgramContext";

interface Props {
  onClose: () => void;
}

export default function EnvVarsEditor({ onClose }: Props) {

  const {
    program,
    setEnvVar,
  } = useProgram();

  const [draft, setDraft] =
    useState(program.envVars.DEBASHER_MOD_DIR ?? "");

  function handleSave() {
    setEnvVar("DEBASHER_MOD_DIR", draft);
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
          width: "60%",
          maxWidth: 720,
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >

        <h3 style={{ margin: 0 }}>
          Environment variables
        </h3>

        <label style={{ fontSize: 14 }}>
          DEBASHER_MOD_DIR
        </label>

        <textarea

          value={draft}

          onChange={(event) =>
            setDraft(event.target.value)
          }

          rows={8}

          spellCheck={false}

          placeholder="/path/to/modules"

          style={{
            width: "100%",
            fontFamily: "ui-monospace, Consolas, monospace",
            resize: "vertical",
          }}

        />

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
