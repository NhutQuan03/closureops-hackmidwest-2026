import { defineConfig } from "@playwright/test";
import baseConfig from "./playwright.config";

export default defineConfig({
  ...baseConfig,
  testDir: "./tests/browser-live",
  outputDir: "test-results/live",
  timeout: 45000,
});
