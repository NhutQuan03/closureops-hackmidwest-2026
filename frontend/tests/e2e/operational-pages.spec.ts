import { expect, test, type Page } from "@playwright/test";
import fixtures from "../fixtures/api.json" with { type: "json" };
import {
  decisionSchema,
  evaluationSchema,
  type Decision,
} from "../../src/api/schemas";

const approval = decisionSchema.parse(fixtures.audit[0]);
const override = decisionSchema.parse({
  ...approval,
  decision_id: `decision_${"b".repeat(32)}`,
  manager_action: "OVERRIDE",
  final_posture: "UNSCHEDULED_TELEWORK",
  override_reason: "Synthetic alternate arrangements confirmed.",
});
const missing = evaluationSchema.parse(fixtures.evaluations.missing_evidence);
const review = decisionSchema.parse({
  ...approval,
  decision_id: `decision_${"c".repeat(32)}`,
  evaluation_id: missing.evaluation_id,
  evaluation: missing,
  evidence_snapshot: missing.evidence_snapshot,
  source_timestamps: missing.source_timestamps,
  evaluation_status: missing.result.evaluation_status,
  original_recommendation: null,
  final_posture: null,
  manager_action: "ACKNOWLEDGE_REVIEW",
});

async function setup(
  page: Page,
  {
    audit = [] as Decision[],
    offline = false,
    emptyFacilities = false,
    invalidAudit = false,
    planStatus = 200,
    mismatchPlan = false,
  } = {},
) {
  const requests: string[] = [];
  await page.route("https://tiles.openfreemap.org/**", (route) =>
    route.abort(),
  );
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (!path.startsWith("/api/")) return route.continue();
    requests.push(`${request.method()} ${path}`);
    if (offline) return route.abort();
    let status = 200;
    let body: unknown;
    if (path === "/api/health")
      body = { ...fixtures.health, local_demo_writes_enabled: false };
    else if (path === "/api/facilities")
      body = emptyFacilities ? [] : fixtures.facilities;
    else if (path === "/api/demo/scenarios") body = fixtures.scenarios;
    else if (path === "/api/audit")
      body = invalidAudit ? [{ decision_id: "broken" }] : audit;
    else if (path.endsWith("/notification-plan")) {
      status = planStatus;
      const decision = audit.find((d) => path.includes(d.decision_id));
      body = {
        ...fixtures.notification_plan,
        decision_id: decision?.decision_id,
        final_posture: mismatchPlan ? "OPEN" : decision?.final_posture,
      };
    } else if (path.startsWith("/api/decisions/"))
      body = audit.find((d) => path.endsWith(d.decision_id));
    else if (path.startsWith("/api/evaluations/"))
      body = Object.values(fixtures.evaluations).find((e) =>
        path.endsWith(e.evaluation_id),
      );
    else status = 404;
    await route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(body ?? {}),
    });
  });
  await page.goto("/");
  await expect(
    page.getByText(offline ? "API offline" : "API connected", { exact: true }),
  ).toBeVisible();
  return requests;
}
async function navigate(page: Page, name: string) {
  if (await page.getByRole("button", { name: "Open navigation" }).isVisible()) {
    await page.getByRole("button", { name: "Open navigation" }).click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name, exact: true })
      .click();
  } else await page.getByRole("button", { name, exact: true }).click();
}
async function load(page: Page, id: string) {
  await navigate(page, "Overview");
  await page.getByLabel("Load a saved evaluation").fill(id);
  await page.getByRole("button", { name: "Load", exact: true }).click();
  await expect(page.locator(".recommendation-card")).toContainText(id);
}

