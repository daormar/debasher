import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ProgramFilesPanel, { FILES_POLL_INTERVAL_MS } from "./ProgramFilesPanel";
import { ProgramProvider } from "../store/ProgramContext";
import { createEmptyProgram } from "../storage/programStorage";

// A home directory holding one user file, `notes.txt`, which someone else
// may write (a new content and version) or delete (a null version).
interface Disk {
  content: string;
  version: string | null;
}

function backend(disk: Disk) {
  const writes: { content: string; expectedVersion?: string }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const body = init?.body ? JSON.parse(String(init.body)) : {};
    const tree = disk.version === null
      ? []
      : [{ name: "notes.txt", path: "notes.txt", type: "file", readonly: false, children: null }];
    if (url === "/api/program-files/tree") {
      return new Response(JSON.stringify({ entries: tree }));
    }
    if (url === "/api/program-files/content") {
      return new Response(JSON.stringify(
        disk.version === null ? { kind: "missing" } : { kind: "file", content: disk.content, version: disk.version }
      ));
    }
    if (url === "/api/program-files/version") {
      return new Response(JSON.stringify({ version: disk.version }));
    }
    if (url === "/api/program-files/write-content") {
      writes.push({ content: body.content, expectedVersion: body.expectedVersion });
      if (body.expectedVersion !== disk.version) {
        return new Response(JSON.stringify({
          detail: { code: "file-version", version: disk.version, message: "notes.txt changed on disk." },
        }), { status: 409 });
      }
      disk.content = body.content;
      disk.version = `${disk.version}+`;
      return new Response(JSON.stringify({ entries: tree, version: disk.version }));
    }
    throw new Error(`unexpected request to ${url}`);
  }));
  return writes;
}

async function poll() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(FILES_POLL_INTERVAL_MS);
  });
}

async function openNotes() {
  render(
    <ProgramProvider initialProgram={{ ...createEmptyProgram("p"), homeDir: "/home/p" }}>
      <ProgramFilesPanel />
    </ProgramProvider>
  );
  await act(async () => {
    fireEvent.click(screen.getByText("Program files"));
  });
  await act(async () => {
    fireEvent.click(screen.getByText("notes.txt"));
  });
}

const buffer = () => document.querySelector("textarea") as HTMLTextAreaElement;

function type(text: string) {
  fireEvent.change(buffer(), { target: { value: text } });
}

describe("the program files panel and what someone else writes", () => {

  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("reads again in place a file that holds no unsaved change", async () => {
    const disk = { content: "v1", version: "1" };
    backend(disk);
    await openNotes();
    expect(buffer().value).toBe("v1");

    disk.content = "v2 from the agent";
    disk.version = "2";
    await poll();

    expect(buffer().value).toBe("v2 from the agent");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("asks before it loses unsaved changes, and saves them over what was written when the user chooses to", async () => {
    const disk = { content: "v1", version: "1" };
    const writes = backend(disk);
    await openNotes();
    type("mine");

    disk.content = "v2 from the agent";
    disk.version = "2";
    await poll();

    expect(screen.getByRole("alert")).toHaveTextContent(/written from elsewhere/);
    expect(buffer().value).toBe("mine");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Save mine over it" }));
    });

    expect(writes.at(-1)).toEqual({ content: "mine", expectedVersion: "2" });
    expect(disk.content).toBe("mine");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("loads what was written, losing the unsaved changes, when the user chooses to", async () => {
    const disk = { content: "v1", version: "1" };
    backend(disk);
    await openNotes();
    type("mine");
    disk.content = "v2 from the agent";
    disk.version = "2";
    await poll();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Load it (lose my changes)" }));
    });

    expect(buffer().value).toBe("v2 from the agent");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("asks when a save finds the file written since it was read, and writes nothing", async () => {
    const disk = { content: "v1", version: "1" };
    const writes = backend(disk);
    await openNotes();
    type("mine");
    disk.content = "v2 from the agent";
    disk.version = "2";

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Save" }));
    });

    expect(writes).toEqual([{ content: "mine", expectedVersion: "1" }]);
    expect(disk.content).toBe("v2 from the agent");
    expect(screen.getByRole("alert")).toHaveTextContent(/written from elsewhere/);
  });

  it("offers only to load a file that someone else deleted", async () => {
    const disk: Disk = { content: "v1", version: "1" };
    backend(disk);
    await openNotes();
    type("mine");

    disk.version = null;
    await poll();

    expect(screen.getByRole("alert")).toHaveTextContent(/deleted from elsewhere/);
    expect(screen.queryByRole("button", { name: "Save mine over it" })).toBeNull();
  });

});
