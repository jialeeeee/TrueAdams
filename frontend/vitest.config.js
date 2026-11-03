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
    // `npm run coverage`. Entry point and test helpers are not app code.
    coverage: {
      provider: "v8",
      include: ["src/**/*.{js,jsx}"],
      exclude: ["src/main.jsx", "src/test/**", "src/**/*.test.{js,jsx}"],
      reporter: ["text-summary", "text"],
      // The floor measured when coverage was added (3 Nov 2026), so it can only rise.
      // Raise these as the remaining branches get tests; 100 is the target.
      thresholds: { statements: 99, lines: 99, functions: 97, branches: 93 },
    },
  },
});
