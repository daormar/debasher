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
import type { ProgramEdge } from "../models/edge";
import { showsGeneralIndicator } from "../models/generalRun";
import { hasSupervisor } from "../models/node";
import { offersShowBatchRuns, offersShowNodeState, wasLaunched } from "../models/nodeState";
import {
  offersRelaunchNode,
  offersRestartNode,
  relaunchOutcome,
  restartNodeWarning,
  restartsWithBothEnds,
  stoppedInOrder,
} from "../models/residentRun";
import {
  getProcessOpts,
  getProcessResolvedOptions,
  getProcessSchedOut,
  getProcessStdout,
  getProcessTasks,
  inspectPath,
  pathInspectionText,
  launchedWithNoHoldFifos,
  relaunchNode,
  restartNode,
  stopProcess,
} from "../api/executionApi";

import { useProgram } from "../store/ProgramContext";
import {
  programToReactFlowNodes,
  programToReactFlowEdges,
  connectionToProgramEdge,
  isValidProgramConnection,
  computeFlippedOptionIds,
  canvasStructuralKey,
  supervisorWiring,
} from "../adapters/reactFlowAdapter";
import ProcessNode from "./ProcessNode";
import FanoutEdge from "./FanoutEdge";
import BackEdge from "./BackEdge";
import SelfLoopEdge from "./SelfLoopEdge";
import ConfirmDialog from "./ConfirmDialog";
import ResidentRunIndicator from "./ResidentRunIndicator";
import RunStatusIndicator from "./RunStatusIndicator";
import ProcessContextMenu, {
  type NodeAction,
  type ProcessMenuAction,
  type ProcessOutputKind,
  type ResidentInspection,
} from "./ProcessContextMenu";
import ProcessTaskPicker from "./ProcessTaskPicker";
import CommandOutputModal from "./CommandOutputModal";
import NodeStateModal from "./NodeStateModal";
import BatchRunsModal from "./BatchRunsModal";
import ProcessIOModal from "./ProcessIOModal";
import FifoWatchModal from "./FifoWatchModal";
import ProgramFilesPanel from "./ProgramFilesPanel";
import CanvasLegend from "./CanvasLegend";

const OUTPUT_KIND_LABEL: Record<ProcessOutputKind, string> = {
  opts: "options",
  stdout: "stdout",
  "sched-out": "scheduler output",
};

// Also covers "io" ("Show inputs and outputs"), which the plain output
// kinds above don't, used for the task picker's label, shared by both
// flows.
const MENU_ACTION_LABEL: Record<ProcessMenuAction, string> = {
  ...OUTPUT_KIND_LABEL,
  io: "inputs and outputs",
  "watch-fifo": "mirrored fifo output",
  "node-state": "node state",
  "batch-runs": "batch runs",
  stop: "process stop",
  restart: "node restart",
  relaunch: "node relaunch",
};

// Above this many indices, listing the family inline stops being
// reasonable, past it, the family gets a "Pick index" row (backed by
// ProcessTaskPicker, see fanoutIndexPicker) instead.
const MAX_FANOUT_INLINE = 10;

// True if `option` itself is fifo-channel, or is a plain ("none"-
// channel) connection whose upstream source is: a "-inf"-style input
// on a "standard"-mode process is never itself channel === "fifo":
// only the writing end opens one, via define_fifo_opt (see
// dispatch_define_opts/worker_define_opts's plain
// define_opt_from_proc_out on the reading side, in
// data/programs/debasher_dynamic_fanout_fifos.sh), so its own
// resolved value is a fifo path all the same, and ProcessIOModal's
// "View" (a plain file read) is just as unsafe on it as on the fifo
// option it's wired to.
function isFifoBackedOption(
  option: ProgramOption,
  edges: ProgramEdge[],
  processes: { options: ProgramOption[] }[]
): boolean {

  if (option.channel === "fifo") {
    return true;
  }

  const sourceEdge = edges.find(edge => edge.targetOptionId === option.id);
  if (!sourceEdge) {
    return false;
  }

  const sourceOption = processes
    .flatMap(process => process.options)
    .find(o => o.id === sourceEdge.sourceOptionId);

  return sourceOption?.channel === "fifo";

}

