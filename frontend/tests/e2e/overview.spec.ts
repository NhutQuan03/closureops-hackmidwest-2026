import { expect, test, type Page } from "@playwright/test";
import fixtures from "../fixtures/api.json" with { type: "json" };

async function mockApi(
  page: Page,
  { offline = false, empty = false, invalid = false, audit = false } = {},
) {
  const methods: string[] = [];
  await page.route("https://tiles.openfreemap.org/**", (route) =>
    route.abort(),
  );
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (!path.startsWith("/api/")) return route.continue();
    methods.push(route.request().method());
    if (offline) return route.abort();
    let body: unknown;
    if (path === "/api/health")
      body = { ...fixtures.health, local_demo_writes_enabled: false };
    else if (path === "/api/facilities")
      body = invalid ? [{ id: "broken" }] : empty ? [] : fixtures.facilities;
    else if (path === "/api/demo/scenarios")
      body = empty ? [] : fixtures.scenarios;
    else if (path === "/api/audit") body = audit ? fixtures.audit : [];
    else if (path.startsWith("/api/evaluations/")) {
      body = Object.values(fixtures.evaluations).find((e) =>
        path.endsWith(e.evaluation_id),
      );
    }
    await route.fulfill({
      status: body === undefined ? 404 : 200,
      contentType: "application/json",
      headers: { "Access-Control-Allow-Origin": "http://127.0.0.1:5173" },
      body: JSON.stringify(body ?? {}),
    });
  });
  return methods;
}
async function openDashboard(page: Page) {
  await page.goto("/");
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Selected facility")).toHaveValue(
    "jefferson-research",
  );
}
async function loadSaved(page: Page, id: string) {
  await page.getByLabel("Load a saved evaluation").fill(id);
  await page.getByRole("button", { name: "Load", exact: true }).click();
}
async function noOverflow(page: Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
}

