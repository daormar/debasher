import type { CSSProperties } from "react";

import type { OptionChannel, OptionDataType, OptionDirection, ProgramOption } from "../models/option";
import { PROCESS_SPEC_ATTRIBUTE_NAMES } from "../models/option";
import type { ConnectedSource, OptionDraft } from "../models/optionForm";
import { listOfferedChannels, listOfferedDataTypes } from "../models/optionForm";
import type { OptionsHandlerMode } from "../models/process";

// The fields of the editor of an option (OptionEditor), one component per
// block of the dialog. Each shows part of the draft and changes it through
// `update`, which the editor corrects (see correctOptionDraft).

export type DraftUpdate = (fields: Partial<OptionDraft>) => void;

const FULL_WIDTH: CSSProperties = { width: "100%" };

// A value that the editor shows and does not let the user change.
const LOCKED_BOX: CSSProperties = {
  width: "100%",
  padding: "6px 8px",
  borderRadius: 4,
  border: "1px solid #bbb",
  color: "#888",
  boxSizing: "border-box",
};

const GREYED = "#999";

// The notices of an option that reads a fanout family (a scatter): its
// process has to run as many tasks as the family has members, which nothing
// enforces; without a count source option, the family counts the tasks of
// this process, and an array is costlier to count than a generator.
export function ScatterNotice({ source, countSource, ownerMode }: {
  source: ConnectedSource;
  countSource: ProgramOption | undefined;
  ownerMode: OptionsHandlerMode | undefined;
}) {
  if (countSource) {
    return (
      <p style={{ margin: 0, color: "#c0392b", fontSize: 13 }}>
        ⚠ This connection is wired to {source.process.name}'s{" "}
        fanout family "{source.option.label}", whose size is set by{" "}
        {`that process's own "${countSource.label}" option`}
        {", so this process's "}{ownerMode === "generator" ? "generator" : "array"} must produce exactly that many tasks.
      </p>
    );
  }
  if (ownerMode !== "array") {
    return null;
  }
  return (
    <p style={{ margin: 0, color: "#8a6d3b", fontSize: 13 }}>
      This connection is wired to {source.process.name}'s{" "}
      fanout family "{source.option.label}", which has no count source option{" "}
      and so counts the tasks of this process. The engine counts an array not defined yet by running its whole{" "}
      option definition again, so a generator is cheaper: put this process in generator mode if{" "}
      it can be, or choose a count source option for the family.
    </p>
  );
}

// The count source of a fanout family: a command line option of the
// process, or the number of tasks of the process at the other end.
export function CountSourceField({ draft, update, tasksCountText, candidates }: {
  draft: OptionDraft;
  update: DraftUpdate;
  tasksCountText: string;
  candidates: ProgramOption[];
}) {
  return (
    <>
      <label>
        Count source
      </label>
      <select
        value={draft.countSourceOptionId}
        onChange={event => update({ countSourceOptionId: event.target.value })}
        style={FULL_WIDTH}
      >
        <option value="">
          {tasksCountText}
        </option>
        {candidates.map(candidate => (
          <option key={candidate.id} value={candidate.id}>
            {candidate.label}
          </option>
        ))}
      </select>
    </>
  );
}

// The data type: a choice, or the one that the channel or the connection
// fixes, with what fixes it.
export function DataTypeField({ draft, update, lockedDataType, lockedText, direction, isConnected }: {
  draft: OptionDraft;
  update: DraftUpdate;
  lockedDataType: OptionDataType | null;
  lockedText: string;
  direction: OptionDirection;
  isConnected: boolean;
}) {
  return (
    <>
      <label>
        Data type
      </label>
      {lockedDataType ? (
        <div style={LOCKED_BOX}>
          {lockedDataType}{" "}
          {lockedText}
        </div>
      ) : (
        <select
          value={draft.dataType}
          onChange={event => update({ dataType: event.target.value as OptionDataType })}
          style={FULL_WIDTH}
        >
          {listOfferedDataTypes(direction, isConnected).map(type => (
            <option key={type} value={type}>
              {type === "None" ? "None (flag)" : type}
            </option>
          ))}
        </select>
      )}
    </>
  );
}

// Where the value comes from besides a channel or a connection: the command
// line (mandatory, or a task shaping option, which is always mandatory), or
// an attribute of the process specifications. The two exclude each other,
// and a connected input takes neither.
export function SourceFields({ draft, update, isConnected, direction, canShapeTasks }: {
  draft: OptionDraft;
  update: DraftUpdate;
  isConnected: boolean;
  direction: OptionDirection;
  canShapeTasks: boolean;
}) {
  const isFlag = draft.dataType === "None";
  const shapes = canShapeTasks && draft.taskShaping;
  return (
    <div style={{ display: "flex", gap: 16 }}>

      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 8 }}>

        <label>
          <input
            type="checkbox"
            checked={draft.commandLine}
            disabled={isConnected && !draft.commandLine}
            onChange={event => update(
              event.target.checked ? { commandLine: true, fromProcessSpec: false } : { commandLine: false }
            )}
          />
          {" "}Command line
        </label>

        <label style={{ color: draft.commandLine && !isFlag ? undefined : GREYED }}>
          <input
            type="checkbox"
            checked={isFlag ? false : draft.mandatory || shapes}
            disabled={!draft.commandLine || isFlag || shapes}
            onChange={event => update({ mandatory: event.target.checked })}
          />
          {" "}Mandatory
        </label>

        <label
          style={{ color: canShapeTasks ? undefined : GREYED }}
          title="Only the options handler reads it, to decide the tasks of the process: no task receives it. Always mandatory."
        >
          <input
            type="checkbox"
            checked={shapes}
            disabled={!canShapeTasks}
            onChange={event => update({ taskShaping: event.target.checked })}
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
              checked={draft.fromProcessSpec}
              disabled={(isConnected && !draft.fromProcessSpec) || direction === "output"}
              onChange={event => update(
                event.target.checked ? { fromProcessSpec: true, commandLine: false } : { fromProcessSpec: false }
              )}
            />
            {" "}From process spec
          </label>

          <label style={{ color: draft.fromProcessSpec ? undefined : GREYED }}>
            Process spec attribute
          </label>

          <select
            value={draft.value}
            disabled={!draft.fromProcessSpec}
            onChange={event => update({ value: event.target.value })}
            style={FULL_WIDTH}
          >
            <option value="">
              (select attribute)
            </option>
            {PROCESS_SPEC_ATTRIBUTE_NAMES.map(attribute => (
              <option key={attribute} value={attribute}>
                {attribute}
              </option>
            ))}
          </select>

        </div>
      )}

    </div>
  );
}

