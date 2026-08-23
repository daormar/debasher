import { useState } from "react";

import { useWorkflow } from "../store/WorkflowContext";
import type { WorkflowNode } from "../models/node";

interface Props {
  node: WorkflowNode;
  onClose: () => void;
}

export default function ComputationalSpecsEditor({ node, onClose }: Props) {

  const { setComputationalSpecs } = useWorkflow();

  const [cpus, setCpus] =
    useState(node.computationalSpecs.cpus?.toString() ?? "");

  const [mem, setMem] =
    useState(node.computationalSpecs.mem?.toString() ?? "");

  const [time, setTime] =
    useState(node.computationalSpecs.time ?? "");

  function handleSave() {

    setComputationalSpecs(node.id, {
      cpus: cpus.trim() ? Number(cpus) : undefined,
      mem: mem.trim() ? Number(mem) : undefined,
      time: time.trim() ? time : undefined,
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
          Computational Specifications
        </h3>

        <label>
          CPUs
        </label>

        <input

          type="number"

          value={cpus}

          onChange={(event) =>
            setCpus(event.target.value)
          }

          style={{
            width: "100%",
          }}

        />

        <label>
          Memory
        </label>

        <input

          type="number"

          value={mem}

          onChange={(event) =>
            setMem(event.target.value)
          }

          style={{
            width: "100%",
          }}

        />

        <label>
          Time
        </label>

        <input

          value={time}

          onChange={(event) =>
            setTime(event.target.value)
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
