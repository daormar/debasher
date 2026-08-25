import { useState } from "react";

import { useWorkflow } from "../store/WorkflowContext";
import { PROCESS_LANGUAGES } from "./codeLanguages";
import CodeEditor from "./CodeEditor";
import OptionEditor from "./OptionEditor";
import ComputationalSpecsEditor from "./ComputationalSpecsEditor";
import AdditionalSpecsEditor from "./AdditionalSpecsEditor";
import GeneratorConfigEditor from "./GeneratorConfigEditor";
import ArrayConfigEditor from "./ArrayConfigEditor";
import ManualConfigEditor from "./ManualConfigEditor";
import ProcessNameDialog from "./ProcessNameDialog";
import type { ProcessLanguage, OptionsHandlerMode } from "../models/process";
import { isValidOptionLabel } from "../models/option";


export default function Inspector() {

  const {
    selectedProcess,
    renameProcess,
    addOption,
    removeOption,
    setProcessLanguage,
    setOptionsHandler,
  } = useWorkflow();


  const [optionLabel, setOptionLabel] =
    useState("");

  const [isCodeEditorOpen, setCodeEditorOpen] =
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


  if (!selectedProcess) {

    return (

      <aside
        style={{
          width: 280,
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


  return (

    <aside
      style={{
        width: 280,
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


      {isChangeNameOpen && (
        <ProcessNameDialog
          title="Change process name"
          confirmLabel="Change"
          initialName={selectedProcess.name}
          onConfirm={(name) =>
            renameProcess(selectedProcess.id, name)
          }
          onClose={() => setChangeNameOpen(false)}
        />
      )}


      <h4>
        Options Handler
      </h4>


      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 4,
          marginBottom: 8,
        }}
      >

        {(["standard", "array", "generator", "manual"] as OptionsHandlerMode[]).map(mode => (

          <button

            key={mode}

            onClick={() =>
              setOptionsHandler(selectedProcess.id, {
                ...selectedProcess.optionsHandler,
                mode,
              })
            }

            style={{
              flex: "1 1 45%",
              fontWeight:
                selectedProcess.optionsHandler.mode === mode
                  ? "bold"
                  : "normal",
              background:
                selectedProcess.optionsHandler.mode === mode
                  ? "#ddd"
                  : "#fff",
            }}

          >
            {mode}
          </button>

        ))}

      </div>


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
          marginBottom: 16,
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


      <h4>
        Options
      </h4>


      <div>

        {selectedProcess.options.map(option => (

          <div
            key={option.id}
            style={{
              display: "flex",
              justifyContent: "space-between",
              marginBottom: 8,
            }}
          >

            <span>
              {option.label}
            </span>


            <span>

              <button

                onClick={() =>
                  setEditingOptionId(option.id)
                }

              >
                Edit
              </button>


              <button

                onClick={() =>
                  removeOption(
                    selectedProcess.id,
                    option.id
                  )
                }

                style={{
                  marginLeft: 4,
                }}

              >
                Remove
              </button>

            </span>


          </div>

        ))}

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

          if (!isValidOptionLabel(optionLabel)) {
            return;
          }

          addOption(
            selectedProcess.id,
            optionLabel
          );

          setOptionLabel("");

        }}

        disabled={!isValidOptionLabel(optionLabel)}

      >
        Add
      </button>


      <hr />


      <h4>
        Code
      </h4>


      <label>
        Language
      </label>


      <select

        value={selectedProcess.language}

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


      <button
        onClick={() => setCodeEditorOpen(true)}
      >
        Edit code
      </button>


      {isCodeEditorOpen && (
        <CodeEditor
          process={selectedProcess}
          onClose={() => setCodeEditorOpen(false)}
        />
      )}


      <h4>
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


        <button
          onClick={() => setAdditionalSpecsOpen(true)}
        >
          Additional Specifications
        </button>

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
