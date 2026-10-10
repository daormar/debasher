interface Props {
  // The text of the field, one directory per line (see models/modDir).
  value: string;
  onChange: (value: string) => void;
  optional?: boolean;
}

// The DEBASHER_MOD_DIR field of the "Env vars" and "Import program" dialogs,
// with the help text that says how to fill it in.
export default function ModDirField({ value, onChange, optional = false }: Props) {

  return (

    <>

      <label style={{ fontSize: 14 }}>
        DEBASHER_MOD_DIR{optional ? " (optional)" : ""}
      </label>

      <p style={{ margin: 0, fontSize: 13, color: "#555" }}>
        Directories where the engine looks for the modules that the program
        loads (with load_debasher_module), one per line, searched in this
        order. Blank lines are ignored. They are saved as a single
        colon-separated list, so a directory name cannot contain a colon.
      </p>

      <textarea

        value={value}

        onChange={(event) =>
          onChange(event.target.value)
        }

        rows={8}

        spellCheck={false}

        placeholder={"/path/to/modules\n/path/to/other/modules"}

        style={{
          width: "100%",
          fontFamily: "ui-monospace, Consolas, monospace",
          resize: "vertical",
        }}

      />

    </>

  );

}