test("Facilities preserves synthetic selection, map, catalog configuration and scenario navigation", async ({
  page,
}) => {
  const requests = await setup(page);
  await navigate(page, "Facilities");
  const details = page.locator(".facilities-page");
  await expect(details).toContainText("Jefferson Research Facility");
  await expect(details).toContainText("SIMULATED DEMO");
  await expect(details).toContainText("38.9517, -92.3341");
  await expect(details).toContainText("Initial synthetic catalog status");
  await expect(details).toContainText(
    fixtures.facilities[0].operating_status_scope,
  );
  await expect(details).toContainText(
    "Detailed gauge association and thresholds are unavailable",
  );
  await expect(details.locator(".facility-marker")).toBeVisible();
  await details.locator(".facility-marker").click();
  await page.getByLabel("Selected facility").selectOption("jefferson-research");
  await expect(page.getByLabel("Selected facility")).toHaveValue(
    "jefferson-research",
  );
  await details.getByRole("button", { name: "Open Decision Queue" }).click();
  await expect(
    page.getByRole("heading", { name: "Decision Queue", exact: true }),
  ).toBeVisible();
  await load(page, fixtures.evaluations.severe_applicable_flood.evaluation_id);
  await navigate(page, "Facilities");
  await expect(details).toContainText("ACCESS_ROUTE");
  await expect(details).toContainText("USGS-00000000");
  await details.getByRole("button", { name: "Inspect saved evidence" }).click();
  await expect(
    page.getByRole("heading", { name: "Alerts", exact: true }),
  ).toBeVisible();
  expect(requests.every((request) => request.startsWith("GET "))).toBe(true);
  await page.screenshot({
    path: "test-results/alerts-simulated.png",
    fullPage: true,
  });
});

test("Alerts derives historical simulated warnings from loaded audit with trend, validity and references", async ({
  page,
}) => {
  await setup(page, { audit: [approval] });
  await navigate(page, "Alerts");
  const alerts = page.locator(".alerts-page");
  await expect(alerts).toContainText("Historical simulated evidence");
  await expect(alerts).toContainText("Flood Warning");
  await expect(alerts).toContainText("Severity: Severe");
  await expect(alerts).toContainText("Recorded gauge trend");
  await expect(alerts).toContainText("RECORDED SIMULATED DEMO");
  await expect(alerts).toContainText("Validity:");
  await expect(alerts).toContainText("Source reference:");
  await expect(alerts).toContainText(
    "Regional gauge readings do not establish facility",
  );
  await expect(alerts).toContainText("No current live alert feed");
  await expect(alerts.getByText("LIVE", { exact: true })).toHaveCount(0);
});

test("Alerts covers missing, stale and no-active-alert evidence without changing reported provenance", async ({
  page,
}) => {
  await setup(page);
  await load(page, fixtures.evaluations.missing_evidence.evaluation_id);
  await navigate(page, "Alerts");
  const alerts = page.locator(".alerts-page");
  await expect(alerts).toContainText("USGS observations unavailable");
  await expect(alerts).toContainText("INSUFFICIENT");
  await load(page, fixtures.evaluations.stale_evidence.evaluation_id);
  await navigate(page, "Alerts");
  await expect(alerts).toContainText("SIMULATED DEMO");
  await expect(alerts).toContainText("REVIEW_NWS_FRESHNESS");
  await expect(alerts).toContainText("REVIEW_GAGE_FRESHNESS");
  await load(page, fixtures.evaluations.normal.evaluation_id);
  await navigate(page, "Alerts");
  await expect(alerts).toContainText("NO_ACTIVE_ALERTS");
  await expect(alerts).toContainText("No active alerts in snapshot");
  await expect(alerts).toContainText("Historical simulated evidence");
});

