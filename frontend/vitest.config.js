import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.js"],
    clearMocks: true,
    // This small suite does not need a worker for every host CPU.
    maxWorkers: 1,
    minWorkers: 1,
  },
});
