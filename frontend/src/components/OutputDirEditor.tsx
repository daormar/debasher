import { useState } from "react";

import { useProgram } from "../store/ProgramContext";

interface Props {
  onClose: () => void;
}

export default function OutputDirEditor({ onClose }: Props) {

  const {
    program,
    setOutputDir,
  } = useProgram();

  const [draft, setDraft] =
    useState(program.outputDir);

  const conflictsWithHomeDir =
    !!program.homeDir.trim() && draft.trim() === program.homeDir.trim();

  function handleSave() {
    if (conflictsWithHomeDir) {
      return;
    }
    setOutputDir(draft);
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
          maxWidth: 480,
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >

        <h3 style={{ margin: 0 }}>
          Output directory
        </h3>

        <input

          type="text"

          value={draft}

          onChange={(event) =>
            setDraft(event.target.value)
          }

          onKeyDown={(event) => {
            if (event.key === "Enter") {
              handleSave();
            }
          }}

          placeholder="/path/to/output/directory"

          autoFocus

          style={{
            width: "100%",
          }}

        />

        {conflictsWithHomeDir && (
          <div style={{ color: "#8a6d00", fontSize: 14 }}>
            This matches the program's save directory ({program.homeDir}).
            Running here would mix engine-internal files into the saved
            program, and "Reset output directory" would delete it. Pick a
            different directory.
          </div>
        )}

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

          <button onClick={handleSave} disabled={conflictsWithHomeDir}>
            Save
          </button>

        </div>

      </div>

    </div>

  );

}
