import { test, expect, type Page } from "@playwright/test";
import fixtures from "../fixtures/api.json" with { type: "json" };

async function setup(
  page: Page,
  options: {
    offline?: boolean;
    writes?: boolean;
    empty?: boolean;
    delay?: boolean;
  } = {},
) {
  const state = { ...options, healthReads: 0, methods: [] as string[] };
  await page.route("https://tiles.openfreemap.org/**", (route) =>
    route.abort(),
  );
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (!path.startsWith("/api/")) return route.continue();
    state.methods.push(route.request().method());
    if (path === "/api/health") {
      state.healthReads++;
      if (state.delay) await new Promise((resolve) => setTimeout(resolve, 700));
    }
    if (state.offline) return route.abort();
    const body =
      path === "/api/health"
        ? {
            ...fixtures.health,
            local_demo_writes_enabled: state.writes ?? false,
            api_key: "test-hidden-setting",
            environment: { token: "test-hidden-setting" },
          }
        : path === "/api/facilities"
          ? state.empty
            ? []
            : fixtures.facilities
          : path === "/api/demo/scenarios"
            ? fixtures.scenarios
            : path === "/api/audit"
              ? []
              : undefined;
    await route.fulfill({
      status: body === undefined ? 404 : 200,
      contentType: "application/json",
      body: JSON.stringify(body ?? {}),
    });
  });
  return state;
}
async function settings(page: Page, mobile = false) {
  await page.goto("/");
  if (mobile)
    await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "System Settings & Integrations" }),
  ).toBeVisible();
}

test("healthy settings show accurate capabilities, configuration and no secrets", async ({
  page,
}) => {
  const state = await setup(page, { writes: true });
  await settings(page);
  await expect(page.getByText("API CONNECTED", { exact: true })).toBeVisible();
  await expect(page.getByTestId("write-capability")).toHaveText(
    "Enabled for local demo",
  );
  await expect(
    page.getByText("CURRENT FEED UNAVAILABLE", { exact: true }),
  ).toHaveCount(1);
  await expect(
    page.getByText("LOCAL BRIEFING AGENT · OPT-IN REQUIRED", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("LOCAL BRIEFING ADAPTER · NOT CHECKED HERE", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText("CONFIGURED · NOT CHECKED HERE", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("AUDIT READ AVAILABLE", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".settings-page")).toContainText(
    "jefferson-research",
  );
  await expect(page.locator(".settings-page")).toContainText("SIMULATED DEMO");
  await expect(page.locator("body")).not.toContainText("test-hidden-setting");
  expect(state.methods.every((method) => method === "GET")).toBe(true);
  await page.screenshot({
    path: "test-results/settings-desktop.png",
    fullPage: true,
  });
});

test("refresh retains last successful timestamp across failure and recovers read-only capability", async ({
  page,
}) => {
  const state = await setup(page, { writes: true });
  await settings(page);
  await expect(page.getByTestId("write-capability")).toHaveText(
    "Enabled for local demo",
  );
  const successfulAt = await page
    .getByTestId("last-successful-health")
    .textContent();
  state.offline = true;
  await page.getByRole("button", { name: "Refresh Status" }).click();
  await expect(
    page.getByText("API UNAVAILABLE", { exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId("last-successful-health")).toHaveText(
    successfulAt!,
  );
  await expect(page.getByTestId("write-capability")).toHaveText(
    "Unavailable · not verified",
  );
  await expect(
    page.getByText("AUDIT READ UNAVAILABLE", { exact: true }),
  ).toBeVisible();
  state.offline = false;
  state.writes = false;
  const before = state.healthReads;
  await page.getByRole("button", { name: "Refresh Status" }).click();
  await expect(page.getByTestId("write-capability")).toHaveText(
    "Disabled · read only",
  );
  expect(state.healthReads).toBeGreaterThan(before);
});

test("initial offline and empty catalog states remain navigable", async ({
  page,
}) => {
  const state = await setup(page, { offline: true });
  await settings(page);
  await expect(
    page.getByText("API UNAVAILABLE", { exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId("last-successful-health")).toHaveText(
    "No successful check this session",
  );
  await expect(
    page.getByText("Facility catalog unavailable. Refresh Status to retry."),
  ).toBeVisible();
  state.offline = false;
  state.empty = true;
  await page.getByRole("button", { name: "Refresh Status" }).click();
  await expect(
    page.getByText(
      "Jefferson Research Facility is unavailable in the returned catalog.",
    ),
  ).toBeVisible();
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Command center" }),
  ).toBeVisible();
});

test("loading state disables repeated status checks", async ({ page }) => {
  await setup(page, { delay: true });
  await settings(page);
  await expect(page.getByText("CHECKING API", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Refresh Status" }),
  ).toBeDisabled();
  await expect(page.getByText("API CONNECTED", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Refresh Status" }),
  ).toBeEnabled();
});

test("browser-local motion preference persists and respects operating-system changes", async ({
  page,
}) => {
  await setup(page);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await settings(page);
  const toggle = page.getByRole("checkbox", {
    name: "Reduce optional mascot motion in this browser",
  });
  await expect(toggle).not.toBeChecked();
  await toggle.check();
  await expect(page.locator(".app-shell")).toHaveAttribute(
    "data-reduced-motion",
    "true",
  );
  expect(
    await page
      .locator(".assistant-mascot")
      .first()
      .evaluate((el) => getComputedStyle(el).animationName),
  ).toBe("none");
  await settings(page);
  await expect(toggle).toBeChecked();
  await toggle.uncheck();
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.locator(".app-shell")).toHaveAttribute(
    "data-reduced-motion",
    "true",
  );
  await expect(page.getByText("Reduce motion", { exact: true })).toBeVisible();
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await expect(page.locator(".app-shell")).toHaveAttribute(
    "data-reduced-motion",
    "false",
  );
});

test("settings fit mobile and laptop layouts with functional navigation", async ({
  page,
}) => {
  await setup(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await settings(page, true);
  await expect(page.getByText("API CONNECTED", { exact: true })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/settings-mobile.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1366, height: 768 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  for (const name of [
    "Facilities",
    "Alerts",
    "Reports",
    "History",
    "Decision Queue",
    "Settings",
  ]) {
    await page.getByRole("button", { name, exact: true }).click();
    await expect(
      page.getByRole("heading", { name, exact: true }),
    ).toBeVisible();
  }
});
