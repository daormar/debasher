import { useState } from "react";
import type { Program } from "../models/program";
import { createEmptyProgram } from "../storage/programStorage";
import NewProgramDialog from "./NewProgramDialog";
import LoadProgramDialog from "./LoadProgramDialog";
import ImportProgramDialog from "./ImportProgramDialog";

interface Props {
  // Called with the program that should be opened in the editor.
  onOpen: (program: Program) => void;
}

export default function HomeScreen({ onOpen }: Props) {
  const [isNewProgramOpen, setNewProgramOpen] = useState(false);
  const [isLoadProgramOpen, setLoadProgramOpen] = useState(false);
  const [isImportProgramOpen, setImportProgramOpen] = useState(false);

  function handleCreate(name: string) {
    onOpen(createEmptyProgram(name));
  }

  return (
    <div style={{ padding: 32, maxWidth: 480, margin: "0 auto" }}>
      <h1>DeBasher</h1>

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
