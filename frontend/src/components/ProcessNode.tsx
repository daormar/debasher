import {
  Handle,
  Position,
} from "@xyflow/react";

import type {
  NodeProps,
  Node,
} from "@xyflow/react";

import type { ProgramProcessData, WiringHandle } from "../adapters/reactFlowAdapter";
import type { ProgramOption } from "../models/option";
import type { ProgramProcess } from "../models/process";
import { configurationSource, noHoldFifosOption, nodeOptionRole, observesOutside } from "../models/node";
import { WIRING_EDGE_COLOR, optionRow } from "../adapters/reactFlowAdapter";
import { fanoutBaseLabel, isFanoutOption } from "../models/option";
import { processNodeBackground, residentProcessStatus } from "../models/processStatus";
import {
  HEAD_BAND_COLOR,
  InitiatorMark,
  NodeKindChip,
  ObserveMark,
  OutsideMark,
  SUPERVISOR_HEAD_BAND_COLOR,
  TriggerMark,
} from "./NodeMarks";
import { useProgram } from "../store/ProgramContext";
import { SELECTED_NODE_COLOR, groupColor } from "../utils/groupColor";

// What the tag of a hollow handle says, in full.
const VALUE_SOURCE_TITLE: Record<string, string> = {
  cmdline: "Given on the command line of the program",
  spec: "Taken from the process specifications",
  flag: "A flag that the module always gives",
  fixed: "A value that the module gives",
};

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
 * of a canvas node, with the handle on the outer side of the label. In a
 * resident program an option whose data cross the border of the program
 * carries a mark outside its handle, and an external input's handle takes
 * no connection. An option whose value comes from elsewhere than a
 * connection has a hollow handle, which takes none either, and a tag after
 * its label that says where its value comes from.
 */
function OptionHandle({
  option,
  row,
  isFanout,
  connectable = true,
  outsideMark,
  valueSource,
}: {
  option: ProgramOption;
  row: "top" | "bottom";
  isFanout: boolean;
  connectable?: boolean;
  outsideMark?: "externalInput" | "readOutside";
  valueSource?: string;
}) {

  const handle = (
    <Handle
      id={option.id}
      type={option.direction === "input" ? "target" : "source"}
      position={row === "top" ? Position.Top : Position.Bottom}
      isConnectable={connectable}
      {...(valueSource ? { style: { background: "#fff", border: "1px solid #555" } } : {})}
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

      {outsideMark && (
        <div
          style={{
            position: "absolute",
            left: "50%",
            transform: "translateX(-50%)",
            lineHeight: 0,
            ...(row === "top" ? { top: -18 } : { bottom: -18 }),
          }}
        >
          <OutsideMark kind={outsideMark} />
        </div>
      )}

      {row === "top" && handle}

      <span
        title={isFanout ? "Fanout family option (dynamic count)" : undefined}
        style={{
          fontSize: 11,
          whiteSpace: "nowrap",
        }}
      >
        <OptionLabel label={option.label} isFanout={isFanout} />
        {valueSource && (
          <span
            data-value-source={valueSource}
            title={VALUE_SOURCE_TITLE[valueSource]}
            style={{ marginLeft: 4, fontSize: 9, color: "#888" }}
          >
            {valueSource}
          </span>
        )}
      </span>

      {row === "bottom" && handle}

    </div>

  );

}

/**
 * A handle of the Supervisor wiring, read only: it accepts no connection,
 * and its label is set apart from those of the options. A trigger port is a
 * lightning bolt instead of the round handle, and the manual trigger port
 * of the Supervisor carries the mark of what is written from outside the
 * program, as an external input does.
 */
function WiringHandleView({ handle }: { handle: WiringHandle }) {

  const isTrigger = handle.kind === "trigger";

  const handleElement = (
    <Handle
      id={handle.id}
      type={handle.type}
      position={handle.row === "top" ? Position.Top : Position.Bottom}
      isConnectable={false}
      style={
        isTrigger
          ? { width: 12, height: 14, minWidth: 0, minHeight: 0, background: "none", border: "none", lineHeight: 0 }
          : { background: WIRING_EDGE_COLOR, borderColor: WIRING_EDGE_COLOR }
      }
    >
      {isTrigger && <TriggerMark />}
    </Handle>
  );

  return (

    <div
      data-wiring-handle={handle.kind}
      style={{
        position: "relative",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        ...(handle.row === "top" ? { paddingTop: 10 } : { paddingBottom: 10 }),
      }}
    >

      {handle.kind === "manual" && (
        <div
          style={{
            position: "absolute",
            left: "50%",
            transform: "translateX(-50%)",
            lineHeight: 0,
            top: -18,
          }}
        >
          <OutsideMark kind="externalInput" />
        </div>
      )}

      {handle.row === "top" && handleElement}

      <span
        style={{
          fontSize: 10,
          fontStyle: "italic",
          color: WIRING_EDGE_COLOR,
          whiteSpace: "nowrap",
        }}
      >
        {handle.label}
      </span>

      {handle.row === "bottom" && handleElement}

    </div>

  );

}

