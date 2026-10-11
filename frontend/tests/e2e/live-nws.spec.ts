import { test, expect, type Page } from "@playwright/test";
import fixtures from "../fixtures/api.json" with { type: "json" };
import { nationalFixture } from "../fixtures/national-nws";

async function setup(page: Page) {
  const state = {
    delayMs: 0,
    response: nationalFixture(),
    failure: false,
    malformed: false,
    reads: 0,
    methods: [] as string[],
  };
  await page.route("https://tiles.openfreemap.org/**", (route) =>
    route.abort(),
  );
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (!path.startsWith("/api/")) return route.continue();
    state.methods.push(route.request().method());
    if (path === "/api/nws/alerts/active") {
      state.reads++;
      if (state.delayMs)
        await new Promise((resolve) => setTimeout(resolve, state.delayMs));
      if (state.failure) return route.abort();
    }
    const body =
      path === "/api/health"
        ? { ...fixtures.health, local_demo_writes_enabled: false }
        : path === "/api/facilities"
          ? fixtures.facilities
          : path === "/api/demo/scenarios"
            ? fixtures.scenarios
            : path === "/api/audit"
              ? fixtures.audit
              : path === "/api/nws/alerts/active"
                ? state.malformed
                  ? { status: "LIVE" }
                  : state.response
                : {};
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Alerts", exact: true }).click();
  return state;
}
test("nationwide live evidence is separate from historical simulated facility evaluations", async ({
  page,
}) => {
  const state = await setup(page);
  expect(state.reads).toBe(0);
  const panel = page.locator(".live-nws-panel");
  await page.getByRole("button", { name: "Refresh Live NWS" }).click();
  await expect(panel.getByText("LIVE", { exact: true })).toHaveCount(2);
  await expect(panel).toContainText("Synthetic nationwide test warning");
  await expect(panel).toContainText("NOT ASSESSED");
  await expect(panel).toContainText("not a complete nationwide alert list");
  await expect(panel.getByRole("link").last()).toHaveAttribute(
    "href",
    state.response.alerts[0].source_url,
  );
  await expect(page.locator(".alerts-page")).toContainText(
    "Historical simulated evidence",
  );
  await expect(page.locator(".alerts-page")).toContainText(
    "RECORDED SIMULATED DEMO",
  );
  expect(state.methods.every((method) => method === "GET")).toBe(true);
  state.failure = true;
  await page.getByRole("button", { name: "Refresh Live NWS" }).click();
  await expect(panel.getByText("STALE", { exact: true })).toHaveCount(2);
  await expect(panel.getByText("LIVE", { exact: true })).toHaveCount(0);
  await expect(panel).toContainText("Synthetic nationwide test warning");
  await page.screenshot({
    path: "test-results/nws-stale-desktop.png",
    fullPage: true,
  });
  state.failure = false;
  state.delayMs = 1000;
  await page.getByRole("button", { name: "Refresh Live NWS" }).click();
  await expect(
    page.getByRole("button", { name: "Refresh Live NWS" }),
  ).toBeDisabled();
  await expect(panel.getByText("STALE", { exact: true })).toHaveCount(2);
  await expect(panel.getByText("LIVE", { exact: true })).toHaveCount(2);
});
test("empty, stale, unavailable and malformed collections make no false current claims", async ({
  page,
}) => {
  const state = await setup(page);
  const panel = page.locator(".live-nws-panel");
  state.malformed = true;
  await page.getByRole("button", { name: "Refresh Live NWS" }).click();
  await expect(panel.getByRole("alert")).toContainText("schema");
  await expect(panel.getByText("LIVE", { exact: true })).toHaveCount(0);
  state.malformed = false;
  state.response = {
    ...nationalFixture(),
    status: "NO_ACTIVE_ALERTS",
    alerts: [],
    collection_limited: false,
    examined_count: 0,
  };
  await page.getByRole("button", { name: "Refresh Live NWS" }).click();
  await expect(
    panel.getByText("NO_ACTIVE_ALERTS", { exact: true }),
  ).toBeVisible();
  state.response = {
    ...nationalFixture(),
    status: "STALE",
    alerts: [{ ...nationalFixture().alerts[0], status: "STALE" }],
  };
  // Both timestamps belong to the same response snapshot.
  state.response.alerts[0].retrieved_at = state.response.retrieved_at!;
  await page.getByRole("button", { name: "Refresh Live NWS" }).click();
  await expect(panel.getByText("STALE", { exact: true })).toHaveCount(2);
  state.response = {
    ...nationalFixture(),
    ok: false,
    status: "UNAVAILABLE",
    alerts: [],
    retrieved_at: null,
    fresh_until: null,
    error: "HTTP_ERROR",
  };
  await page.getByRole("button", { name: "Refresh Live NWS" }).click();
  await expect(panel.getByRole("alert")).toContainText(
    "unavailable or incomplete",
  );
  await expect(panel.getByText("LIVE", { exact: true })).toHaveCount(0);
});
test("loaded live evidence becomes stale with time and fits narrow layouts", async ({
  page,
}) => {
  await page.clock.install();
  await setup(page);
  await page.getByRole("button", { name: "Refresh Live NWS" }).click();
  await expect(
    page.locator(".live-nws-panel").getByText("LIVE", { exact: true }),
  ).toHaveCount(2);
  await page.clock.fastForward(360_000);
  await expect(
    page.locator(".live-nws-panel").getByText("STALE", { exact: true }),
  ).toHaveCount(2);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
