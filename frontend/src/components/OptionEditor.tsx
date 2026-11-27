import { useEffect, useState } from "react";

import { useProgram } from "../store/ProgramContext";
import type {
  ProgramOption,
  OptionDataType,
  OptionChannel,
} from "../models/option";
import type { ProgramType } from "../models/program";
import { findOptionLabelProblem } from "../models/process";
import { findFanoutCountProcesses } from "../models/connections";
import {
  getOptionDirection,
  isValidOptionLabel,
  isFanoutOption,
  PROCESS_SPEC_ATTRIBUTE_NAMES,
} from "../models/option";
import {
  buildOptionChanges,
  canShapeTasks as canOptionShapeTasks,
  describeFanoutCount,
  describeLockedDataType,
  findScatterCountSource,
  getLockedDataType,
  isScatterConsumer as isScatterConsumerOf,
  listConnectedSources,
  listOfferedChannels,
  listOfferedDataTypes,
} from "../models/optionForm";

interface Props {
  processId: string;
  option: ProgramOption;
  manualMode: boolean;
  // In a resident program an option is a business output (an output
  // through a FIFO), a business input (an input that a connection reaches),
  // an external input (an input through a FIFO written from outside the
  // program, tagged "external") or a configuration option (a direct
  // value). Value descriptors, shared directories and FIFO mirrors are not
  // offered, and the labels of the Supervisor wiring are reserved.
  programType?: ProgramType;
  onClose: () => void;
}

