import type { CSSProperties } from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { ProgramOption } from "../models/option";
import { fanoutBaseLabel, isFanoutOption } from "../models/option";


interface OptionRowProps {
  option: ProgramOption;
  isFanoutMode: boolean;
  onEdit: () => void;
  onRemove: () => void;
}

export default function OptionRow({
  option,
  isFanoutMode,
  onEdit,
  onRemove,
}: OptionRowProps) {

  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: option.id });

  const style: CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
    transform: CSS.Translate.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (

    <div ref={setNodeRef} style={style}>

      <span style={{ display: "flex", alignItems: "center", gap: 6 }}>

        <span
          {...attributes}
          {...listeners}
          title="Drag to reorder"
          style={{
            cursor: "grab",
            touchAction: "none",
            color: "#888",
            userSelect: "none",
          }}
        >
          ⠿
        </span>

        <span>
          {isFanoutMode && isFanoutOption(option.label) ? (
            <>
              {fanoutBaseLabel(option.label)}
              <span style={{ color: "#c0392b" }}>ith</span>
            </>
          ) : (
            option.label
          )}
        </span>

      </span>


      <span>

        <button onClick={onEdit}>
          Edit
        </button>

        <button
          onClick={onRemove}
          style={{ marginLeft: 4 }}
        >
          Remove
        </button>

      </span>

    </div>

  );

}
