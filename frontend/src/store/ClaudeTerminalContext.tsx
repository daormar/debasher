import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import { requestClaudeSession, terminalUrl } from "../api/claudeTerminalApi";
import type { ClaudeConversation } from "../models/claudeCommand";
import { endingNotice, exitStatusOf, refusalNotice, resizeMessage } from "../models/claudeTerminal";

// The session of Claude Code in the page of the open program (see "Claude
// Code in the page" in doc/design_doc_webui.md): one per editor, which lives
// as long as its WebSocket, and which the terminal panel shows. The provider
// owns the WebSocket; the panel gives it a terminal to write into.

// "none" while the editor has no panel: before its first session, and once
// the user ended or closed one; "ended" keeps the panel, with why the session
// ended on its own.
export type TerminalPhase = "none" | "starting" | "running" | "ended";

// The terminal of the panel, as the session sees it.
export interface TerminalSink {
  write: (data: Uint8Array) => void;
  size: () => { cols: number; rows: number };
  reset: () => void;
}

export interface ClaudeTerminal {
  phase: TerminalPhase;
  // Whether the panel shows; a hidden panel keeps its session.
  visible: boolean;
  // Why the session ended, or why it could not start.
  notice: string | null;
  // Whether the program has a session in another page, which this one can
  // take over.
  takeOverOffered: boolean;
  start: (conversation: ClaudeConversation, takeOver?: boolean) => void;
  // Ends the session, if any, and takes the panel away: a new one starts
  // from the Help menu.
  end: () => void;
  setVisible: (visible: boolean) => void;
  attach: (sink: TerminalSink) => () => void;
  type: (data: Uint8Array<ArrayBuffer>) => void;
  resize: (cols: number, rows: number) => void;
}

// The size of a terminal that the panel has not measured yet.
const DEFAULT_SIZE = { cols: 80, rows: 24 };

const NO_TERMINAL: ClaudeTerminal = {
  phase: "none",
  visible: false,
  notice: null,
  takeOverOffered: false,
  start: () => {},
  end: () => {},
  setVisible: () => {},
  attach: () => () => {},
  type: () => {},
  resize: () => {},
};

const ClaudeTerminalContext = createContext<ClaudeTerminal>(NO_TERMINAL);

// Outside an editor (a dialog tested on its own) there is no session.
export function useClaudeTerminal(): ClaudeTerminal {
  return useContext(ClaudeTerminalContext);
}

export function isSessionActive(phase: TerminalPhase): boolean {
  return phase === "starting" || phase === "running";
}

interface Props {
  // The home directory of the program, empty while it was never saved.
  homeDir: string;
  children: ReactNode;
}

export function ClaudeTerminalProvider({ homeDir, children }: Props) {

  const [phase, setPhase] = useState<TerminalPhase>("none");
  const [visible, setVisible] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [takeOverOffered, setTakeOverOffered] = useState(false);

  const socketRef = useRef<WebSocket | null>(null);
  const sinkRef = useRef<TerminalSink | null>(null);
  // What the session wrote before the panel gave it a terminal.
  const pendingRef = useRef<Uint8Array[]>([]);
  // Each start supersedes the ones before it.
  const attemptRef = useRef(0);
  // Whether a request for a session waits for its answer.
  const requestingRef = useRef(false);

  const write = useCallback((data: Uint8Array) => {
    if (sinkRef.current) {
      sinkRef.current.write(data);
    } else {
      pendingRef.current.push(data);
    }
  }, []);

  const start = useCallback(async (conversation: ClaudeConversation, takeOver = false) => {
    if (!homeDir || requestingRef.current || socketRef.current) {
      return;
    }
    const attempt = ++attemptRef.current;
    setVisible(true);
    setPhase("starting");
    setNotice(null);
    setTakeOverOffered(false);
    pendingRef.current = [];
    sinkRef.current?.reset();

    const size = sinkRef.current?.size() ?? DEFAULT_SIZE;
    let answer;
    requestingRef.current = true;
    try {
      answer = await requestClaudeSession({ homeDir, start: conversation, ...size, takeOver });
    } catch {
      if (attempt === attemptRef.current) {
        setPhase("ended");
        setNotice("The backend did not answer.");
      }
      return;
    } finally {
      requestingRef.current = false;
    }
    if (attempt !== attemptRef.current) {
      return;
    }
    if (!("ticket" in answer)) {
      setPhase("ended");
      setNotice(refusalNotice(answer.status, answer.detail));
      setTakeOverOffered(answer.status === 409);
      return;
    }

    const socket = new WebSocket(terminalUrl(answer.ticket));
    socket.binaryType = "arraybuffer";
    socketRef.current = socket;
    let exitStatus: number | null = null;

    socket.onopen = () => {
      setPhase("running");
      // The panel may have changed size while the session started.
      const measured = sinkRef.current?.size();
      if (measured) {
        socket.send(resizeMessage(measured.cols, measured.rows));
      }
    };
    socket.onmessage = event => {
      if (typeof event.data === "string") {
        exitStatus = exitStatusOf(event.data) ?? exitStatus;
      } else {
        write(new Uint8Array(event.data));
      }
    };
    socket.onclose = event => {
      if (socketRef.current !== socket) {
        return;
      }
      socketRef.current = null;
      setPhase("ended");
      setNotice(endingNotice(event.code, exitStatus));
    };
  }, [homeDir, write]);

  const end = useCallback(() => {
    // A request still waiting for its answer opens nothing once it comes.
    attemptRef.current++;
    const socket = socketRef.current;
    socketRef.current = null;
    socket?.close();
    pendingRef.current = [];
    setPhase("none");
    setVisible(false);
    setNotice(null);
    setTakeOverOffered(false);
  }, []);

  const attach = useCallback((sink: TerminalSink) => {
    sinkRef.current = sink;
    for (const data of pendingRef.current) {
      sink.write(data);
    }
    pendingRef.current = [];
    return () => {
      if (sinkRef.current === sink) {
        sinkRef.current = null;
      }
    };
  }, []);

  const type = useCallback((data: Uint8Array<ArrayBuffer>) => {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(data);
    }
  }, []);

  const resize = useCallback((cols: number, rows: number) => {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(resizeMessage(cols, rows));
    }
  }, []);

  // Leaving the editor ends its session.
  useEffect(() => () => {
    attemptRef.current++;
    socketRef.current?.close();
    socketRef.current = null;
  }, []);

  const value = useMemo<ClaudeTerminal>(() => ({
    phase,
    visible,
    notice,
    takeOverOffered,
    start,
    end,
    setVisible,
    attach,
    type,
    resize,
  }), [phase, visible, notice, takeOverOffered, start, end, attach, type, resize]);

  return (
    <ClaudeTerminalContext.Provider value={value}>
      {children}
    </ClaudeTerminalContext.Provider>
  );

}
