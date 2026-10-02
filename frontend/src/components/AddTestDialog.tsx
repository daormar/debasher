import { useEffect, useState } from "react";

import { getFileContent, writeFileContent } from "../api/programFilesApi";
import type { ProgramProcess } from "../models/process";
import type { Program } from "../models/program";
import {
  TEST_DIR,
  defaultTestFileName,
  testFileNameProblem,
  testFilePath,
  testSkeleton,
  testSkeletonSummary,
} from "../models/testSkeleton";

interface Props {
  program: Program;
  process: ProgramProcess;
  // Opens a test file in the program files panel, with a line to show
  // above it, if any.
  onOpen: (path: string, notice?: string) => void;
  onClose: () => void;
}

// "Add test": says which file it writes and what the skeleton is, lets the
// user change its name, and writes it only when asked; a file that exists
// is opened, never overwritten.
export default function AddTestDialog({ program, process, onOpen, onClose }: Props) {

  const [fileName, setFileName] =
    useState(() => defaultTestFileName(program, process));

  // The name of a file of the test directory that exists, which the dialog
  // offers to open instead of writing it
  const [existing, setExisting] =
    useState<string | null>(null);

  const [error, setError] =
    useState<string | null>(null);

  const [isPending, setPending] =
    useState(false);

  const problem = testFileNameProblem(program, fileName);

  // The proposed name may be that of a test written before
  useEffect(() => {
    const proposed = defaultTestFileName(program, process);
    getFileContent(program.homeDir, testFilePath(proposed))
      .then(file => {
        if (file.kind !== "missing") {
          setExisting(proposed);
        }
      })
      .catch(() => undefined);
  }, [program, process]);

  async function handleCreate() {
    if (problem) {
      return;
    }
    setPending(true);
    setError(null);
    const path = testFilePath(fileName);
    try {
      if ((await getFileContent(program.homeDir, path)).kind !== "missing") {
        setExisting(fileName);
        return;
      }
      await writeFileContent(program.homeDir, program.name, path, testSkeleton(program, process), true);
      onOpen(path, `Created ${path}: fill in its TODOs, then remove the line that makes each test fail.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add the test.");
    } finally {
      setPending(false);
    }
  }

  const exists = existing !== null && existing === fileName;

  return (

    <div
      role="dialog"
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
          width: "60%",
          maxWidth: 560,
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
          fontSize: 14,
        }}
      >

        <h3 style={{ margin: 0 }}>
          Add test for {process.name}
        </h3>

        <label style={{ display: "flex", alignItems: "center", gap: 4 }}>
          File:
          <span style={{ fontFamily: "monospace" }}>{TEST_DIR}/</span>
          <input
            type="text"
            value={fileName}
            onChange={event => {
              setFileName(event.target.value.trim());
              setError(null);
            }}
            style={{ flex: 1, fontFamily: "monospace", fontSize: 13 }}
          />
        </label>

        {problem && (
          <div style={{ color: "#b00020" }}>
            {problem}
          </div>
        )}

        {exists ? (
          <div>
            {testFilePath(fileName)} already exists: open it, or choose another name for a new test.
          </div>
        ) : (
          <div>
            {testSkeletonSummary(program, process)}
          </div>
        )}

        {error && (
          <div style={{ color: "#b00020" }}>
            {error}
          </div>
        )}

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>

          <button onClick={onClose} disabled={isPending}>
            Cancel
          </button>

          {exists ? (
            <button onClick={() => onOpen(testFilePath(fileName))}>
              Open
            </button>
          ) : (
            <button onClick={handleCreate} disabled={isPending || problem !== null}>
              {isPending ? "Creating..." : "Create"}
            </button>
          )}

        </div>

      </div>

    </div>

  );

}
