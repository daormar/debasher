import { useCallback, useEffect, useRef, useState } from "react";

import { inspectNode } from "../api/executionApi";
import {
  formatBytes,
  formatTime,
  inputPortsOf,
  summaryRows,
  type InputLogRecord,
  type InputLogView,
  type NodeCheckpoint,
  type NodeSummary,
  type PortCount,
} from "../models/nodeState";
import type { ProgramProcess } from "../models/process";
import { useProgram } from "../store/ProgramContext";

type View = "summary" | "checkpoints" | "log";

const VIEW_LABELS: Record<View, string> = {
  summary: "Summary",
  checkpoints: "Checkpoints",
  log: "Input log",
};

interface Props {
  process: ProgramProcess;
  taskIndex?: number;
  onClose: () => void;
}

const preStyle: React.CSSProperties = {
  margin: 0,
  padding: 8,
  background: "#f5f5f5",
  border: "1px solid #ddd",
  borderRadius: 4,
  fontFamily: "ui-monospace, Consolas, monospace",
  fontSize: 13,
  whiteSpace: "pre",
  overflow: "auto",
};

const cellStyle: React.CSSProperties = {
  padding: "2px 8px",
  borderBottom: "1px solid #eee",
  textAlign: "left",
  verticalAlign: "top",
};

