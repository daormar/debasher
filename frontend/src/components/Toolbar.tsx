import { useState } from "react";

import { useWorkflow } from "../store/WorkflowContext";
import PreambleEditor from "./PreambleEditor";
import SaveDialog from "./SaveDialog";
import ProcessNameDialog from "./ProcessNameDialog";
import RunMenu from "./RunMenu";

interface Props {
  onClose: () => void;
}

export default function Toolbar({ onClose }: Props) {

  const {
    workflow,
    addProcess,
  } = useWorkflow();

  const [isPreambleOpen, setPreambleOpen] =
    useState(false);

  const [isSaveOpen, setSaveOpen] =
    useState(false);

  const [isNewProcessOpen, setNewProcessOpen] =
    useState(false);


  return (

    <div
      style={{
        padding: 8,
        borderBottom: "1px solid #ddd",
        background: "#f5f5f5",
        display: "flex",
        gap: 8,
      }}
    >

      <strong
        style={{
          alignSelf: "center",
          marginRight: 8,
        }}
      >
        {workflow.name}
      </strong>

      <button
        onClick={() => setPreambleOpen(true)}
      >
        Preamble
      </button>

      <button
        onClick={() => setNewProcessOpen(true)}
      >
        New process
      </button>

      {isNewProcessOpen && (
        <ProcessNameDialog
          title="New process"
          confirmLabel="Create"
          existingNames={workflow.processes.map(process => process.name)}
          preamble={workflow.preamble}
          onConfirm={addProcess}
          onClose={() => setNewProcessOpen(false)}
        />
      )}

      {isPreambleOpen && (
        <PreambleEditor
          onClose={() => setPreambleOpen(false)}
        />
      )}

      <button
        onClick={() => setSaveOpen(true)}
      >
        Save
      </button>

      {isSaveOpen && (
        <SaveDialog
          onClose={() => setSaveOpen(false)}
        />
      )}

      <RunMenu />

      <button
        onClick={onClose}
        style={{ marginLeft: "auto" }}
      >
        Close
      </button>


    </div>

  );

}
