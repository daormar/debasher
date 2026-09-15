import {
  Handle,
  Position,
} from "@xyflow/react";

import type {
  NodeProps,
  Node,
} from "@xyflow/react";

import type { ProgramProcessData } from "../adapters/reactFlowAdapter";
import { optionRow } from "../adapters/reactFlowAdapter";
import { fanoutBaseLabel, isFanoutOption } from "../models/option";
import { processNodeBackground } from "../models/processStatus";
import { useProgram } from "../store/ProgramContext";
import { groupColor } from "../utils/groupColor";

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
  const flippedOptionIds = data.flippedOptionIds;

  const { processStatuses } = useProgram();

  const background = processNodeBackground(processStatuses[process.name]);

  const optionsHandlerMode = process.optionsHandler.mode;
  const isStandard = optionsHandlerMode === "standard";
  const isTaskIndexed = optionsHandlerMode === "array" || optionsHandlerMode === "generator";
  const isManual = optionsHandlerMode === "manual";


  const topOptions =
    process.options.filter(
      option => optionRow(option, flippedOptionIds) === "top"
    );


  const bottomOptions =
    process.options.filter(
      option => optionRow(option, flippedOptionIds) === "bottom"
    );

  const groupSource = process.groupSource;
  const groupBorderColor = groupSource ? groupColor(groupSource.groupId) : null;


  const borderWidth = selected || groupBorderColor ? 2 : 1;
  const borderColor = selected ? "#1a73e8" : groupBorderColor ?? "#999";
  const borderStyle = isManual ? "dashed" : "solid";

  return (

    <div
      style={{
        minWidth: 180,
        padding: 12,
        border: `${borderWidth}px ${borderStyle} ${borderColor}`,
        // Double border signals a task-indexed options handler (array/generator),
        // which fans this process out into multiple tasks at run time.
        outline: isTaskIndexed ? `${borderWidth}px ${borderStyle} ${borderColor}` : undefined,
        outlineOffset: isTaskIndexed ? 3 : undefined,
        borderRadius: 8,
        background,
        position: "relative",
      }}
    >

      {/* Inputs, plus any output flipped here by a mutual-FIFO cycle, along the top edge */}

      <div
        style={{
          display: "flex",
          justifyContent: "center",
          flexWrap: "wrap",
          gap: 16,
          marginBottom: 8,
        }}
      >

        {topOptions.map(
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

                type={option.direction === "input" ? "target" : "source"}

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
          marginBottom: groupSource ? 2 : 12,
          textAlign: "center",
        }}
      >
        {process.name}
      </div>

      {groupSource && (
        <div
          title={`Added from program "${groupSource.programName}" via "Add program"`}
          style={{
            fontSize: 10,
            color: groupBorderColor ?? undefined,
            textAlign: "center",
            marginBottom: 10,
          }}
        >
          {groupSource.programName}
        </div>
      )}


      {/* Outputs, plus any input flipped here by a mutual-FIFO cycle, along the bottom edge */}

      <div
        style={{
          display: "flex",
          justifyContent: "center",
          flexWrap: "wrap",
          gap: 16,
          marginTop: 8,
        }}
      >

        {bottomOptions.map(
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

                type={option.direction === "input" ? "target" : "source"}

                position={Position.Bottom}

              />

            </div>

          )
        )}

      </div>


    </div>

  );
}
