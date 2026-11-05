import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// In development, the Python server runs separately (uv run capabilities serve) and Vite forwards /api to it.
const API_TARGET = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": API_TARGET },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    // Cytoscape alone is about 400 kB. One bundle is fine for a page served locally; revisit when hosted.
    chunkSizeWarningLimit: 900,
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
