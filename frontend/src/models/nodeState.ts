import type { ProgramProcess } from "./process";
import type { ProgramEdge } from "./edge";

// What debasher_inspect_resident prints of a node of a resident program, for
// "Show node state" (see "`debasher_inspect_resident`: what a node keeps" in
// doc/design_doc_resident.md).

export interface NodeInfo {
  runtime_class: string;
  started_at: number;
  heartbeat_interval_secs: number;
  limits: {
    input_log_max_bytes: number;
    out_backlog_max_bytes: number;
    out_backlog_fail_bytes: number;
  };
  updated_at: number;
  healthy: boolean;
  out_backlog_bytes: Record<string, number>;
  checkpoints_skipped_since: number | null;
  age_secs: number;
  stale: boolean;
}

export interface NodeSummary {
  task_state: "alive" | "finished" | "down" | "not_launched";
  checkpoints: { epoch: number; written_at: number | null }[];
  capture_pos: number | null;
  halted_epoch: number | null;
  input_log: {
    bytes: number;
    max_bytes: number | null;
    segments: number;
    first_pos: number | null;
    last_pos: number | null;
    to_replay: number;
    error?: string;
  };
  node_info: NodeInfo | null;
}

export interface PortCount {
  messages: number;
  bytes: number;
}

export interface NodeCheckpoint {
  epoch: number;
  path: string;
  written_at: number | null;
  schema_version: number | null;
  readable: boolean;
  capture_pos?: number;
  closed_ports?: string[];
  out_seq?: Record<string, number>;
  last_seq?: Record<string, number>;
  node_state?: unknown;
  channel_state?: Record<string, PortCount>;
  out_backlog?: Record<string, PortCount>;
}

// A record of the input log, or a line that ends in a newline and does not
// parse, shown in its place.
export type InputLogRecord =
  | { pos: number; port: string; type: string; seq: number | null; payload: unknown }
  | { segment: string; line: number; error: string };

export interface InputLogView {
  capture_pos: number | null;
  records: InputLogRecord[];
}

export type InspectNodeCommand =
  | { command: "summary" }
  | { command: "checkpoint"; epoch: number }
  | { command: "log"; port?: string };

// One line of the summary: `warning` marks what crosses a limit of the
// engine itself, never a threshold of the web UI.
export interface SummaryRow {
  label: string;
  value: string;
  warning?: boolean;
}

