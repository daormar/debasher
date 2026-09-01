import { useMemo, useState } from "react";

import { getCommandLineOptions } from "../models/option";
import type { ProgramOption } from "../models/option";
import { useProgram } from "../store/ProgramContext";

interface Props {
  onClose: () => void;
}

export default function ProgramOptionsEditor({ onClose }: Props) {

  const {
    program,
    setProgramOptions,
  } = useProgram();

  const options = useMemo(
    () => getCommandLineOptions(program.processes),
    [program.processes]
  );

  const mandatoryOptions = useMemo(
    () => options.filter(option => option.mandatory),
    [options]
  );

  const optionalOptions = useMemo(
    () => options.filter(option => !option.mandatory),
    [options]
  );

  const [draft, setDraft] =
    useState<Record<string, string>>(() => {

      const initial: Record<string, string> = {};

      for (const option of options) {
        initial[option.label] =
          program.programOptions[option.label] ?? option.value;
      }

      return initial;

    });

  function handleSave() {
    setProgramOptions(draft);
    onClose();
  }

  function renderOption(option: ProgramOption) {

    return (

      <div key={option.label}>

        <label style={{ fontSize: 14 }}>
          {option.label}
        </label>

        {option.dataType === "None" ? (

          <input

            type="checkbox"

            checked={Boolean(draft[option.label])}

            onChange={(event) =>
              setDraft(current => ({
                ...current,
                [option.label]: event.target.checked ? "true" : "",
              }))
            }

          />

        ) : (

          <input

            type={option.dataType === "string" ? "text" : "number"}

            step={option.dataType === "float" ? "any" : undefined}

            value={draft[option.label] ?? ""}

            onChange={(event) =>
              setDraft(current => ({
                ...current,
                [option.label]: event.target.value,
              }))
            }

            style={{
              width: "100%",
            }}

          />

        )}

        {option.description && (
          <div style={{ fontSize: 12, color: "#888" }}>
            {option.description}
          </div>
        )}

      </div>

    );

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
          Program options
        </h3>

        {options.length === 0 ? (

          <p style={{ fontSize: 14, color: "#666" }}>
            No command line options declared. Mark an option as
            "Command line" on a process to have it appear here.
          </p>

        ) : (

          <>

            {mandatoryOptions.length > 0 && (

              <>

                <h4 style={{ margin: "8px 0 0" }}>
                  Mandatory
                </h4>

                {mandatoryOptions.map(renderOption)}

              </>

            )}

            {optionalOptions.length > 0 && (

              <>

                <h4 style={{ margin: "8px 0 0" }}>
                  Optional
                </h4>

                {optionalOptions.map(renderOption)}

              </>

            )}

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
