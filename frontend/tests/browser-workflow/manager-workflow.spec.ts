import { expect, test, type Page } from "@playwright/test";
import {
  decisionSchema,
  evaluationSchema,
  notificationPlanSchema,
} from "../../src/api/schemas";

async function open(page: Page, port = 8002) {
  // Forward to the isolated real server, preserving the browser's approved
  // 5173 Origin. Responses and all business/security logic remain real.
  await page.route("**/api/**", (route) => {
    const url = new URL(route.request().url());
    if (!url.pathname.startsWith("/api/")) return route.continue();
    url.port = String(port);
    return route.continue({ url: url.toString() });
  });
  await page.goto("/");
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
}
async function evaluate(page: Page, scenario = "severe_applicable_flood") {
  await page.getByLabel("1. Choose demo scenario").selectOption(scenario);
  const response = page.waitForResponse(
    (r) =>
      new URL(r.url()).pathname === "/api/evaluations" &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Evaluate demo scenario" }).click();
  const saved = await response;
  expect(saved.status()).toBe(201);
  return evaluationSchema.parse(await saved.json());
}
async function confirm(page: Page, evaluationId: string) {
  const response = page.waitForResponse((r) =>
    r.url().endsWith(`/api/evaluations/${evaluationId}/decisions`),
  );
  await page.getByRole("button", { name: "Confirm action" }).click();
  const saved = await response;
  expect(saved.status()).toBe(201);
  return decisionSchema.parse(await saved.json());
}

test("complete real approval and notification workflow persists across reload", async ({
  page,
}) => {
  const errors: string[] = [];
  const posts: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (r) => {
    if (r.method() === "POST") posts.push(new URL(r.url()).pathname);
  });
  await open(page);
  const evaluation = await evaluate(page);
  expect(evaluation.result.recommendation).toBe("FACILITY_CLOSURE");
  await expect(
    page.locator(".recommendation-card .assistant-mascot"),
  ).toHaveAttribute("data-state", "high_risk");
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  const decision = await confirm(page, evaluation.evaluation_id);
  expect(decision.manager.display_name).toBe("Synthetic Demo Manager");
  await expect(page.locator(".saved-decision")).toContainText(
    decision.decision_id,
  );
  const response = page.waitForResponse((r) =>
    r.url().endsWith("/notification-plans"),
  );
  await page
    .getByRole("button", { name: "Prepare simulated notifications" })
    .click();
  const planResponse = await response;
  expect(planResponse.status()).toBe(201);
  const plan = notificationPlanSchema.parse(await planResponse.json());
  expect([
    plan.total_assigned,
    plan.total_scheduled,
    plan.group_counts.TELEWORK_ELIGIBLE,
    plan.group_counts.STANDARD_ONSITE,
    plan.group_counts.ESSENTIAL_PERSONNEL,
    plan.total_unscheduled,
  ]).toEqual([54, 47, 31, 10, 6, 7]);
  expect(
    plan.messages.every(
      (m) => m.route === "simulated" && m.status === "GENERATED_SIMULATED",
    ),
  ).toBe(true);
  expect(
    plan.messages.find((m) => m.group === "ESSENTIAL_PERSONNEL")!.message,
  ).toContain("before any travel or facility entry");
  await expect(page.locator(".notification-plan")).toContainText(
    "No real notifications sent",
  );
  await page.screenshot({
    path: "test-results/workflow/approved-notification-plan.png",
    fullPage: true,
  });
  await page.reload();
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Load a saved evaluation")).toHaveValue(
    evaluation.evaluation_id,
  );
  await page.getByRole("button", { name: "Load", exact: true }).click();
  await expect(page.locator(".saved-decision")).toContainText(
    decision.decision_id,
  );
  await expect(page.locator(".notification-plan")).toContainText(
    plan.notification_plan_id,
  );
  await expect(
    page.getByRole("button", { name: "Approve", exact: true }),
  ).toBeDisabled();
  await expect(
    page.locator(".recommendation-card .assistant-mascot"),
  ).toHaveAttribute("data-state", "high_risk");
  await page.getByRole("button", { name: "History", exact: true }).click();
  await page
    .getByRole("button", {
      name: `Inspect ${decision.decision_id}`,
      exact: true,
    })
    .click();
  await expect(page.locator(".decision-inspection")).toContainText(
    "Final manager posture: FACILITY_CLOSURE",
  );
  await expect(page.locator(".decision-inspection")).toContainText(
    plan.notification_plan_id,
  );
  await page
    .getByText("Evidence snapshot references & source timestamps", {
      exact: true,
    })
    .click();
  await expect(page.locator(".decision-inspection")).toContainText("Observed:");
  expect(posts).toHaveLength(3);
  expect(errors).toEqual([]);
});

test("real override records reason and preserves high-risk evidence", async ({
  page,
}) => {
  await open(page);
  const evaluation = await evaluate(page);
  await page.getByRole("button", { name: "Override", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Confirm action" }),
  ).toBeDisabled();
  await page
    .getByLabel("Final manager posture", { exact: true })
    .selectOption("UNSCHEDULED_TELEWORK");
  await page
    .getByLabel("Override reason (required)")
    .fill("Synthetic management verified remote arrangements.");
  const decision = await confirm(page, evaluation.evaluation_id);
  expect(decision.original_recommendation).toBe("FACILITY_CLOSURE");
  expect(decision.final_posture).toBe("UNSCHEDULED_TELEWORK");
  expect(decision.override_reason).toBe(
    "Synthetic management verified remote arrangements.",
  );
  await expect(
    page.locator(".recommendation-card .assistant-mascot"),
  ).toHaveAttribute("data-state", "high_risk");
});

test("real review acknowledgment has no posture or notification eligibility", async ({
  page,
}) => {
  await open(page);
  const evaluation = await evaluate(page, "missing_evidence");
  for (const action of ["Approve", "Override"])
    await expect(
      page.getByRole("button", { name: action, exact: true }),
    ).toBeDisabled();
  await page.getByRole("button", { name: "Acknowledge review" }).click();
  const decision = await confirm(page, evaluation.evaluation_id);
  expect(decision.final_posture).toBeNull();
  expect(decision.original_recommendation).toBeNull();
  await expect(page.locator(".saved-decision")).toContainText(
    "ACKNOWLEDGE_REVIEW",
  );
  await expect(
    page.getByRole("button", { name: "Prepare simulated notifications" }),
  ).toHaveCount(0);
  await expect(
    page.locator(".recommendation-card .assistant-mascot"),
  ).toHaveAttribute("data-state", "review_required");
});

test("real read-only server denies direct writes and exposes no active write controls", async ({
  page,
}) => {
  await open(page, 8003);
  await expect(page.locator(".demo-banner")).toContainText("READ ONLY");
  await expect(
    page.getByRole("button", { name: "Evaluate demo scenario" }),
  ).toBeDisabled();
  const response = await page.request.post(
    "http://127.0.0.1:8003/api/evaluations",
    { data: { facility_id: "jefferson-research", scenario_id: "normal" } },
  );
  expect(response.status()).toBe(403);
  expect((await response.json()).error.code).toBe("DEMO_WRITES_DISABLED");
});

test("mobile workflow and keyboard confirmation remain usable", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page);
  const evaluation = await evaluate(page, "normal");
  await page.getByRole("button", { name: "Approve", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "Approve", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await confirm(page, evaluation.evaluation_id);
  await expect(
    page.locator(".recommendation-card .assistant-mascot"),
  ).toHaveAttribute("data-state", "resolved");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/workflow/mobile-manager-workflow.png",
    fullPage: true,
  });
});
