import { useState } from "react";
import type { ReactNode } from "react";

import { RESIDENT_STATUS_MEANINGS, processNodeBackground } from "../models/processStatus";
import { InitiatorMark, NodeKindChip, ObserveMark, OutsideMark } from "./NodeMarks";

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

/**
 * The legend of the canvas of a resident program, which the user can fold:
 * what each process status means in a resident program, and what each mark
 * of a canvas node means.
 */
export default function CanvasLegend() {

  const [isOpen, setOpen] = useState(true);

  return (

    <div
      data-legend={isOpen ? "open" : "folded"}
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

          <div style={{ fontWeight: "bold" }}>Process status</div>

          {RESIDENT_STATUS_MEANINGS.map(({ status, meaning }) => (
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

          <div style={{ fontWeight: "bold", marginTop: 4 }}>Marks</div>

          <LegendRow mark={<NodeKindChip kind="FBPProcess" />}>
            The node kind, dark for the Supervisor.
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

          <LegendRow mark={<span style={{ fontSize: 10, color: "#666" }}>-opt</span>}>
            Under the node kind: configuration options, with no handle.
          </LegendRow>

        </div>

      )}

    </div>

  );

}
