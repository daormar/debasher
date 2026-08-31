import { useState } from "react";

import { useWorkflow } from "../store/WorkflowContext";

interface Props {
  onClose: () => void;
}

export default function WorkflowDescriptionEditor({ onClose }: Props) {

  const {
    workflow,
    setDescription,
  } = useWorkflow();

  const [draft, setDraft] =
    useState(workflow.description);

  function handleSave() {
    setDescription(draft);
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
          Description
        </h3>

        <textarea

          value={draft}

          onChange={(event) =>
            setDraft(event.target.value)
          }

          rows={16}

          placeholder="Describe what this workflow does..."

          style={{
            width: "100%",
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
