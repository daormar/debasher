import { useState } from "react";
import type { Program } from "../models/program";
import { importProgram } from "../storage/programStorage";
import DirectoryBrowserModal from "./DirectoryBrowserModal";
import FileBrowserModal from "./FileBrowserModal";

interface Props {
  onImport: (program: Program) => void;
  onClose: () => void;
}

// The directory a file path lives in, or "" (browse from the server's
// home directory) when there's no path yet to anchor on.
function parentDirOf(path: string): string {
  const slash = path.lastIndexOf("/");
  return slash <= 0 ? "" : path.slice(0, slash);
}

export default function ImportProgramDialog({ onImport, onClose }: Props) {

  const [scriptPath, setScriptPath] =
    useState("");

  const [debasherModDir, setDebasherModDir] =
    useState("");

  const [isImporting, setImporting] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  const [dirBrowserOpen, setDirBrowserOpen] =
    useState(false);

  const [fileBrowserOpen, setFileBrowserOpen] =
    useState(false);

  async function handleImport() {

    if (!scriptPath.trim()) {
      setError("Please enter a script path.");
      return;
    }

    setImporting(true);
    setError(null);

    try {
      const program = await importProgram(scriptPath.trim(), debasherModDir.trim());
      onImport(program);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to import program."
      );
    } finally {
      setImporting(false);
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
        style={{
          width: "60%",
          maxWidth: 480,
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >

        <h3 style={{ margin: 0 }}>
          Import program
        </h3>

        <label style={{ fontSize: 14 }}>
          DEBASHER_MOD_DIR (optional)
        </label>

        <div style={{ display: "flex", gap: 8 }}>

          <input

            type="text"

            value={debasherModDir}

            onChange={(event) =>
              setDebasherModDir(event.target.value)
            }

            onKeyDown={(event) => {
              if (event.key === "Enter") {
                handleImport();
              }
            }}

            placeholder="/path/to/modules"

            autoFocus

            style={{
              flex: 1,
            }}

          />

          <button
            type="button"
            onClick={() => setDirBrowserOpen(true)}
            disabled={isImporting}
          >
            Browse...
          </button>

        </div>

        {dirBrowserOpen && (
          <DirectoryBrowserModal
            initialPath={debasherModDir}
            onSelect={(path) => {
              setDebasherModDir(path);
              setDirBrowserOpen(false);
            }}
            onClose={() => setDirBrowserOpen(false)}
          />
        )}

        <label style={{ fontSize: 14 }}>
          Script path (.sh)
        </label>

        <div style={{ display: "flex", gap: 8 }}>

          <input

            type="text"

            value={scriptPath}

            onChange={(event) =>
              setScriptPath(event.target.value)
            }

            onKeyDown={(event) => {
              if (event.key === "Enter") {
                handleImport();
              }
            }}

            placeholder="/path/to/program.sh"

            style={{
              flex: 1,
            }}

          />

          <button
            type="button"
            onClick={() => setFileBrowserOpen(true)}
            disabled={isImporting}
          >
            Browse...
          </button>

        </div>

        {fileBrowserOpen && (
          <FileBrowserModal
            initialPath={parentDirOf(scriptPath)}
            fileExtensions={[".sh"]}
            onSelect={(path) => {
              setScriptPath(path);
              setFileBrowserOpen(false);
            }}
            onClose={() => setFileBrowserOpen(false)}
          />
        )}

        {error && (
          <div style={{ color: "#b00020", fontSize: 14 }}>
            {error}
          </div>
        )}

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
          }}
        >

          <button onClick={onClose} disabled={isImporting}>
            Cancel
          </button>

          <button onClick={handleImport} disabled={isImporting}>
            {isImporting ? "Importing..." : "Import"}
          </button>

        </div>

      </div>

    </div>

  );

}
