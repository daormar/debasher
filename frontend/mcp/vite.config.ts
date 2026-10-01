import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

// The build of the MCP server: one JavaScript module for Node.js,
// mcp/dist/debasher_mcp.mjs, which bundles the server with the parts of the
// frontend it imports and the MCP library, so that it runs with nothing
// installed next to it.

const here = (path: string) => fileURLToPath(new URL(path, import.meta.url));

export default defineConfig({
  root: here("."),
  // The server runs no page: Vite must not copy the frontend's public/.
  publicDir: false,
  ssr: {
    noExternal: true,
    target: "node",
  },
  build: {
    ssr: here("src/main.ts"),
    outDir: here("dist"),
    emptyOutDir: true,
    target: "node22",
    minify: false,
    rollupOptions: {
      output: {
        entryFileNames: "debasher_mcp.mjs",
      },
    },
  },
});