// The channel: a choice, or "From connection" for a connected input, whose
// connection gives it; and the mirror of a FIFO output of a general
// program.
export function ChannelField({ draft, update, isConnected, manualMode, direction, isResident }: {
  draft: OptionDraft;
  update: DraftUpdate;
  isConnected: boolean;
  manualMode: boolean;
  direction: OptionDirection;
  isResident: boolean;
}) {
  const disabled = manualMode || draft.commandLine || draft.fromProcessSpec;
  return (
    <>
      <label style={{ color: disabled ? GREYED : undefined }}>
        Channel
      </label>
      {isConnected ? (
        <div style={LOCKED_BOX}>
          From connection
        </div>
      ) : (
        <select
          value={draft.channel}
          disabled={disabled}
          onChange={event => update({ channel: event.target.value as OptionChannel })}
          style={FULL_WIDTH}
        >
          {listOfferedChannels(direction, isResident).map(entry => (
            <option key={entry.channel} value={entry.channel}>
              {entry.text}
            </option>
          ))}
        </select>
      )}
      {draft.channel === "fifo" && direction === "output" && !isResident && (
        <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <input
            type="checkbox"
            checked={draft.mirror}
            onChange={event => update({ mirror: event.target.checked })}
          />
          Mirror (let "Watch FIFO" show this output live)
        </label>
      )}
    </>
  );
}

// The value: what a connected input reads, the name of a shared directory,
// or a Bash word; none for a value descriptor, a process output directory,
// the command line or the process specifications.
export function ValueField({ draft, update, connectedSources, manualMode, sharedDirs }: {
  draft: OptionDraft;
  update: DraftUpdate;
  connectedSources: ConnectedSource[];
  manualMode: boolean;
  sharedDirs: string[];
}) {
  const isSharedDir = draft.channel === "shared_dir";
  const hasNoValue = draft.channel === "value_desc" || draft.channel === "process_outdir";
  const takenElsewhere = draft.commandLine || draft.fromProcessSpec;
  const subpath = draft.subpath.trim();
  return (
    <>
      <label style={{ color: takenElsewhere || draft.channel === "value_desc" || manualMode ? GREYED : undefined }}>
        {draft.channel === "fifo" ? "FIFO name" : "Value"}
      </label>
      {connectedSources.length > 0 ? (
        <div style={{ ...LOCKED_BOX, opacity: draft.commandLine ? 0.5 : 1 }}>
          {isSharedDir
            ? `[${subpath ? `${draft.value}/${subpath}` : draft.value}]`
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
          value={draft.value}
          disabled={takenElsewhere || manualMode}
          onChange={event => update({ value: event.target.value })}
          style={FULL_WIDTH}
        >
          <option value="">
            (select shared directory)
          </option>
          {sharedDirs.map(dir => (
            <option key={dir} value={dir}>
              {dir}
            </option>
          ))}
        </select>
      ) : (
        <input
          value={hasNoValue || takenElsewhere ? "" : draft.value}
          disabled={takenElsewhere || hasNoValue || manualMode}
          onChange={event => update({ value: event.target.value })}
          style={FULL_WIDTH}
        />
      )}
    </>
  );
}

// The subpath of an option on a directory channel: a directory of the
// task's own below the shared directory or the process output directory.
export function SubpathField({ draft, update, manualMode, ownerMode }: {
  draft: OptionDraft;
  update: DraftUpdate;
  manualMode: boolean;
  ownerMode: OptionsHandlerMode | undefined;
}) {
  return (
    <>
      <label style={{ color: manualMode ? GREYED : undefined }}>
        Subdirectory (optional)
      </label>
      <input
        value={draft.subpath}
        disabled={manualMode}
        placeholder={getSubpathHint(ownerMode)}
        onChange={event => update({ subpath: event.target.value })}
        style={FULL_WIDTH}
      />
      <div style={{ color: "#666", fontSize: 12 }}>
        {draft.channel === "shared_dir"
          ? "A directory of this task's own below the shared directory, which the engine creates; a task writes only into its own."
          : "A directory of this task's own below the output directory of the process, which the engine creates and empties before the task runs."}
      </div>
    </>
  );
}

// Takes the options handler mode of a process; returns the example
// subpaths that the subpath field suggests, with the variables that the
// mode provides.
function getSubpathHint(mode: OptionsHandlerMode | undefined): string {
  if (mode === "array") {
    return "e.g. ${task_idx} or ${array[$task_idx]}";
  }
  if (mode === "generator") {
    return "e.g. ${task_idx}";
  }
  return "e.g. results";
}
