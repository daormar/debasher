// `vitest/config` re-exports Vite's defineConfig with the `test` option
// typed, so the same config file covers both `vite build` and `vitest`.
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { viteSingleFile } from 'vite-plugin-singlefile'

// https://vite.dev/config/
export default defineConfig({
  // Inline all JS/CSS into index.html so the built site works when opened
  // directly via file:// (Chromium blocks the external module/CSS fetches
  // that a normal multi-file Vite build otherwise requires).
  plugins: [react(), viteSingleFile()],
  server: {
    // Forward API calls to the FastAPI dev server so relative fetch("/api/...")
    // calls work under `npm run dev` too, not just in the same-origin production
    // build served by FastAPI's static mount.
    proxy: {
      "/api": "http://localhost:8000",
    },
    // The tests read files of the repository outside frontend/ (the sources
    // of the documentation that the Help menu links to); the dev server keeps
    // serving frontend/ only.
    ...(process.env.VITEST ? { fs: { allow: [".."] } } : {}),
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
})