export default function OptionEditor({ processId, option, manualMode, programType = "general", onClose }: Props) {

  const { program, updateOption } = useProgram();

  const isResident = programType === "resident";

  const ownerProcess = program.processes.find(
    process => process.id === processId
  );

  // The outputs that the option reads, each with its sentinel; only an
  // input on a shared directory reads several, and the first one decides
  // what the connection gives the option
  const connectedSources = listConnectedSources(program, ownerProcess, option);
  const isConnected = connectedSources.length > 0;
  const connectedSource = connectedSources[0];

  // The consumer of a scatter: its process has to run as many tasks as the
  // family it reads has members, which nothing enforces, so it is said
  const isScatterConsumer = isScatterConsumerOf(connectedSource);
  const scatterConsumerModeNoun =
    ownerProcess?.optionsHandler.mode === "generator" ? "generator" : "array";
  const scatterCountSource = isScatterConsumer ? findScatterCountSource(connectedSource) : undefined;

  const [label, setLabel] =
    useState(option.label);

  // The spaces around what is typed are dropped on save
  const direction = getOptionDirection(label.trim());

  // Shown once something is typed (see findOptionLabelProblem)
  const labelProblem = ownerProcess
    ? findOptionLabelProblem(ownerProcess, label.trim(), programType, option.id)
    : null;

  // Reactive to the label as it's being typed, so the "Count source"
  // field appears/disappears live as the user adds/removes the "-ith"
  // suffix, rather than only after saving.
  const isFanout = isFanoutOption(label) && ownerProcess?.optionsHandler.mode === "standard";

  // A task shaping option cannot count a family: no task receives it, and
  // the task needs the count to read the family
  const countSourceCandidates =
    ownerProcess?.options.filter(o => o.commandLine && !o.taskShaping && o.id !== option.id) ?? [];

  // Without a count source option, the family counts the tasks of the
  // process at the other end of its connections (see
  // findFanoutCountProcesses)
  const tasksCountText = describeFanoutCount(
    ownerProcess ? findFanoutCountProcesses(program, ownerProcess, option) : []
  );

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
  const isProcessOutdir = channel === "process_outdir";

  // The subpath of a shared subdirectory or task subdirectory, for the two
  // option channels that name a directory
  const [subpath, setSubpath] =
    useState(option.subpath ?? "");

  const [mirror, setMirror] =
    useState(option.mirror);

  // Union of the program's own declared shared dirs and every one it
  // inherits from a loaded module (see Program.availableSharedDirs):
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
    if (direction === "input" && (channel === "value_desc" || channel === "process_outdir")) {
      setChannel("none");
    }
  }, [direction, channel]);

  useEffect(() => {
    // Mirroring only makes sense on an output-direction fifo option
    // (see ProgramOption.mirror's docstring), clear it as soon as
    // either condition stops holding, rather than leaving a stale
    // checked state hidden behind the checkbox's own conditional render.
    if (mirror && !(isFifo && direction === "output")) {
      setMirror(false);
    }
  }, [mirror, isFifo, direction]);

  useEffect(() => {
    // A connected input takes the channel of its connection (see
    // getConnectedInputChannel): "none", or "shared_dir" when it reads a
    // shared directory
    if (isConnected && channel !== "none" && channel !== "shared_dir") {
      setChannel("none");
    }
  }, [isConnected, channel]);

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

  const [taskShaping, setTaskShaping] =
    useState(option.taskShaping ?? false);

  // The data type that the option channel or the connection fixes, shown
  // instead of a choice (see getLockedDataType)
  const lockedDataType = getLockedDataType(channel, commandLine, connectedSource);

  const canShapeTasks = canOptionShapeTasks(ownerProcess, option, { label, dataType, commandLine }, isFanout);

  useEffect(() => {
    // Not a channel (see ProgramOption.fromProcessSpec), but, like a
    // connection, it's still incompatible with one: a process-spec-
    // sourced option's value comes from exactly one define_procspec_opt
    // call, which can't also be a define_value_desc_opt/define_fifo_opt/
    // define_opt_from_shared_dir call for the same label.
    if (fromProcessSpec && channel !== "none") {
      setChannel("none");
    }
  }, [fromProcessSpec, channel]);

  useEffect(() => {
    // An output names what the process produces, never an attribute of its
    // specifications (script_generation.py refuses the combination)
    if (direction === "output" && fromProcessSpec) {
      setFromProcessSpec(false);
    }
  }, [direction, fromProcessSpec]);

  function handleSave() {

    updateOption(processId, option.id, buildOptionChanges(
      {
        label, dataType, channel, subpath, mirror, description, value,
        commandLine, fromProcessSpec, mandatory, taskShaping, countSourceOptionId,
      },
      { isResident, isConnected, lockedDataType, canShapeTasks, isFanout },
    ));

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

        {isScatterConsumer && scatterCountSource && (
          <p style={{ margin: 0, color: "#c0392b", fontSize: 13 }}>
            ⚠ This connection is wired to {connectedSource.process.name}'s{" "}
            fanout family "{connectedSource.option.label}", whose size is set by{" "}
            {`that process's own "${scatterCountSource.label}" option`}
            {", so this process's "}{scatterConsumerModeNoun} must produce exactly that many tasks.
          </p>
        )}

        {/* Without a count source option, the family counts the tasks of
            this process; an array is costlier to count than a generator */}
        {isScatterConsumer && !scatterCountSource && ownerProcess?.optionsHandler.mode === "array" && (
          <p style={{ margin: 0, color: "#8a6d3b", fontSize: 13 }}>
            This connection is wired to {connectedSource.process.name}'s{" "}
            fanout family "{connectedSource.option.label}", which has no count source option{" "}
            and so counts the tasks of this process. The engine counts an array not defined yet by running its whole{" "}
            option definition again, so a generator is cheaper: put this process in generator mode if{" "}
            it can be, or choose a count source option for the family.
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

        {labelProblem && label.trim() && (
          <div style={{ color: "#b00020", fontSize: 13 }}>
            {labelProblem}
          </div>
        )}

        {isFanout && (

          <>

            <label>
              Count source
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
                {tasksCountText}
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

        {lockedDataType ? (

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
            {lockedDataType}{" "}
            {describeLockedDataType(channel, commandLine, connectedSource)}
          </div>

        ) : (

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

            {/* A flag takes no connection (see isValidEdge), nor
                does a command line option or one from the process spec. */}
            {listOfferedDataTypes(direction, isConnected).map(type => (
              <option key={type} value={type}>
                {type === "None" ? "None (flag)" : type}
              </option>
            ))}

          </select>

        )}

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

                disabled={isConnected && !commandLine}

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

                checked={isFlag ? false : mandatory || (canShapeTasks && taskShaping)}

                disabled={!commandLine || isFlag || (canShapeTasks && taskShaping)}

                onChange={(event) =>
                  setMandatory(event.target.checked)
                }

              />
              {" "}Mandatory

            </label>

            <label
              style={{ color: canShapeTasks ? undefined : "#999" }}
              title="Only the options handler reads it, to decide the tasks of the process: no task receives it. Always mandatory."
            >

              <input

                type="checkbox"

                checked={canShapeTasks && taskShaping}

                disabled={!canShapeTasks}

                onChange={(event) =>
                  setTaskShaping(event.target.checked)
                }

              />
              {" "}Task shaping

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

                  disabled={(isConnected && !fromProcessSpec) || direction === "output"}

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

            {isConnected ? (

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

                {listOfferedChannels(direction, isResident).map(entry => (
                  <option key={entry.channel} value={entry.channel}>
                    {entry.text}
                  </option>
                ))}

              </select>

            )}

          </>

        )}

        {isFifo && direction === "output" && !isResident && (

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

            {isConnected ? (

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
                  ? `[${subpath.trim() ? `${value}/${subpath.trim()}` : value}]`
                  : connectedSources.length === 1
                  ? connectedSources[0].sentinel
                  : connectedSources.map((source, index) => (
                      <div key={index}>
                        {source.sentinel}
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

                value={isValueDescriptor || isProcessOutdir || fromProcessSpec || commandLine ? "" : value}

                disabled={commandLine || fromProcessSpec || isValueDescriptor || isProcessOutdir || manualMode}

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

        {(isSharedDir || isProcessOutdir) && !commandLine && !fromProcessSpec && (

          <>

            <label style={{ color: manualMode ? "#999" : undefined }}>
              Subdirectory (optional)
            </label>

            <input

              value={subpath}

              disabled={manualMode}

              placeholder={subpathHint(ownerProcess?.optionsHandler.mode)}

              onChange={(event) =>
                setSubpath(event.target.value)
              }

              style={{
                width: "100%",
              }}

            />

            <div style={{ color: "#666", fontSize: 12 }}>
              {isSharedDir
                ? "A directory of this task's own below the shared directory, which the engine creates; a task writes only into its own."
                : "A directory of this task's own below the output directory of the process, which the engine creates and empties before the task runs."}
            </div>

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
            disabled={!isValidOptionLabel(label.trim()) || labelProblem !== null}
          >
            Save
          </button>

        </div>

      </div>

    </div>

  );

}

// The example subpaths that the subpath field suggests, with the variables
// that the options handler mode provides
function subpathHint(mode: string | undefined): string {
  if (mode === "array") {
    return "e.g. ${task_idx} or ${array[$task_idx]}";
  }
  if (mode === "generator") {
    return "e.g. ${task_idx}";
  }
  return "e.g. results";
}
