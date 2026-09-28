import { useState } from "react";
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
  arrayMove,
} from "@dnd-kit/sortable";

import { useProgram } from "../store/ProgramContext";
import { PROCESS_LANGUAGES } from "./codeLanguages";
import CodeEditor from "./CodeEditor";
import AdditionalMethodsEditor from "./AdditionalMethodsEditor";
import OptionEditor from "./OptionEditor";
import OptionRow from "./OptionRow";
import ComputationalSpecsEditor from "./ComputationalSpecsEditor";
import AdditionalSpecsEditor from "./AdditionalSpecsEditor";
import GeneratorConfigEditor from "./GeneratorConfigEditor";
import ArrayConfigEditor from "./ArrayConfigEditor";
import ManualConfigEditor from "./ManualConfigEditor";
import ProcessNameDialog from "./ProcessNameDialog";
import NodeCodeEditor from "./NodeCodeEditor";
import { isReservedNodeOptionLabel } from "../models/node";
import type { ProcessLanguage, OptionsHandlerMode } from "../models/process";
import { isValidOptionLabel } from "../models/option";
import { computeFlippedOptionIds, optionRow } from "../adapters/reactFlowAdapter";


export default function Inspector() {

  const {
    program,
    selectedProcess,
    renameProcess,
    applyProcessInfo,
    setProcessDescription,
    addOption,
    removeOption,
    reorderOptionGroup,
    setProcessLanguage,
    setOptionsHandler,
    setInitiator,
  } = useProgram();

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 4 },
    })
  );


  const [optionLabel, setOptionLabel] =
    useState("");

  const [isCodeEditorOpen, setCodeEditorOpen] =
    useState(false);

  const [isAdditionalMethodsOpen, setAdditionalMethodsOpen] =
    useState(false);

  const [editingOptionId, setEditingOptionId] =
    useState<string | null>(null);

  const [isComputationalSpecsOpen, setComputationalSpecsOpen] =
    useState(false);

  const [isAdditionalSpecsOpen, setAdditionalSpecsOpen] =
    useState(false);

  const [isGeneratorConfigOpen, setGeneratorConfigOpen] =
    useState(false);

  const [isArrayConfigOpen, setArrayConfigOpen] =
    useState(false);

  const [isManualConfigOpen, setManualConfigOpen] =
    useState(false);

  const [isChangeNameOpen, setChangeNameOpen] =
    useState(false);

  const [isNodeCodeOpen, setNodeCodeOpen] =
    useState(false);


  if (!selectedProcess) {

    return (

      <aside
        style={{
          width: 340,
          padding: 16,
          borderLeft: "1px solid #ddd",
          background: "#fafafa",
        }}
      >

        <p>
          Select a process
        </p>

      </aside>

    );

  }


  // Which node edge (top/bottom) each option currently renders at —
  // matches ProcessNode exactly, including a mutual-FIFO cycle's
  // flipped return option (see computeFlippedOptionIds), so dragging
  // here can reorder options that are visually adjacent on the canvas
  // even when they're not the same direction.
  const flippedOptionIds = computeFlippedOptionIds(program);

  // A resident program writes its nodes in Python, in the parts of a node,
  // and offers neither the manual mode of the options handler nor the
  // additional specifications and methods of a general process. Of its
  // Supervisor, the user edits only the name, the description and the
  // computational specifications: script generation writes the rest.
  const isResident = program.programType === "resident";

  const isSupervisor = selectedProcess.nodeKind === "Supervisor";

  const optionsHandlerModes: OptionsHandlerMode[] = isResident
    ? ["standard", "array", "generator"]
    : ["standard", "array", "generator", "manual"];

  const optionLabelReserved = isResident && isReservedNodeOptionLabel(optionLabel);

  const canAddOption = isValidOptionLabel(optionLabel) && !optionLabelReserved;

  function handleOptionDragEnd(event: DragEndEvent) {

    const { active, over } = event;

    if (!selectedProcess || !over || active.id === over.id) {
      return;
    }

    const activeOption = selectedProcess.options.find(
      o => o.id === active.id
    );

    const overOption = selectedProcess.options.find(
      o => o.id === over.id
    );

    if (!activeOption || !overOption) {
      return;
    }

    const activeRow = optionRow(activeOption, flippedOptionIds);
    const overRow = optionRow(overOption, flippedOptionIds);

    if (activeRow !== overRow) {
      return;
    }

    const groupIds = selectedProcess.options
      .filter(o => optionRow(o, flippedOptionIds) === activeRow)
      .map(o => o.id);

    const newOrder = arrayMove(
      groupIds,
      groupIds.indexOf(activeOption.id),
      groupIds.indexOf(overOption.id)
    );

    reorderOptionGroup(
      selectedProcess.id,
      activeRow,
      newOrder
    );

  }


  return (

    <aside
      style={{
        width: 340,
        padding: 16,
        borderLeft: "1px solid #ddd",
        background: "#fafafa",
        overflowY: "auto",
      }}
    >

      <h3>
        Process
      </h3>


      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginBottom: 16,
        }}
      >

        <span style={{ flex: 1 }}>
          {selectedProcess.name}
        </span>

        <button onClick={() => setChangeNameOpen(true)}>
          Change name
        </button>

      </div>


      <textarea

        value={selectedProcess.description}

        onChange={(event) =>
          setProcessDescription(
            selectedProcess.id,
            event.target.value
          )
        }

        placeholder="Description"

        rows={3}

        style={{
          width: "100%",
          marginBottom: 8,
          fontFamily: "inherit",
          resize: "none",
          overflowY: "auto",
        }}

      />


      {isResident && (
        <div style={{ marginBottom: 8, fontSize: 14 }}>
          Node kind: <strong>{selectedProcess.nodeKind}</strong>
        </div>
      )}


      {isResident && !isSupervisor && (
        <label
          style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8, fontSize: 14 }}
          title="A round starts at an initiator. A program made of independent subgraphs needs one in each."
        >
          <input
            type="checkbox"
            checked={Boolean(selectedProcess.initiator)}
            onChange={(event) => setInitiator(selectedProcess.id, event.target.checked)}
          />
          Initiator (rounds start here)
        </label>
      )}


      {isSupervisor && (
        <p style={{ color: "#666", fontSize: 13 }}>
          Script generation writes all of the code and the options of the
          Supervisor, and derives its wiring to every node. Only its name,
          its description and its computational specifications are edited
          here.
        </p>
      )}


      {isChangeNameOpen && (
        <ProcessNameDialog
          title="Change process name"
          confirmLabel="Change"
          initialName={selectedProcess.name}
          existingNames={program.processes
            .filter(process => process.id !== selectedProcess.id)
            .map(process => process.name)}
          preamble={program.preamble}
          envVars={program.envVars}
          programType={program.programType}
          onConfirm={(name, info) => {
            renameProcess(selectedProcess.id, name);
            if (info) {
              applyProcessInfo(selectedProcess.id, info);
            }
          }}
          onClose={() => setChangeNameOpen(false)}
        />
      )}


      {!isSupervisor && (<>

      <h4 style={{ marginTop: 0, marginBottom: 8 }}>
        Options Handler
      </h4>


      <select

        value={selectedProcess.optionsHandler.mode}

        onChange={(event) =>
          setOptionsHandler(selectedProcess.id, {
            ...selectedProcess.optionsHandler,
            mode: event.target.value as OptionsHandlerMode,
          })
        }

        style={{
          width: "100%",
          marginBottom: 8,
        }}

      >

        {optionsHandlerModes.map(mode => (
          <option key={mode} value={mode}>
            {mode}
          </option>
        ))}

      </select>


      <button

        disabled={selectedProcess.optionsHandler.mode === "standard"}

        onClick={() => {
          if (selectedProcess.optionsHandler.mode === "generator") {
            setGeneratorConfigOpen(true);
          } else if (selectedProcess.optionsHandler.mode === "manual") {
            setManualConfigOpen(true);
          } else {
            setArrayConfigOpen(true);
          }
        }}

        style={{
          marginBottom: 8,
        }}

      >
        Configure
      </button>


      {isGeneratorConfigOpen && (
        <GeneratorConfigEditor
          process={selectedProcess}
          onClose={() => setGeneratorConfigOpen(false)}
        />
      )}


      {isArrayConfigOpen && (
        <ArrayConfigEditor
          process={selectedProcess}
          onClose={() => setArrayConfigOpen(false)}
        />
      )}


      {isManualConfigOpen && (
        <ManualConfigEditor
          process={selectedProcess}
          onClose={() => setManualConfigOpen(false)}
        />
      )}


      <h4 style={{ marginTop: 8, marginBottom: 8 }}>
        Options
      </h4>


      <div
        style={{
          maxHeight: 160,
          overflowY: "auto",
          border: "1px solid #ddd",
          borderRadius: 4,
          padding: 8,
          marginBottom: 8,
        }}
      >

        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleOptionDragEnd}
        >

          {(["top", "bottom"] as const).map(row => {

            const groupOptions = selectedProcess.options.filter(
              o => optionRow(o, flippedOptionIds) === row
            );

            if (groupOptions.length === 0) {
              return null;
            }

            return (
              <SortableContext
                key={row}
                items={groupOptions.map(o => o.id)}
                strategy={verticalListSortingStrategy}
              >

                {groupOptions.map(option => (
                  <OptionRow
                    key={option.id}
                    option={option}
                    isFanoutMode={selectedProcess.optionsHandler.mode === "standard"}
                    onEdit={() => setEditingOptionId(option.id)}
                    onRemove={() =>
                      removeOption(
                        selectedProcess.id,
                        option.id
                      )
                    }
                  />
                ))}

              </SortableContext>
            );

          })}

        </DndContext>

      </div>


      {editingOptionId && (() => {

        const editingOption =
          selectedProcess.options.find(
            o => o.id === editingOptionId
          );

        if (!editingOption) {
          return null;
        }

        return (
          <OptionEditor
            processId={selectedProcess.id}
            option={editingOption}
            manualMode={selectedProcess.optionsHandler.mode === "manual"}
            programType={program.programType}
            onClose={() => setEditingOptionId(null)}
          />
        );

      })()}


      <hr />


      <input

        placeholder="Option label"

        value={optionLabel}

        onChange={(event) =>
          setOptionLabel(
            event.target.value
          )
        }

        style={{
          width: "100%",
          marginBottom: 8,
        }}

      />


      <button

        onClick={() => {

          if (!canAddOption) {
            return;
          }

          addOption(
            selectedProcess.id,
            optionLabel
          );

          setOptionLabel("");

        }}

        disabled={!canAddOption}

      >
        Add
      </button>


      {optionLabelReserved && (
        <div style={{ color: "#b00020", fontSize: 13, marginTop: 4 }}>
          {optionLabel.trim()} belongs to the Supervisor wiring, which script
          generation writes: choose another label.
        </div>
      )}


      <hr />


      <h4 style={{ marginTop: 16, marginBottom: 8 }}>
        Code
      </h4>


      {isResident ? (

        <>

          <div style={{ fontSize: 14, marginBottom: 8 }}>
            Python: a class that derives from {selectedProcess.nodeKind}, in parts
          </div>

          <button onClick={() => setNodeCodeOpen(true)}>
            Edit node code
          </button>

          {isNodeCodeOpen && (
            <NodeCodeEditor
              process={selectedProcess}
              onClose={() => setNodeCodeOpen(false)}
            />
          )}

        </>

      ) : (<>

      <label>
        Language
      </label>


      <select

        value={selectedProcess.language}

        disabled={Boolean(selectedProcess.additionalSpecs.alias || selectedProcess.additionalSpecs.externalAlias)}

        onChange={(event) =>
          setProcessLanguage(
            selectedProcess.id,
            event.target.value as ProcessLanguage
          )
        }

        style={{
          width: "100%",
          marginBottom: 8,
        }}

      >

        {PROCESS_LANGUAGES.map(({ value, label }) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}

      </select>


      {(selectedProcess.additionalSpecs.alias || selectedProcess.additionalSpecs.externalAlias) ? (

        <div
          style={{
            width: "100%",
            padding: "6px 8px",
            borderRadius: 4,
            border: "1px solid #bbb",
            color: "#888",
            boxSizing: "border-box",
            marginBottom: 8,
          }}
        >
          Implementation comes from {selectedProcess.additionalSpecs.alias ? "the alias" : "the external alias"}
        </div>

      ) : (

        <button
          onClick={() => setCodeEditorOpen(true)}
        >
          Edit code
        </button>

      )}


      <button
        style={{ marginLeft: 16 }}
        onClick={() => setAdditionalMethodsOpen(true)}
      >
        Configure additional methods
      </button>


      {isCodeEditorOpen && (
        <CodeEditor
          process={selectedProcess}
          onClose={() => setCodeEditorOpen(false)}
        />
      )}


      {isAdditionalMethodsOpen && (
        <AdditionalMethodsEditor
          process={selectedProcess}
          onClose={() => setAdditionalMethodsOpen(false)}
        />
      )}

      </>)}

      </>)}


      <h4 style={{ marginTop: 16, marginBottom: 8 }}>
        Specifications
      </h4>


      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-start",
          gap: 8,
        }}
      >

        <button
          onClick={() => setComputationalSpecsOpen(true)}
        >
          Computational Specifications
        </button>


        {!isResident && (
          <button
            onClick={() => setAdditionalSpecsOpen(true)}
          >
            Additional Specifications
          </button>
        )}

      </div>


      {isComputationalSpecsOpen && (
        <ComputationalSpecsEditor
          process={selectedProcess}
          onClose={() => setComputationalSpecsOpen(false)}
        />
      )}


      {isAdditionalSpecsOpen && (
        <AdditionalSpecsEditor
          process={selectedProcess}
          onClose={() => setAdditionalSpecsOpen(false)}
        />
      )}


    </aside>

  );

}
