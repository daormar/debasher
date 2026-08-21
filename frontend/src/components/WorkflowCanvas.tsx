import { useState, useEffect, useCallback, useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  applyNodeChanges,
  type NodeChange,
  type Connection,
  type Edge,
  type Node,
} from "@xyflow/react";

import type { WorkflowNodeData } from "../adapters/reactFlowAdapter";

import { useWorkflow } from "../store/WorkflowContext";
import {
  workflowToReactFlowNodes,
  workflowToReactFlowEdges,
  connectionToWorkflowEdge,
  isValidWorkflowConnection,
} from "../adapters/reactFlowAdapter";
import WorkflowNode from "./WorkflowNode";

export default function WorkflowCanvas() {
  const { workflow, selectNode, moveNode, connect } = useWorkflow();

  // "Business" nodes: recalculated whenever workflow changes.
  const nodes = useMemo(
    () => workflowToReactFlowNodes(workflow),
    [workflow]
  );

  const edges = useMemo(
    () => workflowToReactFlowEdges(workflow),
    [workflow]
  );

  const nodeTypes = useMemo(
    () => ({
      workflow: WorkflowNode,
    }),
    []
  );

  // "React Flow" nodes: the local copy that stays in sync frame by
  // frame during dragging, via applyNodeChanges.
  const [localNodes, setLocalNodes] = useState(nodes);

  // "Fingerprint" of everything except position: id, name and
  // handles. Changes only when a node is added/removed, renamed,
  // or a handle is added/removed, never when a node is moved.
  const structuralKey = useMemo(
    () =>
      workflow.nodes
        .map(
          node =>
            `${node.id}:${node.name}:${node.handles
              .map(h => h.id)
              .join(",")}`
        )
        .join("|"),
    [workflow.nodes]
  );

  // Syncs localNodes with workflow ONLY on structural changes,
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

  const onNodesChange = useCallback(
     (changes: NodeChange<Node<WorkflowNodeData>>[]) => {
      // 1. Update the array React Flow needs, right away.
      setLocalNodes(current => applyNodeChanges(changes, current));

      // 2. Persist the final position in the business model.
      changes.forEach(change => {
        if (change.type === "position" && change.position) {
          moveNode(change.id, change.position);
        }
      });
    },
    [moveNode]
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      const edge = connectionToWorkflowEdge(connection);
      if (edge) {
        connect(edge);
      }
    },
    [connect]
  );

  const isValidConnection = useCallback(
    (connection: Connection | Edge) =>
      isValidWorkflowConnection(workflow, connection),
    [workflow]
  );

  const onNodeClick = useCallback(
    (_event: React.MouseEvent, node: { id: string }) => {
      selectNode(node.id);
    },
    [selectNode]
  );

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
      }}
    >
      <ReactFlow
        nodes={localNodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onConnect={onConnect}
        isValidConnection={isValidConnection}
        onNodeClick={onNodeClick}
        onNodesChange={onNodesChange}
        fitView
      >
        <Background />
        <Controls />
        <MiniMap />
      </ReactFlow>
    </div>
  );
}
