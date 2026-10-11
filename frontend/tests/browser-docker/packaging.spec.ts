import { expect, test } from "@playwright/test";
import { writeFile } from "node:fs/promises";
import { nationalAlertsSchema } from "../../src/api/schemas";

test("Nginx serves real API reads and rejects manager writes and inference", async ({
  request,
}) => {
  const healthResponse = await request.get("/api/health");
  expect(healthResponse.ok()).toBe(true);
  expect(await healthResponse.json()).toMatchObject({
    status: "ok",
    data_mode: "synthetic_demo",
    local_demo_writes_enabled: false,
    ai_briefing_enabled: false,
  });
  expect((await (await request.get("/api/facilities")).json()).length).toBe(1);
  expect((await (await request.get("/api/demo/scenarios")).json()).length).toBe(
    7,
  );
  expect(Array.isArray(await (await request.get("/api/audit")).json())).toBe(
    true,
  );
  for (const path of [
    "/api/evaluations",
    `/api/evaluations/eval_${"0".repeat(32)}/decisions`,
    `/api/evaluations/eval_${"0".repeat(32)}/ai-briefing`,
    `/api/decisions/dec_${"0".repeat(32)}/notification-plans`,
  ]) {
    const response = await request.post(path, { data: {} });
    expect(response.status()).toBe(403);
    expect(await response.json()).toMatchObject({
      error: { code: "CONTAINER_READ_ONLY" },
    });
  }
  const refresh = await request.get("/facilities");
  expect(refresh.ok()).toBe(true);
  expect(refresh.headers()["content-type"]).toContain("text/html");
  expect(await refresh.text()).toContain('<div id="root">');
  expect(refresh.headers()["content-security-policy"]).toContain(
    "https://tiles.openfreemap.org",
  );
});

test("production browser uses same origin, loads OpenFreeMap, and preserves navigation", async ({
  page,
}) => {
  const apiOrigins = new Set<string>();
  const errors: string[] = [];
  const mapResponses: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/api/")) apiOrigins.add(url.origin);
  });
  page.on("response", (response) => {
    if (
      response.ok() &&
      response.url().startsWith("https://tiles.openfreemap.org/")
    )
      mapResponses.push(response.url());
  });
  await page.goto("/");
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Selected facility")).toHaveValue(
    "jefferson-research",
  );
  await expect(
    page.getByRole("button", { name: "Approve", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Override", exact: true }),
  ).toBeDisabled();
  const map = page.locator(".map-card");
  await expect(map.locator(".facility-marker")).toBeVisible();
  await expect(map.locator(".map-state")).toHaveCount(0, { timeout: 60000 });
  expect(mapResponses.some((url) => url.endsWith("/styles/dark"))).toBe(true);
  expect(mapResponses.some((url) => url.includes(".pbf"))).toBe(true);
  const attribution = map.locator(".maplibregl-ctrl-attrib");
  if (
    !(await attribution
      .getByRole("link", { name: "OpenFreeMap", exact: true })
      .isVisible())
  )
    await attribution.locator("summary").click();
  for (const name of ["OpenFreeMap", "OpenMapTiles", "OpenStreetMap"])
    await expect(
      attribution.getByRole("link", { name: new RegExp(name) }),
    ).toBeVisible();
  await expect(map).toContainText("SIMULATED DEMO");
  await expect(map).toContainText("Risk unavailable");
  await expect(map).not.toContainText("API KEY REQUIRED");
  await page.screenshot({
    path: "../artifacts/docker/overview-desktop.png",
    fullPage: true,
  });
  for (const name of [
    "Facilities",
    "Decision Queue",
    "History",
    "Reports",
    "Settings",
  ])
    await page.getByRole("button", { name, exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "System Settings & Integrations" }),
  ).toBeVisible();
  await expect(
    page.getByText("Same origin · /api", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "../artifacts/docker/settings.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Facilities", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Facility details" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../artifacts/docker/facilities-mobile.png",
    fullPage: true,
  });
  expect([...apiOrigins]).toEqual(["http://127.0.0.1:8080"]);
  expect(errors).toEqual([]);
});

test("live NWS refresh reaches the actual public source through Docker", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Alerts", exact: true }).click();
  const responsePromise = page.waitForResponse(
    (response) => new URL(response.url()).pathname === "/api/nws/alerts/active",
    { timeout: 65000 },
  );
  await page.getByRole("button", { name: "Refresh Live NWS" }).click();
  const response = await responsePromise;
  expect(response.ok()).toBe(true);
  const feed = nationalAlertsSchema.parse(await response.json());
  const result = {
    status: feed.status,
    retrieved_at: feed.retrieved_at,
    examined_count: feed.examined_count,
    displayed: feed.alerts.length,
    error: feed.error,
    facility_applicability: feed.facility_applicability,
  };
  await writeFile(
    "../artifacts/docker/nws-result.json",
    JSON.stringify(result, null, 2),
  );
  console.log(JSON.stringify(result));
  await expect(page.locator(".live-nws-panel")).toContainText("NOT ASSESSED");
  await page.screenshot({
    path: "../artifacts/docker/nws-desktop.png",
    fullPage: true,
  });
  // Outbound failure is reported honestly; success must be fresh, not cached demo evidence.
  if (["UNAVAILABLE", "STALE"].includes(feed.status)) {
    test.skip(
      true,
      `Public NWS unavailable during Docker verification: ${feed.status}`,
    );
    return;
  }
  expect(["LIVE", "NO_ACTIVE_ALERTS"]).toContain(feed.status);
  for (const alert of feed.alerts) {
    expect(alert.source_url).toMatch(/^https:\/\/api\.weather\.gov\//);
    expect(alert.status).toBe("LIVE");
  }
});
