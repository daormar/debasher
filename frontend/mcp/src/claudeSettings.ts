import type { Tool } from "./tools";

// The name under which debasher_claude gives the MCP server to Claude Code,
// which names its tools mcp__<server>__<tool>.
export const SERVER_NAME = "debasher";

export interface ClaudeSettings {
  permissions: {
    allow: string[];
    ask: string[];
    deny: string[];
  };
}

// The permissions that debasher_claude gives Claude Code, from what each tool
// says it does: a tool that only reads is allowed without asking; one that
// deletes or stops something asks every time, even once the user chose to
// always allow it, since an "ask" rule wins over an "allow" one; any other
// tool, which edits the program or runs its code, is left to Claude Code,
// which asks until the user allows it. Claude Code works in the home
// directory of the program, and its tools that edit files are denied the
// program metadata (.debasher), which only the MCP tools change, keeping
// their rules and the revision of the program. A command of Bash is not
// covered, but Claude Code asks before running one.
export function claudeSettings(tools: Tool[]): ClaudeSettings {
  const name = (tool: Tool) => `mcp__${SERVER_NAME}__${tool.name}`;
  return {
    permissions: {
      allow: tools.filter(tool => tool.annotations.readOnlyHint).map(name),
      ask: tools.filter(tool => tool.annotations.destructiveHint).map(name),
      deny: ["Edit(**/.debasher/**)"],
    },
  };
}
