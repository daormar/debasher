import { useEffect, useRef, useState } from "react";
import type { Program } from "../models/program";
import { getFifoMirror } from "../api/executionApi";

// Fast enough to feel "live" for an interactive debugging panel, unlike
// the coarser status polling in ProgramContext.tsx (PROCESS_STATUS_POLL_
// INTERVAL_MS) — there's no streaming/SSE infra in this codebase, so a
// plain re-fetch-and-replace poll is the whole mechanism (see
// api/routers/execution.py's /fifo-mirror, which just cats the mirror
// log file each time).
const FIFO_WATCH_POLL_INTERVAL_MS = 2000;

interface Props {
  title: string;
  program: Program;
  processName: string;
  // The fifo's name as given to define_fifo_opt (the mirrored option's
  // own `value`), not the option's label.
  fifoName: string;
  taskIndex?: number;
  onClose: () => void;
}

export default function FifoWatchModal({
  title,
  program,
  processName,
  fifoName,
  taskIndex,
  onClose,
}: Props) {

  const [output, setOutput] =
    useState("");

  const [error, setError] =
    useState<string | null>(null);

  const textareaRef =
    useRef<HTMLTextAreaElement>(null);

  useEffect(() => {

    let cancelled = false;

    async function poll() {
      try {
        const result = await getFifoMirror(program, processName, fifoName, taskIndex);
        if (!cancelled) {
          setOutput(result);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to get mirrored fifo output.");
        }
      }
    }

    poll();
    const timer = window.setInterval(poll, FIFO_WATCH_POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };

  }, [program, processName, fifoName, taskIndex]);

  // Keeps the view pinned to the newest lines as they arrive, matching
  // what a `tail -f` reader of this fifo would expect to see.
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.scrollTop = textareaRef.current.scrollHeight;
    }
  }, [output]);

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
          maxWidth: 720,
          maxHeight: "80vh",
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >

        <h3 style={{ margin: 0 }}>
          {title}
        </h3>

        {error && (
          <p style={{ margin: 0, color: "#c0392b", fontSize: 13 }}>
            {error}
          </p>
        )}

        <textarea

          ref={textareaRef}

          readOnly

          value={output || "No output yet."}

          style={{
            width: "100%",
            height: "50vh",
            margin: 0,
            padding: 8,
            background: "#f5f5f5",
            border: "1px solid #ddd",
            borderRadius: 4,
            fontFamily: "ui-monospace, Consolas, monospace",
            fontSize: 13,
            whiteSpace: "pre-wrap",
            overflow: "auto",
            boxSizing: "border-box",
            resize: "vertical",
          }}

        />

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
          }}
        >

          <button onClick={onClose}>
            Close
          </button>

        </div>

      </div>

    </div>

  );

}
