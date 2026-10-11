import { defineConfig } from "@playwright/test";
import baseConfig from "./playwright.config";

// Each run gets a new SQLite file. No previous verification records are touched.
const database = `backend/data/manager-workflow-test-${Date.now()}.sqlite3`;
export default defineConfig({
  ...baseConfig,
  testDir: "./tests/browser-workflow",
  outputDir: "test-results/workflow",
  timeout: 45000,
  webServer: [
    baseConfig.webServer as {
      command: string;
      url: string;
      reuseExistingServer: boolean;
      timeout: number;
    },
    {
      command:
        ".\\.venv\\Scripts\\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8002 --no-proxy-headers",
      cwd: "..",
      url: "http://127.0.0.1:8002/api/health",
      reuseExistingServer: false,
      env: {
        CLOSUREOPS_LOCAL_DEMO_WRITES: "true",
        CLOSUREOPS_DEMO_DATABASE: database,
      },
      timeout: 30000,
    },
    {
      command:
        ".\\.venv\\Scripts\\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8003 --no-proxy-headers",
      cwd: "..",
      url: "http://127.0.0.1:8003/api/health",
      reuseExistingServer: false,
      env: {
        CLOSUREOPS_LOCAL_DEMO_WRITES: "false",
        CLOSUREOPS_DEMO_DATABASE: database,
      },
      timeout: 30000,
    },
  ],
});
