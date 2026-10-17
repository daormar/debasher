import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ProgramEditor from "./ProgramEditor";
import { ProgramProvider } from "../store/ProgramContext";
import { createEmptyProgram } from "../storage/programStorage";
import { DEFAULT_WEBUI_INFO } from "../api/webuiApi";
import { CLOSE_NORMAL } from "../models/claudeTerminal";
import { FakeWebSocket } from "../test/fakeWebSocket";

// xterm.js draws on a canvas, which jsdom has not: a terminal that stands in
// for it keeps what it is given, and types what the test says.
const terminals = vi.hoisted(() => [] as Array<{
  written: string[];
  type: (data: string) => void;
  focused: boolean;
}>);

vi.mock("@xterm/xterm", () => ({
  Terminal: class {
    cols = 80;
    rows = 24;
    written: string[] = [];
    focused = false;
    private dataListener: (data: string) => void = () => {};
    constructor() {
      terminals.push(this as never);
    }
    loadAddon() {}
    open() {}
    write(data: Uint8Array) {
      this.written.push(new TextDecoder().decode(data));
    }
    reset() {}
    focus() {
      this.focused = true;
    }
    dispose() {}
    onData(listener: (data: string) => void) {
      this.dataListener = listener;
      return { dispose() {} };
    }
    onBinary() {
      return { dispose() {} };
    }
    onResize() {
      return { dispose() {} };
    }
    type(data: string) {
      this.dataListener(data);
    }
  },
}));

vi.mock("@xterm/addon-fit", () => ({
  FitAddon: class {
    fit() {}
  },
}));

class NoResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

