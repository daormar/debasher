import { useState } from "react";
import CodeMirror from "@uiw/react-codemirror";

import { useProgram } from "../store/ProgramContext";
import { validateProcessName } from "../api/processApi";
import { languageExtension, PROCESS_LANGUAGES } from "./codeLanguages";
import type { ProcessLanguage } from "../models/process";
import type { SeqProcess } from "../models/seqProcess";
import {
  aliasOptMapFromText,
  aliasOptMapToText,
  createSeqProcess,
  seqProcessesProblem,
  withSeqProcessChanges,
} from "../models/seqProcess";

interface Props {
  onClose: () => void;
}

// A number field of the specifications: blank leaves it unset.
function numberOrUndefined(text: string): number | undefined {
  const trimmed = text.trim();
  if (trimmed === "") {
    return undefined;
  }
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : undefined;
}

/**
 * The "Sequential processes" dialog: lists the sequential processes of the
 * program, adds, renames and removes them, and edits each one (its name,
 * description, specifications with its alias, and code). It edits a draft
 * of the whole list and hands it to the store when the user saves it.
 */
export default function SeqProcessesEditor({ onClose }: Props) {

  const { program, setSeqProcesses } = useProgram();

  const [drafts, setDrafts] = useState<SeqProcess[]>(program.seqProcesses);

  const [selectedId, setSelectedId] = useState<string | null>(
    program.seqProcesses[0]?.id ?? null
  );

  const [error, setError] = useState<string | null>(null);

  const [saving, setSaving] = useState(false);

  const selected = drafts.find(draft => draft.id === selectedId) ?? null;

  function update(changes: Partial<SeqProcess>) {
    setDrafts(current =>
      current.map(draft => (draft.id === selectedId ? withSeqProcessChanges(draft, changes) : draft))
    );
  }

  function handleAdd() {
    let index = drafts.length + 1;
    const names = new Set(drafts.map(draft => draft.name));
    while (names.has(`step${index}`)) {
      index += 1;
    }
    const added = createSeqProcess(`step${index}`);
    setDrafts(current => [...current, added]);
    setSelectedId(added.id);
  }

  function handleRemove() {
    if (!selected) {
      return;
    }
    const remaining = drafts.filter(draft => draft.id !== selected.id);
    setDrafts(remaining);
    setSelectedId(remaining[0]?.id ?? null);
  }

  async function handleSave() {

    const trimmed = drafts.map(draft => ({ ...draft, name: draft.name.trim() }));

    const problem = seqProcessesProblem(
      trimmed,
      program.processes.map(process => process.name)
    );
    if (problem) {
      setError(problem);
      return;
    }

    setSaving(true);
    setError(null);

    try {
      // Only the names that changed or are new: the others were checked
      // when they were given
      const known = new Set(program.seqProcesses.map(seqProcess => seqProcess.name));
      for (const draft of trimmed) {
        if (!known.has(draft.name) && !(await validateProcessName(draft.name))) {
          setError(`Invalid name "${draft.name}": it follows the rules of a process name.`);
          return;
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to validate the names.");
      return;
    } finally {
      setSaving(false);
    }

    if (setSeqProcesses(trimmed)) {
      onClose();
    }

  }

  const fieldStyle = { display: "flex", flexDirection: "column" as const, gap: 2 };

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
          width: "80%",
          maxWidth: 1100,
          maxHeight: "90vh",
          overflow: "auto",
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >

        <h3 style={{ margin: 0 }}>
          Sequential processes
        </h3>

        <p style={{ margin: 0, color: "#555" }}>
          Code that a process runs as a step with <code>seq_execute</code>.
          Renaming or removing one does not change the calls that name it.
        </p>

        <div style={{ display: "flex", gap: 12, minHeight: 420 }}>

          <div style={{ width: 200, display: "flex", flexDirection: "column", gap: 4 }}>

            <ul
              aria-label="Sequential processes"
              style={{ listStyle: "none", margin: 0, padding: 0, border: "1px solid #ccc", flex: 1, overflow: "auto" }}
            >
              {drafts.map(draft => (
                <li key={draft.id}>
                  <button
                    onClick={() => setSelectedId(draft.id)}
                    style={{
                      width: "100%",
                      textAlign: "left",
                      border: "none",
                      background: draft.id === selectedId ? "#e0ecff" : "transparent",
                      padding: "4px 6px",
                    }}
                  >
                    {draft.name || "(no name)"}
                    {draft.groupSource ? ` [${draft.groupSource.programName}]` : ""}
                  </button>
                </li>
              ))}
            </ul>

            <div style={{ display: "flex", gap: 4 }}>
              <button onClick={handleAdd}>Add</button>
              <button onClick={handleRemove} disabled={!selected}>Remove</button>
            </div>

          </div>

          {selected ? (

            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 6 }}>

              <label style={fieldStyle}>
                Name
                <input
                  value={selected.name}
                  onChange={event => update({ name: event.target.value })}
                />
              </label>

              <label style={fieldStyle}>
                Description
                <input
                  value={selected.description}
                  onChange={event => update({ description: event.target.value })}
                />
              </label>

              <div style={{ display: "flex", gap: 8 }}>
                <label style={fieldStyle}>
                  CPUs
                  <input
                    value={selected.computationalSpecs.cpus?.toString() ?? ""}
                    onChange={event =>
                      update({
                        computationalSpecs: {
                          ...selected.computationalSpecs,
                          cpus: numberOrUndefined(event.target.value),
                        },
                      })
                    }
                    style={{ width: 80 }}
                  />
                </label>
                <label style={fieldStyle}>
                  Memory (MB)
                  <input
                    value={selected.computationalSpecs.mem?.toString() ?? ""}
                    onChange={event =>
                      update({
                        computationalSpecs: {
                          ...selected.computationalSpecs,
                          mem: numberOrUndefined(event.target.value),
                        },
                      })
                    }
                    style={{ width: 100 }}
                  />
                </label>
                <label style={fieldStyle}>
                  Time
                  <input
                    value={selected.computationalSpecs.time ?? ""}
                    placeholder="hh:mm:ss"
                    onChange={event =>
                      update({
                        computationalSpecs: {
                          ...selected.computationalSpecs,
                          time: event.target.value.trim() || undefined,
                        },
                      })
                    }
                    style={{ width: 100 }}
                  />
                </label>
              </div>

              <div style={{ display: "flex", gap: 8 }}>
                <label style={fieldStyle}>
                  Alias
                  <input
                    value={selected.additionalSpecs.alias ?? ""}
                    onChange={event =>
                      update({
                        additionalSpecs: {
                          ...selected.additionalSpecs,
                          alias: event.target.value.trim() || undefined,
                        },
                      })
                    }
                  />
                </label>
                <label style={fieldStyle}>
                  External alias
                  <input
                    value={selected.additionalSpecs.externalAlias ?? ""}
                    onChange={event =>
                      update({
                        additionalSpecs: {
                          ...selected.additionalSpecs,
                          externalAlias: event.target.value.trim() || undefined,
                        },
                      })
                    }
                  />
                </label>
                <label style={{ ...fieldStyle, flex: 1 }}>
                  Option map of the alias
                  <input
                    value={aliasOptMapToText(selected.additionalSpecs.aliasOptMap)}
                    placeholder="-old:-new,..."
                    onChange={event =>
                      update({
                        additionalSpecs: {
                          ...selected.additionalSpecs,
                          aliasOptMap: aliasOptMapFromText(event.target.value),
                        },
                      })
                    }
                  />
                </label>
              </div>

              <label style={fieldStyle}>
                Language
                <select
                  value={selected.language}
                  onChange={event => update({ language: event.target.value as ProcessLanguage })}
                  style={{ width: 140 }}
                >
                  {PROCESS_LANGUAGES.map(({ value, label }) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </label>

              {selected.additionalSpecs.alias || selected.additionalSpecs.externalAlias ? (
                <p style={{ margin: 0, color: "#555" }}>
                  An alias runs the code it names: its own code is not used.
                </p>
              ) : (
                <div style={{ border: "1px solid #ccc" }}>
                  <CodeMirror
                    value={selected.code}
                    height="240px"
                    extensions={[languageExtension(selected.language)]}
                    onChange={value => update({ code: value })}
                  />
                </div>
              )}

            </div>

          ) : (

            <p style={{ flex: 1, color: "#555" }}>
              The program has no sequential processes.
            </p>

          )}

        </div>

        {error && (
          <p role="alert" style={{ margin: 0, color: "#b00020" }}>
            {error}
          </p>
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

          <button onClick={handleSave} disabled={saving}>
            Save
          </button>

        </div>

      </div>

    </div>

  );

}
