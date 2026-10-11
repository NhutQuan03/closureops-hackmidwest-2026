import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import fixtures from "../fixtures/api.json";
import { healthSchema, facilitySchema } from "../../src/api/schemas";
import { SettingsPage } from "../../src/components/SettingsPage";
import { AssistantMascot } from "../../src/components/AssistantMascot";
import { MotionContext } from "../../src/hooks/MotionPreference";
import { integrationStatuses, publicApiBaseUrl } from "../../src/lib/settings";
import type { Resource } from "../../src/hooks/useCommandCenter";
import type { Decision, Health } from "../../src/api/schemas";

const ready = <T>(data: T): Resource<T> => ({
  status: "ready",
  data,
  error: null,
  checkedAt: "2026-10-11T18:00:00Z",
  successfulAt: "2026-10-11T18:00:00Z",
});
const offline = <T>(): Resource<T> => ({
  status: "error",
  data: null,
  error: "Local API unavailable.",
  checkedAt: "2026-10-11T18:10:00Z",
  successfulAt: null,
});
function render(health: Resource<Health>, empty = false) {
  return renderToStaticMarkup(
    createElement(SettingsPage, {
      health,
      facilities: ready(
        empty ? [] : fixtures.facilities.map((f) => facilitySchema.parse(f)),
      ),
      audit: ready<Decision[]>([]),
      onRefresh: () => {},
    }),
  );
}

describe("system settings data integrity", () => {
  it.each([true, false])(
    "displays server-owned write capability %s with authorization caveats",
    (enabled) => {
      const markup = render(
        ready(
          healthSchema.parse({
            ...fixtures.health,
            local_demo_writes_enabled: enabled,
          }),
        ),
      );
      expect(markup).toContain(
        enabled ? "Enabled for local demo" : "Disabled · read only",
      );
      expect(markup).toContain(
        "do not establish authentication or authorization",
      );
      expect(markup).toContain("SIMULATED DEMO (synthetic_demo)");
      expect(markup).toContain("jefferson-research");
      expect(markup).toContain("No real notifications are sent");
    },
  );
  it("shows unavailable and never-successful states without inferring write access", () => {
    const markup = render(offline(), true);
    expect(markup).toContain("API UNAVAILABLE");
    expect(markup).toContain("Unavailable · not verified");
    expect(markup).toContain("No successful check this session");
    expect(markup).toContain("Jefferson Research Facility is unavailable");
  });
  it("does not display unknown health configuration or URL credentials", () => {
    const markup = render(
      ready(
        healthSchema.parse({
          ...fixtures.health,
          api_key: "test-only-hidden-value",
          environment: { token: "test-only-hidden-value" },
        }),
      ),
    );
    expect(markup).not.toContain("test-only-hidden-value");
    expect(
      publicApiBaseUrl(
        "https://demo:password@example.com/base?token=hidden#private",
      ),
    ).toBe("https://example.com/base");
    expect(publicApiBaseUrl("invalid")).toBe("Invalid API URL");
    expect(publicApiBaseUrl("javascript:alert(1)")).toBe("Invalid API URL");
  });
  it("labels known configuration without claiming external live connectivity", () => {
    const statuses = integrationStatuses(ready<Decision[]>([]));
    expect(statuses).toHaveLength(6);
    expect(statuses.slice(0, 2).map((s) => s.status)).toEqual([
      "NATIONWIDE READ AVAILABLE · NOT CHECKED HERE",
      "CURRENT FEED UNAVAILABLE",
    ]);
    expect(statuses[2].status).toBe("LOCAL BRIEFING AGENT · OPT-IN REQUIRED");
    expect(statuses[3].status).toBe(
      "LOCAL BRIEFING ADAPTER · NOT CHECKED HERE",
    );
    expect(statuses[4].status).toBe("CONFIGURED · NOT CHECKED HERE");
    expect(statuses[5].status).toBe("AUDIT READ AVAILABLE");
    expect(integrationStatuses(offline())[5].status).toBe(
      "AUDIT READ UNAVAILABLE",
    );
  });
  it("uses static replacement mascot artwork when local reduced motion is effective", () => {
    const markup = renderToStaticMarkup(
      createElement(
        MotionContext.Provider,
        {
          value: {
            preferReducedMotion: true,
            systemReducedMotion: false,
            reducedMotion: true,
            storageUnavailable: false,
            setPreferReducedMotion: () => {},
          },
        },
        createElement(AssistantMascot, {
          state: "idle",
          assets: {
            idle: {
              static: "/test-static.png",
              animated: "/test-animated.gif",
            },
          },
        }),
      ),
    );
    expect(markup).toContain("/test-static.png");
    expect(markup).not.toContain("/test-animated.gif");
  });
});
