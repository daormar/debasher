import { useEffect, useRef } from "react";

const MENU_ITEMS = [
  "Show options",
  "Show stdout",
  "Show scheduler output",
  "Show inputs and outputs",
] as const;

export type ProcessOutputKind = "stdout" | "sched-out" | "opts";

// "io" opens the structured "Show inputs and outputs" modal rather
// than a plain-text CommandOutputModal — see ProgramCanvas's onSelect.
export type ProcessMenuAction = ProcessOutputKind | "io";

const KIND_BY_ITEM: Record<(typeof MENU_ITEMS)[number], ProcessMenuAction> = {
  "Show options": "opts",
  "Show stdout": "stdout",
  "Show scheduler output": "sched-out",
  "Show inputs and outputs": "io",
};

interface Props {
  x: number;
  y: number;
  isPending: boolean;
  onSelect: (action: ProcessMenuAction) => void;
  onClose: () => void;
}

export default function ProcessContextMenu({
  x,
  y,
  isPending,
  onSelect,
  onClose,
}: Props) {

  const containerRef =
    useRef<HTMLDivElement>(null);

  useEffect(() => {

    function handleClickOutside(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        onClose();
      }
    }

    document.addEventListener("mousedown", handleClickOutside, true);

    return () =>
      document.removeEventListener("mousedown", handleClickOutside, true);

  }, [onClose]);

  return (

    <div
      ref={containerRef}
      style={{
        position: "fixed",
        top: y,
        left: x,
        background: "#fff",
        border: "1px solid #ccc",
        borderRadius: 4,
        boxShadow: "0 2px 8px rgba(0, 0, 0, 0.15)",
        display: "flex",
        flexDirection: "column",
        minWidth: 200,
        zIndex: 1000,
      }}
    >

      {MENU_ITEMS.map(item => (

        <button

          key={item}

          onClick={() => onSelect(KIND_BY_ITEM[item])}

          disabled={isPending}

          style={{
            textAlign: "left",
            padding: "8px 12px",
            border: "none",
            background: "none",
            cursor: "pointer",
          }}

        >
          {item}
        </button>

      ))}

    </div>

  );

}
