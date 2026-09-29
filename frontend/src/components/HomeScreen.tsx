import { useState } from "react";
import type { Program, ProgramType } from "../models/program";
import { createEmptyProgram } from "../storage/programStorage";
import NewProgramDialog from "./NewProgramDialog";
import LoadProgramDialog from "./LoadProgramDialog";
import ImportProgramDialog from "./ImportProgramDialog";

interface Props {
  // Called with the program that should be opened in the editor.
  onOpen: (program: Program) => void;
  // Where a run left in progress goes on, after leaving the editor.
  notice: string | null;
  onDismissNotice: () => void;
}

export default function HomeScreen({ onOpen, notice, onDismissNotice }: Props) {
  const [isNewProgramOpen, setNewProgramOpen] = useState(false);
  const [isLoadProgramOpen, setLoadProgramOpen] = useState(false);
  const [isImportProgramOpen, setImportProgramOpen] = useState(false);

  function handleCreate(name: string, programType: ProgramType) {
    onOpen(createEmptyProgram(name, programType));
  }

  return (
    <div style={{ padding: 32, maxWidth: 480, margin: "0 auto" }}>
      <h1>DeBasher</h1>

      {notice && (
        <div
          data-run-notice
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: 12,
            marginBottom: 16,
            padding: "10px 12px",
            background: "#fdf6dc",
            border: "1px solid #e6d9a8",
            borderRadius: 4,
            fontSize: 14,
          }}
        >
          <span style={{ flex: 1 }}>{notice}</span>
          <button onClick={onDismissNotice}>Dismiss</button>
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <button onClick={() => setNewProgramOpen(true)}>
          Create new program
        </button>

        <button onClick={() => setLoadProgramOpen(true)}>
          Load program
        </button>

        <button onClick={() => setImportProgramOpen(true)}>
          Import program
        </button>
      </div>

      {isNewProgramOpen && (
        <NewProgramDialog
          onCreate={handleCreate}
          onClose={() => setNewProgramOpen(false)}
        />
      )}

      {isLoadProgramOpen && (
        <LoadProgramDialog
          onLoad={onOpen}
          onClose={() => setLoadProgramOpen(false)}
        />
      )}

      {isImportProgramOpen && (
        <ImportProgramDialog
          onImport={onOpen}
          onClose={() => setImportProgramOpen(false)}
        />
      )}
    </div>
  );
}