test("Reports uses loaded approval, override and review records and inspects original history", async ({
  page,
}) => {
  const requests = await setup(page, { audit: [approval, override, review] });
  await navigate(page, "Reports");
  const reports = page.locator(".reports-page");
  for (const [label, value] of [
    ["Loaded finalized decisions", "3"],
    ["Approvals", "1"],
    ["Overrides", "1"],
    ["Review acknowledgments", "1"],
  ]) {
    await expect(
      reports
        .locator(".report-metric")
        .filter({ hasText: label })
        .locator("strong"),
    ).toHaveText(value);
  }
  await expect(reports).toContainText(
    "only the available loaded records (up to 100)",
  );
  await expect(reports.locator("table")).toContainText("FACILITY_CLOSURE");
  await expect(reports.locator("table")).toContainText("UNSCHEDULED_TELEWORK");
  await expect(reports.locator("table")).toContainText(
    "None — review acknowledged",
  );
  await page
    .getByLabel("Decision for employee impact")
    .selectOption(override.decision_id);
  await expect(reports.locator(".notification-plan")).toContainText(
    "GENERATED_SIMULATED",
  );
  await expect(reports.locator(".notification-plan")).toContainText(
    "No real notifications sent",
  );
  await expect(
    reports.locator(".impact-counts").filter({ hasText: "Scheduled" }),
  ).toContainText("47");
  await page
    .getByLabel("Decision for employee impact")
    .selectOption(review.decision_id);
  await expect(reports).toContainText(
    "Not eligible: review acknowledgment has no operating posture",
  );
  await expect(reports.locator(".notification-plan")).toHaveCount(0);
  expect(
    requests.some((request) =>
      request.includes(`${review.decision_id}/notification-plan`),
    ),
  ).toBe(false);
  await reports
    .getByRole("button", {
      name: `Inspect ${override.decision_id}`,
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("heading", { name: "History", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".decision-inspection")).toContainText(
    override.override_reason!,
  );
  expect(requests.every((request) => request.startsWith("GET "))).toBe(true);
});

test("empty catalogs and history show useful page states", async ({ page }) => {
  await setup(page, { emptyFacilities: true });
  await navigate(page, "Facilities");
  await expect(
    page.getByRole("heading", { name: "No facilities returned" }),
  ).toBeVisible();
  await navigate(page, "Alerts");
  await expect(
    page.getByRole("heading", { name: "No saved evaluation available" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Choose a demo scenario" }).click();
  await expect(
    page.getByRole("button", { name: "Evaluate demo scenario" }),
  ).toBeDisabled();
  await navigate(page, "Reports");
  await expect(
    page.getByRole("heading", { name: "No finalized decisions loaded" }),
  ).toBeVisible();
  await expect(
    page.locator(".report-metric").first().locator("strong"),
  ).toHaveText("0");
});

test("offline and malformed audit responses remain unavailable instead of zero", async ({
  page,
}) => {
  await setup(page, { offline: true });
  for (const screen of ["Facilities", "Alerts", "Reports"]) {
    await navigate(page, screen);
    await expect(
      page.getByRole("heading", { name: screen, exact: true }),
    ).toBeVisible();
  }
  await expect(
    page.getByRole("heading", { name: "Report unavailable" }),
  ).toBeVisible();
  await expect(page.locator(".report-metric")).toHaveCount(0);
  await page.unroute("**/api/**");
  await setup(page, { invalidAudit: true });
  await navigate(page, "Reports");
  await expect(page.locator(".reports-page")).toContainText("expected schema");
  await expect(page.locator(".report-metric")).toHaveCount(0);
});

for (const planStatus of [404, 503]) {
  test(`notification plan ${planStatus} supplies no fabricated employee counts`, async ({
    page,
  }) => {
    await setup(page, { audit: [approval], planStatus });
    await navigate(page, "Reports");
    await expect(page.locator(".reports-page")).toContainText(
      planStatus === 404
        ? "No notification plan recorded"
        : "Notification status unavailable",
    );
    await expect(page.locator(".reports-page .impact-counts")).toHaveCount(0);
  });
}
test("mismatched notification posture is rejected in Reports", async ({
  page,
}) => {
  await setup(page, { audit: [approval], mismatchPlan: true });
  await navigate(page, "Reports");
  await expect(page.locator(".reports-page")).toContainText(
    "does not match the persisted manager decision",
  );
  await expect(page.locator(".reports-page .notification-plan")).toHaveCount(0);
});

test("new screens are readable at laptop and narrow widths with all core navigation", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await setup(page, { audit: [approval, override, review] });
  for (const width of [1440, 1366, 768, 390, 320]) {
    await page.setViewportSize({ width, height: width < 500 ? 844 : 900 });
    for (const name of [
      "Facilities",
      "Alerts",
      "Reports",
      "Overview",
      "Decision Queue",
      "History",
    ]) {
      await navigate(page, name);
      await expect(
        page.getByRole("heading", {
          name: name === "Overview" ? "Command center" : name,
          exact: true,
        }),
      ).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      ).toBe(true);
      if (
        width === 1440 &&
        ["Facilities", "Alerts", "Reports"].includes(name)
      ) {
        if (name === "Facilities")
          await expect(
            page.locator(".facilities-page .facility-marker"),
          ).toBeVisible();
        if (name === "Reports")
          await expect(
            page.locator(".reports-page .notification-plan"),
          ).toBeVisible();
        await page.screenshot({
          path: `test-results/${name.toLowerCase()}-desktop.png`,
          fullPage: true,
        });
      }
      if (width === 390 && ["Facilities", "Alerts", "Reports"].includes(name))
        await page.screenshot({
          path: `test-results/${name.toLowerCase()}-mobile.png`,
          fullPage: true,
        });
    }
  }
  expect(errors).toEqual([]);
});
