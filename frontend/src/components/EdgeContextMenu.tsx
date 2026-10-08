import { useRef } from "react";

import type { EdgeDisplayAction } from "../models/edgeDisplay";
import { useClickOutside } from "./useClickOutside";

interface Props {
  x: number;
  y: number;
  actions: EdgeDisplayAction[];
  onSelect: (action: EdgeDisplayAction) => void;
  onClose: () => void;
}

/**
 * The right-click menu of an edge of the canvas: how the edge, or every
 * edge of its output, is drawn (see edgeDisplayActions).
 */
export default function EdgeContextMenu({ x, y, actions, onSelect, onClose }: Props) {

  const containerRef = useRef<HTMLDivElement>(null);

  useClickOutside(containerRef, true, onClose);

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

      {actions.map(action => (

        <button

          key={action.label}

          onClick={() => onSelect(action)}

          style={{
            textAlign: "left",
            padding: "8px 12px",
            border: "none",
            background: "none",
            cursor: "pointer",
          }}

        >
          {action.label}
        </button>

      ))}

    </div>

  );

}
