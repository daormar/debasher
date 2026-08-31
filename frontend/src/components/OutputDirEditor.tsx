import { useState } from "react";

import { useWorkflow } from "../store/WorkflowContext";

interface Props {
  onClose: () => void;
}

export default function OutputDirEditor({ onClose }: Props) {

  const {
    workflow,
    setOutputDir,
  } = useWorkflow();

  const [draft, setDraft] =
    useState(workflow.outputDir);

  function handleSave() {
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
