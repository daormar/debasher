import { describe, expect, it } from "vitest";

import { backendUrl, claudeCommand, DEFAULT_BACKEND_URL, shellWord } from "./claudeCommand";

describe("backendUrl", () => {

  it("is the origin of the page, which the backend serves", () => {
    expect(backendUrl({ protocol: "http:", origin: "http://127.0.0.1:8123" })).toBe("http://127.0.0.1:8123");
    expect(backendUrl({ protocol: "https:", origin: "https://lab.example.org" })).toBe("https://lab.example.org");
  });

  it("is the default of debasher_webui for a page opened from a file", () => {
    expect(backendUrl({ protocol: "file:", origin: "null" })).toBe(DEFAULT_BACKEND_URL);
  });

});

describe("shellWord", () => {

  it("leaves a plain path as it is", () => {
    expect(shellWord("/home/me/programs/wordcount")).toBe("/home/me/programs/wordcount");
    expect(shellWord("http://127.0.0.1:8000")).toBe("http://127.0.0.1:8000");
  });

  it("quotes what the shell would read otherwise, a quote of its own included", () => {
    expect(shellWord("/home/me/my programs")).toBe("'/home/me/my programs'");
    expect(shellWord("/tmp/$HOME;ls")).toBe("'/tmp/$HOME;ls'");
    expect(shellWord("~/x")).toBe("'~/x'");
    expect(shellWord("/tmp/it's")).toBe("'/tmp/it'\\''s'");
    expect(shellWord("")).toBe("''");
  });

});

describe("claudeCommand", () => {

  it("names the home directory and the backend", () => {
    expect(claudeCommand("/home/me/my programs/wc", "http://127.0.0.1:8000")).toBe(
      "debasher_claude --home-dir '/home/me/my programs/wc' --url http://127.0.0.1:8000"
    );
  });

});
