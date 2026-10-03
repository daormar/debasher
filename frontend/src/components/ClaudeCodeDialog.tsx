import { useEffect, useRef, useState } from "react";

import { DEFAULT_WEBUI_INFO, getWebuiInfo } from "../api/webuiApi";
import type { WebuiInfo } from "../api/webuiApi";
import { CLAUDE_SKILLS, claudeCommand } from "../models/claudeCommand";
import { copyOrSelect } from "../utils/clipboard";

interface Props {
  // The home directory of the program, empty while it was never saved.
  homeDir: string;
  unsavedChanges: boolean;
  onClose: () => void;
}

// "Claude Code" of the Help menu: the command that starts Claude Code on the
// program (debasher_claude), for the user to run in a terminal of their own,
// and the skills that the session offers. The web UI runs nothing itself.
// The backend says what the command is run through, as the `docker compose
// exec` that runs it inside the container of the Docker image, and how
// Claude Code is installed there; where Claude Code cannot work on its
// programs, the dialog gives no command and says why.
export default function ClaudeCodeDialog({ homeDir, unsavedChanges, onClose }: Props) {

  // Null until the backend answers; a backend that cannot answer is taken
  // to offer the command as it is, which is no harm where it does not work.
  const [info, setInfo] = useState<WebuiInfo | null>(null);

  // The URL of the backend from the machine where the command runs: the one
  // that the backend gives, or else the origin of the page, which the
  // backend serves (under the dev server, which forwards /api, it reaches the
  // API too).
  const [url, setUrl] = useState("");

  useEffect(() => {
    let isCurrent = true;
    getWebuiInfo()
      .catch(() => DEFAULT_WEBUI_INFO)
      .then(answer => {
        if (isCurrent) {
          setInfo(answer);
          setUrl(answer.backendUrl ?? window.location.origin);
        }
      });
    return () => {
      isCurrent = false;
    };
  }, []);

  const [copyNote, setCopyNote] = useState<string | null>(null);

  const commandRef = useRef<HTMLTextAreaElement>(null);

  const command = homeDir ? claudeCommand(homeDir, url.trim(), info?.claudeCodePrefix ?? null) : "";

  async function handleCopy() {
    setCopyNote(
      await copyOrSelect(command, commandRef.current)
        ? "Copied."
        : "The browser did not let the page copy: the command is selected, copy it with the keyboard."
    );
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
        role="dialog"
        aria-label="Claude Code"
        style={{
          width: "60%",
          maxWidth: 720,
          background: "#fff",
          borderRadius: 4,
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 12,
          fontSize: 14,
        }}
      >

        <h3 style={{ margin: 0 }}>
          Claude Code
        </h3>

        {info === null ? null : !info.claudeCode ? (

          <p style={{ margin: 0 }}>
            Claude Code is not available with this web UI: the directories of
            its server are not those of the machine where Claude Code would
            work on the program.
          </p>

        ) : !homeDir ? (

          <p style={{ margin: 0 }}>
            Claude Code works on a program saved in its home directory: save
            this one first, with Save in the toolbar.
          </p>

        ) : (

          <>

            <p style={{ margin: 0 }}>
              {info.claudeCodePrefix
                ? "Run this in a terminal to work on this program with Claude Code, which runs where this web UI runs (in its container):"
                : "Run this in a terminal to work on this program with Claude Code:"}
            </p>

            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
              Backend URL
              <input
                value={url}
                onChange={event => setUrl(event.target.value)}
                style={{ flex: 1, fontFamily: "ui-monospace, Consolas, monospace", fontSize: 12 }}
              />
            </label>

            <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
              <textarea
                ref={commandRef}
                aria-label="Command"
                readOnly
                rows={info.claudeCodePrefix ? 3 : 2}
                value={command}
                style={{
                  flex: 1,
                  fontFamily: "ui-monospace, Consolas, monospace",
                  fontSize: 12,
                  resize: "none",
                }}
              />
              <button onClick={handleCopy}>Copy</button>
            </div>

            {copyNote && <span style={{ fontSize: 13, color: "#555" }}>{copyNote}</span>}

            {info.claudeCodeInstall && (
              <p style={{ margin: 0 }}>
                The first time, install Claude Code there
                with <code>{info.claudeCodeInstall}</code>; on its first
                start, it asks you to log in, once.
              </p>
            )}

            {unsavedChanges && (
              <p style={{ margin: 0, color: "#8a5300" }}>
                This program has unsaved changes, which Claude Code does not
                see: it works on the program as saved. Save it first.
              </p>
            )}

            <div>
              In the session you can ask anything, or call a skill:
              <ul style={{ margin: "4px 0 0", paddingLeft: 20 }}>
                {CLAUDE_SKILLS.map(skill => (
                  <li key={skill.command}>
                    <code>{skill.command}</code>: {skill.does}
                  </li>
                ))}
              </ul>
            </div>

            <p style={{ margin: 0, color: "#555" }}>
              This editor loads again what Claude Code saves.
            </p>

          </>

        )}

        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button onClick={onClose}>
            Close
          </button>
        </div>

      </div>

    </div>

  );

}
