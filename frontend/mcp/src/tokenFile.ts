import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

// The token file: where debasher_webui (api/serve.py) leaves the token of a
// backend for the MCP server to read by itself, named after its port, in the
// user's private runtime directory, with the PID of the backend and the time
// at which it started. The MCP server uses it only while that backend is
// alive, and only towards the local machine.

interface TokenFileContent {
  token: string;
  pid: number;
  started: string;
}

export function tokenFilePath(port: string, env: NodeJS.ProcessEnv = process.env): string {
  const dir = env.XDG_RUNTIME_DIR
    ? join(env.XDG_RUNTIME_DIR, "debasher")
    : join(homedir(), ".debasher", "run");
  return join(dir, `webui-${port}.token`);
}

export function urlPort(url: URL): string {
  return url.port || (url.protocol === "https:" ? "443" : "80");
}

export function isLoopbackHost(hostname: string): boolean {
  return hostname === "localhost"
    || hostname === "[::1]"
    || /^127\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(hostname);
}

// When the process `pid` started, as `ps -o lstart=` prints it in the C locale
// and in UTC, as the backend recorded it; empty when there is no such process.
export function processStartTime(pid: number): string {
  try {
    return execFileSync("ps", ["-o", "lstart=", "-p", String(pid)], {
      env: { ...process.env, LC_ALL: "C", TZ: "UTC" },
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    return "";
  }
}

// Whether `pid` is a live process of the user: a signal 0 to the process of
// another user fails (EPERM), as to one that does not exist (ESRCH).
export function isOwnLiveProcess(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function readTokenFile(path: string): TokenFileContent | null {
  try {
    const content = JSON.parse(readFileSync(path, "utf8"));
    return typeof content?.token === "string"
      && Number.isInteger(content.pid)
      && typeof content.started === "string"
      ? content
      : null;
  } catch {
    return null;
  }
}

export interface TokenFromFile {
  // The token to send, read at every request, since the backend may restart
  // with another one while the agent works.
  token: () => string | null;
  // Where the token comes from, for the error of a refused request.
  describe: () => string;
}

export function tokenFromFile(url: URL, env: NodeJS.ProcessEnv = process.env): TokenFromFile {
  const port = urlPort(url);
  const path = tokenFilePath(port, env);

  if (!isLoopbackHost(url.hostname)) {
    return {
      token: () => null,
      describe: () => "debasher_mcp sends no token to a backend on another machine.",
    };
  }

  // The start time of the process asked for the last content read, whose
  // comparison is the costly part of the check (it runs ps).
  let checked: { raw: string; started: string } | null = null;

  function token(): string | null {
    const content = readTokenFile(path);
    if (content === null || !isOwnLiveProcess(content.pid)) {
      return null;
    }
    const raw = JSON.stringify(content);
    if (checked?.raw !== raw) {
      checked = { raw, started: processStartTime(content.pid) };
    }
    return checked.started === content.started ? content.token : null;
  }

  return {
    token,
    describe: () => token() === null
      ? `debasher_mcp found no token of a live backend in ${path}, which debasher_webui writes when it starts on this machine with port ${port}: is it running there?`
      : `debasher_mcp sent the token of ${path}, which the backend does not take: was the backend started by hand, with no token file?`,
  };
}
