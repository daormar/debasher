import { useState } from "react";

import { useProgram } from "../store/ProgramContext";
import type { ComputationalSpecs, ProgramProcess } from "../models/process";
import { DEFAULT_COMPUTATIONAL_SPECS } from "../models/process";
import { RESIDENT_SPEC_FIELDS, RESIDENT_SPEC_LABELS } from "../models/node";

// The schedulers that a ProgramLauncher may give its batch runs.
const BATCH_SCHEDULERS = ["BUILTIN", "SLURM"];

interface Props {
  process: ProgramProcess;
  onClose: () => void;
}

export default function ComputationalSpecsEditor({ process, onClose }: Props) {

  const { setComputationalSpecs } = useProgram();

  const [cpus, setCpus] =
    useState(
      (process.computationalSpecs.cpus ?? DEFAULT_COMPUTATIONAL_SPECS.cpus).toString()
    );

  const [mem, setMem] =
    useState(
      (process.computationalSpecs.mem ?? DEFAULT_COMPUTATIONAL_SPECS.mem).toString()
    );

  const [time, setTime] =
    useState(process.computationalSpecs.time ?? DEFAULT_COMPUTATIONAL_SPECS.time);

  // The specifications that the node kind of a process of a resident
  // program reads, besides cpus, mem and time; an empty one leaves the
  // default of its class. None for a process of a general program.
  const residentFields = process.nodeKind ? RESIDENT_SPEC_FIELDS[process.nodeKind] : [];

  const [residentValues, setResidentValues] =
    useState<Record<string, string>>(() =>
      Object.fromEntries(
        residentFields.map(field => [field, process.computationalSpecs[field]?.toString() ?? ""])
      )
    );

  function handleSave() {

    const specs: ComputationalSpecs = {
      cpus: cpus.trim() ? Number(cpus) : undefined,
      mem: mem.trim() ? Number(mem) : undefined,
      time: time.trim() ? time : undefined,
    };

    for (const field of residentFields) {
      const text = residentValues[field].trim();
      if (!text) {
        continue;
      }
      if (field === "batch_sched") {
        specs.batch_sched = text;
      } else {
        specs[field] = Number(text);
      }
    }

    setComputationalSpecs(process.id, specs);

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
          maxHeight: "90vh",
          overflowY: "auto",
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
          Memory (MB)
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
          Time (hh:mm:ss)
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

        {residentFields.map(field => (

          <div key={field} style={{ display: "flex", flexDirection: "column", gap: 4 }}>

            <label>
              {RESIDENT_SPEC_LABELS[field]}
            </label>

            {field === "batch_sched" ? (

              <select
                value={residentValues[field]}
                onChange={(event) =>
                  setResidentValues(current => ({ ...current, [field]: event.target.value }))
                }
                style={{ width: "100%" }}
              >
                <option value="">Default of the class</option>
                {BATCH_SCHEDULERS.map(sched => (
                  <option key={sched} value={sched}>{sched}</option>
                ))}
              </select>

            ) : (

              <input
                type="number"
                min={0}
                value={residentValues[field]}
                placeholder="Default of the class"
                onChange={(event) =>
                  setResidentValues(current => ({ ...current, [field]: event.target.value }))
                }
                style={{ width: "100%" }}
              />

            )}

          </div>

        ))}

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
