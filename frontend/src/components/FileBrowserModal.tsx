import { useState } from "react";
import DirectoryBrowser from "./DirectoryBrowser";

interface Props {
  // Directory to open the browser at; falsy/invalid falls back to the
  // server's home directory (see api/routers/fs_browse.py).
  initialPath: string;
  // Case-insensitive suffix filter, e.g. [".sh"].
  fileExtensions?: string[];
  onSelect: (path: string) => void;
  onClose: () => void;
}

// Standalone "pick a file" dialog: a modal wrapper around
// DirectoryBrowser in "files" mode, with its own Select/Cancel step.
// See DirectoryBrowserModal for the directory-picking equivalent.
export default function FileBrowserModal({
  initialPath,
  fileExtensions,
  onSelect,
  onClose,
}: Props) {

  const [selectedPath, setSelectedPath] =
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
          Select a file
        </h3>

        <DirectoryBrowser
          initialPath={initialPath}
          mode="files"
          fileExtensions={fileExtensions}
          onPathChange={setSelectedPath}
        />

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
            onClick={() => selectedPath && onSelect(selectedPath)}
            disabled={!selectedPath}
          >
            Select this file
          </button>

        </div>

      </div>

    </div>

  );

}
