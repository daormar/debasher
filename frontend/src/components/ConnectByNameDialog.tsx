import { useId, useState } from "react";

import type { ConnectionCandidate } from "../models/connections";
import type { EdgeDisplay } from "../models/edge";

interface Props {
  // "<process> <option>" of the input being connected.
  targetText: string;
  // The outputs it can be connected to (see connectionCandidates).
  candidates: ConnectionCandidate[];
  onConnect: (candidate: ConnectionCandidate, display: EdgeDisplay) => void;
  onClose: () => void;
}

/**
 * Connects an input to an output named by typing it, with the outputs it
 * can be connected to offered as the name is typed, rather than by drawing
 * an edge that may have to cross the whole canvas. The new edge is a label
 * edge unless the user unticks it.
 */
export default function ConnectByNameDialog({ targetText, candidates, onConnect, onClose }: Props) {

  const candidatesListId = useId();

  const [text, setText] =
    useState("");

  const [asLabel, setAsLabel] =
    useState(true);

  const [error, setError] =
    useState<string | null>(null);

  function handleConnect() {

    const candidate = candidates.find(c => c.text === text.trim());

    if (!candidate) {
      setError(`"${text.trim()}" is not an output that ${targetText} can be connected to.`);
      return;
    }

    onConnect(candidate, asLabel ? "label" : "line");
    onClose();

  }

  return (

    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0, 0, 0, 0.4)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >

      <div
        style={{
          width: "60%",
          maxWidth: 480,
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >

        <h3 style={{ margin: 0 }}>
          Connect {targetText} to
        </h3>

        <label style={{ fontSize: 14 }}>
          Output (process and option)
        </label>

        <input

          type="text"

          list={candidatesListId}

          value={text}

          onChange={(event) => {
            setText(event.target.value);
            setError(null);
          }}

          onKeyDown={(event) => {
            if (event.key === "Enter") {
              handleConnect();
            }
          }}

          autoFocus

          style={{
            width: "100%",
            fontFamily: "monospace",
          }}

        />

        <datalist id={candidatesListId}>
          {candidates.map(candidate => (
            <option key={`${candidate.sourceProcessId}:${candidate.sourceOptionId}`} value={candidate.text} />
          ))}
        </datalist>

        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 14 }}>

          <input

            type="checkbox"

            checked={asLabel}

            onChange={(event) =>
              setAsLabel(event.target.checked)
            }

          />

          Draw as a label edge (a stub at each end) instead of a line

        </label>

        {error && (
          <div style={{ color: "#b00020", fontSize: 14 }}>
            {error}
          </div>
        )}

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
          }}
        >

          <button onClick={onClose}>
            Cancel
          </button>

          <button onClick={handleConnect} disabled={!text.trim()}>
            Connect
          </button>

        </div>

      </div>

    </div>

  );

}
