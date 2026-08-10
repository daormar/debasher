import {
  Handle,
  Position,
} from "@xyflow/react";

import type {
  NodeProps,
  Node,
} from "@xyflow/react";

import type { WorkflowNodeData } from "../adapters/reactFlowAdapter";

export default function WorkflowNode({
  data,
}: NodeProps<Node<WorkflowNodeData>>) {

  const node = data.node;


  const inputHandles =
    node.handles.filter(
      handle => handle.direction === "input"
    );


  const outputHandles =
    node.handles.filter(
      handle => handle.direction === "output"
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

        {inputHandles.map(
          handle => (

            <div
              key={handle.id}
              style={{
                position: "relative",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                paddingTop: 10,
              }}
            >

              <Handle

                id={handle.id}

                type="target"

                position={Position.Top}

              />

              <span
                style={{
                  fontSize: 11,
                  whiteSpace: "nowrap",
                }}
              >
                {handle.label}
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
        {node.name}
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

        {outputHandles.map(
          handle => (

            <div
              key={handle.id}
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
                {handle.label}
              </span>

              <Handle

                id={handle.id}

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
