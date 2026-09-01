import { useEffect, useRef, useState } from "react";

import {
  checkWorkflowOptions,
  getWorkflowStatus,
  runWorkflowDebug,
  stopWorkflow,
} from "../api/executionApi";
import type { Workflow } from "../models/workflow";
import { useWorkflow } from "../store/WorkflowContext";
import CommandOutputModal from "./CommandOutputModal";
import ExecutionOptionsEditor from "./ExecutionOptionsEditor";
import OutputDirEditor from "./OutputDirEditor";
import WorkflowOptionsEditor from "./WorkflowOptionsEditor";

const MENU_ITEMS = [
  "Set output directory",
  "Set execution options",
  "Set workflow options",
  "Check workflow options",
  "Run workflow (debug)",
  "Run workflow",
  "Get workflow status",
  "Stop workflow",
] as const;

type MenuItem = (typeof MENU_ITEMS)[number];

const REQUIRES_OUTPUT_DIR = new Set<MenuItem>([
  "Check workflow options",
  "Run workflow (debug)",
  "Run workflow",
  "Get workflow status",
  "Stop workflow",
]);

const REQUIRES_HOME_DIR = new Set<MenuItem>([
  "Check workflow options",
  "Run workflow (debug)",
  "Run workflow",
]);

const PENDING_LABELS: Partial<Record<MenuItem, string>> = {
  "Check workflow options": "Checking...",
  "Run workflow (debug)": "Running...",
  "Run workflow": "Running...",
  "Get workflow status": "Getting status...",
  "Stop workflow": "Stopping...",
};

interface CommandOutput {
  title: string;
  output: string;
}

export default function RunMenu() {

  const { workflow, runPhase, startWorkflowRun } = useWorkflow();

  const [isOpen, setOpen] =
    useState(false);

  const [isOutputDirOpen, setOutputDirOpen] =
    useState(false);

  const [isExecutionOptionsOpen, setExecutionOptionsOpen] =
    useState(false);

  const [isWorkflowOptionsOpen, setWorkflowOptionsOpen] =
    useState(false);

  const [commandOutput, setCommandOutput] =
    useState<CommandOutput | null>(null);

  const [pendingAction, setPendingAction] =
    useState<MenuItem | null>(null);

  const [actionError, setActionError] =
    useState<string | null>(null);

  const containerRef =
    useRef<HTMLDivElement>(null);

  async function handleRunWorkflow() {

    setActionError(null);
    setPendingAction("Run workflow");

    try {
      await startWorkflowRun();
    } catch (err) {
      setPendingAction(null);
      setActionError(err instanceof Error ? err.message : "Failed to run workflow.");
      return;
    }

    setPendingAction(null);
    setOpen(false);

  }

  async function runOutputAction(
    item: MenuItem,
    title: string,
    action: (workflow: Workflow) => Promise<string>
  ) {

    setPendingAction(item);
    setActionError(null);

    try {
      const output = await action(workflow);
      setCommandOutput({ title, output });
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

    if (REQUIRES_OUTPUT_DIR.has(item) && !workflow.outputDir.trim()) {
      setActionError("Set the output directory before running this action.");
      return;
    }

    if (REQUIRES_HOME_DIR.has(item) && !workflow.homeDir.trim()) {
      setActionError("Save the workflow before running this action.");
      return;
    }

    if (item === "Set output directory") {
      setOpen(false);
      setOutputDirOpen(true);
    } else if (item === "Set execution options") {
      setOpen(false);
      setExecutionOptionsOpen(true);
    } else if (item === "Set workflow options") {
      setOpen(false);
      setWorkflowOptionsOpen(true);
    } else if (item === "Check workflow options") {
      runOutputAction(item, "Check workflow options", checkWorkflowOptions);
    } else if (item === "Run workflow (debug)") {
      runOutputAction(item, "Run workflow (debug)", runWorkflowDebug);
    } else if (item === "Run workflow") {
      handleRunWorkflow();
    } else if (item === "Get workflow status") {
      runOutputAction(item, "Workflow status", getWorkflowStatus);
    } else if (item === "Stop workflow") {
      runOutputAction(item, "Stop workflow", stopWorkflow);
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

              disabled={
                pendingAction !== null ||
                (item === "Run workflow" && runPhase === "running")
              }

              style={{
                textAlign: "left",
                padding: "8px 12px",
                border: "none",
                background: "none",
                cursor: "pointer",
              }}

            >
              {item === "Run workflow" && runPhase === "running"
                ? "Running..."
                : pendingAction === item
                ? PENDING_LABELS[item]
                : item}
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

      {commandOutput !== null && (
        <CommandOutputModal
          title={commandOutput.title}
          output={commandOutput.output}
          onClose={() => setCommandOutput(null)}
        />
      )}

    </div>

  );

}
