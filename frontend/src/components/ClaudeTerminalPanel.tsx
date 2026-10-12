import { useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";

import { useClaudeTerminal } from "../store/ClaudeTerminalContext";

// The terminal panel: at the bottom of the editor, across its whole width,
// the terminal of the session of Claude Code in the page (see "The terminal
// panel" in doc/design_doc_webui.md). Its upper edge changes its height; a
// hidden panel keeps its session, and its terminal, and leaves a mini window
// on the canvas (ClaudeTerminalMini) to show it again. "End", or "Close" once
// the session ended, takes it away: a new session starts from the Help menu.

const DEFAULT_HEIGHT = 320;
const MIN_HEIGHT = 120;
// What the panel leaves above it, for the toolbar and some canvas.
const ROOM_ABOVE = 200;

const encoder = new TextEncoder();

export default function ClaudeTerminalPanel() {

  const terminal = useClaudeTerminal();
  const { phase, visible, notice, takeOverOffered } = terminal;

  // Kept in the tab only.
  const [height, setHeight] = useState(DEFAULT_HEIGHT);

  if (phase === "none") {
    return null;
  }

  function startResize(event: ReactPointerEvent<HTMLDivElement>) {
    event.preventDefault();
    const startY = event.clientY;
    const startHeight = height;
    function onMove(move: PointerEvent) {
      const max = Math.max(MIN_HEIGHT, window.innerHeight - ROOM_ABOVE);
      setHeight(Math.min(max, Math.max(MIN_HEIGHT, startHeight + startY - move.clientY)));
    }
    function onUp() {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  const status =
    phase === "starting" ? "Starting..." :
    phase === "running" ? null :
    notice;

  return (

    <section
      aria-label="Claude Code terminal"
      style={{
        display: visible ? "flex" : "none",
        flexDirection: "column",
        height,
        flexShrink: 0,
        borderTop: "1px solid #ccc",
        background: "#1e1e1e",
      }}
    >

      <div
        role="separator"
        aria-orientation="horizontal"
        aria-label="Resize the Claude Code terminal"
        onPointerDown={startResize}
        style={{ height: 5, cursor: "ns-resize", background: "#ddd", flexShrink: 0 }}
      />

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "4px 8px",
          background: "#f3f3f3",
          fontSize: 13,
          flexShrink: 0,
        }}
      >

        <strong>Claude Code</strong>

        {status && <span style={{ color: "#555" }}>{status}</span>}

        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>

          {phase === "ended" && takeOverOffered && (
            <button onClick={() => terminal.start("continue", true)}>
              Bring it here
            </button>
          )}

          <button onClick={() => terminal.setVisible(false)}>Hide</button>

          <button onClick={terminal.end}>
            {phase === "ended" ? "Close" : "End"}
          </button>

        </div>

      </div>

      <TerminalView />

    </section>

  );

}

// The terminal itself, made once for the editor and given to the session.
function TerminalView() {

  const { attach, type, resize, phase, visible } = useClaudeTerminal();

  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }
    const term = new Terminal({
      cursorBlink: true,
      // Named fonts before the generic one: the terminal measures its
      // characters in this font, and draws nothing where the browser maps
      // the generic `monospace` to no font.
      fontFamily: 'ui-monospace, "SF Mono", Menlo, Consolas, "Liberation Mono", "DejaVu Sans Mono", monospace',
      fontSize: 13,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(container);
    termRef.current = term;

    // A hidden panel has no size to fit.
    const fitIfShown = () => {
      if (container.offsetWidth > 0 && container.offsetHeight > 0) {
        fit.fit();
      }
    };
    fitIfShown();

    const detach = attach({
      write: data => term.write(data),
      size: () => ({ cols: term.cols, rows: term.rows }),
      reset: () => term.reset(),
    });
    const typed = term.onData(data => type(encoder.encode(data)));
    // Mouse reports come as a string of bytes.
    const binary = term.onBinary(data => type(Uint8Array.from(data, ch => ch.charCodeAt(0))));
    const resized = term.onResize(({ cols, rows }) => resize(cols, rows));
    const observer = new ResizeObserver(fitIfShown);
    observer.observe(container);

    return () => {
      observer.disconnect();
      resized.dispose();
      binary.dispose();
      typed.dispose();
      detach();
      term.dispose();
      termRef.current = null;
    };
  }, [attach, type, resize]);

  // The keys go to the terminal once the session runs and shows.
  useEffect(() => {
    if (phase === "running" && visible) {
      termRef.current?.focus();
    }
  }, [phase, visible]);

  return (
    <div
      ref={containerRef}
      style={{ flex: 1, minHeight: 0, padding: "2px 4px" }}
    />
  );

}
