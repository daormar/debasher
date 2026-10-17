import { Fragment, useMemo, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";

import { useProgram } from "../store/ProgramContext";
import { languageExtensions } from "./codeLanguages";
import type { MethodCodeKey, ProgramProcess } from "../models/process";
import { processMethod } from "../models/processMethods";
import { buildMethodPrompt } from "../models/methodPrompt";
import { SKIP_PY_TEMPLATE } from "../models/codeTemplates";
import CodePromptPanel, { CodePromptButton } from "./CodePromptPanel";
import FuncLanguageSelect, { useLanguageDrafts } from "./FuncLanguageSelect";
import EnvDataEditor, { type EnvData, hasIncompleteRow, trimmedRows } from "./EnvDataEditor";

interface Props {
  process: ProgramProcess;
  methodKey: MethodCodeKey;
  onClose: () => void;
}

export default function MethodBodyEditor({
  process,
  methodKey,
  onClose,
}: Props) {

  const { program, setAdditionalMethods } = useProgram();

  const method = processMethod(methodKey);

  const methods = process.additionalMethods;

  const isSkip = methodKey === "skipCode";

  // The skip method may be a skip file in Python; any other method is Bash
  const { language, setLanguage, draft, setDraft } = useLanguageDrafts(
    isSkip ? methods.skipLanguage ?? "bash" : "bash",
    methods[methodKey],
    { bash: "", python: SKIP_PY_TEMPLATE },
  );

  // The Conda environments and the Docker images may be data instead of a
  // body, which they are by default; the model holds one or the other
  const initialData: EnvData | null =
    methodKey === "condaEnvsCode" ? { kind: "conda", rows: methods.condaEnvs ?? [] }
      : methodKey === "dockerImgsCode" ? { kind: "docker", rows: methods.dockerImgs ?? [] }
        : null;

  const [envData, setEnvData] = useState(initialData);

  const [isData, setIsData] = useState(
    initialData !== null && (initialData.rows.length > 0 || !methods[methodKey])
  );

  const showsData = envData !== null && isData;

  function handleSave() {

    const changes: Partial<typeof methods> = { [methodKey]: draft };
    if (isSkip) {
      changes.skipLanguage = language;
    }
    if (envData !== null) {
      const data = trimmedRows(envData);
      changes[methodKey] = showsData ? undefined : draft;
      if (data.kind === "conda") {
        changes.condaEnvs = showsData ? data.rows : [];
      } else {
        changes.dockerImgs = showsData ? data.rows : [];
      }
    }

    setAdditionalMethods(process.id, { ...methods, ...changes });

    onClose();

  }

  // The prompt panel, as in the code editor of a process.
  const [isPromptOpen, setPromptOpen] = useState(false);

  const [codeRequest, setCodeRequest] = useState("");

  const codePrompt = useMemo(
    () => isPromptOpen ? buildMethodPrompt(program, process, methodKey, draft, codeRequest, language) : "",
    [isPromptOpen, program, process, methodKey, draft, codeRequest, language]
  );

  return (

    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0, 0, 0, 0.4)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1001,
      }}
    >

      <div
        style={{
          width: isPromptOpen ? "92%" : "70%",
          maxWidth: isPromptOpen ? 1500 : 900,
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >

        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 8,
          }}
        >

          <h3 style={{ margin: 0 }}>
            {method.name}: {process.name}
          </h3>

          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {isSkip && <FuncLanguageSelect value={language} onChange={setLanguage} />}
            {envData !== null && (
              <label style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 4 }}>
                Given as
                <select
                  value={isData ? "data" : "body"}
                  onChange={event => {
                    setIsData(event.target.value === "data");
                    setPromptOpen(false);
                  }}
                >
                  <option value="data">Data</option>
                  <option value="body">Bash body</option>
                </select>
              </label>
            )}
            {!showsData && (
              <CodePromptButton isOpen={isPromptOpen} onToggle={() => setPromptOpen(open => !open)} />
            )}
          </div>

        </div>

        <p style={{ margin: 0, color: "#666", fontSize: 13 }}>
          {withCodeSpans(
            showsData ? ENV_DATA_SUMMARIES[envData.kind]
              : isSkip && language === "python" ? PYTHON_SKIP_SUMMARY
                : method.summary
          )}
        </p>

        <div
          style={{
            display: "flex",
            gap: 12,
            alignItems: "stretch",
          }}
        >

          <div
            style={{
              flex: 1,
              minWidth: 0,
              border: "1px solid #ccc",
            }}
          >

            {showsData ? (

              <EnvDataEditor data={envData} onChange={setEnvData} />

            ) : (

            <CodeMirror

              value={draft}

              height="400px"

              extensions={languageExtensions(language)}

              // The setter itself, which keeps its identity while the language

              // stays the same: a new function at each render would reconfigure

              // the editor (see languageExtensions).

              onChange={setDraft}

            />

            )}

          </div>

          {isPromptOpen && (
            <CodePromptPanel
              prompt={codePrompt}
              request={codeRequest}
              onRequestChange={setCodeRequest}
              pasteHint="Paste the code of the answer into the editor."
            />
          )}

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

          <button
            onClick={handleSave}
            disabled={showsData && hasIncompleteRow(envData)}
            title={showsData && hasIncompleteRow(envData) ? "Fill in or remove the incomplete rows" : undefined}
          >
            Save
          </button>

        </div>

      </div>

    </div>

  );

}

// What the editor says of the environments given as data, and of a skip
// file in Python, in place of the summary of the method.
const ENV_DATA_SUMMARIES = {
  conda: "The Conda environments of the process: the name of each and its YAML file, which a run with `--conda-support` creates when no environment of that name exists. The file is looked for in the directories of `DEBASHER_YML_DIR`, then among those that DeBasher installs; the process activates an environment with `conda_activate <name>`.",
  docker: "The Docker images of the process, which a run with `--docker-support` pulls when they are not present; the process runs a container with `\"${DOCKER}\"`.",
};

const PYTHON_SKIP_SUMMARY =
  "A Python file that defines `skip(task)`, which returns `True` to skip the task and `False` to run it. `task.value(\"-opt\")` reads an option of the task (the value that a value descriptor holds), and `task.given(\"-flag\")` tests a flag; an exception or another value fails the task.";

// A text whose code spans are written between backquotes, with each span
// shown as code.
function withCodeSpans(text: string) {
  return text.split("`").map((piece, i) => (
    i % 2 === 1 ? <code key={i}>{piece}</code> : <Fragment key={i}>{piece}</Fragment>
  ));
}
