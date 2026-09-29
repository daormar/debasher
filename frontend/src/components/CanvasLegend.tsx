import { useState } from "react";
import type { ReactNode } from "react";

import { WIRING_EDGE_COLOR } from "../adapters/reactFlowAdapter";
import type { ProgramType } from "../models/program";
import {
  GENERAL_STATUS_MEANINGS,
  RESIDENT_STATUS_MEANINGS,
  processNodeBackground,
} from "../models/processStatus";
import type { ProcessRunStatus } from "../models/processStatus";
import { InitiatorMark, NodeKindChip, ObserveMark, OutsideMark, TriggerMark } from "./NodeMarks";

function LegendRow({ mark, children }: { mark: ReactNode; children: ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
      <div style={{ flex: "0 0 auto", minWidth: 24, display: "flex", justifyContent: "center" }}>
        {mark}
      </div>
      <div>{children}</div>
    </div>
  );
}

function Heading({ children }: { children: ReactNode }) {
  return <div style={{ fontWeight: "bold", marginTop: 4 }}>{children}</div>;
}

function StatusRows({ meanings }: { meanings: { status: ProcessRunStatus; meaning: string }[] }) {
  return (
    <>
      {meanings.map(({ status, meaning }) => (
        <LegendRow
          key={status}
          mark={
            <span
              style={{
                display: "inline-block",
                width: 18,
                height: 12,
                border: "1px solid #999",
                borderRadius: 3,
                background: processNodeBackground(status),
              }}
            />
          }
        >
          <b>{status}</b>: {meaning}
        </LegendRow>
      ))}
    </>
  );
}

// A small box drawn with the border of a canvas node.
function BorderSample({ border, double }: { border: string; double?: boolean }) {
  return (
    <span
      style={{
        display: "inline-block",
        width: 16,
        height: 10,
        border,
        borderRadius: 2,
        outline: double ? border : undefined,
        outlineOffset: double ? 2 : undefined,
      }}
    />
  );
}

// The hollow handle of an option that takes no connection.
function HollowHandleSample() {
  return (
    <span
      style={{
        display: "inline-block",
        width: 6,
        height: 6,
        borderRadius: "50%",
        border: "1px solid #555",
        background: "#fff",
      }}
    />
  );
}

// A short edge, as a polyline in a 24 by 12 box.
function EdgeSample({ points, dash, color = "#999" }: { points: string; dash?: string; color?: string }) {
  return (
    <svg width={24} height={12} viewBox="0 0 24 12">
      <polyline points={points} fill="none" stroke={color} strokeWidth={1.5} strokeDasharray={dash} />
    </svg>
  );
}

/** What the canvas of a general program draws. */
function GeneralLegend() {
  return (
    <>
      <Heading>Process status</Heading>
      <StatusRows meanings={GENERAL_STATUS_MEANINGS} />

      <Heading>Borders</Heading>
      <LegendRow mark={<BorderSample border="1px solid #999" double />}>
        Double: array or generator mode, a task for each element or index.
      </LegendRow>
      <LegendRow mark={<BorderSample border="1px dashed #999" />}>
        Dashed: manual mode.
      </LegendRow>
      {/* Red, with the saturation and lightness of every group color (see
          groupColor). */}
      <LegendRow mark={<BorderSample border="2px solid hsl(0, 65%, 45%)" />}>
        Colored, with a badge: a group brought in by "Add program".
      </LegendRow>

      <Heading>Edges</Heading>
      <LegendRow mark={<EdgeSample points="0,6 24,6" />}>
        From a file or a value.
      </LegendRow>
      <LegendRow mark={<EdgeSample points="0,6 24,6" dash="6 4" />}>
        From a FIFO.
      </LegendRow>
      <LegendRow
        mark={
          <svg width={24} height={12} viewBox="0 0 24 12">
            <polygon points="0,5 24,1 24,11 0,7" fill="#999" />
          </svg>
        }
      >
        A fanout: one becomes many, narrow at the fanout family.
      </LegendRow>
      <LegendRow mark={<EdgeSample points="4,11 4,9 22,9 22,1 10,1 10,3" />}>
        Around the processes, on the right: an edge that goes back up, or a
        self-loop around its own process.
      </LegendRow>
      <LegendRow
        mark={<span style={{ fontSize: 10 }}>-out<span style={{ color: "#c0392b" }}>ith</span></span>}
      >
        A fanout family: as many options as another option says.
      </LegendRow>
    </>
  );
}

/** What the canvas of a resident program draws. */
function ResidentLegend() {
  return (
    <>
      <Heading>Process status</Heading>
      <StatusRows meanings={RESIDENT_STATUS_MEANINGS} />

      <Heading>Marks</Heading>
      <LegendRow mark={<NodeKindChip kind="FBPProcess" />}>
        The node kind, in the blue gray of the wiring for the Supervisor.
      </LegendRow>
      <LegendRow mark={<InitiatorMark />}>
        An initiator: rounds start there.
      </LegendRow>
      <LegendRow mark={<ObserveMark />}>
        Observes the world outside the program.
      </LegendRow>
      <LegendRow mark={<OutsideMark kind="externalInput" />}>
        Above an input: written from outside the program.
      </LegendRow>
      <LegendRow mark={<OutsideMark kind="readOutside" />}>
        Below an output: read outside the program.
      </LegendRow>
      <LegendRow mark={<HollowHandleSample />}>
        A hollow handle takes no connection: its tag says where the value
        comes from (cmdline, spec, flag or fixed).
      </LegendRow>
      <LegendRow mark={<TriggerMark />}>
        A trigger port of the Supervisor wiring.
      </LegendRow>
      <LegendRow mark={<EdgeSample points="0,6 24,6" dash="2 4" color={WIRING_EDGE_COLOR} />}>
        The Supervisor wiring, read only, shown from the menu of the
        Supervisor.
      </LegendRow>
    </>
  );
}

/**
 * The legend of the canvas, which the user can fold: what each process
 * status means in a program of this type, and what the canvas draws to tell
 * its processes and edges apart. Whether it is folded belongs to the tab.
 */
export default function CanvasLegend({ programType }: { programType: ProgramType }) {

  const [isOpen, setOpen] = useState(true);

  return (

    <div
      data-legend={isOpen ? "open" : "folded"}
      data-legend-type={programType}
      style={{
        width: isOpen ? 250 : undefined,
        background: "#fff",
        border: "1px solid #ccc",
        borderRadius: 4,
        fontSize: 11,
        boxShadow: "0 1px 3px rgba(0, 0, 0, 0.15)",
      }}
    >

      <button
        onClick={() => setOpen(open => !open)}
        style={{
          width: "100%",
          textAlign: "left",
          border: "none",
          background: "none",
          padding: "6px 8px",
          fontWeight: "bold",
          cursor: "pointer",
        }}
      >
        {isOpen ? "▾ Legend" : "▸ Legend"}
      </button>

      {isOpen && (

        <div style={{ padding: "0 8px 8px", display: "flex", flexDirection: "column", gap: 6 }}>
          {programType === "resident" ? <ResidentLegend /> : <GeneralLegend />}
        </div>

      )}

    </div>

  );

}
