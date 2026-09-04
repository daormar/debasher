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

export default function ProgramCanvas() {
  const {
    program,
    selectProcess,
    moveProcess,
    removeProcess,
    connect,
    disconnect,
    runPhase,
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
        }
      });
    },
    [moveProcess]
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
              onClose={dismissProgramRun}
            />
          </Panel>
        )}
      </ReactFlow>
    </div>
  );
}
