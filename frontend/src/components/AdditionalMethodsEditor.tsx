import { useState, type ReactNode } from "react";

import MethodBodyEditor from "./MethodBodyEditor";
import type { AdditionalMethods, ProgramProcess } from "../models/process";

interface Props {
  process: ProgramProcess;
  onClose: () => void;
}

interface MethodDescriptor {
  key: keyof AdditionalMethods;
  name: string;
  description: ReactNode;
}

// The DEBASHER_PROCESS_METHODS (engine/debasher_lib.sh) not covered
// elsewhere in the Inspector: "document" is the Description field,
// "exec" is the "Edit code" implementation, and the option explanation/
// definition methods are driven by the process's options/options
// handler.
const METHODS: MethodDescriptor[] = [
  {
    key: "resetOutfilesCode",
    name: "reset_outfiles",
    description: (
      <>
        Runs instead of the engine's default output-directory cleanup,
        right before this process's implementation. Receives the same
        option arguments as the implementation itself, accessible via{" "}
        <code>"$@"</code> (e.g.{" "}
        <code>{'read_opt_value_from_func_args "-opt" "$@"'}</code>).
      </>
    ),
  },
  {
    key: "postCode",
    name: "post",
    description: (
      <>
        Runs right after this process's implementation succeeds, e.g. for
        post-processing or cleanup. Receives the same option arguments as
        the implementation itself, accessible via <code>"$@"</code>.
      </>
    ),
  },
  {
    key: "outdirBasenameCode",
    name: "outdir_basename",
    description: (
      <>
        Echoes the basename to use for this process's own output
        directory, instead of the default (its process name). Takes no
        arguments.
      </>
    ),
  },
  {
    key: "skipCode",
    name: "skip",
    description: (
      <>
        Decides whether to skip running this process: return{" "}
        <code>0</code> to skip it, non-zero to run it normally. Receives
        the same option arguments as the implementation itself, accessible
        via <code>"$@"</code>.
      </>
    ),
  },
  {
    key: "condaEnvsCode",
    name: "conda_envs",
    description: (
      <>
        Declares this process's conda environments, e.g.{" "}
        <code>define_conda_env myenv myenv.yml</code>. Takes no arguments,
        and runs once per process regardless of its number of tasks.
      </>
    ),
  },
  {
    key: "dockerImgsCode",
    name: "docker_imgs",
    description: (
      <>
        Declares this process's Docker images, e.g.{" "}
        <code>{'pull_docker_img "library/hello-world"'}</code>. Takes no
        arguments, and runs once per process regardless of its number of
        tasks.
      </>
    ),
  },
];

export default function AdditionalMethodsEditor({ process, onClose }: Props) {

  const [editingMethod, setEditingMethod] = useState<MethodDescriptor | null>(null);

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
          width: "70%",
          maxWidth: 900,
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >

        <h3 style={{ margin: 0 }}>
          Additional Methods: {process.name}
        </h3>

        <p style={{ margin: 0, color: "#666", fontSize: 13 }}>
          Configure the remaining process methods debasher supports,
          beyond option definition/explanation and the implementation
          itself.
        </p>

        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-start",
            gap: 8,
          }}
        >

          {METHODS.map(method => (
            <button
              key={method.key}
              onClick={() => setEditingMethod(method)}
            >
              Edit {method.name}
              {process.additionalMethods[method.key] ? " (defined)" : ""}
            </button>
          ))}

        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
          }}
        >

          <button onClick={onClose}>
            Close
          </button>

        </div>

      </div>

      {editingMethod && (
        <MethodBodyEditor
          process={process}
          methodKey={editingMethod.key}
          methodName={editingMethod.name}
          description={editingMethod.description}
          onClose={() => setEditingMethod(null)}
        />
      )}

    </div>

  );

}
