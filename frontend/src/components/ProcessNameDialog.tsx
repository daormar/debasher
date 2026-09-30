import { useEffect, useId, useState } from "react";

import {
  getNodeInfo,
  getProcessInfo,
  suggestNodes,
  suggestProcessNames,
  validateProcessName,
} from "../api/processApi";
import type { ProcessInfo } from "../models/process";
import type { ProgramType } from "../models/program";
import type { NodeInfo, NodeKind, SuggestedNode } from "../models/node";
import { NODE_KINDS, nodeNameProblem } from "../models/node";

interface Props {
  title: string;
  confirmLabel: string;
  initialName?: string;
  existingNames: string[];
  preamble: string;
  envVars: Record<string, string>;
  // In a resident program the dialog refuses a name whose class would hide
  // a class of the runtime library or a Python builtin.
  programType?: ProgramType;
  // When adding a process to a resident program: the node kind is chosen
  // here, once, and the dialog suggests the nodes that the modules of the
  // preamble define, which bring their node kind, code and options with
  // them (NodeInfo), read by the rules of import. `supervisorTaken` is
  // whether the program already has its one Supervisor.
  chooseNodeKind?: boolean;
  supervisorTaken?: boolean;
  onConfirm: (
    name: string,
    info: ProcessInfo | null,
    nodeKind?: NodeKind,
    nodeInfo?: NodeInfo
  ) => void;
  onClose: () => void;
}

export default function ProcessNameDialog({
  title,
  confirmLabel,
  initialName = "",
  existingNames,
  preamble,
  envVars,
  programType = "general",
  chooseNodeKind = false,
  supervisorTaken = false,
  onConfirm,
  onClose,
}: Props) {

  const suggestionsListId = useId();

  const isResident = programType === "resident";

  const [nodeKind, setNodeKind] =
    useState<NodeKind>("FBPProcess");

  const [name, setName] =
    useState(initialName);

  const [suggestions, setSuggestions] =
    useState<string[]>([]);

  const [nodeSuggestions, setNodeSuggestions] =
    useState<SuggestedNode[]>([]);

  // The node kind of the suggested node that the name names, if any: it
  // comes with the node, and cannot be chosen.
  const suggestedKind =
    nodeSuggestions.find(node => node.name === name.trim())?.nodeKind;

  const effectiveKind = suggestedKind ?? nodeKind;

  const [isValidating, setValidating] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  useEffect(() => {

    let cancelled = false;

    if (isResident) {

      if (chooseNodeKind) {
        suggestNodes(preamble, envVars)
          .then(nodes => {
            if (!cancelled) {
              setNodeSuggestions(nodes);
              setSuggestions(nodes.map(node => node.name));
            }
          })
          .catch(() => {
            // Suggestions are a convenience: silently ignore failures.
          });
      }

      return () => {
        cancelled = true;
      };

    }

    suggestProcessNames(preamble, envVars)
      .then(names => {
        if (!cancelled) {
          setSuggestions(names);
        }
      })
      .catch(() => {
        // Suggestions are a convenience — silently ignore failures.
      });

    return () => {
      cancelled = true;
    };

  }, [preamble, envVars, isResident, chooseNodeKind]);

  async function handleConfirm() {

    const trimmedName = name.trim();

    if (!trimmedName) {
      setError("Please enter a process name.");
      return;
    }

    const isDuplicate = existingNames.some(
      existingName => existingName.toLowerCase() === trimmedName.toLowerCase()
    );

    if (isDuplicate) {
      setError("A process with this name already exists.");
      return;
    }

    if (isResident) {
      const problem = nodeNameProblem(trimmedName);
      if (problem) {
        setError(`${problem} Choose another name.`);
        return;
      }
    }

    if (chooseNodeKind && effectiveKind === "Supervisor" && supervisorTaken) {
      setError("This program already has a Supervisor: a program has at most one.");
      return;
    }

    setValidating(true);
    setError(null);

    try {
      const valid = await validateProcessName(trimmedName);

      if (!valid) {
        setError("Invalid process name.");
        return;
      }

      let info: ProcessInfo | null = null;

      if (!isResident && suggestions.includes(trimmedName)) {
        try {
          info = await getProcessInfo(preamble, envVars, trimmedName);
        } catch {
          // Injecting an existing process's info is a convenience:
          // proceed with a blank process rather than blocking on it.
        }
      }

      // A suggested node is read by the rules of import, and one that the
      // web UI cannot hold is refused, with its reasons, which the dialog
      // shows instead of adding the node.
      const nodeInfo = suggestedKind
        ? await getNodeInfo(preamble, envVars, trimmedName)
        : undefined;

      onConfirm(trimmedName, info, chooseNodeKind ? effectiveKind : undefined, nodeInfo);
      onClose();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to validate process name."
      );
    } finally {
      setValidating(false);
    }

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
          width: "60%",
          maxWidth: 480,
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >

        <h3 style={{ margin: 0 }}>
          {title}
        </h3>

        <label style={{ fontSize: 14 }}>
          Name
        </label>

        <input

          type="text"

          list={suggestionsListId}

          value={name}

          onChange={(event) =>
            setName(event.target.value)
          }

          onKeyDown={(event) => {
            if (event.key === "Enter") {
              handleConfirm();
            }
          }}

          autoFocus

          style={{
            width: "100%",
          }}

        />

        {chooseNodeKind && (

          <>

            <label style={{ fontSize: 14 }}>
              Node kind
            </label>

            <select
              value={effectiveKind}
              disabled={Boolean(suggestedKind)}
              onChange={(event) => setNodeKind(event.target.value as NodeKind)}
              style={{ width: "100%" }}
            >
              {NODE_KINDS.map(({ value, label }) => (
                <option
                  key={value}
                  value={value}
                  disabled={value === "Supervisor" && supervisorTaken}
                >
                  {label}
                </option>
              ))}
            </select>

            <div style={{ color: "#666", fontSize: 12 }}>
              {suggestedKind
                ? "A node that a module of the preamble defines: its node kind, " +
                  "code, options and description come with it."
                : NODE_KINDS.find(kind => kind.value === nodeKind)?.description}
            </div>

          </>

        )}

        <datalist id={suggestionsListId}>
          {suggestions.map(suggestion => (
            <option key={suggestion} value={suggestion} />
          ))}
        </datalist>

        {error && (
          <div style={{ color: "#b00020", fontSize: 14, whiteSpace: "pre-wrap", maxHeight: 240, overflowY: "auto" }}>
            {error}
          </div>
        )}

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
          }}
        >

          <button onClick={onClose} disabled={isValidating}>
            Cancel
          </button>

          <button onClick={handleConfirm} disabled={isValidating}>
            {isValidating ? "Validating..." : confirmLabel}
          </button>

        </div>

      </div>

    </div>

  );

}
