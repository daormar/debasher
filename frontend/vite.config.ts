// `vitest/config` re-exports Vite's defineConfig with the `test` option
// typed, so the same config file covers both `vite build` and `vitest`.
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { viteSingleFile } from 'vite-plugin-singlefile'

// https://vite.dev/config/
export default defineConfig({
  // Inline all JS/CSS into index.html, a single file that the backend serves
  // without the token, as it holds none of the user's data.
  plugins: [react(), viteSingleFile()],
  server: {
    // Forward API calls to the FastAPI dev server so relative fetch("/api/...")
    // calls work under `npm run dev` too, not just in the same-origin production
    // build served by FastAPI's static mount. The requests keep their token
    // (Authorization) and their Host as they come: the proxy adds no token of
    // its own, which it would hand to anyone who reaches its port. Open
    // http://localhost:5173/#token=<the backend's DEBASHER_WEBUI_TOKEN> once.
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
