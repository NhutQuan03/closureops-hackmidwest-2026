import { expect, test } from "@playwright/test";
import { z } from "zod";
import {
  decisionSchema,
  facilitySchema,
  healthSchema,
} from "../../src/api/schemas";
import { summarizeDecisions } from "../../src/lib/reports";

test("operational pages display actual local API records without manager writes", async ({
  page,
}) => {
  const origin = "http://127.0.0.1:8001";
  const healthResponse = await page.request.get(`${origin}/api/health`);
  expect(healthResponse.ok()).toBe(true);
  expect(
    healthSchema.parse(await healthResponse.json()).local_demo_writes_enabled,
  ).toBe(false);
  const facilityResponse = await page.request.get(`${origin}/api/facilities`);
  const facilities = z
    .array(facilitySchema)
    .parse(await facilityResponse.json());
  const auditResponse = await page.request.get(`${origin}/api/audit?limit=100`);
  const records = z.array(decisionSchema).parse(await auditResponse.json());
  const summary = summarizeDecisions(records);
  const current = records.find(
    (record) => record.facility_id === facilities[0]?.id,
  )?.evaluation;
  const methods: string[] = [];
  const errors: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/"))
      methods.push(request.method());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Facilities", exact: true }).click();
  await expect(page.locator(".facilities-page")).toContainText(
    facilities[0].source,
  );
  await expect(page.locator(".facilities-page")).toContainText(
    "SIMULATED DEMO",
  );
  await expect(page.locator(".facilities-page .facility-marker")).toBeVisible();
  await expect(
    page.getByText("Loading reference map tiles", { exact: false }),
  ).toHaveCount(0, { timeout: 20000 });
  await page.screenshot({
    path: "test-results/live/facilities-api.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Alerts", exact: true }).click();
  await expect(page.locator(".alerts-page")).toContainText(
    "nationwide NWS feed above is separate",
  );
  if (current)
    await expect(page.locator(".alerts-page")).toContainText(
      current.evaluation_id,
    );
  else
    await expect(
      page.getByRole("heading", { name: "No saved evaluation available" }),
    ).toBeVisible();
  await page.screenshot({
    path: "test-results/live/alerts-api.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Reports", exact: true }).click();
  const report = page.locator(".reports-page");
  for (const [label, value] of [
    ["Loaded finalized decisions", summary.total],
    ["Approvals", summary.approvals],
    ["Overrides", summary.overrides],
    ["Review acknowledgments", summary.reviews],
  ] as const) {
    await expect(
      report
        .locator(".report-metric")
        .filter({ hasText: label })
        .locator("strong"),
    ).toHaveText(String(value));
  }
  if (summary.total) {
    await expect(report.locator(".decision-inspection")).toContainText(
      "Decision ID:",
    );
    await expect(
      report.locator(".decision-inspection [role='status']"),
    ).not.toContainText("Loading");
    await report
      .getByRole("button", {
        name: `Inspect ${summary.decisions[0].decision_id}`,
        exact: true,
      })
      .click();
    await expect(
      page.getByRole("heading", { name: "History", exact: true }),
    ).toBeVisible();
    await expect(page.locator(".decision-inspection")).toContainText(
      summary.decisions[0].decision_id,
    );
    await page.getByRole("button", { name: "Reports", exact: true }).click();
    await expect(report.locator(".decision-inspection")).toContainText(
      "Decision ID:",
    );
    await expect(
      report.locator(".decision-inspection [role='status']"),
    ).not.toContainText("Loading");
  }
  await page.screenshot({
    path: "test-results/live/reports-api.png",
    fullPage: true,
  });
  expect(methods.length).toBeGreaterThan(0);
  expect(methods.every((method) => method === "GET")).toBe(true);
  expect(errors).toEqual([]);
});
