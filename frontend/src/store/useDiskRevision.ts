import { useState } from "react";
import type { RefObject } from "react";

import type { Program } from "../models/program";
import { hasUnsavedChanges, onDiskRevision } from "../models/externalChanges";
import { getProgramRevision } from "../storage/programStorage";
import { usePolling } from "../utils/usePolling";

export const DISK_REVISION_POLL_INTERVAL_MS = 3000;

// The requests of the tab that write the program metadata: how many are in
// flight, and how many have been answered. A revision read while one was in
// flight, or before one was answered, may be the tab's own, not yet taken.
export interface ProgramWrites {
  inFlight: number;
  answered: number;
}

interface Options {
  homeDir: string;
  // The latest program, and the program as it was last loaded or saved,
  // both ahead of the render: whether the program holds unsaved changes is
  // decided from them when a revision is read, never from a render before.
  programRef: RefObject<Program>;
  savedProgramRef: RefObject<Program>;
  writesRef: RefObject<ProgramWrites>;
  // Replaces the program of the tab with the one saved in its home
  // directory.
  reloadFromDisk: () => Promise<void>;
}

/**
 * Follows the revision of the program metadata in the home directory, which
 * another tab or an agent through the MCP server may save: polled while the
 * page is visible, every DISK_REVISION_POLL_INTERVAL_MS. A tab with nothing
 * unsaved loads the program again on its own; a tab with unsaved changes gets
 * `externalRevision`, the revision on disk, for the user to choose between
 * loading it and saving the tab over it. `askAbout` raises the same question
 * when a write of the tab finds the revision first, refused for it.
 */
export function useDiskRevision({ homeDir, programRef, savedProgramRef, writesRef, reloadFromDisk }: Options) {

  const [externalRevision, setExternalRevision] =
    useState<number | null>(null);

  usePolling(async isCancelled => {
    const writes = writesRef.current;
    if (writes.inFlight > 0) {
      return;
    }
    const answered = writes.answered;
    const diskRevision = await getProgramRevision(homeDir);
    if (isCancelled() || writes.inFlight > 0 || writes.answered !== answered) {
      return;
    }
    const action = onDiskRevision({
      tabRevision: programRef.current.revision ?? 0,
      diskRevision,
      unsavedChanges: hasUnsavedChanges(programRef.current, savedProgramRef.current),
    });
    if (action === "clear") {
      setExternalRevision(null);
    } else if (action === "ask") {
      setExternalRevision(diskRevision);
    } else if (action === "reload") {
      await reloadFromDisk();
      setExternalRevision(null);
    }
  }, { intervalMs: DISK_REVISION_POLL_INTERVAL_MS, enabled: Boolean(homeDir), resetKey: homeDir });

  return { externalRevision, askAbout: setExternalRevision };

}
