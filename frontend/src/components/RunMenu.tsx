import { useEffect, useRef, useState } from "react";

import { runWorkflow, stopWorkflow } from "../api/executionApi";
import type { Workflow } from "../models/workflow";
import { useWorkflow } from "../store/WorkflowContext";
import ExecutionOptionsEditor from "./ExecutionOptionsEditor";
import OutputDirEditor from "./OutputDirEditor";
import WorkflowOptionsEditor from "./WorkflowOptionsEditor";

const MENU_ITEMS = [
  "Set output directory",
  "Set execution options",
  "Set workflow options",
  "Run workflow",
  "Stop workflow",
] as const;

type MenuItem = (typeof MENU_ITEMS)[number];

const WORKFLOW_ACTIONS: Partial<
  Record<MenuItem, (workflow: Workflow) => Promise<void>>
> = {
  "Run workflow": runWorkflow,
  "Stop workflow": stopWorkflow,
};

const PENDING_LABELS: Partial<Record<MenuItem, string>> = {
  "Run workflow": "Running...",
  "Stop workflow": "Stopping...",
};

export default function RunMenu() {

  const { workflow } = useWorkflow();

  const [isOpen, setOpen] =
    useState(false);

  const [isOutputDirOpen, setOutputDirOpen] =
    useState(false);

  const [isExecutionOptionsOpen, setExecutionOptionsOpen] =
    useState(false);

  const [isWorkflowOptionsOpen, setWorkflowOptionsOpen] =
    useState(false);

  const [pendingAction, setPendingAction] =
    useState<MenuItem | null>(null);

  const [actionError, setActionError] =
    useState<string | null>(null);

  const containerRef =
    useRef<HTMLDivElement>(null);

  async function runWorkflowAction(
    item: MenuItem,
    action: (workflow: Workflow) => Promise<void>
  ) {

    setPendingAction(item);
    setActionError(null);

    try {
      await action(workflow);
      setOpen(false);
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : `Failed to ${item.toLowerCase()}.`
      );
    } finally {
      setPendingAction(null);
    }

  }

  function handleItemClick(item: MenuItem) {

    if (item === "Set output directory") {
      setOpen(false);
      setOutputDirOpen(true);
    } else if (item === "Set execution options") {
      setOpen(false);
      setExecutionOptionsOpen(true);
    } else if (item === "Set workflow options") {
      setOpen(false);
      setWorkflowOptionsOpen(true);
    } else if (WORKFLOW_ACTIONS[item]) {
      runWorkflowAction(item, WORKFLOW_ACTIONS[item]);
    } else {
      setOpen(false);
    }

  }

  useEffect(() => {

    if (!isOpen) {
      return;
    }

    function handleClickOutside(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside, true);

    return () =>
      document.removeEventListener("mousedown", handleClickOutside, true);

  }, [isOpen]);

  return (

    <div
      ref={containerRef}
      style={{
        position: "relative",
      }}
    >

      <button
        onClick={() => {
          setActionError(null);
          setOpen(open => !open);
        }}
      >
        Run
      </button>

      {isOpen && (

        <div
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            marginTop: 4,
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

          {MENU_ITEMS.map(item => (

            <button

              key={item}

              onClick={() => handleItemClick(item)}

              disabled={pendingAction !== null}

              style={{
                textAlign: "left",
                padding: "8px 12px",
                border: "none",
                background: "none",
                cursor: "pointer",
              }}

            >
              {pendingAction === item ? PENDING_LABELS[item] : item}
            </button>

          ))}

          {actionError && (
            <div
              style={{
                padding: "0 12px 8px",
                color: "#b00020",
                fontSize: 13,
              }}
            >
              {actionError}
            </div>
          )}

        </div>

      )}

      {isOutputDirOpen && (
        <OutputDirEditor
          onClose={() => setOutputDirOpen(false)}
        />
      )}

      {isExecutionOptionsOpen && (
        <ExecutionOptionsEditor
          onClose={() => setExecutionOptionsOpen(false)}
        />
      )}

      {isWorkflowOptionsOpen && (
        <WorkflowOptionsEditor
          onClose={() => setWorkflowOptionsOpen(false)}
        />
      )}

    </div>

  );

}
