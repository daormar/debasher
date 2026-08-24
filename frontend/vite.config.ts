import { defineConfig } from 'vite'
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
  },
})
