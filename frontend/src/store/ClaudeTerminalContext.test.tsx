import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ClaudeTerminalProvider, useClaudeTerminal } from "./ClaudeTerminalContext";
import type { TerminalSink } from "./ClaudeTerminalContext";
import { CLOSE_BAD_TICKET, CLOSE_NORMAL, CLOSE_TAKEN_OVER } from "../models/claudeTerminal";
import { FakeWebSocket } from "../test/fakeWebSocket";

// The answers of the backend to the requests for a session, in order.
function stubSessionAnswers(...answers: Array<{ status: number; body: unknown }>) {
  const fetchMock = vi.fn();
  for (const { status, body } of answers) {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(body), { status }));
  }
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function requestBody(fetchMock: ReturnType<typeof vi.fn>, call = 0) {
  return JSON.parse(fetchMock.mock.calls[call][1].body);
}

function renderTerminal(homeDir = "/home/me/wc") {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <ClaudeTerminalProvider homeDir={homeDir}>{children}</ClaudeTerminalProvider>
  );
  return renderHook(() => useClaudeTerminal(), { wrapper });
}

function sink(cols = 120, rows = 30) {
  const written: string[] = [];
  const value: TerminalSink = {
    write: data => written.push(new TextDecoder().decode(data)),
    size: () => ({ cols, rows }),
    reset: vi.fn(),
  };
  return { value, written };
}

async function startedSocket(result: { current: ReturnType<typeof useClaudeTerminal> }) {
  await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
  const socket = FakeWebSocket.instances[0];
  act(() => socket.open());
  expect(result.current.phase).toBe("running");
  return socket;
}

