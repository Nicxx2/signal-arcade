import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

const workspaceNodeModules = fileURLToPath(new URL("../node_modules", import.meta.url));

export default defineConfig({
  resolve: {
    // The pnpm workspace uses Windows junctions; force the components and
    // test renderer to share one React hook dispatcher.
    alias: {
      react: `${workspaceNodeModules}/react`,
      "react-dom": `${workspaceNodeModules}/react-dom`,
    },
    dedupe: ["react", "react-dom"],
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    server: {
      deps: {
        // Process Testing Library through Vite so its act() helper follows
        // the same React aliases as the components it renders.
        inline: ["@testing-library/react", "react", "react-dom"],
      },
    },
  },
});
