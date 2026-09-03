import { useEffect, useState } from "react";

import { useProgram } from "../store/ProgramContext";
import type {
  ProgramOption,
  OptionDataType,
  OptionChannel,
} from "../models/option";
import { getOptionDirection, isValidOptionLabel } from "../models/option";

interface Props {
  processId: string;
  option: ProgramOption;
  manualMode: boolean;
  onClose: () => void;
}

export default function OptionEditor({ processId, option, manualMode, onClose }: Props) {

  const { program, updateOption } = useProgram();

  const connectingEdge = program.edges.find(
    edge =>
      edge.targetProcessId === processId &&
      edge.targetOptionId === option.id
  );

  const connectedSourceOption = (() => {

    if (!connectingEdge) {
      return null;
    }

    const sourceProcess = program.processes.find(
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

  // Informational only — matches script_generation.py's own rule
  // (_add_opts_definition_func): ${task_idx} is only ever regenerated
  // when both this option's own process and the connected source are
  // generator mode, since that's the only combination where the source
  // is guaranteed to actually have a task N to pull from.
  const ownerProcess = program.processes.find(
    process => process.id === processId
  );

  const isTaskIndexed =
    ownerProcess?.optionsHandler.mode === "generator" &&
    connectedSourceOption?.sourceProcess.optionsHandler.mode === "generator";

  const connectedSourceLabel = connectedSourceOption &&
    (isTaskIndexed
      ? `[${connectedSourceOption.sourceProcess.name};${connectedSourceOption.sourceOption.label};\${task_idx}]`
      : `[${connectedSourceOption.sourceProcess.name};${connectedSourceOption.sourceOption.label}]`);

  const [label, setLabel] =
    useState(option.label);

  const direction = getOptionDirection(label);

  const [dataType, setDataType] =
    useState<OptionDataType>(option.dataType);

  const isFlag = dataType === "None";

  const [channel, setChannel] =
    useState<OptionChannel>(option.channel);

  const isValueDescriptor = channel === "value_desc";
  const isFifo = channel === "fifo";

  useEffect(() => {
    if (direction === "output" && dataType === "None") {
      setDataType("string");
    }
  }, [direction, dataType]);

  useEffect(() => {
    // value_desc is always output-direction (see models.py); fifo isn't
    // restricted, a process can legitimately open an input on a fifo it
    // rendezvous on by name.
    if (direction === "input" && channel === "value_desc") {
      setChannel("none");
    }
  }, [direction, channel]);

  useEffect(() => {
    // A connected option's value always comes from define_opt_from_proc_out,
    // never from its own define_value_desc_opt/define_fifo_opt call — the
    // channel describes how the *source* option got its value, not how
    // this one receives it, so a connected option's own channel is always
    // "none".
    if (connectedSourceLabel && channel !== "none") {
      setChannel("none");
    }
  }, [connectedSourceLabel, channel]);

  const [description, setDescription] =
    useState(option.description);

  const [value, setValue] =
    useState(option.value);

  const [commandLine, setCommandLine] =
    useState(option.commandLine);

  const [mandatory, setMandatory] =
    useState(option.mandatory);

  function handleSave() {

    updateOption(processId, option.id, {
      label,
      direction: getOptionDirection(label),
      dataType,
      channel: isFlag || connectedSourceLabel ? "none" : channel,
      description,
      value: isFlag || isValueDescriptor ? "" : value,
      commandLine,
      mandatory: commandLine && mandatory && !isFlag,
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

          <option value="file">
            file
          </option>

          {direction === "input" && (
            <option value="None">
              None (flag)
            </option>
          )}

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

        <label style={{ color: commandLine && !isFlag ? undefined : "#999" }}>

          <input

            type="checkbox"

            checked={isFlag ? false : mandatory}

            disabled={!commandLine || isFlag}

            onChange={(event) =>
              setMandatory(event.target.checked)
            }

          />
          {" "}Mandatory

        </label>

        {!isFlag && (

          <>

            <label style={{ color: manualMode ? "#999" : undefined }}>
              Channel
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
                }}
              >
                From connection
              </div>

            ) : (

              <select

                value={channel}

                disabled={manualMode}

                onChange={(event) =>
                  setChannel(event.target.value as OptionChannel)
                }

                style={{
                  width: "100%",
                }}

              >

                <option value="none">
                  Direct value
                </option>

                {direction === "output" && (
                  <option value="value_desc">
                    Value descriptor
                  </option>
                )}

                <option value="fifo">
                  FIFO
                </option>

              </select>

            )}

          </>

        )}

        {!isFlag && (

          <>

            <label style={{ color: commandLine || isValueDescriptor || manualMode ? "#999" : undefined }}>
              {isFifo ? "FIFO name" : "Value"}
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

                value={isValueDescriptor ? "" : value}

                disabled={commandLine || isValueDescriptor || manualMode}

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
