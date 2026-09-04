import { useEffect, useState } from "react";

import { useProgram } from "../store/ProgramContext";
import type {
  ProgramOption,
  OptionDataType,
  OptionChannel,
} from "../models/option";
import { getOptionDirection, isValidOptionLabel, isFanoutOption } from "../models/option";

interface Props {
  processId: string;
  option: ProgramOption;
  manualMode: boolean;
  onClose: () => void;
}

// Modes whose _define_opts/_generate_opts produces one save_opt_list
// call per task, numbered 0..N-1 — see script_generation.py's own
// _TASK_INDEXED_MODES, which this mirrors for display purposes only.
const TASK_INDEXED_MODES = new Set(["generator", "array"]);

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
  // (_option_definition_line/_TASK_INDEXED_MODES): a task-indexed
  // connection is only ever regenerated when both this option's own
  // process and the connected source are generator or array mode,
  // since that's the only combination where the source is guaranteed
  // to actually have a task N to pull from. The index variable itself
  // is "task_idx" for a generator-mode owner, "idx" for an array-mode
  // one (see script_generation.py's _task_idx_var).
  const ownerProcess = program.processes.find(
    process => process.id === processId
  );

  const isTaskIndexed =
    !!ownerProcess && TASK_INDEXED_MODES.has(ownerProcess.optionsHandler.mode) &&
    !!connectedSourceOption && TASK_INDEXED_MODES.has(connectedSourceOption.sourceProcess.optionsHandler.mode);

  const idxVar = ownerProcess?.optionsHandler.mode === "generator" ? "task_idx" : "idx";

  // A "standard"-mode owner gathering from an "array"-mode source
  // (see script_generation.py's _fanout_definition_lines) doesn't share
  // a loop with the source the way generator/array do — it expands into
  // its own local "i" loop at script-gen time, one connection per task.
  const isFanoutGather =
    isFanoutOption(option.label) &&
    ownerProcess?.optionsHandler.mode === "standard" &&
    !!connectedSourceOption &&
    connectedSourceOption.sourceProcess.optionsHandler.mode === "array";

  const connectedSourceLabel = connectedSourceOption &&
    (isTaskIndexed
      ? `[${connectedSourceOption.sourceProcess.name};${connectedSourceOption.sourceOption.label};\${${idxVar}}]`
      : isFanoutGather
      ? `[${connectedSourceOption.sourceProcess.name};${connectedSourceOption.sourceOption.label};\${i}]`
      : `[${connectedSourceOption.sourceProcess.name};${connectedSourceOption.sourceOption.label}]`);

  // Consumer side of a scatter connection (see
  // script_generation.py's _option_definition_line "conn_opt" branch):
  // this option is connected to a fanout family declared on a
  // "standard" process, so this ("array"-mode) process's own task count
  // is implicitly forced to match whatever that family's own count
  // source computes — flagged here since nothing enforces it
  // structurally.
  const isScatterConsumer =
    !!connectedSourceOption &&
    connectedSourceOption.sourceProcess.optionsHandler.mode === "standard" &&
    isFanoutOption(connectedSourceOption.sourceOption.label);

  const scatterCountSource = isScatterConsumer
    ? connectedSourceOption.sourceProcess.options.find(
        o => o.id === connectedSourceOption.sourceOption.countSourceOptionId
      )
    : undefined;

  const [label, setLabel] =
    useState(option.label);

  const direction = getOptionDirection(label);

  // Reactive to the label as it's being typed, so the "Count source"
  // field appears/disappears live as the user adds/removes the "ith"
  // suffix, rather than only after saving.
  const isFanout = isFanoutOption(label) && ownerProcess?.optionsHandler.mode === "standard";

  const countSourceCandidates =
    ownerProcess?.options.filter(o => o.commandLine && o.id !== option.id) ?? [];

  const [countSourceOptionId, setCountSourceOptionId] =
    useState(option.countSourceOptionId ?? "");

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
      countSourceOptionId: isFanout ? (countSourceOptionId || undefined) : undefined,
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

        {isScatterConsumer && (
          <p style={{ margin: 0, color: "#c0392b", fontSize: 13 }}>
            ⚠ This connection is wired to {connectedSourceOption.sourceProcess.name}'s{" "}
            fanout family "{connectedSourceOption.sourceOption.label}", whose size is set by{" "}
            {scatterCountSource
              ? `that process's own "${scatterCountSource.label}" option`
              : "that process's count source (not configured yet)"}
            {" "}— this process's array must produce exactly that many tasks.
          </p>
        )}

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

        {isFanout && (

          <>

            <label>
              Count source (command-line option on this process)
            </label>

            <select

              value={countSourceOptionId}

              onChange={(event) =>
                setCountSourceOptionId(event.target.value)
              }

              style={{
                width: "100%",
              }}

            >

              <option value="">
                (none selected)
              </option>

              {countSourceCandidates.map(candidate => (
                <option key={candidate.id} value={candidate.id}>
                  {candidate.label}
                </option>
              ))}

            </select>

          </>

        )}

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
