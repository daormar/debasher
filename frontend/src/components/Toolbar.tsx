import { useState } from "react";

import { useWorkflow } from "../store/WorkflowContext";
import PreambleEditor from "./PreambleEditor";
import SaveDialog from "./SaveDialog";

interface Props {
  onClose: () => void;
}

export default function Toolbar({ onClose }: Props) {

  const {
    addProcess,
  } = useWorkflow();

  const [isPreambleOpen, setPreambleOpen] =
    useState(false);

  const [isSaveOpen, setSaveOpen] =
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

      <button
        onClick={() => setPreambleOpen(true)}
      >
        Preamble
      </button>

      <button
        onClick={addProcess}
      >
        New process
      </button>

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

      <button
        onClick={onClose}
        style={{ marginLeft: "auto" }}
      >
        Close
      </button>


    </div>

  );

}
