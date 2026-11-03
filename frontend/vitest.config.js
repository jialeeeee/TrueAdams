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
      // Every line and branch is tested. Code that can't be reached is marked with
      // `/* v8 ignore next */` and the reason, as the backend uses "# pragma: no cover".
      thresholds: { statements: 100, lines: 100, functions: 100, branches: 100 },
    },
  },
});
