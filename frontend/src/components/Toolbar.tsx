import { useState } from "react";

import { useWorkflow } from "../store/WorkflowContext";
import EnvVarsEditor from "./EnvVarsEditor";
import WorkflowDescriptionEditor from "./WorkflowDescriptionEditor";
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

  const [isDescriptionOpen, setDescriptionOpen] =
    useState(false);

  const [isPreambleOpen, setPreambleOpen] =
    useState(false);

  const [isEnvVarsOpen, setEnvVarsOpen] =
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
        onClick={() => setEnvVarsOpen(true)}
      >
        Env vars
      </button>

      <button
        onClick={() => setPreambleOpen(true)}
      >
        Preamble
      </button>

      <button
        onClick={() => setDescriptionOpen(true)}
      >
        Description
      </button>

      <button
        onClick={() => setNewProcessOpen(true)}
      >
        Add process
      </button>

      {isNewProcessOpen && (
        <ProcessNameDialog
          title="Add process"
          confirmLabel="Add"
          existingNames={workflow.processes.map(process => process.name)}
          preamble={workflow.preamble}
          envVars={workflow.envVars}
          onConfirm={addProcess}
          onClose={() => setNewProcessOpen(false)}
        />
      )}

      {isDescriptionOpen && (
        <WorkflowDescriptionEditor
          onClose={() => setDescriptionOpen(false)}
        />
      )}

      {isPreambleOpen && (
        <PreambleEditor
          onClose={() => setPreambleOpen(false)}
        />
      )}

      {isEnvVarsOpen && (
        <EnvVarsEditor
          onClose={() => setEnvVarsOpen(false)}
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
