// @vitest-environment node
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { isLoopbackHost, processStartTime, tokenFilePath, tokenFromFile, urlPort } from "./tokenFile";

function runtimeDir(): string {
  const dir = mkdtempSync(join(tmpdir(), "debasher-token-"));
  mkdirSync(join(dir, "debasher"), { mode: 0o700 });
  return dir;
}

function writeTokenFile(dir: string, port: string, content: object) {
  writeFileSync(join(dir, "debasher", `webui-${port}.token`), JSON.stringify(content), { mode: 0o600 });
}

// This process stands for the backend that wrote the token file.
const LIVE = { pid: process.pid, started: processStartTime(process.pid) };

describe("the token file", () => {

  const children: ReturnType<typeof spawn>[] = [];

  afterEach(() => {
    children.forEach(child => child.kill());
  });

  it("is named after the port, in the private runtime directory or else under the home", () => {
    expect(tokenFilePath("8000", { XDG_RUNTIME_DIR: "/run/user/1000" })).toBe("/run/user/1000/debasher/webui-8000.token");
    expect(tokenFilePath("8001", {})).toMatch(/\/\.debasher\/run\/webui-8001\.token$/);
    expect(urlPort(new URL("http://127.0.0.1:9000"))).toBe("9000");
    expect(urlPort(new URL("http://localhost"))).toBe("80");
  });

  it("gives the token of a live backend", () => {
    const dir = runtimeDir();
    writeTokenFile(dir, "8000", { token: "tok", ...LIVE });

    expect(LIVE.started).not.toBe("");
    expect(tokenFromFile(new URL("http://127.0.0.1:8000"), { XDG_RUNTIME_DIR: dir }).token()).toBe("tok");
    expect(tokenFromFile(new URL("http://localhost:8000"), { XDG_RUNTIME_DIR: dir }).token()).toBe("tok");
  });

  it("gives no token of a backend that is gone", async () => {
    const dir = runtimeDir();
    const child = spawn("sleep", ["30"]);
    children.push(child);
    const started = processStartTime(child.pid!);
    writeTokenFile(dir, "8000", { token: "tok", pid: child.pid, started });
    const source = tokenFromFile(new URL("http://127.0.0.1:8000"), { XDG_RUNTIME_DIR: dir });
    expect(source.token()).toBe("tok");

    child.kill();
    await new Promise(resolve => child.on("exit", resolve));

    expect(source.token()).toBeNull();
    expect(source.describe()).toContain(join(dir, "debasher", "webui-8000.token"));
  });

  it("gives no token of a backend that could not tell when it started", () => {
    const dir = runtimeDir();
    writeTokenFile(dir, "8000", { token: "tok", pid: process.pid, started: "" });

    expect(tokenFromFile(new URL("http://127.0.0.1:8000"), { XDG_RUNTIME_DIR: dir }).token()).toBeNull();
  });

  it("gives no token when the PID belongs to a process that started at another time", () => {
    const dir = runtimeDir();
    writeTokenFile(dir, "8000", { token: "tok", pid: process.pid, started: "Thu Jan  1 00:00:00 1970" });

    expect(tokenFromFile(new URL("http://127.0.0.1:8000"), { XDG_RUNTIME_DIR: dir }).token()).toBeNull();
  });

  // Root may signal any process, so for root PID 1 is no process of another
  // user.
  it.skipIf(process.getuid?.() === 0)("gives no token of a process of another user", () => {
    const dir = runtimeDir();
    // PID 1 is not the user's: a signal to it fails with EPERM.
    writeTokenFile(dir, "8000", { token: "tok", pid: 1, started: processStartTime(1) });

    expect(tokenFromFile(new URL("http://127.0.0.1:8000"), { XDG_RUNTIME_DIR: dir }).token()).toBeNull();
  });

  it("gives no token towards another machine, nor for another port", () => {
    const dir = runtimeDir();
    writeTokenFile(dir, "8000", { token: "tok", ...LIVE });

    const remote = tokenFromFile(new URL("http://lab-server:8000"), { XDG_RUNTIME_DIR: dir });
    expect(remote.token()).toBeNull();
    expect(remote.describe()).toMatch(/no token to a backend on another machine/);
    expect(tokenFromFile(new URL("http://127.0.0.1:9000"), { XDG_RUNTIME_DIR: dir }).token()).toBeNull();
  });

  it("knows the loopback hosts", () => {
    expect(["localhost", "127.0.0.1", "127.1.2.3", "[::1]"].every(isLoopbackHost)).toBe(true);
    expect(["lab-server", "192.168.1.20", "[fe80::1]", "127.0.0.1.example.org"].some(isLoopbackHost)).toBe(false);
  });

});
