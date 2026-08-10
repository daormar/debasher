import { useWorkflow } from "../store/WorkflowContext";

interface Props {
  onClose: () => void;
}

export default function Toolbar({ onClose }: Props) {

  const {
    addNode,
    save,
  } = useWorkflow();


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
        onClick={addNode}
      >
        New node
      </button>

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
