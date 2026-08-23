import { useState } from "react";

import { useWorkflow } from "../store/WorkflowContext";
import { PROCESS_LANGUAGES } from "./codeLanguages";
import CodeEditor from "./CodeEditor";
import OptionEditor from "./OptionEditor";
import ComputationalSpecsEditor from "./ComputationalSpecsEditor";
import AdditionalSpecsEditor from "./AdditionalSpecsEditor";
import type { ProcessLanguage } from "../models/process";


export default function Inspector() {

  const {
    selectedProcess,
    renameProcess,
    addOption,
    removeOption,
    setProcessLanguage,
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


      <label>
        Name
      </label>


      <input

        value={selectedProcess.name}

        onChange={(event) =>
          renameProcess(
            selectedProcess.id,
            event.target.value
          )
        }

        style={{
          width: "100%",
          marginBottom: 16,
        }}

      />


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
              {option.direction}: {option.label}
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

          if (!optionLabel.trim()) {
            return;
          }

          addOption(
            selectedProcess.id,
            "input",
            optionLabel
          );

          setOptionLabel("");

        }}

      >
        Add input
      </button>


      <button

        onClick={() => {

          if (!optionLabel.trim()) {
            return;
          }

          addOption(
            selectedProcess.id,
            "output",
            optionLabel
          );

          setOptionLabel("");

        }}

        style={{
          marginLeft: 8,
        }}

      >
        Add output
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
