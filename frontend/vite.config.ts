import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    // Keep React's hook dispatcher singular even when pnpm is using an
    // isolated workspace layout (Windows junctions otherwise look like a
    // second installation to Vite/Vitest).
    dedupe: ["react", "react-dom"],
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/ws": { target: "ws://127.0.0.1:8765", ws: true },
    },
  },
  build: {
    target: "es2022",
    sourcemap: true,
  },
});
