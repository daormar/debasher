import {
  Handle,
  Position,
} from "@xyflow/react";

import type {
  NodeProps,
  Node,
} from "@xyflow/react";

import type { WorkflowProcessData } from "../adapters/reactFlowAdapter";

export default function ProcessNode({
  data,
}: NodeProps<Node<WorkflowProcessData>>) {

  const process = data.process;


  const inputOptions =
    process.options.filter(
      option => option.direction === "input"
    );


  const outputOptions =
    process.options.filter(
      option => option.direction === "output"
    );


  return (

    <div
      style={{
        minWidth: 180,
        padding: 12,
        border: "1px solid #999",
        borderRadius: 8,
        background: "white",
        position: "relative",
      }}
    >

      {/* Inputs, along the top edge */}

      <div
        style={{
          display: "flex",
          justifyContent: "center",
          flexWrap: "wrap",
          gap: 16,
          marginBottom: 8,
        }}
      >

        {inputOptions.map(
          option => (

            <div
              key={option.id}
              style={{
                position: "relative",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                paddingTop: 10,
              }}
            >

              <Handle

                id={option.id}

                type="target"

                position={Position.Top}

              />

              <span
                style={{
                  fontSize: 11,
                  whiteSpace: "nowrap",
                }}
              >
                {option.label}
              </span>

            </div>

          )
        )}

      </div>


      <div
        style={{
          fontWeight: "bold",
          marginBottom: 12,
          textAlign: "center",
        }}
      >
        {process.name}
      </div>


      {/* Outputs, along the bottom edge */}

      <div
        style={{
          display: "flex",
          justifyContent: "center",
          flexWrap: "wrap",
          gap: 16,
          marginTop: 8,
        }}
      >

        {outputOptions.map(
          option => (

            <div
              key={option.id}
              style={{
                position: "relative",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                paddingBottom: 10,
              }}
            >

              <span
                style={{
                  fontSize: 11,
                  whiteSpace: "nowrap",
                }}
              >
                {option.label}
              </span>

              <Handle

                id={option.id}

                type="source"

                position={Position.Bottom}

              />

            </div>

          )
        )}

      </div>


    </div>

  );
}
