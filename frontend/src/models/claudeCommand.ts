// The command that starts Claude Code on the program open in the editor
// (debasher_claude), which the "Claude Code" dialog of the Help menu shows for
// the user to run in a terminal of their own.

// Where debasher_webui listens unless told otherwise.
export const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000";

// The URL of the backend that serves the page: the page and the API share
// their origin, also under the dev server, which forwards /api. A page opened
// from a file has no such origin, and gets the default instead.
export function backendUrl(location: { protocol: string; origin: string }): string {
  return location.protocol === "http:" || location.protocol === "https:"
    ? location.origin
    : DEFAULT_BACKEND_URL;
}

// `word` as one word of a POSIX shell: as it is when it holds nothing that
// the shell would read otherwise, and else between single quotes.
export function shellWord(word: string): string {
  if (/^[A-Za-z0-9_/.,:=@%+-]+$/.test(word)) {
    return word;
  }
  return `'${word.replace(/'/g, `'\\''`)}'`;
}

export function claudeCommand(homeDir: string, url: string): string {
  return `debasher_claude --home-dir ${shellWord(homeDir)} --url ${shellWord(url)}`;
}

// The skills of the plugin of DeBasher, which a session of Claude Code calls
// on its own when the work asks for them, or the user by their command.
export const CLAUDE_SKILLS = [
  { command: "/debasher:help", does: "questions on DeBasher and on this editor" },
  { command: "/debasher:design", does: "the processes of the program and their connections" },
  { command: "/debasher:implement", does: "the code of the processes and their tests" },
];
