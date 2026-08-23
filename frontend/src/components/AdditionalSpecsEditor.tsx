import { useState } from "react";

import { useWorkflow } from "../store/WorkflowContext";
import type { WorkflowNode } from "../models/node";

interface Props {
  node: WorkflowNode;
  onClose: () => void;
}

export default function AdditionalSpecsEditor({ node, onClose }: Props) {

  const { setAdditionalSpecs } = useWorkflow();

  const [forced, setForced] =
    useState(node.additionalSpecs.forced);

  const [processdeps, setProcessdeps] =
    useState(node.additionalSpecs.processdeps ?? "");

  const [alias, setAlias] =
    useState(node.additionalSpecs.alias ?? "");

  const [externalAlias, setExternalAlias] =
    useState(node.additionalSpecs.externalAlias ?? "");

  function handleSave() {

    setAdditionalSpecs(node.id, {
      forced,
      processdeps: processdeps.trim() ? processdeps : undefined,
      alias: alias.trim() ? alias : undefined,
      externalAlias: externalAlias.trim() ? externalAlias : undefined,
    });

    onClose();

  }

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
          width: 360,
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >

        <h3 style={{ margin: 0 }}>
          Additional Specifications
        </h3>

        <label>

          <input

            type="checkbox"

            checked={forced}

            onChange={(event) =>
              setForced(event.target.checked)
            }

          />
          {" "}forced

        </label>

        <label>
          Process dependencies
        </label>

        <input

          value={processdeps}

          onChange={(event) =>
            setProcessdeps(event.target.value)
          }

          style={{
            width: "100%",
          }}

        />

        <label>
          Alias
        </label>

        <input

          value={alias}

          onChange={(event) =>
            setAlias(event.target.value)
          }

          style={{
            width: "100%",
          }}

        />

        <label>
          External Alias
        </label>

        <input

          value={externalAlias}

          onChange={(event) =>
            setExternalAlias(event.target.value)
          }

          style={{
            width: "100%",
          }}

        />

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
            marginTop: 8,
          }}
        >

          <button onClick={onClose}>
            Cancel
          </button>

          <button onClick={handleSave}>
            Save
          </button>

        </div>

      </div>

    </div>

  );

}
