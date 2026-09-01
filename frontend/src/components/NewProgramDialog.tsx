import { useState } from "react";

interface Props {
  onCreate: (name: string) => void;
  onClose: () => void;
}

export default function NewProgramDialog({ onCreate, onClose }: Props) {

  const [name, setName] =
    useState("");

  const [error, setError] =
    useState<string | null>(null);

  function handleCreate() {

    if (!name.trim()) {
      setError("Please enter a program name.");
      return;
    }

    onCreate(name.trim());

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
