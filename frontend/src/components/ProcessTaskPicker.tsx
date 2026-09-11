import { useState } from "react";

// Above this many tasks, rendering one button per index stops being
// cheap (a large array/generator process can leave many thousands of
// task files behind) — past it, only a bounded sample (first/last few)
// is shown as quick picks, and the number input is the only way to
// reach the rest.
const MAX_CHIPS = 60;
const SAMPLE_SIZE = 10;

interface Props {
  processName: string;
  kindLabel: string;
  taskIndices: number[];
  isPending: boolean;
  error: string | null;
  onConfirm: (taskIndex: number) => void;
  onCancel: () => void;
  // What each index names — "task" for an array/generator process's
  // stdout/scheduler-output/options (the default), "option" for one
  // index of a fanout/fanin option family (see ProgramCanvas's
  // fanoutIndexPicker). Only changes wording ("Select <itemLabel>",
  // "<N> <itemLabel>s available", "<ItemLabel> index") — the
  // picking/sampling behavior is identical either way.
  itemLabel?: string;
}

function sampleChips(taskIndices: number[]): number[] {

  if (taskIndices.length <= MAX_CHIPS) {
    return taskIndices;
  }

  const first = taskIndices.slice(0, SAMPLE_SIZE);
  const last = taskIndices.slice(-SAMPLE_SIZE);

  // Dedup in case the sample sizes overlap on a barely-over-the-limit list.
  return Array.from(new Set([...first, ...last]));

}

export default function ProcessTaskPicker({
  processName,
  kindLabel,
  taskIndices,
  isPending,
  error,
  onConfirm,
  onCancel,
  itemLabel = "task",
}: Props) {

  const [draft, setDraft] =
    useState(taskIndices.length > 0 ? String(taskIndices[0]) : "");

  const capitalizedItemLabel = itemLabel.charAt(0).toUpperCase() + itemLabel.slice(1);

  const chips = sampleChips(taskIndices);
  const isSampled = chips.length < taskIndices.length;

  const draftIndex = Number.parseInt(draft, 10);
  const canConfirm = draft.trim() !== "" && Number.isInteger(draftIndex) && draftIndex >= 0;

  function handleConfirm() {
    if (canConfirm) {
      onConfirm(draftIndex);
    }
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
          maxWidth: 420,
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >

        <h3 style={{ margin: 0 }}>
          Select {itemLabel}: {processName} ({kindLabel})
        </h3>

        <p style={{ margin: 0, fontSize: 13, color: "#555" }}>
          {taskIndices.length.toLocaleString()} {itemLabel}{taskIndices.length === 1 ? "" : "s"} available
          {taskIndices.length > 0 &&
            ` (${taskIndices[0]}–${taskIndices[taskIndices.length - 1]})`}
          .
        </p>

        {chips.length > 0 && (

          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: 4,
              maxHeight: 120,
              overflow: "auto",
            }}
          >

            {isSampled && (
              <span style={{ fontSize: 12, color: "#777", alignSelf: "center" }}>
                first/last {SAMPLE_SIZE}:
              </span>
            )}

            {chips.map(index => (

              <button
                key={index}
                onClick={() => setDraft(String(index))}
                disabled={isPending}
                style={{
                  padding: "2px 8px",
                  fontSize: 12,
                  border: String(index) === draft ? "1px solid #1a73e8" : "1px solid #ccc",
                  borderRadius: 12,
                  background: String(index) === draft ? "#e8f0fe" : "#fff",
                  cursor: "pointer",
                }}
              >
                {index}
              </button>

            ))}

          </div>

        )}

        <label style={{ fontSize: 14 }}>
          {capitalizedItemLabel} index
        </label>

        <input

          type="number"

          min={0}

          value={draft}

          onChange={event => setDraft(event.target.value)}

          onKeyDown={event => {
            if (event.key === "Enter") {
              handleConfirm();
            }
          }}

          autoFocus

          style={{ width: "100%" }}

        />

        {error && (
          <div style={{ color: "#b00020", fontSize: 13 }}>
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

          <button onClick={onCancel} disabled={isPending}>
            Cancel
          </button>

          <button onClick={handleConfirm} disabled={isPending || !canConfirm}>
            {isPending ? "Loading..." : "Show"}
          </button>

        </div>

      </div>

    </div>

  );

}
