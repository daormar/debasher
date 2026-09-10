import { useState } from "react";

import { useProgram } from "../store/ProgramContext";
import type { AliasOptMapping, ProgramProcess } from "../models/process";

interface Props {
  process: ProgramProcess;
  onClose: () => void;
}

export default function AdditionalSpecsEditor({ process, onClose }: Props) {

  const { setAdditionalSpecs } = useProgram();

  const [force, setForce] =
    useState(process.additionalSpecs.force);

  const [processdeps, setProcessdeps] =
    useState(process.additionalSpecs.processdeps ?? "");

  const [alias, setAlias] =
    useState(process.additionalSpecs.alias ?? "");

  const [aliasOptMap, setAliasOptMap] =
    useState<AliasOptMapping[]>(process.additionalSpecs.aliasOptMap ?? []);

  const [externalAlias, setExternalAlias] =
    useState(process.additionalSpecs.externalAlias ?? "");

  // Candidates for the "from" side of a mapping: this process's own
  // command-line options — the only ones that can actually appear in
  // its own optlist for the engine to rename (see
  // debasher::_rename_opt_args in engine/debasher_lib_programs.sh).
  const commandLineOptionLabels =
    process.options.filter(option => option.commandLine).map(option => option.label);

  function handleAliasChange(value: string) {
    setAlias(value);
    if (!value.trim() && !externalAlias.trim()) {
      // alias_opt_map is invalid without alias or externalAlias (see
      // debasher::add_debasher_process) — clear it once neither is set
      // any more, same as OptionEditor clears channel when
      // fromProcessSpec is set.
      setAliasOptMap([]);
    }
  }

  function handleExternalAliasChange(value: string) {
    setExternalAlias(value);
    if (!value.trim() && !alias.trim()) {
      setAliasOptMap([]);
    }
  }

  function addMappingRow() {
    setAliasOptMap(current => [
      ...current,
      { fromLabel: commandLineOptionLabels[0] ?? "", toLabel: "" },
    ]);
  }

  function updateMappingRow(index: number, field: keyof AliasOptMapping, value: string) {
    setAliasOptMap(current =>
      current.map((mapping, i) => (i === index ? { ...mapping, [field]: value } : mapping))
    );
  }

  function removeMappingRow(index: number) {
    setAliasOptMap(current => current.filter((_, i) => i !== index));
  }

  function handleSave() {

    const trimmedAlias = alias.trim();
    const trimmedExternalAlias = externalAlias.trim();

    const validAliasOptMap = (trimmedAlias || trimmedExternalAlias)
      ? aliasOptMap.filter(mapping => mapping.fromLabel.trim() && mapping.toLabel.trim())
      : [];

    setAdditionalSpecs(process.id, {
      force,
      processdeps: processdeps.trim() ? processdeps : undefined,
      alias: trimmedAlias ? trimmedAlias : undefined,
      aliasOptMap: validAliasOptMap.length > 0 ? validAliasOptMap : undefined,
      externalAlias: trimmedExternalAlias ? trimmedExternalAlias : undefined,
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
          width: 520,
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

            checked={force}

            onChange={(event) =>
              setForce(event.target.checked)
            }

          />
          {" "}force

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
            handleAliasChange(event.target.value)
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
            handleExternalAliasChange(event.target.value)
          }

          style={{
            width: "100%",
          }}

        />

        {(alias.trim() || externalAlias.trim()) && (

          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 6,
              borderLeft: "1px solid #ddd",
              paddingLeft: 8,
            }}
          >

            <label>
              Option rename map
            </label>

            {commandLineOptionLabels.length === 0 && aliasOptMap.length === 0 ? (

              <div style={{ fontSize: 12, color: "#888" }}>
                No command-line options on this process to rename yet.
              </div>

            ) : (

              aliasOptMap.map((mapping, index) => (

                <div
                  key={index}
                  style={{
                    display: "flex",
                    gap: 6,
                    alignItems: "center",
                  }}
                >

                  <select

                    value={mapping.fromLabel}

                    onChange={(event) =>
                      updateMappingRow(index, "fromLabel", event.target.value)
                    }

                    style={{
                      flex: 1,
                      minWidth: 0,
                    }}

                  >

                    <option value="">
                      (select option)
                    </option>

                    {commandLineOptionLabels.map(label => (
                      <option key={label} value={label}>
                        {label}
                      </option>
                    ))}

                  </select>

                  <span>→</span>

                  <input

                    value={mapping.toLabel}

                    onChange={(event) =>
                      updateMappingRow(index, "toLabel", event.target.value)
                    }

                    placeholder="aliased process's option"

                    style={{
                      flex: 1,
                      minWidth: 0,
                    }}

                  />

                  <button type="button" onClick={() => removeMappingRow(index)}>
                    ✕
                  </button>

                </div>

              ))

            )}

            <button
              type="button"
              onClick={addMappingRow}
              disabled={commandLineOptionLabels.length === 0}
              style={{
                alignSelf: "flex-start",
              }}
            >
              + Add mapping
            </button>

          </div>

        )}

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
