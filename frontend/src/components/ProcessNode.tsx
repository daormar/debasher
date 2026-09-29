import {
  Handle,
  Position,
} from "@xyflow/react";

import type {
  NodeProps,
  Node,
} from "@xyflow/react";

import type { ProgramProcessData } from "../adapters/reactFlowAdapter";
import type { ProgramOption } from "../models/option";
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

/**
 * The handle of an option and its label, along the top or the bottom edge
 * of a canvas node, with the handle on the outer side of the label.
 */
function OptionHandle({
  option,
  row,
  isFanout,
}: {
  option: ProgramOption;
  row: "top" | "bottom";
  isFanout: boolean;
}) {

  const handle = (
    <Handle
      id={option.id}
      type={option.direction === "input" ? "target" : "source"}
      position={row === "top" ? Position.Top : Position.Bottom}
    />
  );

  return (

    <div
      style={{
        position: "relative",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        ...(row === "top" ? { paddingTop: 10 } : { paddingBottom: 10 }),
      }}
    >

      {row === "top" && handle}

      <span
        title={isFanout ? "Fanout family option (dynamic count)" : undefined}
        style={{
          fontSize: 11,
          whiteSpace: "nowrap",
        }}
      >
        <OptionLabel label={option.label} isFanout={isFanout} />
      </span>

      {row === "bottom" && handle}

    </div>

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
            <OptionHandle
              key={option.id}
              option={option}
              row="top"
              isFanout={isStandard && isFanoutOption(option.label)}
            />
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
            <OptionHandle
              key={option.id}
              option={option}
              row="bottom"
              isFanout={isStandard && isFanoutOption(option.label)}
            />
          )
        )}

      </div>


    </div>

  );
}
