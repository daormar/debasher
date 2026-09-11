import { useState, useEffect, useCallback, useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Panel,
  applyNodeChanges,
  applyEdgeChanges,
  type NodeChange,
  type EdgeChange,
  type Connection,
  type Edge,
  type Node,
} from "@xyflow/react";

import type { ProgramProcessData } from "../adapters/reactFlowAdapter";
import type { ProgramProcess } from "../models/process";
import type { ProgramOption, FanoutFamily } from "../models/option";
import { fanoutBaseLabel, isFanoutOption } from "../models/option";
import {
  getProcessOpts,
  getProcessResolvedOptions,
  getProcessSchedOut,
  getProcessStdout,
  getProcessTasks,
  inspectPath,
} from "../api/executionApi";

import { useProgram } from "../store/ProgramContext";
import {
  programToReactFlowNodes,
  programToReactFlowEdges,
  connectionToProgramEdge,
  isValidProgramConnection,
} from "../adapters/reactFlowAdapter";
import ProcessNode from "./ProcessNode";
import FanoutEdge from "./FanoutEdge";
import BackEdge from "./BackEdge";
import RunStatusIndicator from "./RunStatusIndicator";
import ProcessContextMenu, { type ProcessMenuAction, type ProcessOutputKind } from "./ProcessContextMenu";
import ProcessTaskPicker from "./ProcessTaskPicker";
import CommandOutputModal from "./CommandOutputModal";
import ProcessIOModal from "./ProcessIOModal";

const OUTPUT_KIND_LABEL: Record<ProcessOutputKind, string> = {
  opts: "options",
  stdout: "stdout",
  "sched-out": "scheduler output",
};

// Also covers "io" ("Show inputs and outputs"), which the plain output
// kinds above don't — used for the task picker's label, shared by both
// flows.
const MENU_ACTION_LABEL: Record<ProcessMenuAction, string> = {
  ...OUTPUT_KIND_LABEL,
  io: "inputs and outputs",
};

// Above this many indices, listing the family inline stops being
// reasonable — past it, the family gets a "Pick index" row (backed by
// ProcessTaskPicker, see fanoutIndexPicker) instead.
const MAX_FANOUT_INLINE = 10;

// On a "standard"-mode process, a fanout/fanin option's label (e.g.
// "-outfith", "-indith" — see isFanoutOption) is only a template: the
// process actually runs with one concrete option per index ("-outf0",
// "-outf1", ..., "-ind0", "-ind1", ...), one per its countSourceOptionId
// sibling's value (e.g. "-w"). Splits each template into either its
// expanded indexed rows (looked up in resolvedValues the same way as
// any other option) when there are few enough, or a FanoutFamily for
// ProcessIOModal to render as a "Pick index" row instead — which,
// like an array/generator process's own stdout/scheduler-output/
// options, falls back on ProcessTaskPicker's own first/last-N sampling
// for a family with many indices.
function expandFanoutOptions(
  options: ProgramOption[],
  resolvedValues: Record<string, string>
): { options: ProgramOption[]; families: FanoutFamily[] } {

  const byId = new Map(options.map(o => [o.id, o]));
  const families: FanoutFamily[] = [];

  const expanded = options.flatMap(option => {

    if (!isFanoutOption(option.label)) {
      return [option];
    }

    const countSource = option.countSourceOptionId
      ? byId.get(option.countSourceOptionId)
      : undefined;

    const countValue = countSource
      ? resolvedValues[countSource.label] ?? countSource.value
      : undefined;

    const count = countValue !== undefined ? Number(countValue) : NaN;

    // Count unknown/unresolved (e.g. the program hasn't run yet, or
    // its count-source option couldn't be found) — show the template
    // row as-is rather than silently dropping the option.
    if (!Number.isInteger(count) || count <= 0) {
      return [option];
    }

    const base = fanoutBaseLabel(option.label);

    if (count > MAX_FANOUT_INLINE) {
      families.push({ option, baseLabel: base, count });
      return [];
    }

    return Array.from({ length: count }, (_, i) => ({
      ...option,
      id: `${option.id}:${i}`,
      label: `${base}${i}`,
    }));

  });

  return { options: expanded, families };

}

