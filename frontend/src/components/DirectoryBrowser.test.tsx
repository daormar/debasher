import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DirectoryBrowser, { textualParent } from "./DirectoryBrowser";

// A server whose file system holds the directories /home/u and /home/u/runs
// only: listing any other path fails as the backend does.
function backend() {
  const dirs: Record<string, { parent: string; entries: { name: string; path: string; type: string }[] }> = {
    "/home/u": { parent: "/home", entries: [{ name: "runs", path: "/home/u/runs", type: "dir" }] },
    "/home/u/runs": { parent: "/home/u", entries: [] },
  };
  vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => {
    const path = JSON.parse(String(init?.body)).path || "/home/u";
    const dir = dirs[path];
    if (!dir) {
      return new Response(JSON.stringify({ detail: `'${path}' is not a directory` }), { status: 400 });
    }
    return new Response(JSON.stringify({ path, parent: dir.parent, entries: dir.entries }));
  }));
}

async function renderBrowser(initialPath: string, allowMissing = false) {
  const onPathChange = vi.fn();
  await act(async () => {
    render(<DirectoryBrowser initialPath={initialPath} onPathChange={onPathChange} allowMissing={allowMissing} />);
  });
  return onPathChange;
}

describe("DirectoryBrowser", () => {

  beforeEach(backend);

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("takes the typed path as the selection without Enter", async () => {
    const onPathChange = await renderBrowser("/home/u");

    fireEvent.change(screen.getByRole("textbox"), { target: { value: " /home/u/new " } });

    expect(onPathChange).toHaveBeenLastCalledWith("/home/u/new");
  });

  it("keeps a path that does not exist as the selection when allowed", async () => {
    const onPathChange = await renderBrowser("/home/u/new/out", true);

    expect(onPathChange).toHaveBeenLastCalledWith("/home/u/new/out");
    expect(screen.getByRole("textbox")).toHaveProperty("value", "/home/u/new/out");
    expect(screen.getByText(/is created when it is first used/)).toBeTruthy();
    expect(screen.queryByText(/is not a directory/)).toBeNull();
  });

  it("reports a path that cannot be listed as an error otherwise", async () => {
    const onPathChange = await renderBrowser("/home/u/new/out");

    expect(onPathChange).not.toHaveBeenCalled();
    expect(screen.getByText(/is not a directory/)).toBeTruthy();
  });

});

describe("textualParent", () => {

  it("is the directory above a path, from its text", () => {
    expect(textualParent("/home/u/new")).toBe("/home/u");
    expect(textualParent("/home/u/new/")).toBe("/home/u");
    expect(textualParent("/home")).toBe("/");
    expect(textualParent("/")).toBeNull();
    expect(textualParent("relative")).toBeNull();
  });

});
