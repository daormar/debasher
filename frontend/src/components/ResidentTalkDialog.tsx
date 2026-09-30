import { useEffect, useRef, useState } from "react";

import { readResidentFifo, writeResidentFifo } from "../api/executionApi";
import {
  draftPayload,
  entryText,
  talkCandidates,
  type TalkCandidate,
  type TalkEntry,
  type TalkMode,
} from "../models/residentTalk";
import { useProgram } from "../store/ProgramContext";

interface Props {
  onClose: () => void;
}

function portOf(candidate: TalkCandidate): string {
  return `${candidate.processName} ${candidate.option.label}`;
}

// "Talk to FIFOs" in a resident program (see "Observing and talking to a
// live program" in doc/design_doc_webui.md). Its two halves are independent
// and both optional, since a message written need not bring an answer, nor
// an answer come from one: the user writes DATA envelopes into an external
// input, and a loop reads the envelopes of a business output with no reader
// for as long as the dialog is open and reading is not paused. What is
// written and what is read go into one transcript, in the order in which
// they happened.
export default function ResidentTalkDialog({ onClose }: Props) {

  // The program as it was when the dialog opened, as in NodeStateModal.
  const { program: currentProgram } = useProgram();
  const [program] = useState(currentProgram);

  const { inputs, outputs } = talkCandidates(program);

  const [inputId, setInputId] = useState(inputs[0]?.id ?? "");
  const [outputId, setOutputId] = useState(outputs[0]?.id ?? "");
  const [mode, setMode] = useState<TalkMode>("json");
  const [draft, setDraft] = useState("");
  const [transcript, setTranscript] = useState<TalkEntry[]>([]);
  const [isPaused, setPaused] = useState(false);
  const [isWriting, setWriting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const transcriptRef = useRef<HTMLPreElement>(null);
  // The read in flight, if any: a new reading loop waits for it, so that two
  // reads never take from the same FIFO at once.
  const readInFlight = useRef<Promise<unknown> | null>(null);

  const input = inputs.find(c => c.id === inputId);
  const output = outputs.find(c => c.id === outputId);

  useEffect(() => {
    if (transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    }
  }, [transcript]);

  // The reading loop. Pausing or closing stops it after the read in flight,
  // whose answer, when the dialog is still open, is shown all the same, since
  // that read has already taken the message from the channel.
  useEffect(() => {

    if (!output || isPaused) {
      return;
    }

    let stopped = false;
    const port = portOf(output);

    void (async () => {
      await readInFlight.current;
      while (!stopped) {
        const reading = readResidentFifo(program, output.processName, output.option.value);
        readInFlight.current = reading;
        let read;
        try {
          read = await reading;
        } catch (err) {
          read = { error: err instanceof Error ? err.message : "Failed to read." };
        }
        if (read.error) {
          setError(read.error);
          setPaused(true);
          return;
        }
        if (!read.timedOut) {
          setTranscript(current => [...current, { kind: "read", port, read }]);
        }
      }
    })();

    return () => {
      stopped = true;
    };

  }, [program, output, isPaused]);

  async function send() {

    if (!input || isWriting || !draft.trim()) {
      return;
    }

    const payload = draftPayload(draft, mode);
    if (payload === undefined) {
      setError("Not JSON, nothing was written. Switch to text mode to send it as a string.");
      return;
    }

    setWriting(true);
    setError(null);

    try {
      const result = await writeResidentFifo(program, input.processName, input.option.value, draft, mode);
      if (result.ok) {
        setTranscript(current => [...current, { kind: "written", port: portOf(input), payload }]);
        setDraft("");
      } else {
        setError(result.error ?? "Failed to write.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to write.");
    } finally {
      setWriting(false);
    }

  }

  function handleDraftKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      void send();
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
        role="dialog"
        aria-label="Talk to FIFOs"
        style={{
          width: "60%",
          maxWidth: 760,
          maxHeight: "85vh",
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

        <div style={{ display: "grid", gridTemplateColumns: "auto 1fr auto", gap: 8, alignItems: "center", fontSize: 14 }}>

          <label htmlFor="talk-input">Write into</label>
          <select id="talk-input" value={inputId} onChange={e => setInputId(e.target.value)}>
            <option value="">(none)</option>
            {inputs.map(c => (
              <option key={c.id} value={c.id}>{portOf(c)}</option>
            ))}
          </select>
          <span />

          <label htmlFor="talk-output">Read from</label>
          <select id="talk-output" value={outputId} onChange={e => setOutputId(e.target.value)}>
            <option value="">(none)</option>
            {outputs.map(c => (
              <option key={c.id} value={c.id}>{portOf(c)}</option>
            ))}
          </select>
          <button onClick={() => { setError(null); setPaused(paused => !paused); }} disabled={!output}>
            {isPaused ? "Resume reading" : "Pause reading"}
          </button>

        </div>

        {inputs.length === 0 && outputs.length === 0 && (
          <p style={{ margin: 0, fontSize: 13, color: "#888" }}>
            The program has no external input and no business output without a connection.
          </p>
        )}

        <div style={{ fontSize: 13, color: "#666" }}>
          {!output
            ? "Not reading."
            : isPaused
              ? "Reading paused: nothing is taken from the output."
              : `Reading ${portOf(output)}: each message read is taken from the channel.`}
        </div>

        <pre
          ref={transcriptRef}
          data-testid="talk-transcript"
          style={{
            margin: 0,
            height: "40vh",
            padding: 8,
            background: "#f5f5f5",
            border: "1px solid #ddd",
            borderRadius: 4,
            fontFamily: "ui-monospace, Consolas, monospace",
            fontSize: 13,
            whiteSpace: "pre-wrap",
            overflow: "auto",
          }}
        >
          {transcript.map(entryText).join("\n")}
        </pre>

        {error && (
          <p style={{ margin: 0, color: "#c0392b", fontSize: 13 }}>
            {error}
          </p>
        )}

        <div style={{ display: "flex", gap: 12, fontSize: 13 }}>
          <label>
            <input type="radio" name="talk-mode" checked={mode === "json"} onChange={() => setMode("json")} />
            {" "}JSON: any JSON value, received with its type
          </label>
          <label>
            <input type="radio" name="talk-mode" checked={mode === "text"} onChange={() => setMode("text")} />
            {" "}Text: sent as a string
          </label>
        </div>

        <div style={{ display: "flex", gap: 8 }}>

          <textarea
            value={draft}
            onChange={event => setDraft(event.target.value)}
            onKeyDown={handleDraftKeyDown}
            disabled={!input}
            rows={3}
            placeholder={input ? "Ctrl+Enter to send; Enter starts a new line" : "Choose an input to write into"}
            style={{
              flex: 1,
              resize: "vertical",
              fontFamily: "ui-monospace, Consolas, monospace",
              fontSize: 13,
              padding: 8,
              boxSizing: "border-box",
            }}
          />

          <button onClick={() => void send()} disabled={!input || isWriting || !draft.trim()}>
            {isWriting ? "Writing..." : "Send"}
          </button>

        </div>

        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button onClick={onClose}>
            Close
          </button>
        </div>

      </div>

    </div>

  );

}
