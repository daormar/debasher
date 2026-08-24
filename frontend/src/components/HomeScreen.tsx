import { useEffect, useState } from "react";
import type { Workflow } from "../models/workflow";
import {
  listWorkflows,
  loadWorkflow,
  createEmptyWorkflow,
  type WorkflowSummary,
} from "../storage/workflowStorage";
import NewWorkflowDialog from "./NewWorkflowDialog";

interface Props {
  // Called with the workflow that should be opened in the editor.
  onOpen: (workflow: Workflow) => void;
}

export default function HomeScreen({ onOpen }: Props) {
  const [summaries, setSummaries] = useState<WorkflowSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [isNewWorkflowOpen, setNewWorkflowOpen] = useState(false);

  useEffect(() => {
    listWorkflows().then(result => {
      setSummaries(result);
      setLoading(false);
    });
  }, []);

  async function handleOpen(id: string) {
    const workflow = await loadWorkflow(id);
    onOpen(workflow);
  }

  function handleCreate(name: string) {
    onOpen(createEmptyWorkflow(name));
  }

  return (
    <div style={{ padding: 32, maxWidth: 480, margin: "0 auto" }}>
      <h1>My workflows</h1>

      <button onClick={() => setNewWorkflowOpen(true)} style={{ marginBottom: 24 }}>
        + Create new workflow
      </button>

      {isNewWorkflowOpen && (
        <NewWorkflowDialog
          onCreate={handleCreate}
          onClose={() => setNewWorkflowOpen(false)}
        />
      )}

      {loading && <p>Loading...</p>}

      {!loading && summaries.length === 0 && (
        <p>No saved workflows yet.</p>
      )}

      <ul style={{ listStyle: "none", padding: 0 }}>
        {summaries.map(summary => (
          <li key={summary.id} style={{ marginBottom: 8 }}>
            <button onClick={() => handleOpen(summary.id)}>
              {summary.name}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
