import { useState } from "react";

import { useWorkflow } from "../store/WorkflowContext";
import type {
  WorkflowHandle,
  HandleDirection,
  HandleDataType,
} from "../models/handle";

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

  const [dataType, setDataType] =
    useState<HandleDataType>(handle.dataType);

  const [description, setDescription] =
    useState(handle.description);

  const [value, setValue] =
    useState(handle.value);

  const [fifo, setFifo] =
    useState(handle.fifo);

  function handleSave() {

    updateHandle(nodeId, handle.id, {
      label,
      direction,
      dataType,
      description,
      value,
      fifo,
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

        <label>
          Data type
        </label>

        <select

          value={dataType}

          onChange={(event) =>
            setDataType(
              event.target.value as HandleDataType
            )
          }

          style={{
            width: "100%",
          }}

        >

          <option value="int">
            int
          </option>

          <option value="float">
            float
          </option>

          <option value="string">
            string
          </option>

        </select>

        <label>
          Description
        </label>

        <textarea

          value={description}

          onChange={(event) =>
            setDescription(event.target.value)
          }

          rows={4}

          style={{
            width: "100%",
          }}

        />

        <label>
          Value
        </label>

        <input

          value={value}

          onChange={(event) =>
            setValue(event.target.value)
          }

          style={{
            width: "100%",
          }}

        />

        <label>

          <input

            type="checkbox"

            checked={fifo}

            onChange={(event) =>
              setFifo(event.target.checked)
            }

          />
          {" "}FIFO

        </label>

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
