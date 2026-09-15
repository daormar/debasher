import { useEffect, useMemo, useRef, useState } from "react";
import type { DragEvent } from "react";
import CodeMirror from "@uiw/react-codemirror";

import { useProgram } from "../store/ProgramContext";
import { languageExtension } from "./codeLanguages";
import type { ProcessLanguage } from "../models/process";
import {
  createFolder,
  deleteEntry,
  getFileContent,
  getFileTree,
  moveEntry,
  uploadFiles,
  writeFileContent,
} from "../api/programFilesApi";
import type { FileEntry } from "../api/programFilesApi";

// Guesses a CodeMirror language from a previewed file's extension —
// distinct from ProgramProcess.language, which is explicit metadata a
// process always carries; a plain file in the program's home
// directory has no such field, so this is the closest equivalent.
// Anything unrecognized falls back to a plain-text <pre> preview.
const LANGUAGE_BY_EXTENSION: Record<string, ProcessLanguage> = {
  sh: "bash",
  bash: "bash",
  py: "python",
  pl: "perl",
  pm: "perl",
  r: "r",
  groovy: "groovy",
  gvy: "groovy",
};

// Stable reference, not an inline object literal in the JSX below — a
// new object every render makes @uiw/react-codemirror treat basicSetup
// as changed and reconfigure the editor (see previewExtensions).
const CODE_PREVIEW_BASIC_SETUP = { lineNumbers: false, foldGutter: false };

function languageForPath(path: string): ProcessLanguage | null {
  const dot = path.lastIndexOf(".");
  if (dot === -1) {
    return null;
  }
  return LANGUAGE_BY_EXTENSION[path.slice(dot + 1).toLowerCase()] ?? null;
}

function parentOf(path: string): string {
  const slash = path.lastIndexOf("/");
  return slash === -1 ? "" : path.slice(0, slash);
}

function nameOf(path: string): string {
  const slash = path.lastIndexOf("/");
  return slash === -1 ? path : path.slice(slash + 1);
}

function findEntry(entries: FileEntry[], path: string): FileEntry | null {
  for (const entry of entries) {
    if (entry.path === path) {
      return entry;
    }
    if (entry.children) {
      const found = findEntry(entry.children, path);
      if (found) {
        return found;
      }
    }
  }
  return null;
}

interface NodeProps {
  entry: FileEntry;
  depth: number;
  expanded: Set<string>;
  selectedPath: string | null;
  onToggle: (path: string) => void;
  onSelect: (entry: FileEntry) => void;
}

