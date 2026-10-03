import { describe, expect, it } from "vitest";

import { claudeSettings } from "./claudeSettings";
import { TOOLS } from "./tools";

const settings = claudeSettings(TOOLS);

const named = (rules: string[]) => rules.map(rule => rule.replace(/^mcp__debasher__/, ""));

describe("claudeSettings", () => {

  it("allows without asking exactly the tools that only read", () => {
    expect(named(settings.permissions.allow).sort()).toEqual(
      TOOLS.filter(tool => tool.annotations.readOnlyHint).map(tool => tool.name).sort()
    );
    expect(named(settings.permissions.allow)).toContain("get_program");
    // Saving the program or running its code is never only reading.
    for (const name of ["run_program", "validate_program", "run_tests"]) {
      expect(named(settings.permissions.allow)).not.toContain(name);
    }
  });

  it("asks every time before a tool that deletes or stops something", () => {
    expect(named(settings.permissions.ask)).toEqual(
      expect.arrayContaining(["reset_output_dir", "reset_program_state", "delete_program_file", "stop_program"])
    );
    for (const name of named(settings.permissions.ask)) {
      expect(named(settings.permissions.allow)).not.toContain(name);
    }
  });

  it("leaves the tools that edit to Claude Code, which asks until the user allows them", () => {
    const ruled = new Set([...named(settings.permissions.allow), ...named(settings.permissions.ask)]);
    const editing = TOOLS.filter(tool => !ruled.has(tool.name));
    expect(editing.map(tool => tool.name)).toEqual(expect.arrayContaining(["add_process", "apply_edits", "run_program"]));
    for (const tool of editing) {
      expect(tool.annotations.readOnlyHint).toBe(false);
      expect(tool.annotations.destructiveHint).toBe(false);
    }
  });

  it("names every tool as Claude Code names the tools of the server", () => {
    for (const rule of [...settings.permissions.allow, ...settings.permissions.ask]) {
      expect(rule).toMatch(/^mcp__debasher__[a-z_]+$/);
    }
  });

  it("denies editing by hand the files that DeBasher manages in the home directory", () => {
    expect(settings.permissions.deny).toEqual(["Edit(**/.debasher/**)"]);
  });

});