export default function ProgramCanvas() {
  const {
    program,
    selectProcess,
    moveProcess,
    removeProcess,
    connect,
    disconnect,
    runPhase,
    runOutput,
    dismissProgramRun,
  } = useProgram();

  // "Business" nodes: recalculated whenever program changes.
  const nodes = useMemo(
    () => programToReactFlowNodes(program),
    [program]
  );

  const edges = useMemo(
    () => programToReactFlowEdges(program),
    [program]
  );

  const nodeTypes = useMemo(
    () => ({
      program: ProcessNode,
    }),
    []
  );

  const edgeTypes = useMemo(
    () => ({
      fanout: FanoutEdge,
      backedge: BackEdge,
    }),
    []
  );

  // "React Flow" nodes: the local copy that stays in sync frame by
  // frame during dragging, via applyNodeChanges.
  const [localNodes, setLocalNodes] = useState(nodes);

  // "Fingerprint" of everything except position: id, name and
  // options. Changes whenever a process is added/removed/renamed, or
  // an option is added/removed/edited, never when a process is moved.
  const structuralKey = useMemo(
    () =>
      program.processes
        .map(
          process =>
            `${process.id}:${process.name}:${process.options
              .map(o => `${o.id}:${o.label}:${o.direction}`)
              .join(",")}`
        )
        .join("|"),
    [program.processes]
  );

  // Syncs localNodes with program ONLY on structural changes,
  // always preserving the position React Flow already has (so we
  // don't overwrite it mid-drag).
  useEffect(() => {
    setLocalNodes(current => {
      const currentById = new Map(
        current.map(node => [node.id, node])
      );

      return nodes.map(node => {
        const existing = currentById.get(node.id);

        if (existing) {
          return {
            ...node,
            position: existing.position,
          };
        }

        return node;
      });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [structuralKey]);

  // "React Flow" edges: kept in a local copy so that selection
  // changes (needed for delete-key handling) round-trip through
  // onEdgesChange instead of being silently dropped, since `edges`
  // is otherwise a controlled prop with no change handler.
  const [localEdges, setLocalEdges] = useState(edges);

  // Resyncs localEdges whenever the program-derived edges change
  // (edge added/removed), discarding any local-only selection state.
  useEffect(() => {
    setLocalEdges(edges);
  }, [edges]);

  const onNodesChange = useCallback(
     (changes: NodeChange<Node<ProgramProcessData>>[]) => {
      // 1. Update the array React Flow needs, right away.
      setLocalNodes(current => applyNodeChanges(changes, current));

      // 2. Persist the final position in the business model.
      changes.forEach(change => {
        if (change.type === "position" && change.position) {
          moveProcess(change.id, change.position);
        } else if (change.type === "select" && change.selected) {
          // Dragging a node selects it in React Flow (selectNodesOnDrag)
          // without firing onNodeClick, so mirror that into app state here.
          selectProcess(change.id);
        }
      });
    },
    [moveProcess, selectProcess]
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      const edge = connectionToProgramEdge(connection);
      if (edge) {
        connect(edge);
      }
    },
    [connect]
  );

  const isValidConnection = useCallback(
    (connection: Connection | Edge) =>
      isValidProgramConnection(program, connection),
    [program]
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange<Edge>[]) => {
      setLocalEdges(current => applyEdgeChanges(changes, current));
    },
    []
  );

  const onNodesDelete = useCallback(
    (deletedNodes: Node<ProgramProcessData>[]) => {
      deletedNodes.forEach(node => removeProcess(node.id));
    },
    [removeProcess]
  );

  const onEdgesDelete = useCallback(
    (deletedEdges: Edge[]) => {
      deletedEdges.forEach(edge => disconnect(edge.id));
    },
    [disconnect]
  );

  const onNodeClick = useCallback(
    (_event: React.MouseEvent, node: { id: string }) => {
      selectProcess(node.id);
    },
    [selectProcess]
  );

  const onPaneClick = useCallback(() => {
    selectProcess(null);
  }, [selectProcess]);

  // Right-click "Inspect execution" menu — see ProcessContextMenu.
  const [processContextMenu, setProcessContextMenu] =
    useState<{ process: ProgramProcess; x: number; y: number } | null>(null);

  const [isProcessOutputPending, setProcessOutputPending] =
    useState(false);

  const [processCommandOutput, setProcessCommandOutput] =
    useState<{ title: string; output: string } | null>(null);

  // Set instead of fetching straight away whenever the process ran as
  // more than one task (see ProcessTaskPicker) — populated only after
  // getProcessTasks comes back with more than one index.
  const [processTaskPicker, setProcessTaskPicker] =
    useState<{ process: ProgramProcess; kind: ProcessMenuAction; taskIndices: number[] } | null>(null);

  const [isTaskPickerPending, setTaskPickerPending] =
    useState(false);

  const [taskPickerError, setTaskPickerError] =
    useState<string | null>(null);

  // "Show inputs and outputs" — a structured modal (ProcessIOModal)
  // rather than a plain-text CommandOutputModal.
  const [processIO, setProcessIO] = useState<{
    processName: string;
    options: ProgramOption[];
    resolvedValues: Record<string, string>;
    families: FanoutFamily[];
  } | null>(null);

  // A ProcessIOModal fanout family's own "Pick index" button — reuses
  // ProcessTaskPicker (as ProcessTaskPicker's own doc comment puts it,
  // the same "could be huge" concern an array/generator process's own
  // tasks already have). Resolving a picked index needs no network
  // request: resolvedValues (already fetched for the whole process)
  // already has every index's value.
  const [fanoutIndexPicker, setFanoutIndexPicker] =
    useState<FanoutFamily | null>(null);

  // The second-level "View" modal a ProcessIOModal option's path
  // button opens (a file's content, or a directory's listing) — kept
  // separate from processCommandOutput so it stacks on top of
  // processIO instead of replacing it.
  const [pathContent, setPathContent] =
    useState<{ title: string; output: string } | null>(null);

  const [isPathViewPending, setPathViewPending] =
    useState(false);

  const onNodeContextMenu = useCallback(
    (event: React.MouseEvent, node: Node<ProgramProcessData>) => {
      event.preventDefault();
      setProcessContextMenu({
        process: node.data.process,
        x: event.clientX,
        y: event.clientY,
      });
    },
    []
  );

  async function fetchProcessOutput(
    process: ProgramProcess,
    kind: ProcessOutputKind,
    taskIndex?: number
  ): Promise<{ title: string; output: string }> {

    const taskSuffix = taskIndex !== undefined ? ` [task ${taskIndex}]` : "";
    const title = `${process.name}${taskSuffix}: ${OUTPUT_KIND_LABEL[kind]}`;

    const output = kind === "stdout"
      ? await getProcessStdout(program, process.name, taskIndex)
      : kind === "sched-out"
        ? await getProcessSchedOut(program, process.name, taskIndex)
        : await getProcessOpts(program, process.name, taskIndex);

    return { title, output };

  }

  // Excludes only fromProcessSpec options — a resource spec (cpus,
  // mem, ...), shown instead in the inspector's "Specifications"
  // section. commandLine is NOT the right filter here: it means
  // "settable on the overall program's own command line" (opt_is_
  // cmdline), not "is an input/output" — an auto-computed option like
  // "-outf" (define_opt, not define_cmdline_opt) has commandLine=false
  // but is still a real output.
  async function fetchProcessIO(
    process: ProgramProcess,
    taskIndex?: number
  ): Promise<{
    processName: string;
    options: ProgramOption[];
    resolvedValues: Record<string, string>;
    families: FanoutFamily[];
  }> {

    const resolvedValues = await getProcessResolvedOptions(program, process.name, taskIndex);

    const candidates = process.options.filter(o => !o.fromProcessSpec);

    // isFanoutOption/countSourceOptionId are only meaningful on a
    // "standard"-mode process (see models/option.ts) — elsewhere a
    // label ending in "ith" is just an ordinary option.
    const { options, families } = process.optionsHandler.mode === "standard"
      ? expandFanoutOptions(candidates, resolvedValues)
      : { options: candidates, families: [] };

    return {
      processName: process.name,
      options,
      resolvedValues,
      families,
    };

  }

  // Adds the picked index's concrete option (e.g. "-outf" family +
  // index 7 -> "-outf7") to the open ProcessIOModal's option list —
  // the family's own "Pick index" row stays put so more indices can
  // still be picked.
  function handleFanoutIndexPickerConfirm(index: number) {

    if (!fanoutIndexPicker) {
      return;
    }

    const { option, baseLabel } = fanoutIndexPicker;
    const label = `${baseLabel}${index}`;

    setProcessIO(current => {

      if (!current) {
        return current;
      }

      const withoutThisIndex = current.options.filter(
        o => !(o.label === label && o.id.startsWith(`${option.id}:`))
      );

      return {
        ...current,
        options: [
          ...withoutThisIndex,
          { ...option, id: `${option.id}:${index}`, label },
        ],
      };

    });

    setFanoutIndexPicker(null);

  }

  async function handleProcessMenuSelect(action: ProcessMenuAction) {

    if (!processContextMenu) {
      return;
    }

    const { process } = processContextMenu;

    setProcessOutputPending(true);

    try {

      // A "standard" process has no per-task files at all (empty list,
      // so taskIndices[0] is undefined — the plain no-task-index
      // request) and a process that only ever ran as one task doesn't
      // need picking either; anything more brings up the picker rather
      // than guessing which task the user wants.
      const taskIndices = await getProcessTasks(program, process.name);

      if (taskIndices.length > 1) {
        setProcessTaskPicker({ process, kind: action, taskIndices });
        setProcessContextMenu(null);
        return;
      }

      if (action === "io") {
        setProcessIO(await fetchProcessIO(process, taskIndices[0]));
      } else {
        setProcessCommandOutput(await fetchProcessOutput(process, action, taskIndices[0]));
      }
      setProcessContextMenu(null);

    } catch (err) {
      setProcessCommandOutput({
        title: process.name,
        output: err instanceof Error ? err.message : "Failed to inspect process execution.",
      });
      setProcessContextMenu(null);
    } finally {
      setProcessOutputPending(false);
    }

  }

  async function handleTaskPickerConfirm(taskIndex: number) {

    if (!processTaskPicker) {
      return;
    }

    const { process, kind } = processTaskPicker;

    setTaskPickerPending(true);
    setTaskPickerError(null);

    try {
      if (kind === "io") {
        setProcessIO(await fetchProcessIO(process, taskIndex));
      } else {
        setProcessCommandOutput(await fetchProcessOutput(process, kind, taskIndex));
      }
      setProcessTaskPicker(null);
    } catch (err) {
      setTaskPickerError(err instanceof Error ? err.message : "Failed to get process output.");
    } finally {
      setTaskPickerPending(false);
    }

  }

  function handleTaskPickerCancel() {
    setProcessTaskPicker(null);
    setTaskPickerError(null);
  }

  async function handleViewPath(option: ProgramOption, resolvedValue: string) {

    setPathViewPending(true);

    try {
      const result = await inspectPath(resolvedValue);
      const title = `${option.label}: ${resolvedValue}`;

      const output = result.kind === "file"
        ? result.content
        : result.kind === "directory"
          ? (result.entries.length > 0 ? result.entries.join("\n") : "(empty directory)")
          : result.kind === "binary"
            ? `Warning: ${resolvedValue} looks like a binary file — content not shown.`
            : `Path not found: ${resolvedValue}`;

      setPathContent({ title, output });
    } catch (err) {
      setPathContent({
        title: option.label,
        output: err instanceof Error ? err.message : "Failed to inspect path.",
      });
    } finally {
      setPathViewPending(false);
    }

  }

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
      }}
    >
      <ReactFlow
        nodes={localNodes}
        edges={localEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onConnect={onConnect}
        isValidConnection={isValidConnection}
        onNodeClick={onNodeClick}
        onNodeContextMenu={onNodeContextMenu}
        onPaneClick={onPaneClick}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodesDelete={onNodesDelete}
        onEdgesDelete={onEdgesDelete}
        deleteKeyCode={["Delete", "Backspace"]}
        fitView
      >
        <Background />
        <Controls />
        <MiniMap />

        {runPhase !== "idle" && (
          <Panel position="bottom-right" style={{ marginBottom: 170 }}>
            <RunStatusIndicator
              phase={runPhase}
              output={runOutput}
              onClose={dismissProgramRun}
            />
          </Panel>
        )}
      </ReactFlow>

      {processContextMenu && (
        <ProcessContextMenu
          x={processContextMenu.x}
          y={processContextMenu.y}
          isPending={isProcessOutputPending}
          onSelect={handleProcessMenuSelect}
          onClose={() => setProcessContextMenu(null)}
        />
      )}

      {processTaskPicker && (
        <ProcessTaskPicker
          processName={processTaskPicker.process.name}
          kindLabel={MENU_ACTION_LABEL[processTaskPicker.kind]}
          taskIndices={processTaskPicker.taskIndices}
          isPending={isTaskPickerPending}
          error={taskPickerError}
          onConfirm={handleTaskPickerConfirm}
          onCancel={handleTaskPickerCancel}
        />
      )}

      {processCommandOutput && (
        <CommandOutputModal
          title={processCommandOutput.title}
          output={processCommandOutput.output}
          onClose={() => setProcessCommandOutput(null)}
        />
      )}

      {processIO && (
        <ProcessIOModal
          processName={processIO.processName}
          options={processIO.options}
          resolvedValues={processIO.resolvedValues}
          families={processIO.families}
          isViewPending={isPathViewPending}
          onViewPath={handleViewPath}
          onPickFanoutIndex={setFanoutIndexPicker}
          onClose={() => setProcessIO(null)}
        />
      )}

      {fanoutIndexPicker && (
        <ProcessTaskPicker
          processName={processIO?.processName ?? ""}
          kindLabel={fanoutIndexPicker.option.label}
          itemLabel="option"
          taskIndices={Array.from({ length: fanoutIndexPicker.count }, (_, i) => i)}
          isPending={false}
          error={null}
          onConfirm={handleFanoutIndexPickerConfirm}
          onCancel={() => setFanoutIndexPicker(null)}
        />
      )}

      {pathContent && (
        <CommandOutputModal
          title={pathContent.title}
          output={pathContent.output}
          onClose={() => setPathContent(null)}
        />
      )}
    </div>
  );
}
