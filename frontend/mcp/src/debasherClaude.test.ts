// @vitest-environment node
import { execFileSync, spawnSync } from "node:child_process";
import { chmodSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { SERVER_NAME } from "./claudeSettings";

// debasher_claude as `make` builds it (see frontend/Makefile.am), with a
// debasher_mcp that answers --claude-settings and a Claude Code that writes
// down the directory it starts in and the arguments it is given.
const SOURCE = fileURLToPath(new URL("../../claude/debasher_claude.sh", import.meta.url));

let root = "";
let launcher = "";
let fakeClaude = "";
let home = "";

const SETTINGS = '{"permissions":{"allow":["mcp__debasher__get_program"],"ask":[],"deny":[]}}';

function executable(path: string, text: string) {
  writeFileSync(path, text);
  chmodSync(path, 0o755);
}

beforeAll(() => {
  root = realpathSync(mkdtempSync(join(tmpdir(), "debasher-claude-")));
  const bin = join(root, "bin");
  mkdirSync(bin);
  mkdirSync(join(root, "share", "claude", "plugin"), { recursive: true });
  const bash = execFileSync("bash", ["-c", "command -v bash"]).toString().trim();
  launcher = join(bin, "debasher_claude");
  executable(launcher,
    `#! ${bash}\ndebasher_pkgdatadir="${root}/share"\ndebasher_bindir="${bin}"\n${readFileSync(SOURCE, "utf8")}`);
  executable(join(bin, "debasher_mcp"),
    `#!/bin/sh\n[ "$1" = "--claude-settings" ] && echo '${SETTINGS}'\n`);
  fakeClaude = join(root, "claude");
  executable(fakeClaude,
    `#!/bin/sh\npwd > "${root}/claude.cwd"\nfor arg in "$@"; do printf '%s\\n----\\n' "$arg"; done > "${root}/claude.args"\n`);
  home = join(root, "home with space");
  mkdirSync(join(home, ".debasher"), { recursive: true });
  writeFileSync(join(home, ".debasher", "program.json"), "{}");
});

afterAll(() => {
  execFileSync("rm", ["-rf", root]);
});

function launch(args: string[]) {
  return spawnSync(launcher, args, { env: { ...process.env, DEBASHER_CLAUDE_CMD: fakeClaude }, encoding: "utf8" });
}

function claudeArgs(): string[] {
  return readFileSync(join(root, "claude.args"), "utf8").split("\n----\n").slice(0, -1);
}

function option(args: string[], name: string): string {
  return args[args.indexOf(name) + 1];
}

describe("debasher_claude", () => {

  it("starts Claude Code in the home directory with the server, its permissions and the plugin of DeBasher", () => {
    const result = launch(["--home-dir", home, "--url", "http://127.0.0.1:8123"]);

    expect(result.status).toBe(0);
    expect(readFileSync(join(root, "claude.cwd"), "utf8").trim()).toBe(home);
    const args = claudeArgs();
    expect(option(args, "--plugin-dir")).toBe(join(root, "share", "claude", "plugin"));
    // The skills read the reference of the plugin without asking, and only read it.
    expect(option(args, "--allowedTools")).toBe(`Read(/${join(root, "share", "claude", "plugin")}/**)`);
    expect(args).not.toContain("--add-dir");
    // Under the name that the permissions give its tools.
    expect(JSON.parse(option(args, "--mcp-config"))).toEqual({
      mcpServers: { [SERVER_NAME]: { command: join(root, "bin", "debasher_mcp"), args: ["--url", "http://127.0.0.1:8123"] } },
    });
    expect(option(args, "--settings")).toBe(SETTINGS);
    expect(option(args, "--append-system-prompt")).toContain(`home directory is ${home}`);
    expect(args.some(arg => arg.startsWith("/debasher:"))).toBe(false);
  });

  it("starts the session with the skill of the mode given, and passes on what follows --", () => {
    const result = launch(["--home-dir", home, "--mode", "design", "--", "--model", "opus"]);

    expect(result.status).toBe(0);
    expect(claudeArgs().slice(-4)).toEqual(["--model", "opus", "--", "/debasher:design"]);
  });

  it("gives the prompt to the skill of the mode, as a single first message after every option", () => {
    launch(["--home-dir", home, "--mode", "implement", "--prompt", "fill in count", "--", "--allowedTools", "Read"]);
    expect(claudeArgs().slice(-4)).toEqual(["--allowedTools", "Read", "--", "/debasher:implement fill in count"]);

    launch(["--home-dir", home, "--prompt", "what is a FIFO?"]);
    expect(claudeArgs().at(-1)).toBe("what is a FIFO?");
  });

  it("talks to the backend at the default URL of the web UI when none is given", () => {
    launch(["--home-dir", home]);

    expect(JSON.parse(option(claudeArgs(), "--mcp-config")).mcpServers.debasher.args).toEqual(["--url", "http://127.0.0.1:8000"]);
  });

  it("prints the command instead of running it with --dry-run", () => {
    const result = launch(["--home-dir", home, "--mode", "help", "--dry-run"]);

    expect(result.status).toBe(0);
    expect(result.stdout).toMatch(/^cd .*home\\ with\\ space && /);
    expect(result.stdout).toContain("/debasher:help");
  });

  it("refuses to start without the plugin of DeBasher", () => {
    execFileSync("mv", [join(root, "share", "claude", "plugin"), join(root, "share", "claude", "moved")]);
    try {
      const result = launch(["--home-dir", home]);
      expect(result.status).toBe(1);
      expect(result.stderr).toMatch(/plugin of DeBasher is missing/);
    } finally {
      execFileSync("mv", [join(root, "share", "claude", "moved"), join(root, "share", "claude", "plugin")]);
    }
  });

  it("refuses a directory with no program saved, an unknown mode and a missing home directory", () => {
    const empty = join(root, "empty");
    mkdirSync(empty, { recursive: true });

    expect(launch(["--home-dir", empty]).stderr).toMatch(/no program is saved/);
    expect(launch(["--home-dir", home, "--mode", "everything"]).stderr).toMatch(/unknown mode/);
    expect(launch([]).stderr).toMatch(/--home-dir option should be given/);
    expect(launch(["--home-dir", home, "--bogus"]).status).toBe(1);
  });

});
