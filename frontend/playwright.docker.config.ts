import { defineConfig } from "@playwright/test";

// Verify the built images, without starting Vite or mocking API/provider traffic.
export default defineConfig({
  testDir: "./tests/browser-docker",
  outputDir: "../artifacts/docker/playwright",
  workers: 1,
  timeout: 120000,
  use: {
    baseURL: "http://127.0.0.1:8080",
    channel: "msedge",
    headless: true,
    viewport: { width: 1440, height: 900 },
    screenshot: "only-on-failure",
  },
});
