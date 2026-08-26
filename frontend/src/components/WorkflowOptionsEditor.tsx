import { useMemo, useState } from "react";

import { getCommandLineOptions } from "../models/option";
import { useWorkflow } from "../store/WorkflowContext";

interface Props {
  onClose: () => void;
}

export default function WorkflowOptionsEditor({ onClose }: Props) {

  const {
    workflow,
    setWorkflowOptions,
  } = useWorkflow();

  const options = useMemo(
    () => getCommandLineOptions(workflow.processes),
    [workflow.processes]
  );

  const [draft, setDraft] =
    useState<Record<string, string>>(() => {

      const initial: Record<string, string> = {};

      for (const option of options) {
        initial[option.label] =
          workflow.workflowOptions[option.label] ?? option.value;
      }

      return initial;

    });

  function handleSave() {
    setWorkflowOptions(draft);
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
          Workflow options
        </h3>

        {options.length === 0 ? (

          <p style={{ fontSize: 14, color: "#666" }}>
            No command line options declared. Mark an option as
            "Command line" on a process to have it appear here.
          </p>

        ) : (

          options.map(option => (

            <div key={option.label}>

              <label style={{ fontSize: 14 }}>
                {option.label}
              </label>

              <input

                type={option.dataType === "string" ? "text" : "number"}

                step={option.dataType === "float" ? "any" : undefined}

                value={draft[option.label] ?? ""}

                onChange={(event) =>
                  setDraft(current => ({
                    ...current,
                    [option.label]: event.target.value,
                  }))
                }

                style={{
                  width: "100%",
                }}

              />

              {option.description && (
                <div style={{ fontSize: 12, color: "#888" }}>
                  {option.description}
                </div>
              )}

            </div>

          ))

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
