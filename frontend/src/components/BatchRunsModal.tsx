import { useCallback, useEffect, useRef, useState } from "react";

import { getBatchRunStatus, inspectNode, inspectPath, pathInspectionText } from "../api/executionApi";
import {
  batchRunStateText,
  type BatchRun,
  type BatchRuns,
  type NodeSummary,
} from "../models/nodeState";
import type { ProgramProcess } from "../models/process";
import { useProgram } from "../store/ProgramContext";
import CommandOutputModal from "./CommandOutputModal";

interface Props {
  process: ProgramProcess;
  onClose: () => void;
}

const cellStyle: React.CSSProperties = {
  padding: "2px 8px",
  borderBottom: "1px solid #eee",
  textAlign: "left",
  verticalAlign: "top",
};

// The file into which a launcher node writes what the shell of a batch run
// prints, in its run directory.
const LAUNCHER_LOG = "launcher.log";

// "Show batch runs": the batch runs that a launcher node has registered, one
// row each, with what the user can read of each (see "Observing and talking
// to a live program" in doc/design_doc_webui.md). Read when it opens and on
// Refresh, never polled, as "Show node state".
export default function BatchRunsModal({ process, onClose }: Props) {

  // The program as it was when the modal opened, as in NodeStateModal.
  const { program: currentProgram } = useProgram();
  const [program] = useState(currentProgram);

  const [runs, setRuns] = useState<BatchRuns | null>(null);
  // Whether the batch runs are whole general programs, which debasher_status
  // can speak of, or a single process of one (PROCESS).
  const [wholeProgram, setWholeProgram] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setLoading] = useState(false);
  const [shown, setShown] = useState<{ title: string; output: string } | null>(null);
  const [isShowPending, setShowPending] = useState(false);

  const latestRead = useRef(0);

  const load = useCallback(async () => {

    const read = ++latestRead.current;

    setLoading(true);
    setError(null);

    try {
      const [runsAnswer, summaryAnswer] = await Promise.all([
        inspectNode<BatchRuns>(program, process.name, undefined, { command: "runs" }),
        inspectNode<NodeSummary>(program, process.name, undefined, { command: "summary" }),
      ]);
      if (read !== latestRead.current) {
        return;
      }
      setRuns(runsAnswer.result);
      setError(runsAnswer.error);
      setWholeProgram((summaryAnswer.result?.node_info?.launcher?.process ?? null) === null);
    } catch (err) {
      if (read === latestRead.current) {
        setError(err instanceof Error ? err.message : "Failed to read the batch runs.");
      }
    } finally {
      if (read === latestRead.current) {
        setLoading(false);
      }
    }

  }, [program, process.name]);

  useEffect(() => {
    void load();
  }, [load]);

  async function show(run: BatchRun, what: "log" | "status" | "dir") {

    setShowPending(true);

    try {
      if (what === "status") {
        setShown({ title: `${run.run}: debasher_status`, output: await getBatchRunStatus(program, run.run_dir) });
      } else {
        const path = what === "log" ? `${run.run_dir}/${LAUNCHER_LOG}` : run.run_dir;
        setShown({ title: `${run.run}: ${path}`, output: pathInspectionText(path, await inspectPath(path)) });
      }
    } catch (err) {
      setShown({ title: run.run, output: err instanceof Error ? err.message : "Failed to read the batch run." });
    } finally {
      setShowPending(false);
    }

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
        role="dialog"
        aria-label="Batch runs"
        style={{
          width: "70%",
          maxWidth: 900,
          maxHeight: "85vh",
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >

        <h3 style={{ margin: 0 }}>
          {process.name}: batch runs
        </h3>

        {runs && (
          <div style={{ fontSize: 13, color: "#666", overflowWrap: "anywhere" }}>
            Runs root: {runs.runs_root}
          </div>
        )}

        <div style={{ overflow: "auto", minHeight: 0 }}>
          {error ? (
            <pre style={{ margin: 0, color: "#c0392b", whiteSpace: "pre-wrap" }}>{error}</pre>
          ) : isLoading && !runs ? (
            <div style={{ fontSize: 14, color: "#666" }}>Reading…</div>
          ) : runs && runs.runs.length === 0 ? (
            <div style={{ fontSize: 14 }}>The node has registered no batch run yet.</div>
          ) : runs ? (
            <table style={{ borderCollapse: "collapse", fontSize: 13, width: "100%" }}>
              <thead>
                <tr>
                  {["Position", "Name", "State", "Run directory", ""].map(h => (
                    <th key={h} style={cellStyle}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {runs.runs.map(run => (
                  <tr key={run.pos} data-state={run.state}>
                    <td style={cellStyle}>{run.pos}</td>
                    <td style={cellStyle}>{run.run}</td>
                    <td style={{ ...cellStyle, color: run.state === "failed" ? "#c0392b" : undefined }}>
                      {batchRunStateText(run)}
                    </td>
                    <td style={{ ...cellStyle, overflowWrap: "anywhere" }}>{run.run_dir}</td>
                    <td style={{ ...cellStyle, whiteSpace: "nowrap" }}>
                      <button onClick={() => void show(run, "log")} disabled={isShowPending}>
                        Log
                      </button>{" "}
                      {wholeProgram && (
                        <>
                          <button onClick={() => void show(run, "status")} disabled={isShowPending}>
                            Status
                          </button>{" "}
                        </>
                      )}
                      <button onClick={() => void show(run, "dir")} disabled={isShowPending}>
                        Open
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button onClick={() => void load()} disabled={isLoading}>
            Refresh
          </button>
          <button onClick={onClose}>
            Close
          </button>
        </div>

      </div>

      {shown && (
        <CommandOutputModal
          title={shown.title}
          output={shown.output}
          onClose={() => setShown(null)}
        />
      )}

    </div>

  );

}
