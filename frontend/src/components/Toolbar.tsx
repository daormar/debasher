import { useEffect, useState } from "react";
import type { KeyboardEvent } from "react";

import { useProgram } from "../store/ProgramContext";
import EnvVarsEditor from "./EnvVarsEditor";
import PreambleEditor from "./PreambleEditor";
import ProgramDescriptionEditor from "./ProgramDescriptionEditor";
import SaveDialog from "./SaveDialog";
import ProcessNameDialog from "./ProcessNameDialog";
import RunMenu from "./RunMenu";

// Mirrors the shape of an identifier DeBasher can turn into function
// names (<name>_document, <name>_shared_dirs, <name>_program) — no
// server round-trip needed for this, unlike process names, since module
// names aren't checked against a reserved-suffix list by the engine.
const NAME_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

interface Props {
  onClose: () => void;
}

export default function Toolbar({ onClose }: Props) {

  const {
    program,
    setName,
    addProcess,
  } = useProgram();

  const [isPreambleOpen, setPreambleOpen] =
    useState(false);

  const [isDescriptionOpen, setDescriptionOpen] =
    useState(false);

  const [isEnvVarsOpen, setEnvVarsOpen] =
    useState(false);

  const [isSaveOpen, setSaveOpen] =
    useState(false);

  const [isNewProcessOpen, setNewProcessOpen] =
    useState(false);

  const [nameDraft, setNameDraft] =
    useState(program.name);

  // Keep the draft in sync whenever the program's own name changes from
  // outside this input (loading/importing a different program, undo,
  // or this same input's own successful rename committing below).
  useEffect(() => {
    setNameDraft(program.name);
  }, [program.name]);

  function commitNameChange(event: KeyboardEvent<HTMLInputElement>) {

    const trimmed = nameDraft.trim();

    if (trimmed === program.name) {
      event.currentTarget.blur();
      return;
    }

    if (!NAME_RE.test(trimmed)) {
      window.alert(
        "Name must start with a letter or underscore, and contain only letters, digits, and underscores."
      );
      return;
    }

    if (window.confirm(`Rename program to "${trimmed}"?`)) {
      setName(trimmed);
      event.currentTarget.blur();
    }

  }


  return (

    <div
      style={{
        padding: 8,
        borderBottom: "1px solid #ddd",
        background: "#f5f5f5",
        display: "flex",
        gap: 8,
      }}
    >

      <input

        value={nameDraft}

        onChange={(event) =>
          setNameDraft(event.target.value)
        }

        onKeyDown={(event) => {
          if (event.key === "Enter") {
            commitNameChange(event);
          } else if (event.key === "Escape") {
            setNameDraft(program.name);
            event.currentTarget.blur();
          }
        }}

        onBlur={() =>
          setNameDraft(program.name)
        }

        style={{
          alignSelf: "center",
          marginRight: 8,
          width: 220,
          fontSize: 18,
          fontWeight: "bold",
          border: "1px solid transparent",
          background: "transparent",
          padding: "2px 4px",
          // A name longer than the fixed width above is truncated with
          // an ellipsis rather than just cut off — while editing, the
          // browser's own caret handling still scrolls the field to
          // follow the cursor, so the full name stays reachable.
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}

      />

      <button
        onClick={() => setEnvVarsOpen(true)}
      >
        Env vars
      </button>

      <button
        onClick={() => setPreambleOpen(true)}
      >
        Preamble
      </button>

      <button
        onClick={() => setDescriptionOpen(true)}
      >
        Description
      </button>

      <button
        onClick={() => setNewProcessOpen(true)}
      >
        Add process
      </button>

      {isNewProcessOpen && (
        <ProcessNameDialog
          title="Add process"
          confirmLabel="Add"
          existingNames={program.processes.map(process => process.name)}
          preamble={program.preamble}
          envVars={program.envVars}
          onConfirm={addProcess}
          onClose={() => setNewProcessOpen(false)}
        />
      )}

      {isPreambleOpen && (
        <PreambleEditor
          onClose={() => setPreambleOpen(false)}
        />
      )}

      {isDescriptionOpen && (
        <ProgramDescriptionEditor
          onClose={() => setDescriptionOpen(false)}
        />
      )}

      {isEnvVarsOpen && (
        <EnvVarsEditor
          onClose={() => setEnvVarsOpen(false)}
        />
      )}

      <button
        onClick={() => setSaveOpen(true)}
      >
        Save
      </button>

      {isSaveOpen && (
        <SaveDialog
          onClose={() => setSaveOpen(false)}
        />
      )}

      <RunMenu />

      <button
        onClick={onClose}
        style={{ marginLeft: "auto" }}
      >
        Close
      </button>


    </div>

  );

}
