import { useEffect, useRef, useState } from "react";

import { getWebuiInfo } from "../api/webuiApi";
import { backendUrl, CLAUDE_SKILLS, claudeCommand } from "../models/claudeCommand";
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
// Where the backend says that Claude Code cannot work on its programs (it
// runs in a container), it gives no command and says why.
export default function ClaudeCodeDialog({ homeDir, unsavedChanges, onClose }: Props) {

  // Null until the backend answers; a backend that cannot answer is taken
  // to offer Claude Code, as a command is no harm where it does not work.
  const [isOffered, setOffered] = useState<boolean | null>(null);

  useEffect(() => {
    let isCurrent = true;
    getWebuiInfo()
      .then(info => info.claudeCode)
      .catch(() => true)
      .then(offered => {
        if (isCurrent) {
          setOffered(offered);
        }
      });
    return () => {
      isCurrent = false;
    };
  }, []);

  const [url, setUrl] = useState(() => backendUrl(window.location));

  const [copyNote, setCopyNote] = useState<string | null>(null);

  const commandRef = useRef<HTMLTextAreaElement>(null);

  const command = homeDir ? claudeCommand(homeDir, url.trim()) : "";

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

        {isOffered === null ? null : !isOffered ? (

          <p style={{ margin: 0 }}>
            Claude Code is not available with this web UI: it runs in a
            container, whose directories are not those of your computer,
            where Claude Code would work on the program.
          </p>

        ) : !homeDir ? (

          <p style={{ margin: 0 }}>
            Claude Code works on a program saved in its home directory: save
            this one first, with Save in the toolbar.
          </p>

        ) : (

          <>

            <p style={{ margin: 0 }}>
              Run this in a terminal to work on this program with Claude Code:
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
                rows={2}
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
