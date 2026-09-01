import { useEffect, useRef, useState } from "react";

import {
  checkProgramOptions,
  getProgramStatus,
  runProgramDebug,
  stopProgram,
} from "../api/executionApi";
import type { Program } from "../models/program";
import { useProgram } from "../store/ProgramContext";
import CommandOutputModal from "./CommandOutputModal";
import ExecutionOptionsEditor from "./ExecutionOptionsEditor";
import OutputDirEditor from "./OutputDirEditor";
import ProgramOptionsEditor from "./ProgramOptionsEditor";

const MENU_ITEMS = [
  "Set output directory",
  "Set execution options",
  "Set program options",
  "Check program options",
  "Run program (debug)",
  "Run program",
  "Get program status",
  "Stop program",
] as const;

type MenuItem = (typeof MENU_ITEMS)[number];

const REQUIRES_OUTPUT_DIR = new Set<MenuItem>([
  "Check program options",
  "Run program (debug)",
  "Run program",
  "Get program status",
  "Stop program",
]);

const REQUIRES_HOME_DIR = new Set<MenuItem>([
  "Check program options",
  "Run program (debug)",
  "Run program",
]);

const PENDING_LABELS: Partial<Record<MenuItem, string>> = {
  "Check program options": "Checking...",
  "Run program (debug)": "Running...",
  "Run program": "Running...",
  "Get program status": "Getting status...",
  "Stop program": "Stopping...",
};

interface CommandOutput {
  title: string;
  output: string;
}

export default function RunMenu() {

  const { program, runPhase, startProgramRun } = useProgram();

  const [isOpen, setOpen] =
    useState(false);

  const [isOutputDirOpen, setOutputDirOpen] =
    useState(false);

  const [isExecutionOptionsOpen, setExecutionOptionsOpen] =
    useState(false);

  const [isProgramOptionsOpen, setProgramOptionsOpen] =
    useState(false);

  const [commandOutput, setCommandOutput] =
    useState<CommandOutput | null>(null);

  const [pendingAction, setPendingAction] =
    useState<MenuItem | null>(null);

  const [actionError, setActionError] =
    useState<string | null>(null);

  const containerRef =
    useRef<HTMLDivElement>(null);

  async function handleRunProgram() {

    setActionError(null);
    setPendingAction("Run program");

    try {
      await startProgramRun();
    } catch (err) {
      setPendingAction(null);
      setActionError(err instanceof Error ? err.message : "Failed to run program.");
      return;
    }

    setPendingAction(null);
    setOpen(false);

  }

  async function runOutputAction(
    item: MenuItem,
    title: string,
    action: (program: Program) => Promise<string>
  ) {

    setPendingAction(item);
    setActionError(null);

    try {
      const output = await action(program);
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

    if (REQUIRES_OUTPUT_DIR.has(item) && !program.outputDir.trim()) {
      setActionError("Set the output directory before running this action.");
      return;
    }

    if (REQUIRES_HOME_DIR.has(item) && !program.homeDir.trim()) {
      setActionError("Save the program before running this action.");
      return;
    }

    if (item === "Set output directory") {
      setOpen(false);
      setOutputDirOpen(true);
    } else if (item === "Set execution options") {
      setOpen(false);
      setExecutionOptionsOpen(true);
    } else if (item === "Set program options") {
      setOpen(false);
      setProgramOptionsOpen(true);
    } else if (item === "Check program options") {
      runOutputAction(item, "Check program options", checkProgramOptions);
    } else if (item === "Run program (debug)") {
      runOutputAction(item, "Run program (debug)", runProgramDebug);
    } else if (item === "Run program") {
      handleRunProgram();
    } else if (item === "Get program status") {
      runOutputAction(item, "Program status", getProgramStatus);
    } else if (item === "Stop program") {
      runOutputAction(item, "Stop program", stopProgram);
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
                (item === "Run program" && runPhase === "running")
              }

              style={{
                textAlign: "left",
                padding: "8px 12px",
                border: "none",
                background: "none",
                cursor: "pointer",
              }}

            >
              {item === "Run program" && runPhase === "running"
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

      {isProgramOptionsOpen && (
        <ProgramOptionsEditor
          onClose={() => setProgramOptionsOpen(false)}
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
