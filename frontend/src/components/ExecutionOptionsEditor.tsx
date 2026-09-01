import { useEffect, useState } from "react";

import { listSchedulers } from "../api/executionApi";
import { useProgram } from "../store/ProgramContext";

interface Props {
  onClose: () => void;
}

export default function ExecutionOptionsEditor({ onClose }: Props) {

  const {
    program,
    setExecutionOptions,
  } = useProgram();

  const [scheduler, setScheduler] =
    useState(program.executionOptions.scheduler || "BUILTIN");

  const [schedulers, setSchedulers] =
    useState<string[]>([]);

  const [isLoading, setLoading] =
    useState(true);

  const [error, setError] =
    useState<string | null>(null);

  useEffect(() => {

    let cancelled = false;

    listSchedulers()
      .then(names => {
        if (!cancelled) {
          setSchedulers(names);
        }
      })
      .catch(err => {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Failed to list schedulers."
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };

  }, []);

  function handleSave() {
    setExecutionOptions({ scheduler });
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
          Execution options
        </h3>

        <label style={{ fontSize: 14 }}>
          Scheduler
        </label>

        <select

          value={scheduler}

          onChange={(event) =>
            setScheduler(event.target.value)
          }

          disabled={isLoading}

          style={{
            width: "100%",
          }}

        >

          {isLoading && (
            <option value="">
              Loading...
            </option>
          )}

          {schedulers.map(name => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}

        </select>

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

          <button onClick={handleSave}>
            Save
          </button>

        </div>

      </div>

    </div>

  );

}