test("dashboard uses backend counts, unavailable metrics, and disabled manager controls", async ({
  page,
}) => {
  const methods = await mockApi(page);
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await openDashboard(page);
  await expect(
    page.getByRole("heading", { name: "Command center" }),
  ).toBeVisible();
  await expect(
    page
      .locator(".metric-card")
      .filter({ hasText: "Facilities represented" })
      .locator(".metric-value"),
  ).toHaveText("1");
  await expect(
    page
      .locator(".metric-card")
      .filter({ hasText: "Active alerts" })
      .locator(".metric-value"),
  ).toHaveText("Unavailable");
  await expect(
    page
      .locator(".metric-card")
      .filter({ hasText: "Evaluations pending review" })
      .locator(".metric-value"),
  ).toHaveText("Unavailable");
  await expect(
    page
      .locator(".metric-card")
      .filter({ hasText: "Manager-confirmed closures" })
      .locator(".metric-value"),
  ).toHaveText("0");
  await expect(
    page.getByRole("button", { name: "Approve", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Override", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Review Evidence", exact: true }),
  ).toBeDisabled();
  await expect(page.locator(".demo-banner")).toContainText("SIMULATED DEMO");
  await expect(
    page.getByText("Awaiting evaluation", { exact: true }),
  ).toBeVisible();
  const idleImage = page.locator(".recommendation-card .assistant-mascot img");
  await expect(idleImage).toHaveAttribute("src", "/mascot/snoopy-idle.png");
  await expect
    .poll(() =>
      idleImage.evaluate((image) => (image as HTMLImageElement).naturalWidth),
    )
    .toBeGreaterThan(0);
  await expect(
    page.getByText("Basemap unavailable.", { exact: false }),
  ).toBeVisible({ timeout: 20000 });
  const mapCard = page.locator(".map-card");
  await expect(mapCard).toContainText("SIMULATED DEMO");
  await expect(mapCard).toContainText("Risk unavailable");
  const facility = fixtures.facilities[0];
  await expect(mapCard.locator(".coordinates")).toContainText(
    `${facility.coordinates.latitude.toFixed(4)}° N`,
  );
  await expect(mapCard.locator(".coordinates")).toContainText(
    `${Math.abs(facility.coordinates.longitude).toFixed(4)}° W`,
  );
  await expect(
    mapCard.getByRole("button", { name: "Zoom in", exact: true }),
  ).toBeVisible();
  await expect(
    mapCard.getByRole("button", { name: "Zoom out", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", {
      name: "Select Jefferson Research Facility, SIMULATED DEMO location",
      exact: true,
    })
    .click();
  await expect(page.getByLabel("Selected facility")).toHaveValue(
    "jefferson-research",
  );
  await page.locator(".map-facility-label").click();
  await page.getByText("Demo scenario catalog", { exact: true }).click();
  await expect(
    page.getByText("REVIEW_REQUIRED · NO POSTURE").first(),
  ).toBeVisible();
  await page.getByText("Demo scenario catalog", { exact: true }).click();
  await noOverflow(page);
  await page.screenshot({
    path: "test-results/overview-desktop.png",
    fullPage: true,
  });
  expect(methods.length).toBeGreaterThanOrEqual(4);
  expect(methods.every((method) => method === "GET")).toBe(true);
  expect(pageErrors).toEqual([]);
});

test("vector basemap becomes ready and retains attribution and facility controls", async ({
  page,
}) => {
  await mockApi(page);
  let tilesRequested = 0;
  await page.route("https://tiles.openfreemap.org/**", async (route) => {
    if (new URL(route.request().url()).pathname === "/styles/dark") {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          version: 8,
          sources: {
            reference: {
              type: "vector",
              tiles: [
                "https://tiles.openfreemap.org/test-basemap/{z}/{x}/{y}.pbf",
              ],
              maxzoom: 0,
              attribution:
                '<a href="https://openfreemap.org">OpenFreeMap</a> © <a href="https://openmaptiles.org">OpenMapTiles</a> Data from <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
            },
          },
          layers: [
            {
              id: "background",
              type: "background",
              paint: { "background-color": "#17121e" },
            },
            {
              id: "water",
              type: "fill",
              source: "reference",
              "source-layer": "water",
            },
          ],
        }),
      });
    }
    // An empty protobuf tile tests the vector worker without adding geography.
    tilesRequested++;
    await route.fulfill({
      contentType: "application/x-protobuf",
      body: Buffer.alloc(0),
    });
  });
  await openDashboard(page);
  const mapCard = page.locator(".map-card");
  await expect(mapCard.locator(".facility-marker")).toBeVisible();
  await expect(mapCard.locator(".map-state")).toHaveCount(0, {
    timeout: 15000,
  });
  expect(tilesRequested).toBeGreaterThan(0);
  const attribution = mapCard.locator(".maplibregl-ctrl-attrib");
  if (
    !(await attribution
      .getByRole("link", { name: "OpenFreeMap", exact: true })
      .isVisible())
  ) {
    await attribution.locator("summary").click();
  }
  for (const name of ["OpenFreeMap", "OpenMapTiles", "OpenStreetMap"]) {
    await expect(
      attribution.getByRole("link", { name, exact: true }),
    ).toBeVisible();
  }
  await mapCard.getByRole("button", { name: "Zoom in", exact: true }).click();
  await mapCard.getByRole("button", { name: "Zoom out", exact: true }).click();
  await mapCard.getByRole("button", { name: "Recenter facility map" }).click();
  await mapCard.locator(".facility-marker").click();
  await expect(page.getByLabel("Selected facility")).toHaveValue(
    "jefferson-research",
  );
});

