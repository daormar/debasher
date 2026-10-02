import { useState } from "react";

import MethodBodyEditor from "./MethodBodyEditor";
import type { ProgramProcess } from "../models/process";
import { PROCESS_METHODS, type ProcessMethod } from "../models/processMethods";

interface Props {
  process: ProgramProcess;
  onClose: () => void;
}

// The DEBASHER_PROCESS_METHODS (engine/debasher_lib.sh) not covered
// elsewhere in the Inspector: "document" is the Description field,
// "exec" is the "Edit code" implementation, and the option explanation/
// definition methods are driven by the process's options/options
// handler. What each of the others does is in models/processMethods.ts.
export default function AdditionalMethodsEditor({ process, onClose }: Props) {

  const [editingMethod, setEditingMethod] = useState<ProcessMethod | null>(null);

  return (

    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0, 0, 0, 0.4)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
    >

      <div
        style={{
          width: "70%",
          maxWidth: 900,
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >

        <h3 style={{ margin: 0 }}>
          Additional Methods: {process.name}
        </h3>

        <p style={{ margin: 0, color: "#666", fontSize: 13 }}>
          Configure the remaining process methods debasher supports,
          beyond option definition/explanation and the implementation
          itself.
        </p>

        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-start",
            gap: 8,
          }}
        >

          {PROCESS_METHODS.map(method => (
            <button
              key={method.key}
              onClick={() => setEditingMethod(method)}
            >
              Edit {method.name}
              {process.additionalMethods[method.key] ? " (defined)" : ""}
            </button>
          ))}

        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
          }}
        >

          <button onClick={onClose}>
            Close
          </button>

        </div>

      </div>

      {editingMethod && (
        <MethodBodyEditor
          process={process}
          methodKey={editingMethod.key}
          onClose={() => setEditingMethod(null)}
        />
      )}

    </div>

  );

}
