import { useState } from "react";

import { useWorkflow } from "../store/WorkflowContext";
import PreambleEditor from "./PreambleEditor";

interface Props {
  onClose: () => void;
}

export default function Toolbar({ onClose }: Props) {

  const {
    addProcess,
    save,
  } = useWorkflow();

  const [isPreambleOpen, setPreambleOpen] =
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
        onClick={() => save()}
      >
        Save
      </button>

      <button
        onClick={onClose}
        style={{ marginLeft: "auto" }}
      >
        Close
      </button>


    </div>

  );

}
