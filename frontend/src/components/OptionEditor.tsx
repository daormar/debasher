import { useState } from "react";

import { useProgram } from "../store/ProgramContext";
import type { ProgramOption } from "../models/option";
import type { ProgramType } from "../models/program";
import { findOptionLabelProblem } from "../models/process";
import { findFanoutCountProcesses } from "../models/connections";
import { DIRECTORY_CHANNELS, getOptionDirection, isFanoutOption, isValidOptionLabel } from "../models/option";
import {
  buildOptionChanges,
  canShapeTasks as canOptionShapeTasks,
  correctOptionDraft,
  createOptionDraft,
  describeFanoutCount,
  describeLockedDataType,
  findScatterCountSource,
  getLockedDataType,
  isScatterConsumer,
  listConnectedSources,
  type OptionDraft,
} from "../models/optionForm";
import {
  ChannelField,
  CountSourceField,
  DataTypeField,
  ScatterNotice,
  SourceFields,
  SubpathField,
  ValueField,
} from "./OptionEditorFields";

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

// The editor of an option: a draft of its fields, which a save writes with
// buildOptionChanges. What it decides lives in models/optionForm.ts, and
// its fields in OptionEditorFields.tsx.
export default function OptionEditor({ processId, option, manualMode, programType = "general", onClose }: Props) {

  const { program, updateOption } = useProgram();

  const isResident = programType === "resident";

  const ownerProcess = program.processes.find(process => process.id === processId);
  const ownerMode = ownerProcess?.optionsHandler.mode;

  // The outputs that the option reads, each with its sentinel; only an
  // input on a shared directory reads several, and the first one decides
  // what the connection gives the option
  const connectedSources = listConnectedSources(program, ownerProcess, option);
  const isConnected = connectedSources.length > 0;
  const connectedSource = connectedSources[0];

  // Every edit goes through the corrections, so the draft never holds a
  // combination that the editor does not offer
  const [draft, setDraft] = useState<OptionDraft>(() => correctOptionDraft(createOptionDraft(option), isConnected));
  const update = (fields: Partial<OptionDraft>) =>
    setDraft(current => correctOptionDraft({ ...current, ...fields }, isConnected));

  // The spaces around what is typed are dropped on save
  const label = draft.label.trim();
  const direction = getOptionDirection(label);
  const isFlag = draft.dataType === "None";

  // Shown once something is typed (see findOptionLabelProblem)
  const labelProblem = ownerProcess ? findOptionLabelProblem(ownerProcess, label, programType, option.id) : null;

  // A family as the label is typed, so that its count source shows at once
  const isFanout = isFanoutOption(draft.label) && ownerMode === "standard";

  // A task shaping option cannot count a family: no task receives it, and
  // the task needs the count to read the family
  const countSourceCandidates =
    ownerProcess?.options.filter(o => o.commandLine && !o.taskShaping && o.id !== option.id) ?? [];

  const lockedDataType = getLockedDataType(draft.channel, draft.commandLine, connectedSource);

  const canShapeTasks = canOptionShapeTasks(ownerProcess, option, draft, isFanout);

  // The shared directories that the program declares, and those of the
  // modules it loads (see Program.availableSharedDirs)
  const sharedDirs = [...new Set([...program.sharedDirs, ...program.availableSharedDirs])];

  function handleSave() {
    updateOption(
      processId,
      option.id,
      buildOptionChanges(draft, { isResident, isConnected, lockedDataType, canShapeTasks, isFanout }),
    );
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

        {isScatterConsumer(connectedSource) && (
          <ScatterNotice source={connectedSource} countSource={findScatterCountSource(connectedSource)} ownerMode={ownerMode} />
        )}

        <label>
          Label
        </label>

        <input
          value={draft.label}
          onChange={event => update({ label: event.target.value })}
          style={{ width: "100%" }}
        />

        {labelProblem && label && (
          <div style={{ color: "#b00020", fontSize: 13 }}>
            {labelProblem}
          </div>
        )}

        {isFanout && (
          <CountSourceField
            draft={draft}
            update={update}
            tasksCountText={describeFanoutCount(ownerProcess ? findFanoutCountProcesses(program, ownerProcess, option) : [])}
            candidates={countSourceCandidates}
          />
        )}

        <DataTypeField
          draft={draft}
          update={update}
          lockedDataType={lockedDataType}
          lockedText={describeLockedDataType(draft.channel, draft.commandLine, connectedSource)}
          direction={direction}
          isConnected={isConnected}
        />

        <label>
          Description
        </label>

        <textarea
          value={draft.description}
          onChange={event => update({ description: event.target.value })}
          rows={4}
          style={{ width: "100%" }}
        />

        <SourceFields
          draft={draft}
          update={update}
          isConnected={isConnected}
          direction={direction}
          canShapeTasks={canShapeTasks}
        />

        {!isFlag && (
          <ChannelField
            draft={draft}
            update={update}
            isConnected={isConnected}
            manualMode={manualMode}
            direction={direction}
            isResident={isResident}
          />
        )}

        {!isFlag && (
          <ValueField
            draft={draft}
            update={update}
            connectedSources={connectedSources}
            manualMode={manualMode}
            sharedDirs={sharedDirs}
          />
        )}

        {DIRECTORY_CHANNELS.has(draft.channel) && !draft.commandLine && !draft.fromProcessSpec && (
          <SubpathField draft={draft} update={update} manualMode={manualMode} ownerMode={ownerMode} />
        )}

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 8 }}>

          <button onClick={onClose}>
            Cancel
          </button>

          <button
            onClick={handleSave}
            disabled={!isValidOptionLabel(label) || labelProblem !== null}
          >
            Save
          </button>

        </div>

      </div>

    </div>

  );

}