describe("ClaudeTerminalProvider", () => {

  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("has no session until one is started", () => {
    const { result } = renderTerminal();
    expect(result.current.phase).toBe("none");
    expect(result.current.visible).toBe(false);
  });

  it("asks for a session with the size of the terminal, and opens its WebSocket with the ticket", async () => {
    const fetchMock = stubSessionAnswers({ status: 200, body: { ticket: "t1" } });
    const { result } = renderTerminal();
    const terminal = sink(120, 30);
    act(() => {
      result.current.attach(terminal.value);
    });

    act(() => {
      result.current.start("continue");
    });
    expect(result.current.phase).toBe("starting");
    expect(result.current.visible).toBe(true);

    const socket = await startedSocket(result);
    expect(requestBody(fetchMock)).toEqual({
      homeDir: "/home/me/wc", start: "continue", cols: 120, rows: 30, takeOver: false,
    });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/claude/session");
    expect(socket.url).toMatch(/^ws:\/\/[^/]+\/api\/claude\/terminal\?ticket=t1$/);
    expect(socket.binaryType).toBe("arraybuffer");
    // The size again, once open, since the panel may have changed meanwhile.
    expect(socket.sent).toEqual([JSON.stringify({ resize: [120, 30] })]);
  });

  it("writes what the session sends into the terminal, also what came before the panel gave one", async () => {
    stubSessionAnswers({ status: 200, body: { ticket: "t1" } });
    const { result } = renderTerminal();

    act(() => {
      result.current.start("new");
    });
    const socket = await startedSocket(result);
    socket.receive(new TextEncoder().encode("early ").buffer);

    const terminal = sink();
    act(() => {
      result.current.attach(terminal.value);
    });
    socket.receive(new TextEncoder().encode("late").buffer);

    expect(terminal.written.join("")).toBe("early late");
  });

  it("sends what is typed and the size of the terminal while the session runs", async () => {
    stubSessionAnswers({ status: 200, body: { ticket: "t1" } });
    const { result } = renderTerminal();

    act(() => {
      result.current.start("new");
    });
    const socket = await startedSocket(result);
    const typed = new TextEncoder().encode("hi\r");
    result.current.type(typed);
    result.current.resize(100, 40);

    expect(socket.sent).toEqual([typed, JSON.stringify({ resize: [100, 40] })]);
  });

  it("says that Claude Code ended, with its exit status", async () => {
    stubSessionAnswers({ status: 200, body: { ticket: "t1" } });
    const { result } = renderTerminal();

    act(() => {
      result.current.start("new");
    });
    const socket = await startedSocket(result);
    act(() => {
      socket.receive(JSON.stringify({ exit: 2 }));
      socket.end(CLOSE_NORMAL);
    });

    expect(result.current.phase).toBe("ended");
    expect(result.current.notice).toBe("Claude Code ended with exit status 2.");
    expect(result.current.visible).toBe(true);
  });

  it("says that another page took the session over", async () => {
    stubSessionAnswers({ status: 200, body: { ticket: "t1" } });
    const { result } = renderTerminal();

    act(() => {
      result.current.start("new");
    });
    const socket = await startedSocket(result);
    act(() => socket.end(CLOSE_TAKEN_OVER));

    expect(result.current.notice).toBe("The session was opened in another page.");
  });

  it("says that the session could not open when its ticket is refused", async () => {
    stubSessionAnswers({ status: 200, body: { ticket: "t1" } });
    const { result } = renderTerminal();

    act(() => {
      result.current.start("new");
    });
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    act(() => FakeWebSocket.instances[0].end(CLOSE_BAD_TICKET));

    expect(result.current.phase).toBe("ended");
    expect(result.current.notice).toMatch(/could not open/);
  });

  it("says that the connection was lost when the backend goes away", async () => {
    stubSessionAnswers({ status: 200, body: { ticket: "t1" } });
    const { result } = renderTerminal();

    act(() => {
      result.current.start("new");
    });
    const socket = await startedSocket(result);
    act(() => socket.end(1006));

    expect(result.current.notice).toMatch(/connection to the backend was lost/);
  });

  it("ends the session when the user asks", async () => {
    stubSessionAnswers({ status: 200, body: { ticket: "t1" } });
    const { result } = renderTerminal();

    act(() => {
      result.current.start("new");
    });
    const socket = await startedSocket(result);
    act(() => result.current.end());
    expect(socket.closedByPage).toBe(true);
    act(() => socket.end(CLOSE_NORMAL));

    expect(result.current.notice).toBe("The session was ended.");
  });

  it("offers to take over a session open in another page, and takes it over", async () => {
    const fetchMock = stubSessionAnswers(
      { status: 409, body: { detail: "Claude Code is already open on this program in another page" } },
      { status: 200, body: { ticket: "t2" } },
    );
    const { result } = renderTerminal();

    act(() => {
      result.current.start("new");
    });
    await waitFor(() => expect(result.current.phase).toBe("ended"));
    expect(result.current.takeOverOffered).toBe(true);
    expect(result.current.notice).toMatch(/already open on this program in another page/);

    act(() => {
      result.current.start("continue", true);
    });
    expect(result.current.takeOverOffered).toBe(false);
    await startedSocket(result);
    expect(requestBody(fetchMock, 1)).toMatchObject({ takeOver: true });
  });

  it("says why the backend refuses a session", async () => {
    stubSessionAnswers({
      status: 503,
      body: { detail: "This web UI does not run Claude Code in the page" },
    });
    const { result } = renderTerminal();

    act(() => {
      result.current.start("new");
    });
    await waitFor(() => expect(result.current.phase).toBe("ended"));

    expect(result.current.notice).toBe("This web UI does not run Claude Code in the page.");
    expect(result.current.takeOverOffered).toBe(false);
    expect(FakeWebSocket.instances).toHaveLength(0);
  });

  it("starts no second session while one runs, and none for a program never saved", async () => {
    const fetchMock = stubSessionAnswers({ status: 200, body: { ticket: "t1" } });
    const { result } = renderTerminal();

    act(() => {
      result.current.start("new");
    });
    await startedSocket(result);
    act(() => {
      result.current.start("new");
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    cleanup();
    const unsaved = renderTerminal("");
    act(() => {
      unsaved.result.current.start("new");
    });
    expect(unsaved.result.current.phase).toBe("none");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("ends its session when the editor goes", async () => {
    stubSessionAnswers({ status: 200, body: { ticket: "t1" } });
    const { result, unmount } = renderTerminal();

    act(() => {
      result.current.start("new");
    });
    const socket = await startedSocket(result);
    unmount();

    expect(socket.closedByPage).toBe(true);
  });

  it("starts the terminal afresh for a new session", async () => {
    stubSessionAnswers(
      { status: 200, body: { ticket: "t1" } },
      { status: 200, body: { ticket: "t2" } },
    );
    const { result } = renderTerminal();
    const terminal = sink();
    act(() => {
      result.current.attach(terminal.value);
    });

    act(() => {
      result.current.start("new");
    });
    const socket = await startedSocket(result);
    act(() => socket.end(CLOSE_NORMAL));
    act(() => {
      result.current.start("continue");
    });

    expect(terminal.value.reset).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(2));
  });

});
