import { useEffect, useRef, useState } from "react";

import {
  checkLaunch,
  checkProgramOptions,
  getProgramStatus,
  takeSnapshot,
  validateProgram,
} from "../api/executionApi";
import type { RunProgramResult } from "../api/executionApi";
import { LaunchRecordConflict } from "../api/executionApi";
import type { Program } from "../models/program";
import { useProgram } from "../store/ProgramContext";
import { HARD_KILL_CONSEQUENCES, orderlyStopOutcome, snapshotOutcome } from "../models/residentRun";
import CommandOutputModal from "./CommandOutputModal";
import ConfirmDialog from "./ConfirmDialog";
import LaunchRecordDialog from "./LaunchRecordDialog";
import ExecutionOptionsEditor from "./ExecutionOptionsEditor";
import OutputDirEditor from "./OutputDirEditor";
import ProgramOptionsEditor from "./ProgramOptionsEditor";
import ResetOutputDirConfirm from "./ResetOutputDirConfirm";
import TalkToFifosDialog from "./TalkToFifosDialog";

const MENU_ITEMS = [
  "Set output directory",
  "Set execution options",
  "Set program options",
  "Check program options",
  "Validate program",
  "Run program",
  "Get program status",
  "Stop program",
  "Kill program",
  "Take snapshot",
  "Reset output directory",
  "Reset program state",
  "Talk to FIFOs",
] as const;

type MenuItem = (typeof MENU_ITEMS)[number];

const REQUIRES_OUTPUT_DIR = new Set<MenuItem>([
  "Check program options",
  "Validate program",
  "Run program",
  "Get program status",
  "Stop program",
  "Kill program",
  "Take snapshot",
  "Reset output directory",
  "Reset program state",
]);

// The actions on a program that the run menu does not offer while a request
// of this tab to launch, stop or kill it has not been answered.
const ACTS_ON_PROGRAM = new Set<MenuItem>([
  "Set output directory",
  "Check program options",
  "Validate program",
  "Run program",
  "Stop program",
  "Kill program",
  "Take snapshot",
  "Reset output directory",
  "Reset program state",
]);

// Offered on a resident program only while it is live.
const LIVE_ONLY = new Set<MenuItem>([
  "Stop program",
  "Kill program",
  "Take snapshot",
]);

// Offered on a resident program only.
const RESIDENT_ONLY = new Set<MenuItem>([
  "Kill program",
  "Take snapshot",
  "Reset program state",
]);

// Offered on a general program only: a resident program resets its program
// state instead, since its output directory is part of the program.
const GENERAL_ONLY = new Set<MenuItem>([
  "Reset output directory",
]);

const REQUIRES_HOME_DIR = new Set<MenuItem>([
  "Check program options",
  "Validate program",
  "Run program",
]);

const PENDING_LABELS: Partial<Record<MenuItem, string>> = {
  "Check program options": "Checking...",
  "Validate program": "Validating...",
  "Run program": "Launching...",
  "Get program status": "Getting status...",
  "Stop program": "Stopping...",
  "Take snapshot": "Taking snapshot...",
};

interface CommandOutput {
  title: string;
  message?: string;
  output: string;
}

