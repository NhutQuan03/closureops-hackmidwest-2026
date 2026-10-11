import { defineConfig } from "vitest/config";
export default defineConfig({
  test: {
    include: ["tests/integration/**/*.test.ts"],
    environment: "node",
    testTimeout: 15000,
    env: {
      VITE_API_BASE_URL:
        process.env.CLOSUREOPS_TEST_API_URL || "http://127.0.0.1:8001",
    },
  },
});
