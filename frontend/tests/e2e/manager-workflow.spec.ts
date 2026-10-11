import { expect, test, type Page } from "@playwright/test";
import fixtures from "../fixtures/api.json" with { type: "json" };

async function setup(
  page: Page,
  options: {
    readonly?: boolean;
    existing?: boolean;
    lostDecision?: boolean;
    lostPlan?: boolean;
    review?: boolean;
    offline?: boolean;
    revokeWrites?: boolean;
  } = {},
) {
  const evaluation = options.review
    ? fixtures.evaluations.missing_evidence
    : fixtures.evaluations.severe_applicable_flood;
  let decision: unknown = null;
  let plan: unknown = options.existing ? fixtures.notification_plan : null;
  const posts: { path: string; body: unknown }[] = [];
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (!path.startsWith("/api/")) return route.continue();
    let body: unknown;
    if (request.method() === "POST") {
      posts.push({ path, body: request.postDataJSON() });
      if (options.offline) return route.abort();
      if (path === "/api/evaluations") body = evaluation;
      else if (path.endsWith("/decisions")) {
        const input = request.postDataJSON();
        decision = {
          ...fixtures.audit[0],
          evaluation_id: evaluation.evaluation_id,
          evaluation,
          evidence_snapshot: evaluation.evidence_snapshot,
          source_timestamps: evaluation.source_timestamps,
          evaluation_status: evaluation.result.evaluation_status,
          original_recommendation: evaluation.result.recommendation,
          manager_action: input.action,
          final_posture:
            input.action === "ACKNOWLEDGE_REVIEW"
              ? null
              : (input.selected_posture ?? evaluation.result.recommendation),
          override_reason: input.reason ?? null,
        };
        if (options.lostDecision) return route.abort();
        body = decision;
      } else if (path.endsWith("/notification-plans")) {
        plan = fixtures.notification_plan;
        if (options.lostPlan) return route.abort();
        body = plan;
      }
    } else {
      if (path === "/api/health")
        body = {
          ...fixtures.health,
          local_demo_writes_enabled:
            !options.readonly && !(options.revokeWrites && posts.length > 0),
        };
      else if (path === "/api/facilities") body = fixtures.facilities;
      else if (path === "/api/demo/scenarios") body = fixtures.scenarios;
      else if (path === "/api/audit") body = decision ? [decision] : [];
      else if (path.endsWith("/notification-plan")) body = plan ?? undefined;
      else if (path.startsWith("/api/decisions/")) body = decision;
      else if (path.startsWith("/api/evaluations/")) body = evaluation;
    }
    await route.fulfill({
      status:
        body === undefined ? 404 : request.method() === "POST" ? 201 : 200,
      contentType: "application/json",
      body: JSON.stringify(body ?? {}),
    });
  });
  await page.goto("/");
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
  return { posts, evaluation };
}
async function evaluate(page: Page) {
  await page.getByRole("button", { name: "Evaluate demo scenario" }).click();
  await expect(
    page.locator(".recommendation-card .record-id").first(),
  ).toContainText("Evaluation ID: eval_");
}
async function approve(page: Page) {
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("Action: APPROVE");
  await page.getByRole("button", { name: "Confirm action" }).click();
  await expect(page.locator(".saved-decision")).toContainText(
    "Saved decision: APPROVE",
  );
}

