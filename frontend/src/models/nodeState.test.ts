import { describe, expect, it } from "vitest";
import type { ProgramOption } from "./option";
import type { ProgramProcess } from "./process";
import {
  formatBytes,
  inputPortsOf,
  offersShowNodeState,
  summaryRows,
  wasLaunched,
  type NodeInfo,
  type NodeSummary,
} from "./nodeState";

function option(label: string, fields: Partial<ProgramOption> = {}): ProgramOption {
  return {
    id: label,
    label,
    direction: label.startsWith("-out") ? "output" : "input",
    dataType: "string",
    channel: "none",
    mirror: false,
    description: "",
    value: "",
    commandLine: false,
    mandatory: false,
    fromProcessSpec: false,
    ...fields,
  };
}

function process(options: ProgramOption[], fields: Partial<ProgramProcess> = {}): ProgramProcess {
  return { name: "Accumulate", nodeKind: "FBPProcess", options, ...fields } as ProgramProcess;
}

const MiB = 1024 * 1024;

function nodeInfo(fields: Partial<NodeInfo> = {}): NodeInfo {
  return {
    runtime_class: "FBPProcess",
    started_at: 1790000000,
    heartbeat_interval_secs: 5,
    limits: { input_log_max_bytes: 100 * MiB, out_backlog_max_bytes: 8 * MiB, out_backlog_fail_bytes: 64 * MiB },
    updated_at: 1790000100,
    healthy: true,
    out_backlog_bytes: {},
    checkpoints_skipped_since: null,
    age_secs: 2,
    stale: false,
    ...fields,
  };
}

function summary(fields: Partial<NodeSummary> = {}): NodeSummary {
  return {
    task_state: "alive",
    checkpoints: [{ epoch: 7, written_at: 1790000050 }],
    capture_pos: 4,
    halted_epoch: null,
    input_log: { bytes: 342, max_bytes: 100 * MiB, segments: 1, first_pos: 1, last_pos: 6, to_replay: 2 },
    node_info: nodeInfo(),
    ...fields,
  };
}

function warnings(s: NodeSummary): string[] {
  return summaryRows(s).filter(row => row.warning).map(row => row.label);
}

describe("summaryRows", () => {
  it("warns of nothing in a healthy node", () => {
    expect(warnings(summary())).toEqual([]);
  });

  it("warns of a node that is down and of a dead thread", () => {
    expect(warnings(summary({ task_state: "down", node_info: nodeInfo({ healthy: false }) })))
      .toEqual(["Task", "Threads"]);
  });

  it("warns of a stale node info file only in a node that is alive", () => {
    const stale = nodeInfo({ stale: true });
    expect(warnings(summary({ node_info: stale }))).toEqual(["Latest heartbeat tick"]);
    expect(warnings(summary({ task_state: "finished", node_info: stale }))).toEqual([]);
  });

  it("warns once the outbound backlog is over the limit above which checkpoints are skipped", () => {
    const over = nodeInfo({ out_backlog_bytes: { outsum: 9 * MiB }, checkpoints_skipped_since: 7 });
    expect(warnings(summary({ node_info: over }))).toEqual(["Outbound backlog", "Checkpoints skipped"]);
    expect(warnings(summary({ node_info: nodeInfo({ out_backlog_bytes: { outsum: 8 * MiB } }) }))).toEqual([]);
  });

  it("warns of an input log at its cap, never below it", () => {
    const log = summary().input_log;
    expect(warnings(summary({ input_log: { ...log, bytes: 100 * MiB } }))).toEqual(["Input log"]);
    expect(warnings(summary({ input_log: { ...log, bytes: 99 * MiB } }))).toEqual([]);
  });

  it("says what a node without checkpoints or node info file has not done yet", () => {
    const rows = summaryRows(summary({ checkpoints: [], node_info: null }));
    expect(rows.find(row => row.label === "Latest checkpoint")?.value).toBe("none yet");
    expect(rows.find(row => row.label === "Node info")?.value).toMatch(/never written/);
  });

  it("counts the records that a relaunch would replay", () => {
    expect(summaryRows(summary()).find(row => row.label === "To replay")?.value).toMatch(/^2 records /);
  });
});

describe("inputPortsOf", () => {
  it("names the external and the connected inputs without their dash", () => {
    const node = process([
      option("-numbers", { channel: "fifo", fifoTag: "external" }),
      option("-inf"),
      option("-threshold"),
      option("-outsum", { channel: "fifo" }),
    ]);
    const edges = [{ id: "e", sourceProcessId: "P", sourceOptionId: "-outf", targetProcessId: "Accumulate", targetOptionId: "-inf" }];

    expect(inputPortsOf(node, edges)).toEqual(["numbers", "inf"]);
  });
});

describe("Show node state", () => {
  it("is offered on every node but the Supervisor", () => {
    expect(offersShowNodeState(process([]))).toBe(true);
    expect(offersShowNodeState(process([], { nodeKind: "Supervisor" }))).toBe(false);
  });

  it("is enabled once the node has been launched, whatever its status since", () => {
    expect(wasLaunched(undefined)).toBe(false);
    expect(wasLaunched("TO-DO")).toBe(false);
    expect(["IN-PROGRESS", "FINISHED", "UNFINISHED"].every(wasLaunched)).toBe(true);
  });
});

describe("formatBytes", () => {
  it("keeps bytes whole and gives larger sizes one decimal", () => {
    expect(formatBytes(342)).toBe("342 B");
    expect(formatBytes(8 * MiB)).toBe("8.0 MiB");
  });
});
