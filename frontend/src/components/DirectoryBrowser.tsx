import { useEffect, useState } from "react";
import { listDirs } from "../api/fsApi";
import type { FsEntry } from "../api/fsApi";

interface Props {
  // Directory to open the browser at; falsy/invalid falls back to the
  // server's home directory (see api/routers/fs_browse.py).
  initialPath: string;
  // "directories" (default): a directory is the target, and every
  // navigation (including the initial one) reports the browsed
  // directory itself as a valid default. "files": a file is the
  // target, with no such default; only clicking one reports anything.
  // Either way, entries of the other kind are still listed for
  // context (directories to navigate into, files to see what's
  // there), just not selectable.
  mode?: "directories" | "files";
  // Case-insensitive suffix filter for files, e.g. [".sh"]. Never
  // filters out directories.
  fileExtensions?: string[];
  // Fired on every click: the clicked entry's path when it matches
  // `mode` (a valid pick), or "" when it doesn't (clicked entry
  // highlights for feedback, but isn't a usable selection) — a caller
  // with its own confirm button should treat "" as falsy/disabled,
  // same as no selection at all.
  onPathChange: (path: string) => void;
}

function isSelectable(entry: FsEntry, mode: "directories" | "files"): boolean {
  return mode === "files" ? entry.type === "file" : entry.type === "dir";
}

// The bare navigation widget (path field, Up button, entry list), with
// no modal chrome of its own, so a caller can either embed it directly
// inside its own single dialog (see LoadProgramDialog) or wrap it in a
// standalone picker (see DirectoryBrowserModal / FileBrowserModal).
export default function DirectoryBrowser({
  initialPath,
  mode = "directories",
  fileExtensions,
  onPathChange,
}: Props) {

  const [pathInput, setPathInput] =
    useState(initialPath);

  const [parentPath, setParentPath] =
    useState<string | null>(null);

  const [entries, setEntries] =
    useState<FsEntry[]>([]);

  // The entry the user single-clicked without entering it: the
  // effective selection while it's set, distinct from the directory
  // currently listed.
  const [selectedPath, setSelectedPath] =
    useState<string | null>(null);

  const [isLoading, setLoading] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  async function navigateTo(path: string) {
    setLoading(true);
    setError(null);

    try {
      const result = await listDirs(path, {
        includeFiles: true,
        extensions: fileExtensions,
      });
      setPathInput(result.path);
      setParentPath(result.parent);
      setEntries(result.entries);
      setSelectedPath(null);
      // In "directories" mode, browsing into a directory is itself a
      // valid default selection. In "files" mode there's no such
      // default: wait for an explicit file click, and invalidate
      // whatever was selected before this navigation.
      onPathChange(mode === "directories" ? result.path : "");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to list directories."
      );
    } finally {
      setLoading(false);
    }
  }

  function handleEntryClick(entry: FsEntry) {
    // Always highlight whatever was clicked, so clicking something
    // that isn't a valid pick for this mode still gives feedback
    // instead of looking like the click did nothing.
    setSelectedPath(entry.path);

    if (isSelectable(entry, mode)) {
      setPathInput(entry.path);
      onPathChange(entry.path);
    } else {
      onPathChange("");
    }
  }

  useEffect(() => {
    navigateTo(initialPath);
    // Only on mount: navigation from here on is driven by user input.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (

    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 8,
        minHeight: 0,
        flex: 1,
      }}
    >

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
      >

        <button
          onClick={() => parentPath && navigateTo(parentPath)}
          disabled={!parentPath || isLoading}
        >
          Up
        </button>

        <input

          type="text"

          value={pathInput}

          onChange={(event) => {
            setPathInput(event.target.value);
            setSelectedPath(null);
          }}

          onKeyDown={(event) => {
            if (event.key === "Enter") {
              navigateTo(pathInput);
            }
          }}

          style={{
            flex: 1,
            fontFamily: "monospace",
            fontSize: 13,
          }}

        />

      </div>

      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflowY: "auto",
          border: "1px solid #ddd",
          borderRadius: 4,
        }}
      >

        {isLoading && (
          <div style={{ padding: 8, fontSize: 14, color: "#666" }}>
            Loading...
          </div>
        )}

        {!isLoading && entries.length === 0 && (
          <div style={{ padding: 8, fontSize: 14, color: "#666" }}>
            No entries.
          </div>
        )}

        {!isLoading && entries.map((entry) => (
          <div
            key={entry.path}
            onClick={() => handleEntryClick(entry)}
            onDoubleClick={() => {
              if (entry.type === "dir") {
                navigateTo(entry.path);
              } else {
                handleEntryClick(entry);
              }
            }}
            style={{
              padding: "6px 8px",
              fontSize: 14,
              cursor: "pointer",
              borderBottom: "1px solid #f0f0f0",
              background: entry.path === selectedPath ? "#cce5ff" : undefined,
            }}
          >
            {entry.type === "dir" ? "📁" : "📄"} {entry.name}
          </div>
        ))}

      </div>

      {error && (
        <div style={{ color: "#b00020", fontSize: 14 }}>
          {error}
        </div>
      )}

    </div>

  );

}
