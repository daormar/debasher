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
  manualMode: boolean;
  onClose: () => void;
}

export default function OptionEditor({ processId, option, manualMode, onClose }: Props) {

  const { workflow, updateOption } = useWorkflow();

  const connectingEdge = workflow.edges.find(
    edge =>
      edge.targetProcessId === processId &&
      edge.targetOptionId === option.id
  );

  const connectedSourceOption = (() => {

    if (!connectingEdge) {
      return null;
    }

    const sourceProcess = workflow.processes.find(
      process => process.id === connectingEdge.sourceProcessId
    );

    const sourceOption = sourceProcess?.options.find(
      o => o.id === connectingEdge.sourceOptionId
    );

    if (!sourceProcess || !sourceOption) {
      return null;
    }

    return { sourceProcess, sourceOption };

  })();

  const connectedSourceLabel = connectedSourceOption &&
    `[${connectedSourceOption.sourceProcess.name};${connectedSourceOption.sourceOption.label}]`;

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

  const [commandLine, setCommandLine] =
    useState(option.commandLine);

  const [mandatory, setMandatory] =
    useState(option.mandatory);

  const fifoEditable = direction === "output" && !commandLine;

  function handleSave() {

    updateOption(processId, option.id, {
      label,
      direction: getOptionDirection(label),
      dataType,
      description,
      value,
      fifo,
      commandLine,
      mandatory: commandLine && mandatory,
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

          <input

            type="checkbox"

            checked={commandLine}

            onChange={(event) =>
              setCommandLine(event.target.checked)
            }

          />
          {" "}Command line

        </label>

        <label style={{ color: commandLine ? undefined : "#999" }}>

          <input

            type="checkbox"

            checked={mandatory}

            disabled={!commandLine}

            onChange={(event) =>
              setMandatory(event.target.checked)
            }

          />
          {" "}Mandatory

        </label>

        {!manualMode && (

          <label style={{ color: fifoEditable ? undefined : "#999" }}>

            <input

              type="checkbox"

              checked={fifoEditable ? fifo : (connectedSourceOption?.sourceOption.fifo ?? false)}

              disabled={!fifoEditable}

              onChange={(event) =>
                setFifo(event.target.checked)
              }

            />
            {" "}FIFO

          </label>

        )}

        {!manualMode && (

          <>

            <label style={{ color: commandLine ? "#999" : undefined }}>
              Value
            </label>

            {connectedSourceLabel ? (

              <div
                style={{
                  width: "100%",
                  padding: "6px 8px",
                  borderRadius: 4,
                  border: "1px solid #bbb",
                  color: "#888",
                  boxSizing: "border-box",
                  opacity: commandLine ? 0.5 : 1,
                }}
              >
                {connectedSourceLabel}
              </div>

            ) : (

              <input

                value={value}

                disabled={commandLine}

                onChange={(event) =>
                  setValue(event.target.value)
                }

                style={{
                  width: "100%",
                }}

              />

            )}

          </>

        )}

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
