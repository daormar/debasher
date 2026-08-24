import { useState } from "react";

import { useWorkflow } from "../store/WorkflowContext";
import type {
  WorkflowOption,
  OptionDataType,
} from "../models/option";
import { getOptionDirection, isValidOptionLabel } from "../models/option";

interface Props {
  processId: string;
  option: WorkflowOption;
  onClose: () => void;
}

export default function OptionEditor({ processId, option, onClose }: Props) {

  const { updateOption } = useWorkflow();

  const [label, setLabel] =
    useState(option.label);

  const direction = getOptionDirection(label);

  const [dataType, setDataType] =
    useState<OptionDataType>(option.dataType);

  const [description, setDescription] =
    useState(option.description);

  const [value, setValue] =
    useState(option.value);

  const [fifo, setFifo] =
    useState(option.fifo);

  function handleSave() {

    updateOption(processId, option.id, {
      label,
      direction: getOptionDirection(label),
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
          {direction === "output" ? "Output Option" : "Input Option"}
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
          Data type
        </label>

        <select

          value={dataType}

          onChange={(event) =>
            setDataType(
              event.target.value as OptionDataType
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
            disabled={!isValidOptionLabel(label)}
          >
            Save
          </button>

        </div>

      </div>

    </div>

  );

}
