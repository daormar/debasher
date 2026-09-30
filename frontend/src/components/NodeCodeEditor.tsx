import { useEffect, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";

import { useProgram } from "../store/ProgramContext";
import { languageExtension } from "./codeLanguages";
import type { ProgramProcess } from "../models/process";
import type { NodeCode, NodeHookPart, NodeKind } from "../models/node";
import {
  NODE_HOOKS,
  emptyNodeCode,
  inheritedHookNote,
  inheritsHooks,
  isRequiredHook,
  nodeClassName,
} from "../models/node";
import { getInheritedHooks } from "../api/processApi";

// The height of the parts and the editor, the same for every part, and that
// of the inherited code of a hook, which scrolls within it.
const EDITOR_AREA_HEIGHT = "min(560px, 65vh)";
const INHERITED_CODE_HEIGHT = 150;

interface Props {
  process: ProgramProcess;
  onClose: () => void;
}

type Part = keyof NodeCode;

/**
 * The code of a node of a resident program, edited part by part: the node
 * preamble, the class body and one body for each hook. The lines that
 * script generation writes around them (the import of the node kind, the
 * class declaration, the signature of each hook) are shown read only: the
 * class is named after the process and derives from the node kind, so the
 * user never writes it. Every part is edited without the indentation that
 * script generation adds. A node whose class implements every hook (a
 * ProgramLauncher, a DirectoryWatcher) inherits them: next to each hook the
 * editor says so, and shows, read only, the code that it inherits, read from
 * the runtime library, which a body replaces.
 */
export default function NodeCodeEditor({ process, onClose }: Props) {

  const { setNodeCode } = useProgram();

  const kind: NodeKind = process.nodeKind ?? "FBPProcess";

  const className = nodeClassName(process.name);

  const [draft, setDraft] =
    useState<NodeCode>(() => ({ ...emptyNodeCode(), ...process.nodeCode }));

  const [part, setPart] =
    useState<Part>("classBody");

  // The code of the hooks that the node inherits from its class, and why it
  // could not be read, if it could not.
  const [inherited, setInherited] =
    useState<{ hooks: Partial<Record<NodeHookPart, string>>; error: string | null } | null>(null);

  useEffect(() => {
    if (!inheritsHooks(kind)) {
      return;
    }
    let current = true;
    getInheritedHooks(kind)
      .then(result => { if (current) setInherited(result); })
      .catch(err => {
        if (current) setInherited({ hooks: {}, error: err instanceof Error ? err.message : String(err) });
      });
    return () => { current = false; };
  }, [kind]);

  const parts: { part: Part; label: string; note?: string }[] = [
    { part: "preamble", label: "Node preamble" },
    { part: "classBody", label: "Class body" },
    ...NODE_HOOKS.map(({ part: hook, name }) => ({
      part: hook as Part,
      label: name,
      note: isRequiredHook(kind, hook)
        ? "required"
        : kind === "FBPProcess"
          ? "only to observe the outside world"
          : `overrides that of ${kind}`,
    })),
  ];

  const hook = NODE_HOOKS.find(h => h.part === part);

  const showsInherited = hook !== undefined && inheritsHooks(kind);

  const inheritedCode = hook ? inherited?.hooks[hook.part] : undefined;

  // What script generation writes before the part being edited, shown
  // above the editor so that the part reads in its place.
  const context =
    part === "preamble"
      ? `from debasher_runtime_lib import ${kind}`
      : hook
        ? `class ${className}(${kind}):\n    ${hook.signature}`
        : `class ${className}(${kind}):`;

  function handleSave() {
    setNodeCode(process.id, draft);
    onClose();
  }

  return (

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
          width: "80%",
          maxWidth: 1100,
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >

        <h3 style={{ margin: 0 }}>
          Node code: {process.name} ({kind})
        </h3>

        {/* One height for every part, so that switching parts never resizes
            the window: the editor takes what the other blocks leave, and
            each block scrolls within it. */}
        <div style={{ display: "flex", gap: 12, height: EDITOR_AREA_HEIGHT }}>

          <nav
            style={{
              width: 220,
              display: "flex",
              flexDirection: "column",
              gap: 4,
              overflowY: "auto",
            }}
          >

            {parts.map(({ part: p, label, note }) => (
              <button
                key={p}
                onClick={() => setPart(p)}
                style={{
                  textAlign: "left",
                  fontWeight: p === part ? "bold" : undefined,
                  background: p === part ? "#e8eefc" : undefined,
                }}
              >
                {label}
                {draft[p].trim() ? " •" : ""}
                {note && (
                  <span style={{ display: "block", color: "#666", fontSize: 11, fontWeight: "normal" }}>
                    {note}
                  </span>
                )}
              </button>
            ))}

          </nav>

          <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 4 }}>

            {/* Above the declaration, which reads on with the body below it. */}
            {showsInherited && (
              <div data-testid="inherited-note" style={{ color: "#555", fontSize: 12 }}>
                {inheritedHookNote(kind, hook.name, hook.signature, draft[part].trim() !== "")}
              </div>
            )}

            <pre
              style={{
                margin: 0,
                padding: "6px 8px",
                background: "#f4f4f4",
                color: "#666",
                border: "1px solid #ddd",
                fontSize: 13,
              }}
            >
              {context}
            </pre>

            <div style={{ flex: 1, minHeight: 0, border: "1px solid #ccc" }}>

              <CodeMirror

                key={part}

                value={draft[part]}

                height="100%"

                style={{ height: "100%" }}

                extensions={[
                  languageExtension("python"),
                ]}

                onChange={value => setDraft(current => ({ ...current, [part]: value }))}

              />

            </div>

            <div style={{ color: "#666", fontSize: 12 }}>
              {part === "classBody"
                ? "Class attributes, the constructor, which gives the node state its " +
                  "first value, and helper methods. The ports of the node come from " +
                  "its options: the class never declares them."
                : part === "preamble"
                  ? "Imports, helper functions and constants, before the class."
                  : "The body of the hook, without its signature. An empty body " +
                    "leaves the hook out."}
            </div>

            {showsInherited && (
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <div style={{ color: "#666", fontSize: 12 }}>
                  Inherited from {kind}, read only:
                </div>
                <pre
                  data-testid="inherited-code"
                  style={{
                    margin: 0,
                    padding: "6px 8px",
                    height: INHERITED_CODE_HEIGHT,
                    boxSizing: "border-box",
                    overflow: "auto",
                    background: "#f7f7f7",
                    color: "#888",
                    border: "1px dashed #ccc",
                    fontSize: 12,
                  }}
                >
                  {inherited === null
                    ? "Reading..."
                    : inherited.error
                      ? `The inherited code could not be read: ${inherited.error}`
                      : inheritedCode ?? `${kind} does not define ${hook.name}.`}
                </pre>
              </div>
            )}

          </div>

        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
          }}
        >

          <button onClick={onClose}>
            Cancel
          </button>

          <button onClick={handleSave}>
            Save
          </button>

        </div>

      </div>

    </div>

  );

}