test("scenario, explicit approval, backend notification groups and persisted audit", async ({
  page,
}) => {
  const { posts, evaluation } = await setup(page);
  await evaluate(page);
  expect(posts[0].body).toEqual({
    facility_id: "jefferson-research",
    scenario_id: "severe_applicable_flood",
  });
  await expect(
    page.getByRole("heading", { name: "Facility closure", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".recommendation-card")).toContainText(
    "SUFFICIENT",
  );
  await expect(
    page.locator(".recommendation-card .assistant-mascot"),
  ).toHaveAttribute("data-state", "high_risk");
  expect(posts).toHaveLength(1);
  await approve(page);
  expect(posts[1].body).toEqual({ action: "APPROVE" });
  await expect(
    page.getByRole("button", { name: "Approve", exact: true }),
  ).toBeDisabled();
  await expect(
    page.locator(".recommendation-card .assistant-mascot img"),
  ).toHaveAttribute("src", "/mascot/snoopy-high-risk.png");
  await page
    .getByRole("button", { name: "Prepare simulated notifications" })
    .click();
  await expect(page.locator(".notification-plan")).toContainText(
    "GENERATED_SIMULATED",
  );
  for (const count of ["54", "47", "31", "10", "6", "7"])
    await expect(page.locator(".impact-counts")).toContainText(count);
  await expect(page.locator(".notification-plan")).toContainText(
    "No real notifications sent",
  );
  await page.getByText("ESSENTIAL PERSONNEL · 6", { exact: false }).click();
  await expect(page.locator(".notification-plan")).toContainText(
    "Essential designation alone does not authorize entry",
  );
  await page.getByRole("button", { name: "History", exact: true }).click();
  await page.getByRole("button", { name: /^Inspect decision_/ }).click();
  await expect(page.locator(".decision-inspection")).toContainText(
    evaluation.evaluation_id,
  );
  await expect(page.locator(".decision-inspection")).toContainText(
    "Original deterministic recommendation: FACILITY_CLOSURE",
  );
  await expect(page.locator(".decision-inspection")).toContainText(
    "GENERATED_SIMULATED",
  );
  expect(posts.map((p) => p.path)).toEqual([
    "/api/evaluations",
    `/api/evaluations/${evaluation.evaluation_id}/decisions`,
    `/api/decisions/${fixtures.audit[0].decision_id}/notification-plans`,
  ]);
});

test("override requires a reason and preserves the original recommendation", async ({
  page,
}) => {
  const { posts } = await setup(page);
  await evaluate(page);
  await page.getByRole("button", { name: "Override", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Confirm action" }),
  ).toBeDisabled();
  await page.getByLabel("Override reason (required)").fill("   ");
  await expect(
    page.getByRole("button", { name: "Confirm action" }),
  ).toBeDisabled();
  await page
    .getByLabel("Final manager posture", { exact: true })
    .selectOption("UNSCHEDULED_TELEWORK");
  await page
    .getByLabel("Override reason (required)")
    .fill("Synthetic manager confirmed alternate arrangements.");
  await page.getByRole("button", { name: "Confirm action" }).click();
  await expect(page.locator(".saved-decision")).toContainText(
    "UNSCHEDULED_TELEWORK",
  );
  await expect(
    page.getByRole("heading", { name: "Facility closure", exact: true }),
  ).toBeVisible();
  await expect(
    page.locator(".recommendation-card .assistant-mascot"),
  ).toHaveAttribute("data-state", "high_risk");
  expect(posts[1].body).toEqual({
    action: "OVERRIDE",
    selected_posture: "UNSCHEDULED_TELEWORK",
    reason: "Synthetic manager confirmed alternate arrangements.",
  });
});

test("review can only be acknowledged and has no posture or notifications", async ({
  page,
}) => {
  const { posts } = await setup(page, { review: true });
  await page
    .getByLabel("1. Choose demo scenario")
    .selectOption("missing_evidence");
  await evaluate(page);
  await expect(
    page.getByRole("heading", { name: "Manual review required" }),
  ).toBeVisible();
  for (const action of ["Approve", "Override"])
    await expect(
      page.getByRole("button", { name: action, exact: true }),
    ).toBeDisabled();
  await page.getByRole("button", { name: "Acknowledge review" }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "None — acknowledgment records review only",
  );
  await page.getByRole("button", { name: "Confirm action" }).click();
  await expect(page.locator(".saved-decision")).toContainText(
    "ACKNOWLEDGE_REVIEW",
  );
  await expect(
    page.getByRole("button", { name: "Prepare simulated notifications" }),
  ).toHaveCount(0);
  await expect(
    page.locator(".recommendation-card .assistant-mascot"),
  ).toHaveAttribute("data-state", "review_required");
  expect(posts[1].body).toEqual({ action: "ACKNOWLEDGE_REVIEW" });
});

test("read-only backend keeps all write controls disabled", async ({
  page,
}) => {
  const { posts, evaluation } = await setup(page, { readonly: true });
  await expect(
    page.getByRole("button", { name: "Evaluate demo scenario" }),
  ).toBeDisabled();
  await page
    .getByLabel("Load a saved evaluation")
    .fill(evaluation.evaluation_id);
  await page.getByRole("button", { name: "Load", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Facility closure", exact: true }),
  ).toBeVisible();
  for (const action of ["Approve", "Override"])
    await expect(
      page.getByRole("button", { name: action, exact: true }),
    ).toBeDisabled();
  expect(posts).toEqual([]);
});

test("existing notification plan is retrieved without duplicate generation", async ({
  page,
}) => {
  const { posts } = await setup(page, { existing: true });
  await evaluate(page);
  await approve(page);
  await page
    .getByRole("button", { name: "Prepare simulated notifications" })
    .click();
  await expect(page.locator(".notification-plan")).toContainText(
    fixtures.notification_plan.notification_plan_id,
  );
  expect(posts).toHaveLength(2);
});

test("lost write responses recover saved decision and plan without repeating submissions", async ({
  page,
}) => {
  const { posts } = await setup(page, { lostDecision: true, lostPlan: true });
  await evaluate(page);
  await approve(page);
  await page
    .getByRole("button", { name: "Prepare simulated notifications" })
    .click();
  await expect(page.locator(".notification-plan")).toContainText(
    "GENERATED_SIMULATED",
  );
  expect(posts).toHaveLength(3);
});

test("scenario network failure leaves the UI functional and cannot approve", async ({
  page,
}) => {
  const { posts } = await setup(page, { offline: true });
  await page.getByRole("button", { name: "Evaluate demo scenario" }).click();
  await expect(page.locator(".scenario-workflow [role=alert]")).toContainText(
    "No evaluation was confirmed",
  );
  await expect(
    page.getByRole("button", { name: "Approve", exact: true }),
  ).toBeDisabled();
  expect(posts).toHaveLength(1);
});

test("rechecks authorization before the human POST when backend writes are revoked", async ({
  page,
}) => {
  const { posts } = await setup(page, { revokeWrites: true });
  await evaluate(page);
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await page.getByRole("button", { name: "Confirm action" }).click();
  await expect(page.locator(".manager-workflow [role=alert]")).toContainText(
    "Local demo writes are disabled",
  );
  await expect(
    page.getByRole("button", { name: "Approve", exact: true }),
  ).toBeDisabled();
  await expect(page.locator(".saved-decision")).toHaveCount(0);
  expect(posts).toHaveLength(1);
});

test("rapid duplicate scenario clicks create only one evaluation", async ({
  page,
}) => {
  const { posts } = await setup(page);
  await page.getByRole("button", { name: "Evaluate demo scenario" }).dblclick();
  await expect(
    page.getByRole("heading", { name: "Facility closure", exact: true }),
  ).toBeVisible();
  expect(posts).toHaveLength(1);
});
