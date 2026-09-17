import { useState } from "react";
import DirectoryBrowser from "./DirectoryBrowser";

interface Props {
  // Directory to open the browser at; falsy/invalid falls back to the
  // server's home directory (see api/routers/fs_browse.py).
  initialPath: string;
  onSelect: (path: string) => void;
  onClose: () => void;
}

// Standalone "pick a directory" dialog: a modal wrapper around
// DirectoryBrowser with its own Select/Cancel step, for callers that
// need a directory chosen separately from another action (e.g. a
// "Browse..." button next to an existing path field). When the
// browser itself *is* the dialog's whole purpose, embed
// DirectoryBrowser directly instead (see LoadProgramDialog).
export default function DirectoryBrowserModal({ initialPath, onSelect, onClose }: Props) {

  const [currentPath, setCurrentPath] =
    useState<string | null>(null);

  return (

    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0, 0, 0, 0.4)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1100,
      }}
    >

      <div
        style={{
          width: "60%",
          maxWidth: 560,
          height: "70%",
          maxHeight: 480,
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >

        <h3 style={{ margin: 0 }}>
          Select a directory
        </h3>

        <DirectoryBrowser initialPath={initialPath} onPathChange={setCurrentPath} />

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
          }}
        >

          <button onClick={onClose}>
            Cancel
          </button>

          <button
            onClick={() => currentPath && onSelect(currentPath)}
            disabled={!currentPath}
          >
            Select this directory
          </button>

        </div>

      </div>

    </div>

  );

}