function FileTreeNode({ entry, depth, expanded, selectedPath, onToggle, onSelect }: NodeProps) {

  const isExpanded = expanded.has(entry.path);
  const isSelected = entry.path === selectedPath;

  return (

    <div>

      <div

        onClick={() => {
          if (entry.type === "dir") {
            onToggle(entry.path);
          }
          onSelect(entry);
        }}

        style={{
          display: "flex",
          alignItems: "center",
          gap: 4,
          paddingLeft: depth * 16,
          paddingTop: 2,
          paddingBottom: 2,
          cursor: "pointer",
          background: isSelected ? "#e0edff" : "transparent",
          fontFamily: "ui-monospace, Consolas, monospace",
          fontSize: 13,
        }}

      >

        <span style={{ width: 12, display: "inline-block", color: "#888" }}>
          {entry.type === "dir" ? (isExpanded ? "▾" : "▸") : ""}
        </span>

        <span>
          {entry.name}
          {entry.type === "dir" ? "/" : ""}
        </span>

        {entry.readonly && (
          <span style={{ color: "#888", fontSize: 11 }}>
            (read-only)
          </span>
        )}

      </div>

      {entry.type === "dir" && isExpanded && entry.children && (
        <div>
          {entry.children.map(child => (
            <FileTreeNode
              key={child.path}
              entry={child}
              depth={depth + 1}
              expanded={expanded}
              selectedPath={selectedPath}
              onToggle={onToggle}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}

    </div>

  );

}

export default function ProgramFilesPanel() {

  const { program } = useProgram();

  // Docked top-left on the canvas like the minimap — starts minimized to
  // a small chip and expands into the full browser on click.
  const [isOpen, setOpen] =
    useState(false);

  const [tree, setTree] =
    useState<FileEntry[]>([]);

  const [loading, setLoading] =
    useState(true);

  const [error, setError] =
    useState<string | null>(null);

  const [expanded, setExpanded] =
    useState<Set<string>>(new Set());

  const [selectedPath, setSelectedPath] =
    useState<string | null>(null);

  const [preview, setPreview] =
    useState<{ path: string; kind: "file" | "binary" | "missing"; content?: string } | null>(null);

  const [previewLoading, setPreviewLoading] =
    useState(false);

  // The editable buffer for whichever file is previewed — starts in
  // sync with preview.content on load, diverges as the user types.
  // null whenever there's nothing file-shaped to edit (a dir, binary,
  // missing, or nothing selected yet).
  const [draft, setDraft] =
    useState<string | null>(null);

  const [savingContent, setSavingContent] =
    useState(false);

  const [isDragOver, setDragOver] =
    useState(false);

  const fileInputRef =
    useRef<HTMLInputElement>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const entries = await getFileTree(program.homeDir, program.name);
      setTree(entries);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to list program files.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (isOpen) {
      refresh();
    }
    // Re-fetch fresh each time it's expanded, not on every keystroke
    // elsewhere in the app.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  const selectedEntry =
    selectedPath ? findEntry(tree, selectedPath) : null;

  const previewLanguage =
    preview && preview.kind === "file" ? languageForPath(preview.path) : null;

  // Stable across every keystroke (draft changing re-renders this
  // component): without this, `[languageExtension(previewLanguage)]`
  // would be a brand-new array — and languageExtension() a brand-new
  // Extension instance — every render, and CodeMirror reconfigures
  // its whole state (dropping syntax highlighting for a frame, then
  // reapplying it) whenever `extensions` changes identity, even when
  // the language itself hasn't. Only reruns when the language
  // actually changes.
  const previewExtensions = useMemo(
    () => (previewLanguage ? [languageExtension(previewLanguage)] : []),
    [previewLanguage]
  );

  const canEditPreview =
    !!selectedEntry && !selectedEntry.readonly && preview?.kind === "file";

  const isDirty =
    canEditPreview && draft !== null && draft !== preview?.content;

  // Where "Upload files" / "New folder" write to: the selected
  // directory, the selected file's parent, or the root when nothing
  // is selected.
  const targetDir =
    selectedEntry?.type === "dir"
      ? selectedEntry.path
      : selectedPath
        ? parentOf(selectedPath)
        : "";

  function toggle(path: string) {
    setExpanded(current => {
      const next = new Set(current);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  }

  async function handleSelect(entry: FileEntry) {

    if (isDirty && !window.confirm("Discard unsaved changes to this file?")) {
      return;
    }

    setSelectedPath(entry.path);

    if (entry.type === "dir") {
      setPreview(null);
      setDraft(null);
      return;
    }

    setPreviewLoading(true);
    try {
      const result = await getFileContent(program.homeDir, entry.path);
      setPreview({ path: entry.path, ...result });
      setDraft(result.kind === "file" ? (result.content ?? "") : null);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to read ${entry.path}.`);
    } finally {
      setPreviewLoading(false);
    }

  }

  async function handleSaveContent() {
    if (!selectedEntry || !canEditPreview || draft === null) {
      return;
    }
    setSavingContent(true);
    setError(null);
    try {
      const entries = await writeFileContent(program.homeDir, program.name, selectedEntry.path, draft);
      setTree(entries);
      setPreview(current => (current ? { ...current, content: draft } : current));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save.");
    } finally {
      setSavingContent(false);
    }
  }

  async function handleUpload(files: File[]) {
    if (files.length === 0) {
      return;
    }
    setError(null);
    try {
      const entries = await uploadFiles(program.homeDir, program.name, targetDir, files);
      setTree(entries);
      if (targetDir) {
        setExpanded(current => new Set(current).add(targetDir));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload file(s).");
    }
  }

  async function handleNewFolder() {
    const name = window.prompt("New folder name:");
    if (!name || !name.trim()) {
      return;
    }
    const path = targetDir ? `${targetDir}/${name.trim()}` : name.trim();
    setError(null);
    try {
      const entries = await createFolder(program.homeDir, program.name, path);
      setTree(entries);
      if (targetDir) {
        setExpanded(current => new Set(current).add(targetDir));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create folder.");
    }
  }

  async function handleDelete() {
    if (!selectedEntry || selectedEntry.readonly) {
      return;
    }
    if (!window.confirm(`Delete "${selectedEntry.path}"? This cannot be undone.`)) {
      return;
    }
    setError(null);
    try {
      const entries = await deleteEntry(program.homeDir, program.name, selectedEntry.path);
      setTree(entries);
      setSelectedPath(null);
      setPreview(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete.");
    }
  }

  async function handleRename() {
    if (!selectedEntry || selectedEntry.readonly) {
      return;
    }
    const currentName = nameOf(selectedEntry.path);
    const newName = window.prompt("Rename to:", currentName);
    if (!newName || !newName.trim() || newName.trim() === currentName) {
      return;
    }
    const parent = parentOf(selectedEntry.path);
    const dstPath = parent ? `${parent}/${newName.trim()}` : newName.trim();
    setError(null);
    try {
      const entries = await moveEntry(program.homeDir, program.name, selectedEntry.path, dstPath);
      setTree(entries);
      setSelectedPath(dstPath);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to rename.");
    }
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragOver(false);
    handleUpload(Array.from(event.dataTransfer.files));
  }

  if (!isOpen) {
    return (
      <div
        onClick={() => setOpen(true)}
        style={{
          background: "#fff",
          border: "1px solid #ccc",
          borderRadius: 4,
          padding: "6px 10px",
          fontSize: 13,
          cursor: "pointer",
          boxShadow: "0 1px 4px rgba(0, 0, 0, 0.2)",
        }}
      >
        Program files
      </div>
    );
  }

  return (

    <div
      style={{
        width: 1000,
        maxWidth: "90vw",
        // A definite height, not just maxHeight: a flex column with no
        // explicit height shrinks to fit its content instead of giving
        // its flex:1 children (the tree/preview row, and CodeMirror's
        // height="100%" further down) any space to grow into — nothing
        // below this would ever get taller than its own natural size.
        height: "70vh",
        background: "#fff",
        border: "1px solid #ccc",
        borderRadius: 4,
        boxShadow: "0 2px 12px rgba(0, 0, 0, 0.25)",
        padding: 16,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        // Without this, content taller than maxHeight grows the card
        // itself instead of being clipped — pushing each pane's own
        // scrollbar past the viewport instead of keeping it pinned to
        // that pane's own (always-visible) bottom edge.
        overflow: "hidden",
      }}
    >

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>

        <h3 style={{ margin: 0 }}>
          Program files: {program.homeDir || "(not saved yet)"}
        </h3>

        <button onClick={() => setOpen(false)}>
          Minimize
        </button>

      </div>

      {!program.homeDir.trim() ? (

          <div style={{ color: "#8a6d00", fontSize: 14 }}>
            Save the program before managing its files. This browses the
            directory it's saved into.
          </div>

        ) : (

          <>

            <div style={{ display: "flex", gap: 8 }}>

              <input
                ref={fileInputRef}
                type="file"
                multiple
                style={{ display: "none" }}
                onChange={(event) => {
                  handleUpload(Array.from(event.target.files ?? []));
                  event.target.value = "";
                }}
              />

              <button onClick={() => fileInputRef.current?.click()}>
                Upload files
              </button>

              <button onClick={handleNewFolder}>
                New folder
              </button>

              <button
                onClick={handleRename}
                disabled={!selectedEntry || selectedEntry.readonly}
              >
                Rename
              </button>

              <button
                onClick={handleDelete}
                disabled={!selectedEntry || selectedEntry.readonly}
              >
                Delete
              </button>

              <button
                onClick={handleSaveContent}
                disabled={!canEditPreview || !isDirty || savingContent}
              >
                {savingContent ? "Saving..." : "Save"}
              </button>

              <span style={{ alignSelf: "center", fontSize: 12, color: "#888" }}>
                Uploads and new folders go into: {targetDir || "(root)"}
              </span>

            </div>

            {error && (
              <div style={{ color: "#b00020", fontSize: 14 }}>
                {error}
              </div>
            )}

            <div style={{ display: "flex", gap: 8, flex: 1, minHeight: 0 }}>

              <div

                onDragOver={(event) => {
                  event.preventDefault();
                  setDragOver(true);
                }}

                onDragLeave={() => setDragOver(false)}

                onDrop={handleDrop}

                style={{
                  flex: "0 0 260px",
                  border: isDragOver ? "2px dashed #4a90d9" : "1px solid #ccc",
                  overflow: "auto",
                  padding: 4,
                }}

              >

                {loading ? (
                  <div style={{ padding: 8, color: "#888" }}>Loading…</div>
                ) : tree.length === 0 ? (
                  <div style={{ padding: 8, color: "#888" }}>
                    No files yet. Upload one, or drop it here.
                  </div>
                ) : (
                  tree.map(entry => (
                    <FileTreeNode
                      key={entry.path}
                      entry={entry}
                      depth={0}
                      expanded={expanded}
                      selectedPath={selectedPath}
                      onToggle={toggle}
                      onSelect={handleSelect}
                    />
                  ))
                )}

              </div>

              <div
                style={{
                  flex: 1,
                  border: "1px solid #ccc",
                  // "hidden" here, not "auto": CodeMirror manages its
                  // own internal scrolling (.cm-scroller, both axes).
                  // If this wrapper also scrolled, its content would
                  // be free to grow unbounded instead of being clipped
                  // to the pane's actual size, pushing its scrollbar
                  // out of view until scrolled all the way down.
                  overflow: "hidden",
                  display: "flex",
                  flexDirection: "column",
                }}
              >

                {previewLoading ? (
                  <div style={{ padding: 8, color: "#888" }}>Loading…</div>
                ) : !preview ? (
                  <div style={{ padding: 8, color: "#888" }}>Select a file to preview.</div>
                ) : preview.kind === "binary" ? (
                  <div style={{ padding: 8, color: "#888" }}>Binary file, no preview available.</div>
                ) : preview.kind === "missing" ? (
                  <div style={{ padding: 8, color: "#888" }}>File not found.</div>
                ) : previewLanguage ? (
                  // @uiw/react-codemirror renders its own wrapper div
                  // around .cm-editor with no height of its own, so a
                  // plain height:100% on the editor has nothing to
                  // resolve against and collapses to a few px. `display:
                  // "flex"` here (row, default align-items: stretch)
                  // stretches that wrapper to this div's full height
                  // with no flex-grow needed on the wrapper itself —
                  // *then* height="100%" below has something real to
                  // fill, and CodeMirror's own .cm-scroller takes over
                  // scrolling in both directions from there.
                  <div style={{ flex: 1, minHeight: 0, display: "flex" }}>
                    <CodeMirror
                      value={draft ?? ""}
                      height="100%"
                      style={{ flex: 1, minWidth: 0 }}
                      extensions={previewExtensions}
                      editable={canEditPreview}
                      onChange={value => setDraft(value)}
                      // No line-number/fold gutter here: it isn't used
                      // anywhere else CodeMirror shows up in this app
                      // (CodeEditor.tsx doesn't have one either), and
                      // it otherwise shifts this preview's text right
                      // compared to every other file's plain <pre>/
                      // <textarea> preview below, reading as a stray
                      // indent. Hoisted to a module-level constant, not
                      // an inline object literal, for the same reason
                      // previewExtensions is memoized above — a new
                      // object every render makes CodeMirror reconfigure
                      // (and briefly drop highlighting) on every keystroke.
                      basicSetup={CODE_PREVIEW_BASIC_SETUP}
                    />
                  </div>
                ) : canEditPreview ? (
                  <textarea
                    value={draft ?? ""}
                    onChange={event => setDraft(event.target.value)}
                    spellCheck={false}
                    wrap="off"
                    style={{
                      flex: 1,
                      minHeight: 0,
                      margin: 0,
                      padding: 8,
                      border: "none",
                      resize: "none",
                      overflow: "auto",
                      fontFamily: "ui-monospace, Consolas, monospace",
                      fontSize: 13,
                      whiteSpace: "pre",
                    }}
                  />
                ) : (
                  <pre
                    style={{
                      flex: 1,
                      minHeight: 0,
                      margin: 0,
                      padding: 8,
                      overflow: "auto",
                      fontFamily: "ui-monospace, Consolas, monospace",
                      fontSize: 13,
                      whiteSpace: "pre",
                    }}
                  >
                    {draft ?? ""}
                  </pre>
                )}

              </div>

            </div>

          </>

        )}

    </div>

  );

}
