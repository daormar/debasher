import { useState } from "react";

import type { ProgramType } from "../models/program";

interface Props {
  onCreate: (name: string, programType: ProgramType) => void;
  onClose: () => void;
}

// The type of a program is chosen here, once: it never changes
// afterwards, since the two types accept different processes and
// connections.
const PROGRAM_TYPES: { value: ProgramType; label: string; description: string }[] = [
  {
    value: "general",
    label: "General program",
    description: "A run that starts and finishes.",
  },
  {
    value: "resident",
    label: "Resident program",
    description:
      "Nodes that stay alive, keep state, recover from crashes and go " +
      "through rounds. The type cannot be changed later.",
  },
];

export default function NewProgramDialog({ onCreate, onClose }: Props) {

  const [name, setName] =
    useState("");

  const [programType, setProgramType] =
    useState<ProgramType>("general");

  const [error, setError] =
    useState<string | null>(null);

  function handleCreate() {

    if (!name.trim()) {
      setError("Please enter a program name.");
      return;
    }

    onCreate(name.trim(), programType);

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
          width: "60%",
          maxWidth: 480,
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >

        <h3 style={{ margin: 0 }}>
          New program
        </h3>

        <label style={{ fontSize: 14 }}>
          Program name
        </label>

        <input

          type="text"

          value={name}

          onChange={(event) =>
            setName(event.target.value)
          }

          onKeyDown={(event) => {
            if (event.key === "Enter") {
              handleCreate();
            }
          }}

          placeholder="My program"

          autoFocus

          style={{
            width: "100%",
          }}

        />

        <label style={{ fontSize: 14 }}>
          Program type
        </label>

        {PROGRAM_TYPES.map(({ value, label, description }) => (
          <label
            key={value}
            style={{ display: "flex", alignItems: "flex-start", gap: 6, fontSize: 14 }}
          >
            <input
              type="radio"
              name="program-type"
              value={value}
              checked={programType === value}
              onChange={() => setProgramType(value)}
            />
            <span>
              {label}
              <span style={{ display: "block", color: "#666", fontSize: 12 }}>
                {description}
              </span>
            </span>
          </label>
        ))}

        {error && (
          <div style={{ color: "#b00020", fontSize: 14 }}>
            {error}
          </div>
        )}

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
          }}
        >

          <button onClick={onClose}>
            Cancel
          </button>

          <button onClick={handleCreate}>
            Create
          </button>

        </div>

      </div>

    </div>

  );

}
