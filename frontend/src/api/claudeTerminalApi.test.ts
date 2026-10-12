import { afterEach, describe, expect, it, vi } from "vitest";

import { requestClaudeSession, terminalUrl } from "./claudeTerminalApi";

const REQUEST = { homeDir: "/home/me/wc", start: "new" as const, cols: 80, rows: 24, takeOver: false };

describe("claudeTerminalApi", () => {

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("opens the WebSocket on the origin of the page, encrypted when the page is", () => {
    expect(terminalUrl("a+b/c", { protocol: "http:", host: "localhost:8000" }))
      .toBe("ws://localhost:8000/api/claude/terminal?ticket=a%2Bb%2Fc");
    expect(terminalUrl("t", { protocol: "https:", host: "lab:443" }))
      .toBe("wss://lab:443/api/claude/terminal?ticket=t");
  });

  it("gives the ticket of a granted session", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ ticket: "t1" }))));

    expect(await requestClaudeSession(REQUEST)).toEqual({ ticket: "t1" });
  });

  it("gives the status and the detail of a refused one", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "busy" }), { status: 409 }),
    ));
    expect(await requestClaudeSession(REQUEST)).toEqual({ status: 409, detail: "busy" });

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("not json", { status: 502 })));
    expect(await requestClaudeSession(REQUEST)).toEqual({ status: 502, detail: "" });
  });

});
