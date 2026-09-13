import { useEffect, useMemo, useState } from "react";

import { getAllEnvVars } from "../storage/programStorage";
import { useProgram } from "../store/ProgramContext";

interface Props {
  onClose: () => void;
}

export default function EnvVarsEditor({ onClose }: Props) {

  const {
    program,
    setEnvVar,
  } = useProgram();

  const [draft, setDraft] =
    useState(program.envVars.DEBASHER_MOD_DIR ?? "");

  const [filter, setFilter] = useState("");

  // Read-only: these aren't the program's own to edit — they're every
  // variable bound while sourcing the program's current preamble (see
  // api/script_generation.py's get_all_envvars). Recomputed live every
  // time this modal opens, rather than cached, so an edit to the
  // preamble (or to the module it loads) shows up immediately.
  const [inheritedVars, setInheritedVars] =
    useState<Record<string, string>>({});

  const [isLoadingInheritedVars, setLoadingInheritedVars] =
    useState(true);

  useEffect(() => {

    let cancelled = false;

    setLoadingInheritedVars(true);

    getAllEnvVars(program)
      .then(envVars => {
        if (!cancelled) {
          setInheritedVars(envVars);
        }
      })
      .catch(() => {
        // A convenience lookup — leave whatever was already shown.
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingInheritedVars(false);
        }
      });

    return () => {
      cancelled = true;
    };

    // Only re-fetch when the modal is (re)opened, not on every keystroke
    // while it's open — program itself only changes once Save is hit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const inheritedEntries = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return Object.entries(inheritedVars)
      .filter(([name]) => !needle || name.toLowerCase().includes(needle))
      .sort(([a], [b]) => a.localeCompare(b));
  }, [inheritedVars, filter]);

  const hasInheritedVars = Object.keys(inheritedVars).length > 0;

  function handleSave() {
    setEnvVar("DEBASHER_MOD_DIR", draft);
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
          maxWidth: 720,
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >

        <h3 style={{ margin: 0 }}>
          Environment variables
        </h3>

        <h4 style={{ margin: 0 }}>
          Session variables
        </h4>

        <label style={{ fontSize: 14 }}>
          DEBASHER_MOD_DIR
        </label>

        <textarea

          value={draft}

          onChange={(event) =>
            setDraft(event.target.value)
          }

          rows={8}

          spellCheck={false}

          placeholder="/path/to/modules"

          style={{
            width: "100%",
            fontFamily: "ui-monospace, Consolas, monospace",
            resize: "vertical",
          }}

        />

        {isLoadingInheritedVars && (
          <div style={{ fontSize: 14, color: "#555" }}>
            Loading module-defined variables...
          </div>
        )}

        {!isLoadingInheritedVars && (

          <>

            <h4 style={{ margin: 0 }}>
              Module-defined (inherited) variables
            </h4>

            {hasInheritedVars && (
              <input

                type="text"

                value={filter}

                onChange={(event) => setFilter(event.target.value)}

                placeholder="Filter by name..."

                style={{ width: "100%", boxSizing: "border-box" }}

              />
            )}

            <textarea

              value={
                hasInheritedVars
                  ? inheritedEntries
                      .map(([varName, value]) => `${varName}=${value}`)
                      .join("\n")
                  : ""
              }

              readOnly

              rows={8}

              spellCheck={false}

              placeholder="(none)"

              style={{
                width: "100%",
                fontFamily: "ui-monospace, Consolas, monospace",
                resize: "vertical",
                background: "#f0f0f0",
                color: "#555",
              }}

            />

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

          <button onClick={handleSave}>
            Save
          </button>

        </div>

      </div>

    </div>

  );

}