// On a "standard"-mode process, a fanout/fanin option's label (e.g.
// "-outfith", "-indith", see isFanoutOption) is only a template: the
// process actually runs with one concrete option per index ("-outf0",
// "-outf1", ..., "-ind0", "-ind1", ...), one per its countSourceOptionId
// sibling's value (e.g. "-w"). Splits each template into either its
// expanded indexed rows (looked up in resolvedValues the same way as
// any other option) when there are few enough, or a FanoutFamily for
// ProcessIOModal to render as a "Pick index" row instead, which,
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
    // its count-source option couldn't be found), show the template
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
    runEndSeen,
    processStatuses,
    residentPhase,
  } = useProgram();

  const isResident = program.programType === "resident";

  const inOrder = stoppedInOrder(processStatuses);

  // The indicator of the run, hidden by its Hide button until the run phase
  // changes: what it shows is then new.
  const indicatorKey = isResident
    ? (residentPhase === "stopped" ? `stopped:${inOrder}` : residentPhase)
    : runPhase;

  const [hiddenIndicator, setHiddenIndicator] =
    useState<string | null>(null);

  // Whether the Supervisor wiring of a resident program is shown. It belongs
  // to the tab, like the selection, and is not saved.
  const [showWiring, setShowWiring] = useState(false);

  // "Business" nodes: recalculated whenever program changes.
  const nodes = useMemo(
    () => programToReactFlowNodes(program, showWiring),
    [program, showWiring]
  );

  // The edges of the Supervisor wiring, read only, come after those of the
  // program, derived from it as its handles are.
  const edges = useMemo(
    () => [
      ...programToReactFlowEdges(program),
      ...(showWiring ? supervisorWiring(program).edges : []),
    ],
    [program, showWiring]
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
      selfloop: SelfLoopEdge,
    }),
    []
  );

  // "React Flow" nodes: the local copy that stays in sync frame by
  // frame during dragging, via applyNodeChanges.
  const [localNodes, setLocalNodes] = useState(nodes);

  // Everything but the positions that the canvas nodes draw from their
  // processes (see canvasStructuralKey).
  const structuralKey = useMemo(
    () => canvasStructuralKey(program, showWiring),
    [program, showWiring]
  );

  // Fingerprint of which options are currently rendered with a flipped
  // handle (see computeFlippedOptionIds), this is position-dependent
  // (it can change when a process is dragged past a FIFO partner it
  // forms a cycle with), unlike structuralKey above, so it's tracked
  // separately rather than folded into it. As a memoized string,
  // equal values across consecutive drag frames are ===-equal, so this
  // only changes on the rare frame a pair's relative order actually
  // flips, it doesn't reintroduce per-frame resyncing below.
  const flipFingerprint = useMemo(
    () => [...computeFlippedOptionIds(program)].sort().join(","),
    [program]
  );

  // Syncs localNodes with program on structural changes or a handle
  // flip, always preserving the position React Flow already has (so we
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
  }, [structuralKey, flipFingerprint]);

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

  // Right-click "Inspect execution" menu, see ProcessContextMenu.
  const [processContextMenu, setProcessContextMenu] =
    useState<{ process: ProgramProcess; x: number; y: number } | null>(null);

  const [isProcessOutputPending, setProcessOutputPending] =
    useState(false);

  const [processCommandOutput, setProcessCommandOutput] =
    useState<{ title: string; message?: string; output: string } | null>(null);

  // "Restart node" waiting for the user's confirmation, with its warning.
  const [restartConfirm, setRestartConfirm] =
    useState<{ process: ProgramProcess; warning: string[] } | null>(null);

  // Set instead of fetching straight away whenever the process ran as
  // more than one task (see ProcessTaskPicker), populated only after
  // getProcessTasks comes back with more than one index.
  const [processTaskPicker, setProcessTaskPicker] =
    useState<{ process: ProgramProcess; kind: ProcessMenuAction; taskIndices: number[] } | null>(null);

  const [isTaskPickerPending, setTaskPickerPending] =
    useState(false);

  const [taskPickerError, setTaskPickerError] =
    useState<string | null>(null);

  // "Show inputs and outputs", a structured modal (ProcessIOModal)
  // rather than a plain-text CommandOutputModal.
  const [processIO, setProcessIO] = useState<{
    processName: string;
    options: ProgramOption[];
    resolvedValues: Record<string, string>;
    families: FanoutFamily[];
    fifoBackedOptionIds: Set<string>;
  } | null>(null);

  // A ProcessIOModal fanout family's own "Pick index" button, reuses
  // ProcessTaskPicker (as ProcessTaskPicker's own doc comment puts it,
  // the same "could be huge" concern an array/generator process's own
  // tasks already have). Resolving a picked index needs no network
  // request: resolvedValues (already fetched for the whole process)
  // already has every index's value.
  const [fanoutIndexPicker, setFanoutIndexPicker] =
    useState<FanoutFamily | null>(null);

  // The second-level "View" modal a ProcessIOModal option's path
  // button opens (a file's content, or a directory's listing), kept
  // separate from processCommandOutput so it stacks on top of
  // processIO instead of replacing it.
  const [pathContent, setPathContent] =
    useState<{ title: string; output: string } | null>(null);

  const [isPathViewPending, setPathViewPending] =
    useState(false);

  // "Watch FIFO", a live-polling FifoWatchModal (see
  // handleProcessMenuSelect's "watch-fifo" branch) rather than a
  // one-shot processCommandOutput.
  const [fifoWatch, setFifoWatch] = useState<{
    title: string;
    processName: string;
    fifoName: string;
    taskIndex?: number;
  } | null>(null);

  // "Show node state" on a node of a resident program.
  const [nodeState, setNodeState] =
    useState<{ process: ProgramProcess; taskIndex?: number } | null>(null);

  // "Show batch runs" on a launcher node, which is never a task of an array.
  const [batchRunsOf, setBatchRunsOf] =
    useState<ProgramProcess | null>(null);

  // Set instead of opening fifoWatch directly whenever a process has
  // more than one mirrored output fifo option, mirrors
  // processTaskPicker's own "pick first" pattern.
  const [fifoPicker, setFifoPicker] = useState<{
    process: ProgramProcess;
    options: ProgramOption[];
    taskIndex?: number;
  } | null>(null);

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

  // Excludes only fromProcessSpec options, a resource spec (cpus,
  // mem, ...), shown instead in the inspector's "Specifications"
  // section. commandLine is NOT the right filter here: it means
  // "settable on the overall program's own command line" (opt_is_
  // cmdline), not "is an input/output", an auto-computed option like
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
    fifoBackedOptionIds: Set<string>;
  }> {

    const resolvedValues = await getProcessResolvedOptions(program, process.name, taskIndex);

    const candidates = process.options.filter(o => !o.fromProcessSpec);

    // Resolved from candidates (real option ids, matching program.edges)
    // before fanout expansion synthesizes any "id:index" ones, a
    // fanout option's own concrete rows already inherit its channel
    // unchanged (see expandFanoutOptions), so they don't need this.
    const fifoBackedOptionIds = new Set(
      candidates
        .filter(option => isFifoBackedOption(option, program.edges, program.processes))
        .map(option => option.id)
    );

    // isFanoutOption/countSourceOptionId are only meaningful on a
    // "standard"-mode process (see models/option.ts), elsewhere a
    // label ending in "ith" is just an ordinary option.
    const { options, families } = process.optionsHandler.mode === "standard"
      ? expandFanoutOptions(candidates, resolvedValues)
      : { options: candidates, families: [] };

    return {
      processName: process.name,
      options,
      resolvedValues,
      families,
      fifoBackedOptionIds,
    };

  }

  // Adds the picked index's concrete option (e.g. "-outf" family +
  // index 7 -> "-outf7") to the open ProcessIOModal's option list;
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

  // Shared by handleProcessMenuSelect and handleTaskPickerConfirm's own
  // "watch-fifo" branch. No network call needed to find the candidate
  // options, process.options (with channel/direction/mirror already
  // resolved) is loaded client-side, same data fetchProcessIO reads.
  function openFifoWatch(process: ProgramProcess, taskIndex?: number) {

    const mirroredOptions = process.options.filter(
      o => o.channel === "fifo" && o.direction === "output" && o.mirror
    );

    if (mirroredOptions.length === 0) {
      setProcessCommandOutput({
        title: process.name,
        output: 'No mirrored output fifo on this process. Enable "Mirror" on an output fifo option first.',
      });
    } else if (mirroredOptions.length === 1) {
      setFifoWatch({
        title: `${process.name}: ${mirroredOptions[0].label} (fifo)`,
        processName: process.name,
        fifoName: mirroredOptions[0].value,
        taskIndex,
      });
    } else {
      setFifoPicker({ process, options: mirroredOptions, taskIndex });
    }

  }

  function handleFifoPickerSelect(option: ProgramOption) {

    if (!fifoPicker) {
      return;
    }

    setFifoWatch({
      title: `${fifoPicker.process.name}: ${option.label} (fifo)`,
      processName: fifoPicker.process.name,
      fifoName: option.value,
      taskIndex: fifoPicker.taskIndex,
    });

    setFifoPicker(null);

  }

  async function handleProcessMenuSelect(action: ProcessMenuAction) {

    if (!processContextMenu) {
      return;
    }

    const { process } = processContextMenu;

    setProcessOutputPending(true);

    try {

      // debasher_stop -p has no per-task variant, it stops every task
      // of the named process at once, so this skips the task-index
      // flow below entirely, unlike the other actions.
      if (action === "stop") {
        setProcessCommandOutput({
          title: `${process.name}: stop`,
          output: await stopProcess(program, process.name),
        });
        setProcessContextMenu(null);
        return;
      }

      if (action === "restart") {
        await askRestartNode(process);
        setProcessContextMenu(null);
        return;
      }

      if (action === "batch-runs") {
        setBatchRunsOf(process);
        setProcessContextMenu(null);
        return;
      }

      if (action === "relaunch") {
        const result = await relaunchNode(program, process.name);
        setProcessCommandOutput({
          title: `${process.name}: relaunch`,
          message: relaunchOutcome(result.relaunched, result.exitCode),
          output: result.output,
        });
        setProcessContextMenu(null);
        return;
      }

      // A "standard" process has no per-task files at all (empty list,
      // so taskIndices[0] is undefined, the plain no-task-index
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
      } else if (action === "node-state") {
        setNodeState({ process, taskIndex: taskIndices[0] });
      } else if (action === "watch-fifo") {
        openFifoWatch(process, taskIndices[0]);
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

  // "Restart node" asks first, with a warning that says what the restart
  // does. When the node has a channel whose two ends restart together, the
  // warning says that it may lose what it held: without a Supervisor always,
  // with one only when it was launched with -no-hold-fifos.
  async function askRestartNode(process: ProgramProcess) {

    const supervised = hasSupervisor(program.processes);

    const losesHeldChannel =
      restartsWithBothEnds(program.edges, process.id) &&
      (!supervised || await launchedWithNoHoldFifos(program));

    setRestartConfirm({
      process,
      warning: restartNodeWarning(process, supervised, losesHeldChannel),
    });

  }

  async function handleConfirmRestart() {

    if (!restartConfirm) {
      return;
    }

    const { process } = restartConfirm;
    setRestartConfirm(null);

    try {
      const result = await restartNode(program, process.name);
      setProcessCommandOutput({
        title: `${process.name}: restart`,
        message: !hasSupervisor(program.processes)
          ? relaunchOutcome(result.relaunched, result.exitCode)
          : result.exitCode === 0
          ? "The node was stopped, and the Supervisor relaunches it from its last checkpoint and its input log."
          : `debasher_stop ended with exit code ${result.exitCode}. What it printed:`,
        output: result.output,
      });
    } catch (err) {
      setProcessCommandOutput({
        title: `${process.name}: restart`,
        output: err instanceof Error ? err.message : "Failed to restart the node.",
      });
    }

  }

  // The actions on the process itself in its context menu; those of a
  // resident program act on a live program only.
  function nodeActionsOf(process: ProgramProcess): NodeAction[] {

    if (!isResident) {
      return [{ label: "Stop process", action: "stop", disabled: false, destructive: true }];
    }

    const notLive = residentPhase !== "live";
    const actions: NodeAction[] = [];

    if (offersRelaunchNode(program)) {
      actions.push({ label: "Relaunch node", action: "relaunch", disabled: notLive, destructive: false });
    }

    if (offersRestartNode(program, process)) {
      actions.push({ label: "Restart node", action: "restart", disabled: notLive, destructive: true });
    }

    return actions;

  }

  // The inspection actions of a node of a resident program, enabled once the
  // node has been launched, whatever the run phase.
  function residentInspectionsOf(process: ProgramProcess): ResidentInspection[] {

    if (!isResident) {
      return [];
    }

    const disabled = !wasLaunched(processStatuses[process.name]);
    const inspections: ResidentInspection[] = [];

    if (offersShowNodeState(process)) {
      inspections.push({ label: "Show node state", action: "node-state", disabled });
    }

    if (offersShowBatchRuns(process)) {
      inspections.push({ label: "Show batch runs", action: "batch-runs", disabled });
    }

    return inspections;

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
      } else if (kind === "node-state") {
        setNodeState({ process, taskIndex });
      } else if (kind === "watch-fifo") {
        openFifoWatch(process, taskIndex);
      } else if (kind === "batch-runs") {
        setBatchRunsOf(process);
      } else if (kind === "stop" || kind === "restart" || kind === "relaunch") {
        // Unreachable in practice, handleProcessMenuSelect handles
        // these actions before ever reaching the task picker,
        // kept here only so this switch stays exhaustive over
        // ProcessMenuAction.
        setProcessCommandOutput({
          title: `${process.name}: stop`,
          output: await stopProcess(program, process.name),
        });
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

      setPathContent({ title, output: pathInspectionText(resolvedValue, result) });
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

        <Panel position="top-left">
          <ProgramFilesPanel />
        </Panel>

        <Panel position="top-right">
          <CanvasLegend programType={program.programType} />
        </Panel>

        {!isResident && runPhase !== "idle" && showsGeneralIndicator(runPhase, runEndSeen) &&
          hiddenIndicator !== indicatorKey && (
          <Panel position="bottom-right" style={{ marginBottom: 170 }}>
            <RunStatusIndicator
              phase={runPhase}
              output={runOutput}
              onHide={() => setHiddenIndicator(indicatorKey)}
            />
          </Panel>
        )}

        {isResident && residentPhase !== "new" &&
          hiddenIndicator !== indicatorKey && (
          <Panel position="bottom-right" style={{ marginBottom: 170 }}>
            <ResidentRunIndicator
              phase={residentPhase}
              inOrder={inOrder}
              onHide={() => setHiddenIndicator(indicatorKey)}
            />
          </Panel>
        )}
      </ReactFlow>

      {processContextMenu && (
        <ProcessContextMenu
          x={processContextMenu.x}
          y={processContextMenu.y}
          isPending={isProcessOutputPending}
          isResident={isResident}
          residentInspections={residentInspectionsOf(processContextMenu.process)}
          onSelect={handleProcessMenuSelect}
          onClose={() => setProcessContextMenu(null)}
          nodeActions={nodeActionsOf(processContextMenu.process)}
          canvasAction={
            program.programType === "resident" &&
            processContextMenu.process.nodeKind === "Supervisor"
              ? {
                  label: showWiring ? "Hide Supervisor wiring" : "Show Supervisor wiring",
                  onSelect: () => {
                    setShowWiring(shown => !shown);
                    setProcessContextMenu(null);
                  },
                }
              : undefined
          }
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

      {restartConfirm && (
        <ConfirmDialog
          title={`Restart node ${restartConfirm.process.name}?`}
          confirmLabel="Restart"
          onConfirm={handleConfirmRestart}
          onCancel={() => setRestartConfirm(null)}
        >
          {restartConfirm.warning.map(paragraph => (
            <p key={paragraph} style={{ margin: 0 }}>
              {paragraph}
            </p>
          ))}
        </ConfirmDialog>
      )}

      {processCommandOutput && (
        <CommandOutputModal
          title={processCommandOutput.title}
          message={processCommandOutput.message}
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
          fifoBackedOptionIds={processIO.fifoBackedOptionIds}
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

      {fifoPicker && (
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
              width: 320,
              background: "#fff",
              borderRadius: 4,
              padding: 16,
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >
            <h3 style={{ margin: 0 }}>
              {fifoPicker.process.name}: pick a mirrored fifo
            </h3>
            {fifoPicker.options.map(option => (
              <button key={option.id} onClick={() => handleFifoPickerSelect(option)}>
                {option.label}
              </button>
            ))}
            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button onClick={() => setFifoPicker(null)}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {nodeState && (
        <NodeStateModal
          process={nodeState.process}
          taskIndex={nodeState.taskIndex}
          onClose={() => setNodeState(null)}
        />
      )}

      {batchRunsOf && (
        <BatchRunsModal
          process={batchRunsOf}
          onClose={() => setBatchRunsOf(null)}
        />
      )}

      {fifoWatch && (
        <FifoWatchModal
          title={fifoWatch.title}
          program={program}
          processName={fifoWatch.processName}
          fifoName={fifoWatch.fifoName}
          taskIndex={fifoWatch.taskIndex}
          onClose={() => setFifoWatch(null)}
        />
      )}
    </div>
  );
}