export function formatBytes(bytes: number): string {
  const units = ["B", "KiB", "MiB", "GiB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return unit === 0 ? `${bytes} B` : `${value.toFixed(1)} ${units[unit]}`;
}

export function formatTime(epochSecs: number | null): string {
  return epochSecs === null ? "unknown" : new Date(epochSecs * 1000).toLocaleString();
}

const TASK_STATE_TEXT: Record<NodeSummary["task_state"], string> = {
  alive: "alive",
  finished: "finished",
  down: "down",
  not_launched: "not launched",
};

function outboundBacklogRows(info: NodeInfo): SummaryRow[] {
  const { out_backlog_max_bytes: max, out_backlog_fail_bytes: fail } = info.limits;
  const ports = Object.entries(info.out_backlog_bytes);
  const total = ports.reduce((sum, [, bytes]) => sum + bytes, 0);
  const perPort = ports.map(([port, bytes]) => `${port}: ${formatBytes(bytes)}`).join(", ");
  return [
    {
      label: "Outbound backlog",
      value:
        `${formatBytes(total)}${perPort ? ` (${perPort})` : ""}; checkpoints are skipped above ` +
        `${formatBytes(max)}, the node fails above ${formatBytes(fail)}`,
      warning: total > max,
    },
  ];
}

// The node info file is that of the latest incarnation. It is stale by
// nature in a node that is not alive, and warns only in one that is: one
// still replaying its input log, or whose heartbeat thread has died.
function nodeInfoRows(info: NodeInfo | null, alive: boolean): SummaryRow[] {
  if (info === null) {
    return [{ label: "Node info", value: "never written: the node has not started its threads yet" }];
  }
  const rows: SummaryRow[] = [
    { label: "Incarnation started", value: formatTime(info.started_at) },
    {
      label: "Latest heartbeat tick",
      value: info.stale && alive
        ? `${formatTime(info.updated_at)}, ${Math.round(info.age_secs)} s ago: older than two ` +
          "heartbeat intervals, so the node is still replaying its input log, or its heartbeat " +
          "thread has died"
        : `${formatTime(info.updated_at)}, ${Math.round(info.age_secs)} s ago`,
      warning: info.stale && alive,
    },
    {
      label: "Threads",
      value: info.healthy
        ? "every thread alive at the latest tick"
        : "a thread was dead at the latest tick: the node does nothing, although its process lives",
      warning: !info.healthy,
    },
    ...outboundBacklogRows(info),
  ];
  if (info.checkpoints_skipped_since !== null) {
    rows.push({
      label: "Checkpoints skipped",
      value: `none written since epoch ${info.checkpoints_skipped_since}, because of the size of the outbound backlog`,
      warning: true,
    });
  }
  return rows;
}

function inputLogRow(summary: NodeSummary): SummaryRow {
  const log = summary.input_log;
  const cap = log.max_bytes === null
    ? ""
    : ` of ${formatBytes(log.max_bytes)} (${Math.floor((100 * log.bytes) / log.max_bytes)}%)`;
  const positions = log.first_pos === null ? "no records" : `records ${log.first_pos} to ${log.last_pos}`;
  return {
    label: "Input log",
    value: log.error
      ? `${formatBytes(log.bytes)}${cap}; ${log.error}`
      : `${formatBytes(log.bytes)}${cap}, ${log.segments} segment${log.segments === 1 ? "" : "s"}, ${positions}`,
    warning: Boolean(log.error) || (log.max_bytes !== null && log.bytes >= log.max_bytes),
  };
}

// The summary of a node, in the order in which "Show node state" lists it.
export function summaryRows(summary: NodeSummary): SummaryRow[] {
  const latest = summary.checkpoints.at(-1);
  return [
    { label: "Task", value: TASK_STATE_TEXT[summary.task_state], warning: summary.task_state === "down" },
    ...nodeInfoRows(summary.node_info, summary.task_state === "alive"),
    {
      label: "Latest checkpoint",
      value: latest
        ? `epoch ${latest.epoch}, written ${formatTime(latest.written_at)} (${summary.checkpoints.length} retained)`
        : "none yet",
    },
    {
      label: "Halted",
      value: summary.halted_epoch === null ? "no" : `at epoch ${summary.halted_epoch}`,
    },
    inputLogRow(summary),
    {
      label: "To replay",
      value: `${summary.input_log.to_replay} record${summary.input_log.to_replay === 1 ? "" : "s"} ` +
        "above the latest checkpoint, which a relaunch now would replay",
    },
  ];
}

// The input ports of a node that the model knows, the names by which its
// input log records them: its external inputs and its connected inputs,
// named without their leading dash. The control port of an initiator is not
// in the model (see "The canvas of a resident program"), and shows among
// the ports of the records read.
export function inputPortsOf(process: ProgramProcess, edges: ProgramEdge[]): string[] {
  return process.options
    .filter(option =>
      option.direction === "input" &&
      (option.fifoTag === "external" || edges.some(edge => edge.targetOptionId === option.id))
    )
    .map(option => option.label.replace(/^-/, ""));
}

// "Show node state" is offered on every node of a resident program but the
// Supervisor, which keeps no node state, and enabled once the node has been
// launched, whatever the run phase, since a stopped node keeps what it held.
export function offersShowNodeState(process: ProgramProcess): boolean {
  return process.nodeKind !== "Supervisor";
}

export function wasLaunched(status: string | undefined): boolean {
  return status !== undefined && status !== "TO-DO";
}
