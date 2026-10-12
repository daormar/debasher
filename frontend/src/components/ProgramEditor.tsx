import { useEffect } from "react";

import Toolbar from "./Toolbar";
import ExternalChangeBanner from "./ExternalChangeBanner";
import { useProgram } from "../store/ProgramContext";
import { ClaudeTerminalProvider, isSessionActive, useClaudeTerminal } from "../store/ClaudeTerminalContext";
import ProgramCanvas from "./ProgramCanvas";
import Inspector from "./Inspector";
import ClaudeTerminalPanel from "./ClaudeTerminalPanel";

interface Props {
  onClose: (runMessage: string | null) => void;
}

export default function ProgramEditor({ onClose }: Props) {

  const { program } = useProgram();

  return (
    <ClaudeTerminalProvider homeDir={program.homeDir}>
      <EditorLayout onClose={onClose} />
    </ClaudeTerminalProvider>
  );

}

function EditorLayout({ onClose }: Props) {

  const { unsavedChanges } = useProgram();

  const { phase } = useClaudeTerminal();
  const sessionActive = isSessionActive(phase);

  // Closing or reloading the browser tab with unsaved changes, or with a
  // session of Claude Code that it would end, asks first; the browser words
  // the question.
  useEffect(() => {
    if (!unsavedChanges && !sessionActive) {
      return;
    }
    function handleBeforeUnload(event: BeforeUnloadEvent) {
      event.preventDefault();
    }
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [unsavedChanges, sessionActive]);

  return (

    <div
      style={{
        width: "100%",
        height: "100vh",
        display: "flex",
        flexDirection: "column",
      }}
    >

      <Toolbar onClose={onClose} />

      <ExternalChangeBanner />


      <div
        style={{
          flex: 1,
          display: "flex",
          minHeight: 0,
        }}
      >

        <div
          style={{
            flex: 1,
          }}
        >

          <ProgramCanvas />

        </div>


        <Inspector />


      </div>

      <ClaudeTerminalPanel />

    </div>

  );

}
