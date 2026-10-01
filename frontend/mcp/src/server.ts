import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";

import type { Backend } from "./backend";
import { TOOLS } from "./tools";

// The MCP server: every MCP tool, answering with its text, or, when it
// refuses or the backend fails, with the reason as an error for the agent.
export function createServer(backend: Backend, version: string): McpServer {

  const server = new McpServer({ name: "debasher", version });

  for (const tool of TOOLS) {
    server.registerTool(
      tool.name,
      { description: tool.description, inputSchema: tool.input, annotations: tool.annotations },
      async (args: Record<string, unknown>) => {
        try {
          const { text, structured } = await tool.run(backend, args);
          return { content: [{ type: "text" as const, text }], ...(structured ? { structuredContent: structured } : {}) };
        } catch (err) {
          const text = err instanceof Error ? err.message : String(err);
          return { content: [{ type: "text" as const, text }], isError: true };
        }
      }
    );
  }

  return server;

}