test("operational pages navigate and sidebar collapses", async ({ page }) => {
  await mockApi(page);
  await openDashboard(page);
  for (const name of ["Facilities", "Alerts", "Reports"]) {
    await page.getByRole("button", { name, exact: true }).click();
    await expect(
      page.getByRole("heading", { name, exact: true }),
    ).toBeVisible();
    await expect(page.locator(".demo-banner")).toBeVisible();
  }
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "System Settings & Integrations" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Decision Queue", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Evaluate demo scenario" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "History", exact: true }).click();
  await expect(
    page.getByText("No manager decisions recorded.", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await page.getByRole("button", { name: "Collapse sidebar" }).click();
  await expect(
    page.getByRole("button", { name: "Expand sidebar" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Expand sidebar" }).click();
  await expect(
    page.getByRole("button", { name: "Collapse sidebar" }),
  ).toBeVisible();
});

test("REVIEW_REQUIRED preserves no posture and evidence dialog works by keyboard", async ({
  page,
}) => {
  const methods = await mockApi(page);
  await openDashboard(page);
  await loadSaved(page, fixtures.evaluations.missing_evidence.evaluation_id);
  await expect(
    page.getByRole("heading", { name: "Manual review required" }),
  ).toBeVisible();
  await expect(
    page.getByText("REVIEW_REQUIRED", { exact: true }),
  ).toBeVisible();
  await expect(
    page.locator(".recommendation-card .assistant-mascot"),
  ).toHaveAttribute("data-state", "review_required");
  await expect(
    page.locator(".recommendation-card .assistant-mascot img"),
  ).toHaveAttribute("src", "/mascot/snoopy-idle.png");
  await expect(page.getByRole("heading", { name: "Remain open" })).toHaveCount(
    0,
  );
  await expect(
    page.getByRole("button", { name: "Approve", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Review Evidence" }).click();
  await expect(
    page.getByRole("dialog", { name: "Evaluation evidence" }),
  ).toBeVisible();
  await expect(
    page.getByText("Source freshness & attribution", { exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Review Evidence" }),
  ).toBeFocused();
  expect(methods.every((method) => method === "GET")).toBe(true);
});

test("closure recommendation is separate from confirmed closures", async ({
  page,
}) => {
  await mockApi(page);
  await openDashboard(page);
  await loadSaved(
    page,
    fixtures.evaluations.severe_applicable_flood.evaluation_id,
  );
  await expect(
    page.getByRole("heading", { name: "Facility closure", exact: true }),
  ).toBeVisible();
  await expect(
    page.locator(".recommendation-card .assistant-mascot"),
  ).toHaveAttribute("data-state", "high_risk");
  const highRiskImage = page.locator(
    ".recommendation-card .assistant-mascot img",
  );
  await expect(highRiskImage).toHaveAttribute(
    "src",
    "/mascot/snoopy-high-risk.png",
  );
  await expect
    .poll(() =>
      highRiskImage.evaluate(
        (image) => (image as HTMLImageElement).naturalWidth,
      ),
    )
    .toBeGreaterThan(0);
  await expect(
    page
      .locator(".metric-card")
      .filter({ hasText: "Manager-confirmed closures" })
      .locator(".metric-value"),
  ).toHaveText("0");
  await expect(
    page.getByText("Gauge height: 7 ft", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".recommendation-card")).toContainText(
    "PROTOTYPE - NOT OFFICIAL USDA POLICY",
  );
  await page.screenshot({
    path: "test-results/overview-evaluation.png",
    fullPage: true,
  });
});

test("confirmed closure count comes from actual finalized API records", async ({
  page,
}) => {
  await mockApi(page, { audit: true });
  await openDashboard(page);
  await expect(
    page
      .locator(".metric-card")
      .filter({ hasText: "Manager-confirmed closures" })
      .locator(".metric-value"),
  ).toHaveText("1");
});

test("offline API leaves dashboard and navigation usable", async ({ page }) => {
  await mockApi(page, { offline: true });
  await page.goto("/");
  await expect(page.getByText("API offline", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Local API unavailable.", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".metric-value.unknown")).toHaveCount(4);
  await expect(page.getByLabel("Selected facility")).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Approve", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "System Settings & Integrations" }),
  ).toBeVisible();
});

test("empty and invalid catalogs do not fabricate facilities", async ({
  page,
}) => {
  await mockApi(page, { empty: true });
  await page.goto("/");
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Selected facility")).toBeDisabled();
  await expect(
    page
      .locator(".metric-card")
      .filter({ hasText: "Facilities represented" })
      .locator(".metric-value"),
  ).toHaveText("0");
  await page.unroute("**/api/**");
  await mockApi(page, { invalid: true });
  await page.getByRole("button", { name: "Refresh API" }).click();
  await expect(
    page
      .locator(".metric-card")
      .filter({ hasText: "Facilities represented" })
      .locator(".metric-value"),
  ).toHaveText("Unavailable");
  await expect(page.getByRole("alert")).toContainText("expected schema");
});

test("mobile navigation, reduced motion, and narrow layouts", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await mockApi(page);
  await openDashboard(page);
  expect(
    await page
      .getByLabel("Selected facility")
      .evaluate((el) => el.getBoundingClientRect().width),
  ).toBeGreaterThan(170);
  await expect(
    page.getByRole("button", { name: "Open navigation" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Facilities", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Facility details" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Overview", exact: true })
    .click();
  await noOverflow(page);
  expect(
    await page
      .locator(".assistant-mascot")
      .first()
      .evaluate((el) => getComputedStyle(el).animationName),
  ).toBe("none");
  await page.screenshot({
    path: "test-results/overview-mobile.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 320, height: 700 });
  await noOverflow(page);
  await page.setViewportSize({ width: 768, height: 900 });
  await noOverflow(page);
  await page.setViewportSize({ width: 1366, height: 768 });
  await noOverflow(page);
});
