import { expect, test } from "@playwright/test";
import { nationalAlertsSchema } from "../../src/api/schemas";

test("actual national NWS collection renders without affecting saved simulated decisions", async ({
  page,
}) => {
  // A separate read-only local server loads the new route without restarting the user's demo server.
  const nationalOrigin =
    process.env.CLOSUREOPS_NWS_VERIFY_ORIGIN ?? "http://127.0.0.1:8001";
  if (nationalOrigin !== "http://127.0.0.1:8001") {
    await page.route("http://127.0.0.1:8001/api/nws/alerts/active", (route) =>
      route.continue({ url: `${nationalOrigin}/api/nws/alerts/active` }),
    );
  }
  const methods: string[] = [];
  const errors: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/"))
      methods.push(request.method());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page.getByRole("button", { name: "Alerts", exact: true }).click();
  const responsePromise = page.waitForResponse(
    (response) => new URL(response.url()).pathname === "/api/nws/alerts/active",
  );
  await page.getByRole("button", { name: "Refresh Live NWS" }).click();
  const response = await responsePromise;
  expect(response.ok()).toBe(true);
  const feed = nationalAlertsSchema.parse(await response.json());
  expect(["LIVE", "NO_ACTIVE_ALERTS"]).toContain(feed.status);
  const panel = page.locator(".live-nws-panel");
  await expect(panel).toContainText("NOT ASSESSED");
  if (feed.alerts.length) {
    await expect(panel).toContainText(feed.alerts[0].event);
    await expect(panel.getByText("LIVE", { exact: true })).toHaveCount(
      feed.alerts.length + 1,
    );
  } else
    await expect(
      panel.getByText("NO_ACTIVE_ALERTS", { exact: true }),
    ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Saved evidence & alerts" }),
  ).toBeVisible();
  console.log(
    JSON.stringify({
      status: feed.status,
      retrieved_at: feed.retrieved_at,
      examined_count: feed.examined_count,
      displayed: feed.alerts.length,
      events: feed.alerts.map((alert) => alert.event),
    }),
  );
  await page.screenshot({
    path: "test-results/live/nws-actual-desktop.png",
    fullPage: true,
  });
  await panel.screenshot({ path: "test-results/live/nws-actual-feed.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/live/nws-actual-mobile.png",
    fullPage: true,
  });
  expect(methods.every((method) => method === "GET")).toBe(true);
  expect(errors).toEqual([]);
});
