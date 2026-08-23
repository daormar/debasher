import { useState } from "react";

import { useWorkflow } from "../store/WorkflowContext";
import { NODE_LANGUAGES } from "./codeLanguages";
import CodeEditor from "./CodeEditor";
import OptionEditor from "./OptionEditor";
import ComputationalSpecsEditor from "./ComputationalSpecsEditor";
import AdditionalSpecsEditor from "./AdditionalSpecsEditor";
import type { NodeLanguage } from "../models/node";


export default function Inspector() {

  const {
    selectedNode,
    renameNode,
    addOption,
    removeOption,
    setNodeLanguage,
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


  if (!selectedNode) {

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
          Select a node
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
        Node
      </h3>


      <label>
        Name
      </label>


      <input

        value={selectedNode.name}

        onChange={(event) =>
          renameNode(
            selectedNode.id,
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

        {selectedNode.options.map(option => (

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
                    selectedNode.id,
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
          selectedNode.options.find(
            o => o.id === editingOptionId
          );

        if (!editingOption) {
          return null;
        }

        return (
          <OptionEditor
            nodeId={selectedNode.id}
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
            selectedNode.id,
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
            selectedNode.id,
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

        value={selectedNode.language}

        onChange={(event) =>
          setNodeLanguage(
            selectedNode.id,
            event.target.value as NodeLanguage
          )
        }

        style={{
          width: "100%",
          marginBottom: 8,
        }}

      >

        {NODE_LANGUAGES.map(({ value, label }) => (
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
          node={selectedNode}
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
          node={selectedNode}
          onClose={() => setComputationalSpecsOpen(false)}
        />
      )}


      {isAdditionalSpecsOpen && (
        <AdditionalSpecsEditor
          node={selectedNode}
          onClose={() => setAdditionalSpecsOpen(false)}
        />
      )}


    </aside>

  );

}
