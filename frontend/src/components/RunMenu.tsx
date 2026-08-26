import { useEffect, useRef, useState } from "react";

import { runWorkflow } from "../api/executionApi";
import { useWorkflow } from "../store/WorkflowContext";
import EnvVarsEditor from "./EnvVarsEditor";
import ExecutionOptionsEditor from "./ExecutionOptionsEditor";
import OutputDirEditor from "./OutputDirEditor";

const MENU_ITEMS = [
  "Set environment variables",
  "Set output directory",
  "Set execution options",
  "Set workflow options",
  "Run workflow",
  "Stop workflow",
] as const;

export default function RunMenu() {

  const { workflow } = useWorkflow();

  const [isOpen, setOpen] =
    useState(false);

  const [isEnvVarsOpen, setEnvVarsOpen] =
    useState(false);

  const [isOutputDirOpen, setOutputDirOpen] =
    useState(false);

  const [isExecutionOptionsOpen, setExecutionOptionsOpen] =
    useState(false);

  const [isRunning, setRunning] =
    useState(false);

  const [runError, setRunError] =
    useState<string | null>(null);

  const containerRef =
    useRef<HTMLDivElement>(null);

  async function handleRun() {

    setRunning(true);
    setRunError(null);

    try {
      await runWorkflow(workflow);
      setOpen(false);
    } catch (err) {
      setRunError(
        err instanceof Error ? err.message : "Failed to run workflow."
      );
    } finally {
      setRunning(false);
    }

  }

  function handleItemClick(item: (typeof MENU_ITEMS)[number]) {

    if (item === "Set environment variables") {
      setOpen(false);
      setEnvVarsOpen(true);
    } else if (item === "Set output directory") {
      setOpen(false);
      setOutputDirOpen(true);
    } else if (item === "Set execution options") {
      setOpen(false);
      setExecutionOptionsOpen(true);
    } else if (item === "Run workflow") {
      handleRun();
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
          setRunError(null);
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

              disabled={item === "Run workflow" && isRunning}

              style={{
                textAlign: "left",
                padding: "8px 12px",
                border: "none",
                background: "none",
                cursor: "pointer",
              }}

            >
              {item === "Run workflow" && isRunning ? "Running..." : item}
            </button>

          ))}

          {runError && (
            <div
              style={{
                padding: "0 12px 8px",
                color: "#b00020",
                fontSize: 13,
              }}
            >
              {runError}
            </div>
          )}

        </div>

      )}

      {isEnvVarsOpen && (
        <EnvVarsEditor
          onClose={() => setEnvVarsOpen(false)}
        />
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

    </div>

  );

}