// The backend: what it offers, and its answers to the requests for a
// session, in order.
function stubBackend(sessionAnswers: Array<{ status: number; body: unknown }>, terminal = true) {
  const answers = [...sessionAnswers];
  const fetchMock = vi.fn(async (url: string) => {
    if (url === "/api/webui/info") {
      return new Response(JSON.stringify({ ...DEFAULT_WEBUI_INFO, claudeCodeTerminal: terminal }));
    }
    if (url === "/api/claude/session") {
      const { status, body } = answers.shift()!;
      return new Response(JSON.stringify(body), { status });
    }
    if (url === "/api/programs/digest") {
      return new Response(JSON.stringify({ digest: "2" }));
    }
    return new Response(JSON.stringify({ statuses: {}, hasProgramState: false, output: "", notices: [] }));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function sessionRequests(fetchMock: ReturnType<typeof stubBackend>) {
  return fetchMock.mock.calls
    .filter(([url]) => url === "/api/claude/session")
    .map(call => JSON.parse((call as unknown as [string, RequestInit])[1].body as string));
}

function renderEditor() {
  render(
    <ProgramProvider initialProgram={{ ...createEmptyProgram("p"), id: "p", homeDir: "/home/p", digest: "2" }}>
      <ProgramEditor onClose={vi.fn()} />
    </ProgramProvider>
  );
}

async function openInThePage() {
  fireEvent.click(screen.getByRole("button", { name: "Help" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Claude Code..." }));
  fireEvent.click(await screen.findByRole("button", { name: "Open in the page" }));
}

async function runningSession() {
  await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
  const socket = FakeWebSocket.instances[0];
  act(() => socket.open());
  return socket;
}

function panel() {
  // Found by its label: a hidden panel is no region for the queries by role.
  const element = document.querySelector<HTMLElement>('section[aria-label="Claude Code terminal"]');
  expect(element).not.toBeNull();
  return element!;
}

describe("ClaudeTerminalPanel", () => {

  beforeEach(() => {
    terminals.length = 0;
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
    vi.stubGlobal("ResizeObserver", NoResizeObserver);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("opens from the Claude Code dialog, at the bottom of the editor, and runs the session there", async () => {
    const fetchMock = stubBackend([{ status: 200, body: { ticket: "t1" } }]);
    renderEditor();
    expect(screen.queryByRole("region", { name: "Claude Code terminal" })).toBeNull();

    await openInThePage();

    expect(screen.queryByRole("dialog", { name: "Claude Code" })).toBeNull();
    expect(panel()).toHaveTextContent("Starting...");
    const socket = await runningSession();
    expect(sessionRequests(fetchMock)[0]).toMatchObject({ homeDir: "/home/p", start: "new", takeOver: false });

    socket.receive(new TextEncoder().encode("Welcome").buffer);
    expect(terminals[0].written.join("")).toBe("Welcome");
    expect(terminals[0].focused).toBe(true);

    terminals[0].type("hi");
    expect(new TextDecoder().decode(socket.sent.at(-1) as Uint8Array)).toBe("hi");

    expect(screen.getByRole("button", { name: "End" })).toBeInTheDocument();
  });

  it("hides into a mini window on the canvas, keeping its session, and shows again from it", async () => {
    stubBackend([{ status: 200, body: { ticket: "t1" } }]);
    renderEditor();
    await openInThePage();
    const socket = await runningSession();
    expect(screen.queryByRole("status", { name: "Claude Code session" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Claude Code" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Hide" }));
    expect(panel()).not.toBeVisible();
    expect(socket.closedByPage).toBe(false);
    const mini = screen.getByRole("status", { name: "Claude Code session" });
    expect(mini).toHaveTextContent("Claude Code: Running");

    fireEvent.click(within(mini).getByRole("button", { name: "Show" }));
    expect(panel()).toBeVisible();
    expect(screen.queryByRole("status", { name: "Claude Code session" })).toBeNull();
  });

  it("takes the panel and its mini window away with End, and starts again from the Help menu", async () => {
    stubBackend([
      { status: 200, body: { ticket: "t1" } },
      { status: 200, body: { ticket: "t2" } },
    ]);
    renderEditor();
    await openInThePage();
    const socket = await runningSession();

    fireEvent.click(screen.getByRole("button", { name: "End" }));

    expect(socket.closedByPage).toBe(true);
    expect(document.querySelector('section[aria-label="Claude Code terminal"]')).toBeNull();
    expect(screen.queryByRole("status", { name: "Claude Code session" })).toBeNull();

    await openInThePage();
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(2));
  });

  it("says why the session ended on its own, also in the mini window, and Close takes it away", async () => {
    stubBackend([{ status: 200, body: { ticket: "t1" } }]);
    renderEditor();
    await openInThePage();
    const socket = await runningSession();
    fireEvent.click(screen.getByRole("button", { name: "Hide" }));

    act(() => {
      socket.receive(JSON.stringify({ exit: 0 }));
      socket.end(CLOSE_NORMAL);
    });

    expect(screen.getByRole("status", { name: "Claude Code session" })).toHaveTextContent("Claude Code ended.");
    fireEvent.click(screen.getByRole("button", { name: "Show" }));
    expect(panel()).toHaveTextContent("Claude Code ended.");
    expect(screen.queryByRole("button", { name: "Start again" })).toBeNull();

    // The panel's own Close, not the editor's.
    fireEvent.click(within(panel()).getByRole("button", { name: "Close" }));
    expect(document.querySelector('section[aria-label="Claude Code terminal"]')).toBeNull();
  });

  it("offers to bring here a session open in another page", async () => {
    const fetchMock = stubBackend([
      { status: 409, body: { detail: "Claude Code is already open on this program in another page" } },
      { status: 200, body: { ticket: "t2" } },
    ]);
    renderEditor();
    await openInThePage();

    fireEvent.click(await screen.findByRole("button", { name: "Bring it here" }));

    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    expect(sessionRequests(fetchMock)[1]).toMatchObject({ start: "continue", takeOver: true });
  });

  it("asks before the editor or the tab ends a running session", async () => {
    stubBackend([{ status: 200, body: { ticket: "t1" } }]);
    renderEditor();
    const unload = () => {
      const event = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(event);
      return event.defaultPrevented;
    };
    expect(unload()).toBe(false);

    await openInThePage();
    await runningSession();
    expect(unload()).toBe(true);

    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(confirm).toHaveBeenCalledWith("Close the program? The session of Claude Code ends.");
  });

  it("is not offered where the backend does not run Claude Code in the page", async () => {
    stubBackend([], false);
    renderEditor();

    fireEvent.click(screen.getByRole("button", { name: "Help" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Claude Code..." }));

    await screen.findByRole("button", { name: "Copy" });
    expect(screen.queryByRole("button", { name: "Open in the page" })).toBeNull();
  });

  it("shows the running session from the dialog instead of opening another", async () => {
    stubBackend([{ status: 200, body: { ticket: "t1" } }]);
    renderEditor();
    await openInThePage();
    await runningSession();
    fireEvent.click(screen.getByRole("button", { name: "Hide" }));

    fireEvent.click(screen.getByRole("button", { name: "Help" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Claude Code..." }));
    fireEvent.click(await screen.findByRole("button", { name: "Show it in the page" }));

    expect(panel()).toBeVisible();
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

});
