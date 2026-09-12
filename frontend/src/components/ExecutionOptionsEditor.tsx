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

  // ProgramContext's normalizeProgram guarantees this is never falsy, so
  // no fallback here — a fallback would just mask a genuinely empty
  // stored value behind a display that looks fine, which is exactly what
  // let that case go unnoticed before (see normalizeProgram).
  const [scheduler, setScheduler] =
    useState(program.executionOptions.scheduler);

  const [builtinSchedCpus, setBuiltinSchedCpus] =
    useState(program.executionOptions.builtinSchedCpus ?? "");

  const [builtinSchedMem, setBuiltinSchedMem] =
    useState(program.executionOptions.builtinSchedMem ?? "");

  const [dfltNodes, setDfltNodes] =
    useState(program.executionOptions.dfltNodes ?? "");

  const [dfltThrottle, setDfltThrottle] =
    useState(program.executionOptions.dfltThrottle ?? "");

  const [rerunOutdatedProcs, setRerunOutdatedProcs] =
    useState(program.executionOptions.rerunOutdatedProcs ?? false);

  const [condaSupport, setCondaSupport] =
    useState(program.executionOptions.condaSupport ?? false);

  const [dockerSupport, setDockerSupport] =
    useState(program.executionOptions.dockerSupport ?? false);

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
    setExecutionOptions({
      scheduler,
      builtinSchedCpus,
      builtinSchedMem,
      dfltNodes,
      dfltThrottle,
      rerunOutdatedProcs,
      condaSupport,
      dockerSupport,
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

        {scheduler === "BUILTIN" && (
          <>

            <label style={{ fontSize: 14 }}>
              Built-in scheduler CPUs (blank = unlimited)
            </label>

            <input
              type="text"
              value={builtinSchedCpus}
              placeholder="e.g. 4"
              onChange={(event) => setBuiltinSchedCpus(event.target.value)}
              style={{ width: "100%" }}
            />

            <label style={{ fontSize: 14 }}>
              Built-in scheduler memory (blank = unlimited)
            </label>

            <input
              type="text"
              value={builtinSchedMem}
              placeholder="e.g. 4096 or 4G"
              onChange={(event) => setBuiltinSchedMem(event.target.value)}
              style={{ width: "100%" }}
            />

          </>
        )}

        {scheduler === "SLURM" && (
          <>

            <label style={{ fontSize: 14 }}>
              Default nodes (blank = scheduler default)
            </label>

            <input
              type="text"
              value={dfltNodes}
              placeholder="e.g. node01,node02 or node[01-04]"
              onChange={(event) => setDfltNodes(event.target.value)}
              style={{ width: "100%" }}
            />

          </>
        )}

        <label style={{ fontSize: 14 }}>
          Default job array throttle (blank = unthrottled)
        </label>

        <input
          type="text"
          value={dfltThrottle}
          placeholder="e.g. 10"
          onChange={(event) => setDfltThrottle(event.target.value)}
          style={{ width: "100%" }}
        />

        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14 }}>
          <input
            type="checkbox"
            checked={rerunOutdatedProcs}
            onChange={(event) => setRerunOutdatedProcs(event.target.checked)}
          />
          Rerun processes with outdated code
        </label>

        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14 }}>
          <input
            type="checkbox"
            checked={condaSupport}
            onChange={(event) => setCondaSupport(event.target.checked)}
          />
          Enable conda support
        </label>

        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14 }}>
          <input
            type="checkbox"
            checked={dockerSupport}
            onChange={(event) => setDockerSupport(event.target.checked)}
          />
          Enable docker support
        </label>

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
