import { useEffect, useState } from "react";

import { listSchedulers } from "../api/executionApi";
import type { Durability } from "../models/program";
import { useProgram } from "../store/ProgramContext";

// The durability mode of a resident program (see "The non-durable mode" in
// doc/design_doc_resident.md), as the dialog offers it.
const DURABILITY_MODES: { value: Durability; label: string; description: string }[] = [
  {
    value: "durable",
    label: "Durable",
    description:
      "Every node keeps an input log and checkpoints, and comes back from a " +
      "crash or a stop with the state it had. Its process_data has to be " +
      "deterministic, and the program takes snapshots regularly.",
  },
  {
    value: "non-durable",
    label: "Non-durable",
    description:
      "No input log, checkpoints or rounds: a node that crashes or stops " +
      "starts again with its initial state, and nothing is replayed.",
  },
];

interface Props {
  onClose: () => void;
}

const schedulerFieldsStyle: React.CSSProperties = {
  gridArea: "1 / 1",
  display: "flex",
  flexDirection: "column",
  gap: 8,
};

export default function ExecutionOptionsEditor({ onClose }: Props) {

  const {
    program,
    setExecutionOptions,
    setDurability,
  } = useProgram();

  // The engine forces the built-in scheduler in oneshot mode on a resident
  // program, which launches every process at once: there is no scheduler to
  // choose, and only the limits of the built-in scheduler apply.
  const isResident =
    program.programType === "resident";

  // The durability mode, which only a resident program has; the snapshot
  // period applies to the durable mode only
  const [durability, setDurabilityChoice] =
    useState<Durability>(program.durability ?? "durable");

  const isDurable = durability !== "non-durable";

  // programEdits.ts's normalizeProgram guarantees this is never falsy, so
  // no fallback here: a fallback would just mask a genuinely empty
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

  const [snapshotEverySecs, setSnapshotEverySecs] =
    useState(program.executionOptions.snapshotEverySecs ?? "");

  // Empty, or a positive number of seconds, as debasher_snapshot_resident
  // --every takes it.
  const isSnapshotPeriodValid =
    /^\s*(\d*[1-9]\d*)?\s*$/.test(snapshotEverySecs);

  const [schedulers, setSchedulers] =
    useState<string[]>([]);

  const [isLoading, setLoading] =
    useState(!isResident);

  const [error, setError] =
    useState<string | null>(null);

  useEffect(() => {

    if (isResident) {
      return;
    }

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

  }, [isResident]);

  // The limits of the built-in scheduler, shown on a resident program and
  // on another one when it runs under that scheduler.
  const builtinFields = (
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
  );

  function handleSave() {
    if (isResident && durability !== (program.durability ?? "durable")) {
      setDurability(durability);
    }
    setExecutionOptions({
      scheduler,
      builtinSchedCpus,
      builtinSchedMem,
      dfltNodes,
      dfltThrottle,
      rerunOutdatedProcs,
      condaSupport,
      dockerSupport,
      snapshotEverySecs: snapshotEverySecs.trim(),
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

        {isResident ? (

          <p style={{ margin: 0, fontSize: 14, color: "#555" }}>
            A resident program runs under the built-in scheduler, which
            launches every process at once. The launch is refused, before
            any process starts, when the processes do not all fit in the
            limits below.
          </p>

        ) : (

          <>

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

          </>

        )}

        {isResident && builtinFields}

        {/* The fields of each scheduler share one place, sized by the
            tallest, and those of the scheduler not chosen are hidden: the
            dialog keeps its size when the scheduler changes. */}
        {!isResident && (
          <div style={{ display: "grid" }}>

            <div style={{ ...schedulerFieldsStyle, visibility: scheduler === "BUILTIN" ? "visible" : "hidden" }}>
              {builtinFields}
            </div>

            <div style={{ ...schedulerFieldsStyle, visibility: scheduler === "SLURM" ? "visible" : "hidden" }}>
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
            </div>

          </div>
        )}

        {isResident && (
          <>

            <label style={{ fontSize: 14 }}>
              Durability mode
            </label>

            {DURABILITY_MODES.map(({ value, label, description }) => (
              <label
                key={value}
                style={{ display: "flex", alignItems: "flex-start", gap: 6, fontSize: 14 }}
              >
                <input
                  type="radio"
                  name="durability"
                  value={value}
                  checked={durability === value}
                  onChange={() => setDurabilityChoice(value)}
                />
                <span>
                  {label}
                  <span style={{ display: "block", color: "#666", fontSize: 12 }}>
                    {description}
                  </span>
                </span>
              </label>
            ))}

            <p style={{ margin: 0, fontSize: 13, color: "#555" }}>
              The mode is declared in the generated script. A program does
              not change its mode over the program state of a run: "Run
              program" then offers to reset the state and start afresh.
            </p>

          </>
        )}

        {isResident && isDurable && (
          <>

            <label style={{ fontSize: 14 }}>
              Snapshot period in seconds (blank = no periodic snapshots)
            </label>

            <input
              type="text"
              value={snapshotEverySecs}
              placeholder="e.g. 300"
              onChange={(event) => setSnapshotEverySecs(event.target.value)}
              style={{ width: "100%" }}
            />

            {!isSnapshotPeriodValid && (
              <div style={{ color: "#b00020", fontSize: 13 }}>
                The period must be a positive number of seconds.
              </div>
            )}

            <p style={{ margin: 0, fontSize: 13, color: "#555" }}>
              The nodes write checkpoints and prune their input logs only when
              a round closes. With no period, the only rounds are those of
              "Take snapshot", and the input logs grow until their size cap
              stops the nodes. A period has to be longer than a round takes,
              or each round replaces the one before it and none closes. It
              applies from the next launch from the web UI.
            </p>

          </>
        )}


        {!isResident && (
          <>

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

          </>
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

          <button onClick={handleSave} disabled={!isSnapshotPeriodValid}>
            Save
          </button>

        </div>

      </div>

    </div>

  );

}