/**
 * The head of a canvas node of a resident program: its name, its node kind
 * and the marks of an initiator and of a node that observes the outside
 * world, on a band that groups them (see HEAD_BAND_COLOR).
 */
function ResidentHead({ process }: { process: ProgramProcess }) {

  const isSupervisor = process.nodeKind === "Supervisor";

  return (

    <div style={{ marginBottom: 12, textAlign: "center" }}>

      <div
        data-head={isSupervisor ? "supervisor" : "node"}
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 4,
          background: isSupervisor ? SUPERVISOR_HEAD_BAND_COLOR : HEAD_BAND_COLOR,
          borderRadius: 6,
          padding: "4px 8px",
        }}
      >

        <div style={{ fontWeight: "bold" }}>
          {process.name}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {process.nodeKind && <NodeKindChip kind={process.nodeKind} />}
          {process.initiator && <InitiatorMark />}
          {observesOutside(process) && <ObserveMark />}
        </div>

      </div>

    </div>

  );

}

export default function ProcessNode({
  data,
  selected,
}: NodeProps<Node<ProgramProcessData>>) {

  const process = data.process;
  const flippedOptionIds = data.flippedOptionIds;

  const { program, processStatuses } = useProgram();

  const isResident = program.programType === "resident";

  const status = processStatuses[process.name];

  const background = processNodeBackground(
    isResident ? residentProcessStatus(status) : status
  );

  const optionsHandlerMode = process.optionsHandler.mode;
  const isStandard = optionsHandlerMode === "standard";
  const isTaskIndexed = optionsHandlerMode === "array" || optionsHandlerMode === "generator";
  const isManual = optionsHandlerMode === "manual";


  // Every option has a handle. The Supervisor also has its flag
  // -no-hold-fifos, which script generation writes although the program
  // model does not hold it.
  const handleOptions = isResident && process.nodeKind === "Supervisor"
    ? [...process.options, noHoldFifosOption()]
    : process.options;

  const topOptions =
    handleOptions.filter(
      option => optionRow(option, flippedOptionIds) === "top"
    );


  const bottomOptions =
    handleOptions.filter(
      option => optionRow(option, flippedOptionIds) === "bottom"
    );

  // A business output with no connection is read outside the program. It
  // depends on the edges, which are not part of the structural key, so it
  // is read here from the store rather than from the canvas node's data.
  function outsideMark(option: ProgramOption): "externalInput" | "readOutside" | undefined {
    if (!isResident) {
      return undefined;
    }
    const role = nodeOptionRole(option);
    if (role === "externalInput") {
      return "externalInput";
    }
    if (role === "businessOutput" && !program.edges.some(edge => edge.sourceOptionId === option.id)) {
      return "readOutside";
    }
    return undefined;
  }

  // In a resident program only a business output and an input that a
  // connection can reach take a connection; a configuration option has a
  // hollow handle, tagged with where its value comes from.
  function optionHandle(option: ProgramOption, row: "top" | "bottom") {
    const role = isResident ? nodeOptionRole(option) : null;
    return (
      <OptionHandle
        key={option.id}
        option={option}
        row={row}
        isFanout={isStandard && isFanoutOption(option.label)}
        connectable={!role || role === "businessOutput" || role === "businessInput"}
        outsideMark={outsideMark(option)}
        valueSource={role === "configuration" ? configurationSource(option) : undefined}
      />
    );
  }

  // A resident program has no groups.
  const groupSource = isResident ? undefined : process.groupSource;
  const groupBorderColor = groupSource ? groupColor(groupSource.groupId) : null;


  const borderWidth = selected || groupBorderColor ? 2 : 1;
  const borderColor = selected ? SELECTED_NODE_COLOR : groupBorderColor ?? "#999";
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

        {topOptions.map(option => optionHandle(option, "top"))}

        {data.wiringHandles
          .filter(handle => handle.row === "top")
          .map(handle => <WiringHandleView key={handle.id} handle={handle} />)}

      </div>


      {isResident ? (

        <ResidentHead process={process} />

      ) : (

        <div
          style={{
            fontWeight: "bold",
            marginBottom: groupSource ? 2 : 12,
            textAlign: "center",
          }}
        >
          {process.name}
        </div>

      )}

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

        {bottomOptions.map(option => optionHandle(option, "bottom"))}

        {data.wiringHandles
          .filter(handle => handle.row === "bottom")
          .map(handle => <WiringHandleView key={handle.id} handle={handle} />)}

      </div>


    </div>

  );
}
