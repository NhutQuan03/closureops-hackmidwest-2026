import { afterEach, expect, it, vi } from "vitest";
import { publicApiBaseUrl } from "../../src/lib/settings";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.resetModules();
});

it("an explicitly empty Docker base sends same-origin requests, with no credentials", async () => {
  vi.stubEnv("VITE_API_BASE_URL", "");
  vi.resetModules();
  const { api, API_BASE_URL, validateApiBaseUrl } =
    await import("../../src/api/client");
  const fetch = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({
        status: "ok",
        service: "closureops-api",
        data_mode: "synthetic_demo",
        local_demo_writes_enabled: false,
        ai_briefing_enabled: false,
      }),
      { headers: { "Content-Type": "application/json" } },
    ),
  );
  vi.stubGlobal("fetch", fetch);
  expect(API_BASE_URL).toBe("");
  expect(validateApiBaseUrl("")).toBe("");
  expect(publicApiBaseUrl("")).toBe("Same origin · /api");
  await api.health();
  expect(fetch.mock.calls[0][0]).toBe("/api/health");
  expect(fetch.mock.calls[0][1].credentials).toBe("omit");
});
