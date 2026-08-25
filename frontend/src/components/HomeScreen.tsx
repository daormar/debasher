import { useState } from "react";
import type { Workflow } from "../models/workflow";
import { createEmptyWorkflow } from "../storage/workflowStorage";
import NewWorkflowDialog from "./NewWorkflowDialog";
import LoadWorkflowDialog from "./LoadWorkflowDialog";

interface Props {
  // Called with the workflow that should be opened in the editor.
  onOpen: (workflow: Workflow) => void;
}

export default function HomeScreen({ onOpen }: Props) {
  const [isNewWorkflowOpen, setNewWorkflowOpen] = useState(false);
  const [isLoadWorkflowOpen, setLoadWorkflowOpen] = useState(false);

  function handleCreate(name: string) {
    onOpen(createEmptyWorkflow(name));
  }

  return (
    <div style={{ padding: 32, maxWidth: 480, margin: "0 auto" }}>
      <h1>Debasher</h1>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <button onClick={() => setNewWorkflowOpen(true)}>
          Create new workflow
        </button>

        <button onClick={() => setLoadWorkflowOpen(true)}>
          Load workflow
        </button>

        <button disabled title="Coming soon">
          Import workflow
        </button>
      </div>

      {isNewWorkflowOpen && (
        <NewWorkflowDialog
          onCreate={handleCreate}
          onClose={() => setNewWorkflowOpen(false)}
        />
      )}

      {isLoadWorkflowOpen && (
        <LoadWorkflowDialog
          onLoad={onOpen}
          onClose={() => setLoadWorkflowOpen(false)}
        />
      )}
    </div>
  );
}
