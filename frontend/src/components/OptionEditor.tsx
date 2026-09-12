import { useEffect, useState } from "react";

import { useProgram } from "../store/ProgramContext";
import type {
  ProgramOption,
  OptionDataType,
  OptionChannel,
} from "../models/option";
import {
  getOptionDirection,
  isValidOptionLabel,
  isFanoutOption,
  PROCESS_SPEC_ATTRIBUTE_NAMES,
} from "../models/option";

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

  // A non-command-line, non-fanout input may gather from more than one
  // source (see isValidProgramConnection) — everything below keys off
  // the full list; connectedSourceOption (its first/only entry) remains
  // for the fanout-gather and scatter-consumer checks below, which stay
  // single-connection by construction.
  const connectingEdges = program.edges.filter(
    edge =>
      edge.targetProcessId === processId &&
      edge.targetOptionId === option.id
  );

  const connectedSourceOptions = connectingEdges
    .map(edge => {

      const sourceProcess = program.processes.find(
        process => process.id === edge.sourceProcessId
      );

      const sourceOption = sourceProcess?.options.find(
        o => o.id === edge.sourceOptionId
      );

      if (!sourceProcess || !sourceOption) {
        return null;
      }

      return { sourceProcess, sourceOption };

    })
    .filter((entry): entry is NonNullable<typeof entry> => entry !== null);

  const connectedSourceOption = connectedSourceOptions[0] ?? null;

  const ownerProcess = program.processes.find(
    process => process.id === processId
  );

  const idxVar = ownerProcess?.optionsHandler.mode === "generator" ? "task_idx" : "idx";

  // A "standard"-mode owner gathering from an "array"- or "generator"-
  // mode source (see script_generation.py's _fanout_definition_lines and
  // its _FANOUT_PARTNER_MODES) doesn't share a loop with the source the
  // way generator/array do — it expands into its own local "i" loop at
  // script-gen time, one connection per task.
  const isFanoutGather =
    isFanoutOption(option.label) &&
    ownerProcess?.optionsHandler.mode === "standard" &&
    !!connectedSourceOption &&
    (connectedSourceOption.sourceProcess.optionsHandler.mode === "array" ||
      connectedSourceOption.sourceProcess.optionsHandler.mode === "generator");

  // Informational only — matches script_generation.py's own rule
  // (_option_definition_line/_TASK_INDEXED_MODES): a task-indexed
  // connection is only ever regenerated when both this option's own
  // process and that connection's source are generator or array mode,
  // since that's the only combination where the source is guaranteed
  // to actually have a task N to pull from. Computed per connection —
  // a non-command-line input can gather from several sources whose
  // modes differ.
  const connectedSourceLabels = connectedSourceOptions.map(entry => {

    const entryIsTaskIndexed =
      !!ownerProcess && TASK_INDEXED_MODES.has(ownerProcess.optionsHandler.mode) &&
      TASK_INDEXED_MODES.has(entry.sourceProcess.optionsHandler.mode);

    if (entryIsTaskIndexed) {
      return `[${entry.sourceProcess.name};${entry.sourceOption.label};\${${idxVar}}]`;
    }
    if (isFanoutGather) {
      return `[${entry.sourceProcess.name};${entry.sourceOption.label};\${i}]`;
    }
    return `[${entry.sourceProcess.name};${entry.sourceOption.label}]`;

  });

  const connectedSourceLabel = connectedSourceLabels[0];

  // Consumer side of a scatter connection (see
  // script_generation.py's _option_definition_line "conn_opt" branch):
  // this option is connected to a fanout family declared on a
  // "standard" process, so this ("array"- or "generator"-mode) process's
  // own task count is implicitly forced to match whatever that family's
  // own count source computes — flagged here since nothing enforces it
  // structurally.
  const isScatterConsumer =
    !!connectedSourceOption &&
    connectedSourceOption.sourceProcess.optionsHandler.mode === "standard" &&
    isFanoutOption(connectedSourceOption.sourceOption.label);

  const scatterConsumerModeNoun =
    ownerProcess?.optionsHandler.mode === "generator" ? "generator" : "array";

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
  const isSharedDir = channel === "shared_dir";

  const [mirror, setMirror] =
    useState(option.mirror);

  // Union of the program's own declared shared dirs and every one it
  // inherits from a loaded module (see Program.availableSharedDirs) —
  // an imported program like golem_java.sh declares none of its own but
  // should still offer the ones it inherits.
  const selectableSharedDirs = [
    ...new Set([...program.sharedDirs, ...program.availableSharedDirs]),
  ];

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
    // Mirroring only makes sense on an output-direction fifo option
    // (see ProgramOption.mirror's docstring) — clear it as soon as
    // either condition stops holding, rather than leaving a stale
    // checked state hidden behind the checkbox's own conditional render.
    if (mirror && !(isFifo && direction === "output")) {
      setMirror(false);
    }
  }, [mirror, isFifo, direction]);

  useEffect(() => {
    // A connected option's value always comes from define_opt_from_proc_out,
    // never from its own define_value_desc_opt/define_fifo_opt call — the
    // channel describes how the *source* option got its value, not how
    // this one receives it, so a connected option's own channel is always
    // "none". "shared_dir" is the one exception: its value never depends
    // on a connection at all (see isValidProgramConnection), so a
    // "shared_dir" option keeps its channel regardless of edges.
    if (connectedSourceLabel && channel !== "none" && channel !== "shared_dir") {
      setChannel("none");
    }
  }, [connectedSourceLabel, channel]);

  const [description, setDescription] =
    useState(option.description);

  const [value, setValue] =
    useState(option.value);

  const [commandLine, setCommandLine] =
    useState(option.commandLine);

  const [fromProcessSpec, setFromProcessSpec] =
    useState(option.fromProcessSpec);

  const [mandatory, setMandatory] =
    useState(option.mandatory);

  useEffect(() => {
    // Not a channel (see ProgramOption.fromProcessSpec) — but, like a
    // connection, it's still incompatible with one: a process-spec-
    // sourced option's value comes from exactly one define_procspec_opt
    // call, which can't also be a define_value_desc_opt/define_fifo_opt/
    // define_opt_from_shared_dir call for the same label.
    if (fromProcessSpec && channel !== "none") {
      setChannel("none");
    }
  }, [fromProcessSpec, channel]);

  function handleSave() {

    const savedFromProcessSpec = !isFlag && fromProcessSpec;

    updateOption(processId, option.id, {
      label,
      direction: getOptionDirection(label),
      dataType,
      channel: isFlag ? "none" : isSharedDir ? "shared_dir" : connectedSourceLabel ? "none" : channel,
      mirror: !isFlag && isFifo && direction === "output" && !connectedSourceLabel && mirror,
      description,
      value: isFlag || isValueDescriptor ? "" : value,
      commandLine: commandLine && !savedFromProcessSpec,
      fromProcessSpec: savedFromProcessSpec,
      mandatory: commandLine && !savedFromProcessSpec && mandatory && !isFlag,
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
          width: 480,
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
            {" "}— this process's {scatterConsumerModeNoun} must produce exactly that many tasks.
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

        <div
          style={{
            display: "flex",
            gap: 16,
          }}
        >

          <div
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >

            <label>

              <input

                type="checkbox"

                checked={commandLine}

                onChange={(event) => {
                  const checked = event.target.checked;
                  setCommandLine(checked);
                  if (checked) {
                    setFromProcessSpec(false);
                  }
                }}

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

          </div>

          {!isFlag && (

            <div
              style={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                gap: 8,
                borderLeft: "1px solid #ddd",
                paddingLeft: 16,
              }}
            >

              <label>

                <input

                  type="checkbox"

                  checked={fromProcessSpec}

                  onChange={(event) => {
                    const checked = event.target.checked;
                    setFromProcessSpec(checked);
                    if (checked) {
                      setCommandLine(false);
                    }
                  }}

                />
                {" "}From process spec

              </label>

              <label style={{ color: fromProcessSpec ? undefined : "#999" }}>
                Process spec attribute
              </label>

              <select

                value={value}

                disabled={!fromProcessSpec}

                onChange={(event) =>
                  setValue(event.target.value)
                }

                style={{
                  width: "100%",
                }}

              >

                <option value="">
                  (select attribute)
                </option>

                {PROCESS_SPEC_ATTRIBUTE_NAMES.map(attr => (
                  <option key={attr} value={attr}>
                    {attr}
                  </option>
                ))}

              </select>

            </div>

          )}

        </div>

        {!isFlag && (

          <>

            <label style={{ color: manualMode || commandLine || fromProcessSpec ? "#999" : undefined }}>
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

                disabled={manualMode || commandLine || fromProcessSpec}

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

                <option value="shared_dir">
                  Shared directory
                </option>

              </select>

            )}

          </>

        )}

        {isFifo && direction === "output" && (

          <label style={{ display: "flex", alignItems: "center", gap: 6 }}>

            <input

              type="checkbox"

              checked={mirror}

              onChange={(event) =>
                setMirror(event.target.checked)
              }

            />

            Mirror (let "Watch FIFO" show this output live)

          </label>

        )}

        {!isFlag && (

          <>

            <label style={{ color: commandLine || fromProcessSpec || isValueDescriptor || manualMode ? "#999" : undefined }}>
              {isFifo ? "FIFO name" : "Value"}
            </label>

            {connectedSourceLabels.length > 0 ? (

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
                {isSharedDir
                  ? `[${value}]`
                  : connectedSourceLabels.length === 1
                  ? connectedSourceLabels[0]
                  : connectedSourceLabels.map((sourceLabel, index) => (
                      <div key={index}>
                        {sourceLabel}
                      </div>
                    ))}
              </div>

            ) : isSharedDir ? (

              <select

                value={value}

                disabled={commandLine || fromProcessSpec || manualMode}

                onChange={(event) =>
                  setValue(event.target.value)
                }

                style={{
                  width: "100%",
                }}

              >

                <option value="">
                  (select shared directory)
                </option>

                {selectableSharedDirs.map(dir => (
                  <option key={dir} value={dir}>
                    {dir}
                  </option>
                ))}

              </select>

            ) : (

              <input

                value={isValueDescriptor || fromProcessSpec || commandLine ? "" : value}

                disabled={commandLine || fromProcessSpec || isValueDescriptor || manualMode}

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
