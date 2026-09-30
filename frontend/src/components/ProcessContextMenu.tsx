import { useEffect, useRef } from "react";

const MENU_ITEMS = [
  "Show options",
  "Show stdout",
  "Show scheduler output",
  "Show inputs and outputs",
  "Watch FIFO",
] as const;

export type ProcessOutputKind = "stdout" | "sched-out" | "opts";

// "io" opens the structured "Show inputs and outputs" modal rather
// than a plain-text CommandOutputModal, see ProgramCanvas's onSelect.
// "watch-fifo" opens FifoWatchModal on one of this process's mirrored
// output fifo options (see ProgramCanvas's handleProcessMenuSelect).
// "stop" calls stopProcess directly, skipping the task-index flow the
// other actions go through, debasher_stop -p has no per-task variant.
// "restart" is "Restart node" on a node of a resident program, which asks
// for confirmation first; "relaunch" is "Relaunch node" in a resident
// program without a Supervisor.
// "node-state" opens NodeStateModal, on a node of a resident program.
export type ProcessMenuAction =
  ProcessOutputKind | "io" | "watch-fifo" | "node-state" | "stop" | "restart" | "relaunch";

// An action on the process itself, listed after the inspection actions:
// "Relaunch node" (see offersRelaunchNode), and, in a destructive color,
// "Stop process" in a general program or "Restart node" on a node of a
// resident program (see offersRestartNode).
export interface NodeAction {
  label: "Stop process" | "Restart node" | "Relaunch node";
  action: "stop" | "restart" | "relaunch";
  disabled: boolean;
  destructive: boolean;
}

const KIND_BY_ITEM: Record<(typeof MENU_ITEMS)[number], ProcessMenuAction> = {
  "Show options": "opts",
  "Show stdout": "stdout",
  "Show scheduler output": "sched-out",
  "Show inputs and outputs": "io",
  "Watch FIFO": "watch-fifo",
};

interface Props {
  x: number;
  y: number;
  isPending: boolean;
  // In a resident program "Watch FIFO" is not offered, since the engine
  // refuses --mirror there, and "Show node state" is, when `nodeState` is
  // given (not on the Supervisor).
  isResident: boolean;
  nodeState?: { disabled: boolean };
  onSelect: (action: ProcessMenuAction) => void;
  onClose: () => void;
  nodeActions: NodeAction[];
  // An action of the canvas rather than of the execution of the process,
  // listed after the others: on the Supervisor, showing or hiding the
  // Supervisor wiring.
  canvasAction?: { label: string; onSelect: () => void };
}

export default function ProcessContextMenu({
  x,
  y,
  isPending,
  isResident,
  nodeState,
  onSelect,
  onClose,
  nodeActions,
  canvasAction,
}: Props) {

  const containerRef =
    useRef<HTMLDivElement>(null);

  useEffect(() => {

    function handleClickOutside(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        onClose();
      }
    }

    document.addEventListener("mousedown", handleClickOutside, true);

    return () =>
      document.removeEventListener("mousedown", handleClickOutside, true);

  }, [onClose]);

  return (

    <div
      ref={containerRef}
      style={{
        position: "fixed",
        top: y,
        left: x,
        background: "#fff",
        border: "1px solid #ccc",
        borderRadius: 4,
        boxShadow: "0 2px 8px rgba(0, 0, 0, 0.15)",
        display: "flex",
        flexDirection: "column",
        minWidth: 200,
        zIndex: 1000,
      }}
    >

      {MENU_ITEMS.filter(item => !(isResident && item === "Watch FIFO")).map(item => (

        <button

          key={item}

          onClick={() => onSelect(KIND_BY_ITEM[item])}

          disabled={isPending}

          style={{
            textAlign: "left",
            padding: "8px 12px",
            border: "none",
            background: "none",
            cursor: "pointer",
          }}

        >
          {item}
        </button>

      ))}

      {nodeState && (

        <button

          onClick={() => onSelect("node-state")}

          disabled={isPending || nodeState.disabled}

          style={{
            textAlign: "left",
            padding: "8px 12px",
            border: "none",
            background: "none",
            cursor: "pointer",
          }}

        >
          Show node state
        </button>

      )}

      {nodeActions.map(nodeAction => (

        <button

          key={nodeAction.label}

          onClick={() => onSelect(nodeAction.action)}

          disabled={isPending || nodeAction.disabled}

          style={{
            textAlign: "left",
            padding: "8px 12px",
            border: "none",
            background: "none",
            cursor: "pointer",
            color: nodeAction.destructive ? "#c0392b" : undefined,
          }}

        >
          {nodeAction.label}
        </button>

      ))}

      {canvasAction && (

        <button

          onClick={canvasAction.onSelect}

          style={{
            textAlign: "left",
            padding: "8px 12px",
            border: "none",
            borderTop: "1px solid #eee",
            background: "none",
            cursor: "pointer",
          }}

        >
          {canvasAction.label}
        </button>

      )}

    </div>

  );

}