function SummaryView({ summary }: { summary: NodeSummary }) {
  return (
    <table style={{ borderCollapse: "collapse", fontSize: 14 }}>
      <tbody>
        {summaryRows(summary).map(row => (
          <tr key={row.label} data-warning={row.warning ? "true" : undefined}>
            <th style={{ ...cellStyle, whiteSpace: "nowrap" }}>{row.label}</th>
            <td style={{ ...cellStyle, color: row.warning ? "#c0392b" : undefined }}>{row.value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function PortCounts({ title, counts }: { title: string; counts: Record<string, PortCount> | undefined }) {
  const entries = Object.entries(counts ?? {});
  return (
    <div>
      <strong>{title}:</strong>{" "}
      {entries.length === 0
        ? "none"
        : entries
            .map(([port, c]) => `${port}: ${c.messages} message${c.messages === 1 ? "" : "s"}, ${formatBytes(c.bytes)}`)
            .join("; ")}
    </div>
  );
}

function CheckpointView({ checkpoint }: { checkpoint: NodeCheckpoint }) {
  if (!checkpoint.readable) {
    return (
      <div style={{ fontSize: 14 }}>
        Written {formatTime(checkpoint.written_at)} with schema version {String(checkpoint.schema_version)},
        which is not that of the runtime library: nothing else of it is read. Path: {checkpoint.path}
      </div>
    );
  }
  const seqs = (seq: Record<string, number> | undefined) =>
    Object.entries(seq ?? {}).map(([port, n]) => `${port}: ${n}`).join(", ") || "none";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 14, minHeight: 0 }}>
      <div>Written {formatTime(checkpoint.written_at)}, capture_pos {checkpoint.capture_pos}</div>
      <div>Path: {checkpoint.path}</div>
      <div><strong>Closed ports:</strong> {checkpoint.closed_ports?.join(", ") || "none"}</div>
      <div><strong>Sequence numbers sent (out_seq):</strong> {seqs(checkpoint.out_seq)}</div>
      <div><strong>Sequence numbers received (last_seq):</strong> {seqs(checkpoint.last_seq)}</div>
      <PortCounts title="In transit (channel_state)" counts={checkpoint.channel_state} />
      <PortCounts title="Outbound backlog (out_backlog)" counts={checkpoint.out_backlog} />
      <strong>Node state:</strong>
      <pre style={{ ...preStyle, maxHeight: "35vh" }}>
        {JSON.stringify(checkpoint.node_state, null, 2)}
      </pre>
    </div>
  );
}

function LogRow({ record, capturePos }: { record: InputLogRecord; capturePos: number | null }) {
  if ("error" in record) {
    return (
      <tr style={{ color: "#c0392b" }}>
        <td style={cellStyle} colSpan={5}>
          {record.segment}, line {record.line}: {record.error}
        </td>
      </tr>
    );
  }
  const toReplay = capturePos === null || record.pos > capturePos;
  return (
    <tr style={{ background: toReplay ? "#fff8e1" : undefined }}>
      <td style={cellStyle}>{record.pos}</td>
      <td style={cellStyle}>{record.port}</td>
      <td style={cellStyle}>{record.type}</td>
      <td style={cellStyle}>{record.seq ?? ""}</td>
      <td style={{ ...cellStyle, fontFamily: "ui-monospace, Consolas, monospace", wordBreak: "break-all" }}>
        {JSON.stringify(record.payload)}
      </td>
    </tr>
  );
}

function LogView({ log }: { log: InputLogView }) {
  if (log.records.length === 0) {
    return <div style={{ fontSize: 14 }}>No records.</div>;
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, minHeight: 0 }}>
      <div style={{ fontSize: 13, color: "#666" }}>
        The latest {log.records.length.toLocaleString()} records. Those above the latest checkpoint
        (capture_pos {log.capture_pos ?? "none"}), highlighted, are what a relaunch now would replay.
      </div>
      <div style={{ overflow: "auto", maxHeight: "50vh" }}>
        <table style={{ borderCollapse: "collapse", fontSize: 13, width: "100%" }}>
          <thead>
            <tr>
              {["Position", "Port", "Type", "Seq", "Payload"].map(h => (
                <th key={h} style={cellStyle}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {log.records.map((record, i) => (
              <LogRow key={i} record={record} capturePos={log.capture_pos} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// "Show node state": what a node of a resident program keeps in its execdir,
// read only, in three views (see "Observing and talking to a live program"
// in doc/design_doc_webui.md). Each view is read when it is shown and again
// with Refresh, never polled.
export default function NodeStateModal({ process, taskIndex, onClose }: Props) {

  // The program as it was when the modal opened: a change of the store
  // must not read the node again, only a change of view or Refresh.
  const { program: currentProgram } = useProgram();
  const [program] = useState(currentProgram);

  const [view, setView] = useState<View>("summary");
  const [summary, setSummary] = useState<NodeSummary | null>(null);
  const [epoch, setEpoch] = useState<number | null>(null);
  const [checkpoint, setCheckpoint] = useState<NodeCheckpoint | null>(null);
  const [port, setPort] = useState("");
  const [log, setLog] = useState<InputLogView | null>(null);
  const [portsSeen, setPortsSeen] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setLoading] = useState(false);

  // Only the answer of the latest read is shown: switching views while a
  // read is on its way must not let its answer overwrite a newer one.
  const latestRead = useRef(0);

  const load = useCallback(async () => {

    const read = ++latestRead.current;
    const isLatest = () => read === latestRead.current;

    setLoading(true);
    setError(null);

    try {
      if (view === "summary" || view === "checkpoints") {
        // The checkpoints view reads the summary too, for the epochs that
        // the node retains now, and shows the latest one unless the one
        // chosen is still retained.
        const answer = await inspectNode<NodeSummary>(program, process.name, taskIndex, { command: "summary" });
        if (!isLatest()) {
          return;
        }
        setSummary(answer.result);
        setError(answer.error);
        if (view === "checkpoints" && answer.result) {
          const retained = answer.result.checkpoints.map(c => c.epoch);
          const chosen = epoch !== null && retained.includes(epoch) ? epoch : (retained.at(-1) ?? null);
          if (chosen === null) {
            setCheckpoint(null);
          } else if (chosen !== epoch) {
            // Choosing it reads it, through the effect below.
            setEpoch(chosen);
          } else {
            const shown = await inspectNode<NodeCheckpoint>(
              program, process.name, taskIndex, { command: "checkpoint", epoch: chosen }
            );
            if (isLatest()) {
              setCheckpoint(shown.result);
              setError(shown.error);
            }
          }
        }
      } else {
        const answer = await inspectNode<InputLogView>(
          program, process.name, taskIndex, { command: "log", port: port || undefined }
        );
        if (!isLatest()) {
          return;
        }
        setLog(answer.result);
        setError(answer.error);
        const seen = new Set((answer.result?.records ?? []).flatMap(r => ("port" in r ? [r.port] : [])));
        setPortsSeen(current => [...new Set([...current, ...seen])]);
      }
    } catch (err) {
      if (isLatest()) {
        setError(err instanceof Error ? err.message : "Failed to inspect the node.");
      }
    } finally {
      if (isLatest()) {
        setLoading(false);
      }
    }

  }, [program, process.name, taskIndex, view, epoch, port]);

  useEffect(() => {
    void load();
  }, [load]);

  const ports = [...new Set([...inputPortsOf(process, program.edges), ...portsSeen])].sort();
  const taskSuffix = taskIndex !== undefined ? ` [task ${taskIndex}]` : "";

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
        aria-label="Node state"
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
          {process.name}{taskSuffix}: node state
        </h3>

        <div style={{ display: "flex", gap: 4, borderBottom: "1px solid #ddd" }}>
          {(Object.keys(VIEW_LABELS) as View[]).map(v => (
            <button
              key={v}
              onClick={() => setView(v)}
              aria-pressed={view === v}
              style={{
                border: "none",
                borderBottom: view === v ? "2px solid #1976d2" : "2px solid transparent",
                background: "none",
                padding: "4px 12px",
                fontWeight: view === v ? 600 : undefined,
                cursor: "pointer",
              }}
            >
              {VIEW_LABELS[v]}
            </button>
          ))}
        </div>

        {view === "checkpoints" && summary && summary.checkpoints.length > 0 && (
          <label style={{ fontSize: 14 }}>
            Checkpoint{" "}
            <select value={epoch ?? ""} onChange={e => setEpoch(Number(e.target.value))}>
              {summary.checkpoints.map(c => (
                <option key={c.epoch} value={c.epoch}>
                  epoch {c.epoch}, {formatTime(c.written_at)}
                </option>
              ))}
            </select>
          </label>
        )}

        {view === "log" && (
          <label style={{ fontSize: 14 }}>
            Port{" "}
            <select value={port} onChange={e => setPort(e.target.value)}>
              <option value="">every port</option>
              {ports.map(p => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </label>
        )}

        <div style={{ overflow: "auto", minHeight: 0 }}>
          {error ? (
            <pre style={{ ...preStyle, color: "#c0392b", whiteSpace: "pre-wrap" }}>{error}</pre>
          ) : isLoading ? (
            <div style={{ fontSize: 14, color: "#666" }}>Reading…</div>
          ) : view === "summary" && summary ? (
            <SummaryView summary={summary} />
          ) : view === "checkpoints" ? (
            summary && summary.checkpoints.length === 0
              ? <div style={{ fontSize: 14 }}>The node retains no checkpoint yet.</div>
              : checkpoint && <CheckpointView checkpoint={checkpoint} />
          ) : view === "log" && log ? (
            <LogView log={log} />
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

    </div>

  );

}
