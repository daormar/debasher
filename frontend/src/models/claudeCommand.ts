// The command that starts Claude Code on the program open in the editor
// (debasher_claude), which the "Claude Code" dialog of the Help menu shows for
// the user to run in a terminal of their own.

// `word` as one word of a POSIX shell: as it is when it holds nothing that
// the shell would read otherwise, and else between single quotes.
export function shellWord(word: string): string {
  if (/^[A-Za-z0-9_/.,:=@%+-]+$/.test(word)) {
    return word;
  }
  return `'${word.replace(/'/g, `'\\''`)}'`;
}

// How the session of Claude Code starts: with a new conversation, with the
// last one on the program, or with one that Claude Code lists for the user
// to pick. Claude Code keeps its conversations by the directory where it
// runs, which debasher_claude makes the home directory of the program, so
// the conversations of each program are its own.
export type ClaudeConversation = "new" | "continue" | "resume";

export const CLAUDE_CONVERSATIONS: { value: ClaudeConversation; label: string }[] = [
  { value: "new", label: "Start a new conversation" },
  { value: "continue", label: "Continue the last conversation" },
  { value: "resume", label: "Resume an earlier conversation" },
];

// The options of Claude Code that start each kind of session, which
// debasher_claude passes to it as they are after "--".
const CONVERSATION_ARGS: Record<ClaudeConversation, string> = {
  new: "",
  continue: " -- --continue",
  resume: " -- --resume",
};

// The command, run through `prefix` when given, as the `docker compose exec`
// that runs it inside the container of the backend.
export function claudeCommand(
  homeDir: string,
  url: string,
  prefix: string | null = null,
  conversation: ClaudeConversation = "new",
): string {
  const command = `debasher_claude --home-dir ${shellWord(homeDir)} --url ${shellWord(url)}${CONVERSATION_ARGS[conversation]}`;
  return prefix ? `${prefix} ${command}` : command;
}

// The skills of the plugin of DeBasher, which a session of Claude Code calls
// on its own when the work asks for them, or the user by their command.
export const CLAUDE_SKILLS = [
  { command: "/debasher:help", does: "questions on DeBasher and on this editor" },
  { command: "/debasher:design", does: "the processes of the program and their connections" },
  { command: "/debasher:implement", does: "the code of the processes and their tests" },
  { command: "/debasher:review", does: "feedback on the code and the tests that are written" },
];
