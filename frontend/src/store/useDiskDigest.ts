import { useState } from "react";
import type { RefObject } from "react";

import type { Program } from "../models/program";
import { hasUnsavedChanges, onDiskDigest } from "../models/externalChanges";
import { getProgramDigest } from "../storage/programStorage";
import { usePolling } from "../utils/usePolling";

export const DISK_DIGEST_POLL_INTERVAL_MS = 3000;

// The requests of the tab that write the program: how many are in
// flight, and how many have been answered. A digest read while one was in
// flight, or before one was answered, may be the tab's own, not yet taken.
export interface ProgramWrites {
  inFlight: number;
  answered: number;
}

interface Options {
  homeDir: string;
  // The latest program, and the program as it was last loaded or saved,
  // both ahead of the render: whether the program holds unsaved changes is
  // decided from them when a digest is read, never from a render before.
  programRef: RefObject<Program>;
  savedProgramRef: RefObject<Program>;
  writesRef: RefObject<ProgramWrites>;
  // Replaces the program of the tab with the one saved in its home
  // directory.
  reloadFromDisk: () => Promise<void>;
}

/**
 * Follows the digest of the artifact in the home directory, which
 * another tab or an agent through the MCP server may save: polled while the
 * page is visible, every DISK_DIGEST_POLL_INTERVAL_MS. A tab with nothing
 * unsaved loads the program again on its own; a tab with unsaved changes gets
 * `externalDigest`, the digest on disk, for the user to choose between
 * loading it and saving the tab over it. `askAbout` raises the same question
 * when a write of the tab finds the digest first, refused for it.
 */
export function useDiskDigest({ homeDir, programRef, savedProgramRef, writesRef, reloadFromDisk }: Options) {

  const [externalDigest, setExternalDigest] =
    useState<string | null>(null);

  usePolling(async isCancelled => {
    const writes = writesRef.current;
    if (writes.inFlight > 0) {
      return;
    }
    const answered = writes.answered;
    const diskDigest = await getProgramDigest(homeDir);
    if (isCancelled() || writes.inFlight > 0 || writes.answered !== answered) {
      return;
    }
    const action = onDiskDigest({
      tabDigest: programRef.current.digest ?? "",
      diskDigest,
      unsavedChanges: hasUnsavedChanges(programRef.current, savedProgramRef.current),
    });
    if (action === "clear") {
      setExternalDigest(null);
    } else if (action === "ask") {
      setExternalDigest(diskDigest);
    } else if (action === "reload") {
      await reloadFromDisk();
      setExternalDigest(null);
    }
  }, { intervalMs: DISK_DIGEST_POLL_INTERVAL_MS, enabled: Boolean(homeDir), resetKey: homeDir });

  return { externalDigest, askAbout: setExternalDigest };

}
