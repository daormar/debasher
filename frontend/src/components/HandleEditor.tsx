import { useState } from "react";

import { useWorkflow } from "../store/WorkflowContext";
import type { WorkflowHandle, HandleDirection } from "../models/handle";

interface Props {
  nodeId: string;
  handle: WorkflowHandle;
  onClose: () => void;
}

export default function HandleEditor({ nodeId, handle, onClose }: Props) {

  const { updateHandle } = useWorkflow();

  const [label, setLabel] =
    useState(handle.label);

  const [direction, setDirection] =
    useState<HandleDirection>(handle.direction);

  function handleSave() {

    updateHandle(nodeId, handle.id, {
      label,
      direction,
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
          Handle
        </h3>

        <label>
          Label
        </label>

        <input

          value={label}

          onChange={(event) =>
            setLabel(event.target.value)
          }

          style={{
            width: "100%",
          }}

        />

        <label>
          Direction
        </label>

        <select

          value={direction}

          onChange={(event) =>
            setDirection(
              event.target.value as HandleDirection
            )
          }

          style={{
            width: "100%",
          }}

        >

          <option value="input">
            input
          </option>

          <option value="output">
            output
          </option>

        </select>

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

          <button
            onClick={handleSave}
            disabled={!label.trim()}
          >
            Save
          </button>

        </div>

      </div>

    </div>

  );

}
