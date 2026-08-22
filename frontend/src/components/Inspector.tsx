import { useState } from "react";

import { useWorkflow } from "../store/WorkflowContext";
import { NODE_LANGUAGES } from "./codeLanguages";
import CodeEditor from "./CodeEditor";
import HandleEditor from "./HandleEditor";
import type { NodeLanguage } from "../models/node";


export default function Inspector() {

  const {
    selectedNode,
    renameNode,
    addHandle,
    removeHandle,
    setNodeLanguage,
  } = useWorkflow();


  const [handleLabel, setHandleLabel] =
    useState("");

  const [isCodeEditorOpen, setCodeEditorOpen] =
    useState(false);

  const [editingHandleId, setEditingHandleId] =
    useState<string | null>(null);


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
        Handles
      </h4>


      <div>

        {selectedNode.handles.map(handle => (

          <div
            key={handle.id}
            style={{
              display: "flex",
              justifyContent: "space-between",
              marginBottom: 8,
            }}
          >

            <span>
              {handle.direction}: {handle.label}
            </span>


            <span>

              <button

                onClick={() =>
                  setEditingHandleId(handle.id)
                }

              >
                Edit
              </button>


              <button

                onClick={() =>
                  removeHandle(
                    selectedNode.id,
                    handle.id
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


      {editingHandleId && (() => {

        const editingHandle =
          selectedNode.handles.find(
            h => h.id === editingHandleId
          );

        if (!editingHandle) {
          return null;
        }

        return (
          <HandleEditor
            nodeId={selectedNode.id}
            handle={editingHandle}
            onClose={() => setEditingHandleId(null)}
          />
        );

      })()}


      <hr />


      <input

        placeholder="Handle label"

        value={handleLabel}

        onChange={(event) =>
          setHandleLabel(
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

          if (!handleLabel.trim()) {
            return;
          }

          addHandle(
            selectedNode.id,
            "input",
            handleLabel
          );

          setHandleLabel("");

        }}

      >
        Add input
      </button>


      <button

        onClick={() => {

          if (!handleLabel.trim()) {
            return;
          }

          addHandle(
            selectedNode.id,
            "output",
            handleLabel
          );

          setHandleLabel("");

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


    </aside>

  );

}
