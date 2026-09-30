interface Props {
  // Whether the output directory has a launch record, which then differs
  // from the program; with none, the web UI cannot tell which program
  // produced the program state.
  hasLaunchRecord: boolean;
  onResume: () => void;
  onStartAfresh: () => void;
  onCancel: () => void;
}

// Asked by "Run program" on a resident program whose output directory holds
// program state that the program as it is now may not resume correctly (see
// "The directories of a resident program" in doc/design_doc_webui.md).
export default function LaunchRecordDialog({
  hasLaunchRecord,
  onResume,
  onStartAfresh,
  onCancel,
}: Props) {

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
          maxWidth: 520,
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
          fontSize: 14,
        }}
      >

        <h3 style={{ margin: 0 }}>
          Resume the program state?
        </h3>

        <p style={{ margin: 0 }}>
          {hasLaunchRecord
            ? "The program has changed since the program state in its output " +
              "directory was produced."
            : "The output directory holds program state, but no launch record: " +
              "the web UI cannot tell which program produced it, as when it " +
              "comes from a run launched outside the web UI."}
        </p>

        <p style={{ margin: 0 }}>
          A node resumes from its checkpoint and replays its input log with the
          code that it has now: a changed restore_node_state may not read an old
          node state, a changed process_data replays the input log to another
          result, and a change of the command line options, such as the number
          of tasks of an array, needs a fresh start.
        </p>

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            flexWrap: "wrap",
            gap: 8,
          }}
        >

          <button onClick={onCancel}>
            Cancel
          </button>

          <button onClick={onStartAfresh}>
            Reset the program state and start afresh
          </button>

          <button onClick={onResume}>
            Resume with this program
          </button>

        </div>

      </div>

    </div>

  );

}