export default function RunMenu() {

  const {
    program,
    runPhase,
    isRunInProgress,
    startProgramRun,
    resetOutputDir,
    residentPhase,
    stopRun,
    killResidentProgram,
    resetProgramState,
  } = useProgram();

  const isResident =
    program.programType === "resident";

  // A request of this tab to launch, stop or kill the program has not been
  // answered yet.
  const phase = isResident ? residentPhase : runPhase;
  const isRequestPending = phase === "launching" || phase === "stopping";

  const [isOpen, setOpen] =
    useState(false);

  const [isOutputDirOpen, setOutputDirOpen] =
    useState(false);

  const [isExecutionOptionsOpen, setExecutionOptionsOpen] =
    useState(false);

  const [isProgramOptionsOpen, setProgramOptionsOpen] =
    useState(false);

  const [isResetConfirmOpen, setResetConfirmOpen] =
    useState(false);

  const [isKillConfirmOpen, setKillConfirmOpen] =
    useState(false);

  const [isResetStateConfirmOpen, setResetStateConfirmOpen] =
    useState(false);

  // "Run program" on program state that another program may have produced,
  // waiting for the user's choice.
  const [launchConfirm, setLaunchConfirm] =
    useState<{ hasLaunchRecord: boolean } | null>(null);

  // "Reset program state": delete the program state instead of setting it
  // aside.
  const [deleteState, setDeleteState] =
    useState(false);

  const [isTalkToFifosOpen, setTalkToFifosOpen] =
    useState(false);

  const [isResetPending, setResetPending] =
    useState(false);

  const [resetError, setResetError] =
    useState<string | null>(null);

  const [commandOutput, setCommandOutput] =
    useState<CommandOutput | null>(null);

  const [pendingAction, setPendingAction] =
    useState<MenuItem | null>(null);

  const [actionError, setActionError] =
    useState<string | null>(null);

  const containerRef =
    useRef<HTMLDivElement>(null);

  // "Run program" on a resident program asks first when its output
  // directory holds program state that another program may have produced.
  async function handleRunProgram() {

    setActionError(null);

    if (isResident) {

      setPendingAction("Run program");

      try {
        const check = await checkLaunch(program);
        if (check.needsConfirmation) {
          setPendingAction(null);
          setOpen(false);
          setLaunchConfirm({ hasLaunchRecord: check.hasLaunchRecord });
          return;
        }
      } catch (err) {
        setPendingAction(null);
        setActionError(err instanceof Error ? err.message : "Failed to run program.");
        return;
      }

    }

    await launch(false, true);

  }

  // `fromMenu`: the launch comes from the open menu, which shows an error
  // inline; after the dialog of the launch record, it comes in a modal.
  async function launch(resumeChangedProgram: boolean, fromMenu: boolean) {

    setPendingAction("Run program");

    let result: RunProgramResult;

    try {
      result = await startProgramRun(resumeChangedProgram);
    } catch (err) {
      setPendingAction(null);
      // Another tab may have launched a changed program in between.
      if (err instanceof LaunchRecordConflict) {
        setOpen(false);
        setLaunchConfirm({ hasLaunchRecord: err.hasLaunchRecord });
        return;
      }
      const message = err instanceof Error ? err.message : "Failed to run program.";
      if (fromMenu) {
        setActionError(message);
      } else {
        setCommandOutput({ title: "Run program", output: message });
      }
      return;
    }

    setPendingAction(null);
    setOpen(false);

    // The launch of a resident program, or one with Slurm, is waited for, so
    // a program that the engine refuses is reported at once, with what
    // debasher_exec printed.
    if (result.exitCode !== null && result.exitCode !== 0) {
      setCommandOutput({
        title: "Run program: the launch failed",
        message: `debasher_exec ended with exit code ${result.exitCode}. What it printed:`,
        output: result.output ?? "",
      });
    }

  }

  async function runOutputAction(
    item: MenuItem,
    title: string,
    action: (program: Program) => Promise<string>
  ) {

    setPendingAction(item);
    setActionError(null);

    try {
      const output = await action(program);
      setCommandOutput({ title, output });
      setOpen(false);
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : `Failed to ${item.toLowerCase()}.`
      );
    } finally {
      setPendingAction(null);
    }

  }

  // The orderly stop of a resident program lasts until the program has
  // stopped, up to about the timeout of the tool: the menu closes, the run
  // phase shows the program as stopping, and the outcome comes in a modal.
  async function handleStop() {

    setOpen(false);

    try {
      const result = await stopRun();
      setCommandOutput({
        title: "Stop program",
        message: isResident
          ? orderlyStopOutcome(result.exitCode)
          : result.exitCode === 0
          ? "The run was stopped."
          : `debasher_stop ended with exit code ${result.exitCode}. What it printed:`,
        output: result.output,
      });
    } catch (err) {
      setCommandOutput({
        title: "Stop program",
        output: err instanceof Error ? err.message : "Failed to stop program.",
      });
    }

  }

  async function handleTakeSnapshot() {

    setPendingAction("Take snapshot");
    setActionError(null);

    try {
      const result = await takeSnapshot(program);
      setCommandOutput({
        title: "Take snapshot",
        message: snapshotOutcome(result.exitCode, result.epoch, result.pendingNodes),
        output: result.output,
      });
      setOpen(false);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to take a snapshot.");
    } finally {
      setPendingAction(null);
    }

  }

  function handleResumeChanged() {
    setLaunchConfirm(null);
    launch(true, false);
  }

  // Starting afresh resets the program state first, set aside as "Reset
  // program state" does by default, and then launches.
  async function handleStartAfresh() {

    setLaunchConfirm(null);

    try {
      const reset = await resetProgramState(false);
      if (reset.exitCode !== 0) {
        setCommandOutput({
          title: "Run program",
          message: `The program state could not be reset: debasher_reset_resident ended with exit code ${reset.exitCode}. What it printed:`,
          output: reset.output,
        });
        return;
      }
    } catch (err) {
      setCommandOutput({
        title: "Run program",
        output: err instanceof Error ? err.message : "Failed to reset the program state.",
      });
      return;
    }

    await launch(false, false);

  }

  async function handleConfirmResetState() {

    setResetStateConfirmOpen(false);

    try {
      const result = await resetProgramState(deleteState);
      setCommandOutput({
        title: "Reset program state",
        message: result.exitCode === 0
          ? "The next launch starts every node afresh."
          : `debasher_reset_resident ended with exit code ${result.exitCode}. What it printed:`,
        output: result.output,
      });
    } catch (err) {
      setCommandOutput({
        title: "Reset program state",
        output: err instanceof Error ? err.message : "Failed to reset the program state.",
      });
    }

  }

  async function handleConfirmKill() {

    setKillConfirmOpen(false);

    try {
      const result = await killResidentProgram();
      setCommandOutput({
        title: "Kill program",
        message: result.exitCode === 0
          ? `The program was killed. ${HARD_KILL_CONSEQUENCES}`
          : `debasher_stop ended with exit code ${result.exitCode}. What it printed:`,
        output: result.output,
      });
    } catch (err) {
      setCommandOutput({
        title: "Kill program",
        output: err instanceof Error ? err.message : "Failed to kill program.",
      });
    }

  }

  async function handleConfirmReset() {

    setResetPending(true);
    setResetError(null);

    try {
      const cleared = await resetOutputDir();
      setResetConfirmOpen(false);
      setCommandOutput({
        title: "Reset output directory",
        output: cleared
          ? `Cleared ${program.outputDir}.`
          : "Nothing was reset: the output directory doesn't exist, or is a protected path.",
      });
    } catch (err) {
      setResetError(
        err instanceof Error ? err.message : "Failed to reset output directory."
      );
    } finally {
      setResetPending(false);
    }

  }

  function handleItemClick(item: MenuItem) {

    if (REQUIRES_OUTPUT_DIR.has(item) && !program.outputDir.trim()) {
      setActionError("Set the output directory before running this action.");
      return;
    }

    if (REQUIRES_HOME_DIR.has(item) && !program.homeDir.trim()) {
      setActionError("Save the program before running this action.");
      return;
    }

    if (item === "Set output directory") {
      setOpen(false);
      setOutputDirOpen(true);
    } else if (item === "Set execution options") {
      setOpen(false);
      setExecutionOptionsOpen(true);
    } else if (item === "Set program options") {
      setOpen(false);
      setProgramOptionsOpen(true);
    } else if (item === "Check program options") {
      runOutputAction(item, "Check program options", checkProgramOptions);
    } else if (item === "Validate program") {
      runOutputAction(item, "Validate program", validateProgram);
    } else if (item === "Run program") {
      handleRunProgram();
    } else if (item === "Get program status") {
      runOutputAction(item, "Program status", getProgramStatus);
    } else if (item === "Stop program") {
      handleStop();
    } else if (item === "Reset program state") {
      setOpen(false);
      setDeleteState(false);
      setResetStateConfirmOpen(true);
    } else if (item === "Take snapshot") {
      handleTakeSnapshot();
    } else if (item === "Kill program") {
      setOpen(false);
      setKillConfirmOpen(true);
    } else if (item === "Reset output directory") {
      setOpen(false);
      setResetError(null);
      setResetConfirmOpen(true);
    } else if (item === "Talk to FIFOs") {
      setOpen(false);
      setTalkToFifosOpen(true);
    } else {
      setOpen(false);
    }

  }

  useEffect(() => {

    if (!isOpen) {
      return;
    }

    function handleClickOutside(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside, true);

    return () =>
      document.removeEventListener("mousedown", handleClickOutside, true);

  }, [isOpen]);

  return (

    <div
      ref={containerRef}
      style={{
        position: "relative",
      }}
    >

      <button
        onClick={() => {
          setActionError(null);
          setOpen(open => !open);
        }}
      >
        Run
      </button>

      {isOpen && (

        <div
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            marginTop: 4,
            background: "#fff",
            border: "1px solid #ccc",
            borderRadius: 4,
            boxShadow: "0 2px 8px rgba(0, 0, 0, 0.15)",
            display: "flex",
            flexDirection: "column",
            minWidth: 200,
            zIndex: 1000,
          }}
        >

          {MENU_ITEMS.filter(item => isResident ? !GENERAL_ONLY.has(item) : !RESIDENT_ONLY.has(item)).map(item => (

            <button

              key={item}

              onClick={() => handleItemClick(item)}

              disabled={
                pendingAction !== null ||
                // A run in progress is read from the process statuses,
                // whoever launched it.
                (item === "Run program" && isRunInProgress) ||
                // Nothing else acts on the program while this tab
                // launches, stops or kills it.
                (ACTS_ON_PROGRAM.has(item) && isRequestPending) ||
                // Stopping a resident program, or starting a round in it,
                // with no node alive would find no reader for its triggers.
                (LIVE_ONLY.has(item) && isResident && residentPhase !== "live") ||
                // A program that is new has nothing to reset.
                (item === "Reset program state" && residentPhase !== "stopped") ||
                // Wiping the output directory out from under a run
                // (or repointing which directory this UI watches/
                // controls) would delete files it's using or make it
                // unstoppable — checked via isRunInProgress (not
                // runPhase) so a run launched outside this tab is
                // caught too.
                (item === "Set output directory" && isRunInProgress) ||
                (item === "Reset output directory" && isRunInProgress) ||
                // A fifo only exists on disk once its owning process
                // has started.
                (item === "Talk to FIFOs" && !isRunInProgress) ||
                // A line written raw into a port of a resident program
                // would bring its node down: the nodes read envelopes.
                (item === "Talk to FIFOs" && isResident)
              }

              style={{
                textAlign: "left",
                padding: "8px 12px",
                border: "none",
                background: "none",
                cursor: "pointer",
              }}

            >
              {pendingAction === item
                ? PENDING_LABELS[item]
                : item}
            </button>

          ))}

          {actionError && (
            <div
              style={{
                padding: "0 12px 8px",
                color: "#b00020",
                fontSize: 13,
              }}
            >
              {actionError}
            </div>
          )}

        </div>

      )}

      {isOutputDirOpen && (
        <OutputDirEditor
          onClose={() => setOutputDirOpen(false)}
        />
      )}

      {isResetConfirmOpen && (
        <ResetOutputDirConfirm
          outputDir={program.outputDir}
          isPending={isResetPending}
          error={resetError}
          onConfirm={handleConfirmReset}
          onCancel={() => setResetConfirmOpen(false)}
        />
      )}

      {isExecutionOptionsOpen && (
        <ExecutionOptionsEditor
          onClose={() => setExecutionOptionsOpen(false)}
        />
      )}

      {isProgramOptionsOpen && (
        <ProgramOptionsEditor
          onClose={() => setProgramOptionsOpen(false)}
        />
      )}

      {isKillConfirmOpen && (
        <ConfirmDialog
          title="Kill program?"
          confirmLabel="Kill"
          onConfirm={handleConfirmKill}
          onCancel={() => setKillConfirmOpen(false)}
        >
          <p style={{ margin: 0 }}>
            debasher_stop kills every process of the program at once, with
            no orderly stop: use it for a program known to be stuck, whose
            orderly stop would only reach the hard kill after its timeout.
          </p>
          <p style={{ margin: 0 }}>
            {HARD_KILL_CONSEQUENCES}
          </p>
        </ConfirmDialog>
      )}

      {launchConfirm && (
        <LaunchRecordDialog
          hasLaunchRecord={launchConfirm.hasLaunchRecord}
          onResume={handleResumeChanged}
          onStartAfresh={handleStartAfresh}
          onCancel={() => setLaunchConfirm(null)}
        />
      )}

      {isResetStateConfirmOpen && (
        <ConfirmDialog
          title="Reset program state?"
          confirmLabel="Reset"
          onConfirm={handleConfirmResetState}
          onCancel={() => setResetStateConfirmOpen(false)}
        >
          <p style={{ margin: 0 }}>
            The state of every node is taken away: its checkpoints, its input
            log, its halted marker and what its process left in its output
            directory. The next launch starts every node afresh.
          </p>
          <p style={{ margin: 0 }}>
            It is set aside under __reset__/&lt;timestamp&gt;/ in the output
            directory, since a checkpoint that is lost cannot be made again.
          </p>
          <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input
              type="checkbox"
              checked={deleteState}
              onChange={(event) => setDeleteState(event.target.checked)}
            />
            Delete it instead of setting it aside
          </label>
        </ConfirmDialog>
      )}

      {commandOutput !== null && (
        <CommandOutputModal
          title={commandOutput.title}
          message={commandOutput.message}
          output={commandOutput.output}
          onClose={() => setCommandOutput(null)}
        />
      )}

      {isTalkToFifosOpen && (
        <TalkToFifosDialog
          onClose={() => setTalkToFifosOpen(false)}
        />
      )}

    </div>

  );

}
