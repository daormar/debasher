import { useEffect, useRef, useState } from "react";

import { isFanoutOption, type ProgramOption } from "../models/option";
import { readFifo, writeFifo } from "../api/executionApi";
import { useProgram } from "../store/ProgramContext";

interface Props {
  onClose: () => void;
}

interface FifoCandidate {
  id: string;
  processName: string;
  option: ProgramOption;
}

// Only ordinary "standard"-mode fifo options with no connection either
// way are safe to open directly: a fanout family or an already-
// connected option would compete with a real producer/consumer for
// data (see the plan's discussion of why no mirroring is needed here —
// unlike "Watch FIFO", these fifos are required to have no edge at
// all).
function collectCandidates(
  processes: { name: string; options: ProgramOption[] }[],
  edges: { sourceOptionId: string; targetOptionId: string }[],
  direction: "input" | "output"
): FifoCandidate[] {

  const candidates: FifoCandidate[] = [];

  for (const process of processes) {
    for (const option of process.options) {

      if (option.channel !== "fifo" || option.direction !== direction) {
        continue;
      }
      if (isFanoutOption(option.label)) {
        continue;
      }

      const isConnected = direction === "input"
        ? edges.some(e => e.targetOptionId === option.id)
        : edges.some(e => e.sourceOptionId === option.id);

      if (isConnected) {
        continue;
      }

      candidates.push({ id: option.id, processName: process.name, option });

    }
  }

  return candidates;

}

export default function TalkToFifosDialog({ onClose }: Props) {

  const { program } = useProgram();

  const inputCandidates =
    collectCandidates(program.processes, program.edges, "input");

  const outputCandidates =
    collectCandidates(program.processes, program.edges, "output");

  const [inputOptionId, setInputOptionId] =
    useState("");

  const [outputOptionId, setOutputOptionId] =
    useState("");

  const [started, setStarted] =
    useState(false);

  const [transcript, setTranscript] =
    useState<string[]>([]);

  const [draft, setDraft] =
    useState("");

  const [isWaiting, setWaiting] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  const textareaRef =
    useRef<HTMLTextAreaElement>(null);

  const formRef =
    useRef<HTMLFormElement>(null);

  const abortRef =
    useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.scrollTop = textareaRef.current.scrollHeight;
    }
  }, [transcript]);

  const inputCandidate = inputCandidates.find(c => c.id === inputOptionId);
  const outputCandidate = outputCandidates.find(c => c.id === outputOptionId);

  function handleStart() {
    if (inputCandidate && outputCandidate) {
      setStarted(true);
    }
  }

  // One write+read round trip for a single fifo line — called once per
  // line of the (possibly multi-line, Shift+Enter-separated) draft, in
  // order, so a pasted/typed paragraph plays out as one send+response
  // pair per line, same as typing them one at a time would. Returns
  // false to stop processing further lines (write failed, read failed,
  // or the dialog was closed mid-read).
  async function sendLine(text: string): Promise<boolean> {

    setTranscript(current => [...current, `> ${text}`]);

    const writeResult = await writeFifo(
      program, inputCandidate!.processName, inputCandidate!.option.value, text
    );

    if (!writeResult.ok) {
      setError(writeResult.error ?? "Failed to write to the input fifo.");
      return false;
    }

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      // Each call blocks server-side for a short bounded time (see
      // api/routers/execution.py's _FIFO_READ_TIMEOUT_SECS) — a
      // "timedOut" result just means nothing arrived yet, so keep
      // calling until a real line or a real error comes back.
      for (;;) {
        const result = await readFifo(
          program, outputCandidate!.processName, outputCandidate!.option.value, controller.signal
        );

        if (result.error) {
          setError(result.error);
          return false;
        }

        if (!result.timedOut) {
          setTranscript(current => [...current, result.line ?? ""]);
          return true;
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        return false;
      }
      setError(err instanceof Error ? err.message : "Failed to read from the output fifo.");
      return false;
    } finally {
      abortRef.current = null;
    }

  }

  async function handleSubmit(event: React.FormEvent) {

    event.preventDefault();

    if (!inputCandidate || !outputCandidate || isWaiting || !draft.trim()) {
      return;
    }

    // Each line of the textarea (Shift+Enter separates them) is sent —
    // and its response read — as its own turn, in order.
    const lines = draft.split("\n");
    setDraft("");
    setError(null);
    setWaiting(true);

    for (const line of lines) {
      const ok = await sendLine(line);
      if (!ok) {
        break;
      }
    }

    setWaiting(false);

  }

  function handleDraftKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      formRef.current?.requestSubmit();
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
          Talk to FIFOs
        </h3>

        {started && inputCandidate && outputCandidate && (
          <div style={{ color: "#888", fontSize: 13 }}>
            <div>
              Input: {inputCandidate.processName} {inputCandidate.option.label}
            </div>
            <div>
              Output: {outputCandidate.processName} {outputCandidate.option.label}
            </div>
          </div>
        )}

        {!started ? (

          <>

            <label>
              Input fifo (what you type is written here)
            </label>

            <select
              value={inputOptionId}
              onChange={(event) => setInputOptionId(event.target.value)}
              style={{ width: "100%" }}
            >
              <option value="">
                (select input fifo)
              </option>
              {inputCandidates.map(candidate => (
                <option key={candidate.id} value={candidate.id}>
                  {candidate.processName}: {candidate.option.label}
                </option>
              ))}
            </select>

            <label>
              Output fifo (responses are read from here)
            </label>

            <select
              value={outputOptionId}
              onChange={(event) => setOutputOptionId(event.target.value)}
              style={{ width: "100%" }}
            >
              <option value="">
                (select output fifo)
              </option>
              {outputCandidates.map(candidate => (
                <option key={candidate.id} value={candidate.id}>
                  {candidate.processName}: {candidate.option.label}
                </option>
              ))}
            </select>

            {(inputCandidates.length === 0 || outputCandidates.length === 0) && (
              <p style={{ fontSize: 13, color: "#888" }}>
                No unconnected input/output fifo options were found — a fifo only
                qualifies if no edge connects it to another process either way.
              </p>
            )}

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <button onClick={onClose}>
                Cancel
              </button>
              <button onClick={handleStart} disabled={!inputCandidate || !outputCandidate}>
                Start
              </button>
            </div>

          </>

        ) : (

          <>

            <textarea

              ref={textareaRef}

              readOnly

              value={transcript.join("\n")}

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

            {error && (
              <p style={{ margin: 0, color: "#c0392b", fontSize: 13 }}>
                {error}
              </p>
            )}

            <form ref={formRef} onSubmit={handleSubmit} style={{ display: "flex", gap: 8 }}>

              <textarea

                value={draft}

                onChange={(event) => setDraft(event.target.value)}

                onKeyDown={handleDraftKeyDown}

                // Not disabled while waiting (unlike the Send button):
                // disabling a focused element blurs it immediately, so
                // the user would lose focus on every send — the
                // isWaiting guards in handleSubmit/handleDraftKeyDown
                // already prevent overlapping sends without that.
                autoFocus

                rows={3}

                placeholder="Enter to send, Shift+Enter for a new line"

                style={{
                  flex: 1,
                  resize: "vertical",
                  overflow: "auto",
                  fontFamily: "inherit",
                  fontSize: 13,
                  padding: 8,
                  boxSizing: "border-box",
                }}

              />

              <button type="submit" disabled={isWaiting || !draft.trim()}>
                {isWaiting ? "Waiting..." : "Send"}
              </button>

            </form>

            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button onClick={onClose}>
                Close
              </button>
            </div>

          </>

        )}

      </div>

    </div>

  );

}
