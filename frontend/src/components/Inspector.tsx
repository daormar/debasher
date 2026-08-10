import { useState } from "react";

import { useWorkflow } from "../store/WorkflowContext";


export default function Inspector() {

  const {
    selectedNode,
    renameNode,
    addHandle,
    removeHandle,
  } = useWorkflow();


  const [handleLabel, setHandleLabel] =
    useState("");


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


            <button

              onClick={() =>
                removeHandle(
                  selectedNode.id,
                  handle.id
                )
              }

            >
              Remove
            </button>


          </div>

        ))}

      </div>


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


    </aside>

  );

}
