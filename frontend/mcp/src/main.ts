import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

import { setTokenSource } from "../../src/api/apiFetch";
import { httpBackend, sendRequestsTo } from "./backend";
import { claudeSettings } from "./claudeSettings";
import { createServer } from "./server";
import { tokenFromFile } from "./tokenFile";
import { TOOLS } from "./tools";

// debasher_mcp: the MCP server, spoken over its standard input and output
// by the agent that starts it, a client of the backend at the URL given.

const DEFAULT_URL = "http://127.0.0.1:8000";

const VERSION = "1.0";

const USAGE = `debasher_mcp [--url <string>]

Offers the editing, running and following of DeBasher programs to an agent
through the Model Context Protocol, over standard input and output, as a
client of the backend of the web UI (debasher_webui), which has to be running.
It sends the token of the backend, which it reads from the token file that
debasher_webui writes for its port, when the backend runs on this machine.

--url <string>       URL of the backend (default: ${DEFAULT_URL})
--claude-settings    Print, as JSON, the settings of Claude Code that
                     debasher_claude passes: the permissions of the tools of
                     this server, from what each does, and exit
--help               Show this help and exit`;

function parseArgs(argv: string[]): { url: string } {
  let url = DEFAULT_URL;
  for (let i = 0; i < argv.length; i++) {
    switch (argv[i]) {
      case "--url":
        url = argv[++i] ?? "";
        break;
      case "--help":
        process.stdout.write(`${USAGE}\n`);
        process.exit(0);
        break;
      case "--claude-settings":
        process.stdout.write(`${JSON.stringify(claudeSettings(TOOLS))}\n`);
        process.exit(0);
        break;
      default:
        process.stderr.write(`debasher_mcp: unknown option ${argv[i]}\n\n${USAGE}\n`);
        process.exit(1);
    }
  }
  if (!URL.canParse(url)) {
    process.stderr.write(`debasher_mcp: not a URL: ${url}\n`);
    process.exit(1);
  }
  return { url };
}

const { url } = parseArgs(process.argv.slice(2));

// The clients of the backend send the token of the token file of its port.
const token = tokenFromFile(new URL(url));
setTokenSource(token.token);
sendRequestsTo(url, token.describe);

await createServer(httpBackend, VERSION).connect(new StdioServerTransport());
