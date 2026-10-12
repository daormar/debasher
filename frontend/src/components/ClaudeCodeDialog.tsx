import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { DEFAULT_WEBUI_INFO, getWebuiInfo } from "../api/webuiApi";
import type { WebuiInfo } from "../api/webuiApi";
import { CLAUDE_CONVERSATIONS, CLAUDE_SKILLS, claudeCommand } from "../models/claudeCommand";
import type { ClaudeConversation } from "../models/claudeCommand";
import { isSessionActive, useClaudeTerminal } from "../store/ClaudeTerminalContext";
import { copyOrSelect } from "../utils/clipboard";

// The dialog keeps one size whatever it shows, so that choosing where Claude
// Code runs does not make it jump; what does not fit scrolls.
const DIALOG_HEIGHT = "min(480px, 90vh)";

// The two ways of running Claude Code, where the backend offers both.
const WHERE_CHOICES = [
  { value: "editor", label: "In this editor" },
  { value: "terminal", label: "In a terminal of your own" },
] as const;

interface Props {
  // The home directory of the program, empty while it was never saved.
  homeDir: string;
  unsavedChanges: boolean;
  onClose: () => void;
}

// "Claude Code" of the Help menu: the command that starts Claude Code on the
// program (debasher_claude), for the user to run in a terminal of their own,
// and the skills that the session offers; and, where the backend runs Claude
// Code in the page, "Open in the page", which starts the same command in the
// terminal panel of the editor. The backend says what the command is run
// through, as the `docker compose exec` that runs it inside the container of
// the Docker image, and how Claude Code is installed there; where Claude Code
// cannot work on its programs, the dialog gives no command and says why.
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

  const [conversation, setConversation] = useState<ClaudeConversation>("new");

  // Where Claude Code runs, where the backend offers both ways: the dialog
  // shows only what the chosen one needs.
  const [where, setWhere] = useState<"editor" | "terminal">("editor");

  const [copyNote, setCopyNote] = useState<string | null>(null);

  const terminal = useClaudeTerminal();
  const sessionActive = isSessionActive(terminal.phase);

  const commandRef = useRef<HTMLTextAreaElement>(null);

  const command = homeDir ? claudeCommand(homeDir, url.trim(), info?.claudeCodePrefix ?? null, conversation) : "";

  // The box of the command is as tall as the command, whatever its length
  // and the width of the dialog, so that none of it is hidden.
  useLayoutEffect(() => {
    const box = commandRef.current;
    if (!box) {
      return;
    }
    function fit() {
      if (!box) {
        return;
      }
      box.style.height = "auto";
      if (box.scrollHeight > 0) {
        box.style.height = `${box.scrollHeight + box.offsetHeight - box.clientHeight}px`;
      }
    }
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, [command, where, info]);

  // How the session starts, for both ways of running it: above them when the
  // backend offers the two, else among the fields of the command. The note
  // that installs Claude Code goes the same way.
  const conversationField = (
    <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
      Conversation
      <select
        value={conversation}
        onChange={event => setConversation(event.target.value as ClaudeConversation)}
      >
        {CLAUDE_CONVERSATIONS.map(({ value, label }) => (
          <option key={value} value={value}>{label}</option>
        ))}
      </select>
    </label>
  );

  // Where Claude Code does not come with the rest (the Docker image), how to
  // install it, which both ways need.
  const installNote = info?.claudeCodeInstall && (
    <p style={{ margin: 0 }}>
      The first time, install Claude Code there
      with <code>{info.claudeCodeInstall}</code>; on its first
      start, it asks you to log in, once.
    </p>
  );

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
          height: DIALOG_HEIGHT,
          boxSizing: "border-box",
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

        <div
          style={{
            flex: 1,
            minHeight: 0,
            overflowY: "auto",
            display: "flex",
            flexDirection: "column",
            gap: 12,
          }}
        >

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

              {info.claudeCodeTerminal && conversationField}

              {info.claudeCodeTerminal && (
                <div
                  role="radiogroup"
                  aria-label="Where"
                  style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 13 }}
                >
                  Where
                  {WHERE_CHOICES.map(({ value, label }) => (
                    <label key={value} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <input
                        type="radio"
                        name="claude-code-where"
                        value={value}
                        checked={where === value}
                        onChange={() => setWhere(value)}
                      />
                      {label}
                    </label>
                  ))}
                </div>
              )}

              {info.claudeCodeTerminal && installNote}

              {unsavedChanges && (
                <p style={{ margin: 0, color: "#8a5300" }}>
                  This program has unsaved changes, which Claude Code does not
                  see: it works on the program as saved. Save it first.
                </p>
              )}

              {info.claudeCodeTerminal && where === "editor" ? (

                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ flex: 1 }}>
                    Runs Claude Code in a terminal at the bottom of this editor.
                  </span>
                  <button
                    onClick={() => {
                      if (sessionActive) {
                        terminal.setVisible(true);
                      } else {
                        terminal.start(conversation);
                      }
                      onClose();
                    }}
                  >
                    {sessionActive ? "Show it in the page" : "Open in the page"}
                  </button>
                </div>

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

                  {!info.claudeCodeTerminal && conversationField}

                  <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
                    <textarea
                      ref={commandRef}
                      aria-label="Command"
                      readOnly
                      rows={2}
                      value={command}
                      style={{
                        flex: 1,
                        boxSizing: "border-box",
                        overflow: "hidden",
                        fontFamily: "ui-monospace, Consolas, monospace",
                        fontSize: 12,
                        resize: "none",
                      }}
                    />
                    <button onClick={handleCopy}>Copy</button>
                  </div>

                  {copyNote && <span style={{ fontSize: 13, color: "#555" }}>{copyNote}</span>}

                  {!info.claudeCodeTerminal && installNote}

                </>

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

        </div>

        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button onClick={onClose}>
            Close
          </button>
        </div>

      </div>

    </div>

  );

}
