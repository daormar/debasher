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
import { getProcessOpts, getProcessSchedOut, getProcessStdout, getProcessTasks } from "../api/executionApi";

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
import ProcessContextMenu, { type ProcessOutputKind } from "./ProcessContextMenu";
import ProcessTaskPicker from "./ProcessTaskPicker";
import CommandOutputModal from "./CommandOutputModal";

const OUTPUT_KIND_LABEL: Record<ProcessOutputKind, string> = {
  opts: "options",
  stdout: "stdout",
  "sched-out": "scheduler output",
};

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
    useState<{ process: ProgramProcess; kind: ProcessOutputKind; taskIndices: number[] } | null>(null);

  const [isTaskPickerPending, setTaskPickerPending] =
    useState(false);

  const [taskPickerError, setTaskPickerError] =
    useState<string | null>(null);

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
    const title = `${process.name}${taskSuffix} — ${OUTPUT_KIND_LABEL[kind]}`;

    const output = kind === "stdout"
      ? await getProcessStdout(program, process.name, taskIndex)
      : kind === "sched-out"
        ? await getProcessSchedOut(program, process.name, taskIndex)
        : await getProcessOpts(program, process.name, taskIndex);

    return { title, output };

  }

  async function handleProcessOutputSelect(kind: ProcessOutputKind) {

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
        setProcessTaskPicker({ process, kind, taskIndices });
        setProcessContextMenu(null);
        return;
      }

      const result = await fetchProcessOutput(process, kind, taskIndices[0]);
      setProcessCommandOutput(result);
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
      const result = await fetchProcessOutput(process, kind, taskIndex);
      setProcessCommandOutput(result);
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
          onSelect={handleProcessOutputSelect}
          onClose={() => setProcessContextMenu(null)}
        />
      )}

      {processTaskPicker && (
        <ProcessTaskPicker
          processName={processTaskPicker.process.name}
          kindLabel={OUTPUT_KIND_LABEL[processTaskPicker.kind]}
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
    </div>
  );
}
