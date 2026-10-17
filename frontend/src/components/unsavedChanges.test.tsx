import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ProgramEditor from "./ProgramEditor";
import Toolbar from "./Toolbar";
import { ProgramProvider } from "../store/ProgramContext";
import { DISK_DIGEST_POLL_INTERVAL_MS } from "../store/useDiskDigest";
import { createEmptyProgram } from "../storage/programStorage";
import type { Program } from "../models/program";

// The canvas of the editor measures itself, which jsdom cannot.
class NoResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

function renderEditor() {
  vi.stubGlobal("ResizeObserver", NoResizeObserver);
  render(
    <ProgramProvider initialProgram={onDisk()}>
      <ProgramEditor onClose={vi.fn()} />
    </ProgramProvider>
  );
}

const onDisk = (): Program => ({ ...createEmptyProgram("p"), id: "p", homeDir: "/home/p", digest: "2" });

function renderToolbar(onClose = vi.fn()) {
  render(
    <ProgramProvider initialProgram={onDisk()}>
      <Toolbar onClose={onClose} />
    </ProgramProvider>
  );
  return onClose;
}

// Edits the name of the program, the one edit the toolbar makes in place.
function rename(name: string) {
  const input = screen.getByDisplayValue("p");
  fireEvent.change(input, { target: { value: name } });
  fireEvent.keyDown(input, { key: "Enter" });
}

describe("leaving a program with unsaved changes", () => {

  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ digest: "2" }))));
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("closes at once when nothing is unsaved", () => {
    const confirm = vi.spyOn(window, "confirm");
    const onClose = renderToolbar();

    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    expect(confirm).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("asks first when something is unsaved, and stays when the user declines", () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const onClose = renderToolbar();
    rename("renamed");
    confirm.mockReturnValue(false);

    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    expect(confirm).toHaveBeenLastCalledWith(expect.stringMatching(/changes made since it was last saved are lost/));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("asks the browser to confirm closing its tab when something is unsaved", () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderEditor();
    const unload = () => {
      const event = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(event);
      return event.defaultPrevented;
    };
    expect(unload()).toBe(false);

    rename("renamed");

    expect(unload()).toBe(true);
  });

});

describe("the banner of a digest saved elsewhere", () => {

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("offers to load it or to save the tab over it, while the tab holds unsaved changes", async () => {
    vi.useFakeTimers();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url === "/api/programs/digest") {
        return new Response(JSON.stringify({ digest: "3" }));
      }
      if (url === "/api/programs/load") {
        return new Response(JSON.stringify({ ...onDisk(), name: "theirs", digest: "3" }));
      }
      return new Response(JSON.stringify({ statuses: {}, hasProgramState: false, output: "", notices: [] }));
    }));
    renderEditor();
    rename("mine");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(DISK_DIGEST_POLL_INTERVAL_MS);
    });

    expect(screen.getByRole("alert")).toHaveTextContent(/written from elsewhere/);
    expect(screen.getByRole("button", { name: "Save mine over it" })).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Load it (lose my changes)" }));
    });

    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByDisplayValue("theirs")).toBeInTheDocument();
  });

});
