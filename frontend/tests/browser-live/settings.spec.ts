import { expect, test } from "@playwright/test";
import { healthSchema } from "../../src/api/schemas";

test("Settings reflects the actual local health capability and audit read", async ({
  page,
}) => {
  const response = await page.request.get("http://127.0.0.1:8001/api/health");
  expect(response.ok()).toBe(true);
  const health = healthSchema.parse(await response.json());
  const methods: string[] = [];
  const errors: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/"))
      methods.push(request.method());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(page.getByText("API CONNECTED", { exact: true })).toBeVisible();
  await expect(page.getByTestId("write-capability")).toHaveText(
    health.local_demo_writes_enabled
      ? "Enabled for local demo"
      : "Disabled · read only",
  );
  await expect(page.locator(".settings-page")).toContainText(
    "SIMULATED DEMO (synthetic_demo)",
  );
  await expect(page.locator(".settings-page")).toContainText(
    "Jefferson Research Facility",
  );
  await expect(
    page.getByText("AUDIT READ AVAILABLE", { exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId("last-successful-health")).not.toHaveText(
    "No successful check this session",
  );
  await page.getByRole("button", { name: "Refresh Status" }).click();
  await expect(page.getByText("API CONNECTED", { exact: true })).toBeVisible();
  await expect(
    page.getByText("AUDIT READ AVAILABLE", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/live/settings-api.png",
    fullPage: true,
  });
  expect(methods.every((method) => method === "GET")).toBe(true);
  expect(errors).toEqual([]);
});
