import react from "@vitejs/plugin-react";
import { configDefaults, defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 4173,
    proxy: {
      "/health": "http://127.0.0.1:8000",
      "/v1": {
        target: "http://127.0.0.1:8000",
        ws: true,
      },
    },
  },
  test: {
    exclude: [...configDefaults.exclude, "tests/**"],
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
    css: true,
  },
});
