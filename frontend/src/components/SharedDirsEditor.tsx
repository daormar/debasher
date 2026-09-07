import { useState } from "react";

import { useProgram } from "../store/ProgramContext";

interface Props {
  onClose: () => void;
}

// One shared directory name per line — blank lines are dropped on save,
// so stray empty lines left while editing don't turn into bogus entries.
function linesToSharedDirs(text: string): string[] {
  return text
    .split("\n")
    .map(line => line.trim())
    .filter(line => line !== "");
}

export default function SharedDirsEditor({ onClose }: Props) {

  const {
    program,
    setSharedDirs,
  } = useProgram();

  const [draft, setDraft] =
    useState(program.sharedDirs.join("\n"));

  // Shared directories reachable from this program but not declared by
  // it — inherited from a module it loads (see api/doc_mod.py's
  // run_doc_mod_all_shared_dirs, populated only by import). Shown
  // separately, read-only: they aren't this program's own to edit —
  // sharedDirs is what script generation actually emits from — and
  // any already in sharedDirs are left out here since the editable box
  // above already shows them.
  const inheritedSharedDirs = program.availableSharedDirs.filter(
    (name) => !program.sharedDirs.includes(name)
  );

  function handleSave() {
    setSharedDirs(linesToSharedDirs(draft));
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
          Shared directories
        </h3>

        <textarea

          value={draft}

          onChange={(event) =>
            setDraft(event.target.value)
          }

          rows={12}

          spellCheck={false}

          placeholder="One directory name per line..."

          style={{
            width: "100%",
            fontFamily: "ui-monospace, Consolas, monospace",
            resize: "vertical",
          }}

        />

        {inheritedSharedDirs.length > 0 && (

          <>

            <h4 style={{ margin: 0 }}>
              Previously defined (inherited) shared directories
            </h4>

            <textarea

              value={inheritedSharedDirs.join("\n")}

              readOnly

              rows={6}

              spellCheck={false}

              style={{
                width: "100%",
                fontFamily: "ui-monospace, Consolas, monospace",
                resize: "vertical",
                background: "#f0f0f0",
                color: "#555",
              }}

            />

          </>

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

          <button onClick={handleSave}>
            Save
          </button>

        </div>

      </div>

    </div>

  );

}
