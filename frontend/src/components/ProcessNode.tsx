import {
  Handle,
  Position,
} from "@xyflow/react";

import type {
  NodeProps,
  Node,
} from "@xyflow/react";

import type { ProgramProcessData } from "../adapters/reactFlowAdapter";
import { fanoutBaseLabel, isFanoutOption } from "../models/option";

function OptionLabel({ label, isFanout }: { label: string; isFanout: boolean }) {

  if (!isFanout) {
    return <>{label}</>;
  }

  return (
    <>
      {fanoutBaseLabel(label)}
      <span style={{ color: "#c0392b" }}>ith</span>
    </>
  );

}

export default function ProcessNode({
  data,
  selected,
}: NodeProps<Node<ProgramProcessData>>) {

  const process = data.process;

  const isStandard = process.optionsHandler.mode === "standard";


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
        border: selected ? "2px solid #1a73e8" : "1px solid #999",
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
                title={isStandard && isFanoutOption(option.label) ? "Fanout family option (dynamic count)" : undefined}
                style={{
                  fontSize: 11,
                  whiteSpace: "nowrap",
                }}
              >
                <OptionLabel label={option.label} isFanout={isStandard && isFanoutOption(option.label)} />
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
                title={isStandard && isFanoutOption(option.label) ? "Fanout family option (dynamic count)" : undefined}
                style={{
                  fontSize: 11,
                  whiteSpace: "nowrap",
                }}
              >
                <OptionLabel label={option.label} isFanout={isStandard && isFanoutOption(option.label)} />
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
