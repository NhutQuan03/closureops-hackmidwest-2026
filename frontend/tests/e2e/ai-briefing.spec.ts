import { expect, test, type Page } from "@playwright/test";
import fixtures from "../fixtures/api.json" with { type: "json" };
import { evaluationSchema } from "../../src/api/schemas";
import { briefingFixture } from "../fixtures/ai-briefing";

async function setup(
  page: Page,
  enabled = true,
  scenario:
    | "severe_applicable_flood"
    | "missing_evidence"
    | "stale_evidence" = "severe_applicable_flood",
) {
  const evaluation = evaluationSchema.parse(fixtures.evaluations[scenario]);
  const state = {
    briefing: briefingFixture(evaluation),
    enabled,
    failure: false,
    hold: false,
    release: () => {},
    posts: [] as { path: string; body: unknown }[],
  };
  await page.route("https://tiles.openfreemap.org/**", (route) =>
    route.abort(),
  );
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (!path.startsWith("/api/")) return route.continue();
    if (request.method() === "POST")
      state.posts.push({ path, body: request.postDataJSON() });
    let body: unknown;
    if (path.endsWith("/ai-briefing")) {
      if (state.hold)
        await new Promise<void>((resolve) => {
          state.release = resolve;
        });
      if (state.failure) return route.abort();
      body = { ...state.briefing, secret: "hidden-test-config" };
    } else if (path === "/api/health")
      body = {
        ...fixtures.health,
        local_demo_writes_enabled: true,
        ai_briefing_enabled: state.enabled,
      };
    else if (path === "/api/facilities") body = fixtures.facilities;
    else if (path === "/api/demo/scenarios") body = fixtures.scenarios;
    else if (path === "/api/audit") body = [];
    else if (
      path === "/api/evaluations" ||
      path === `/api/evaluations/${evaluation.evaluation_id}`
    )
      body = evaluation;
    else if (path.endsWith("/decisions"))
      body = {
        ...fixtures.audit[0],
        evaluation,
        evaluation_id: evaluation.evaluation_id,
      };
    await route.fulfill({
      status: body === undefined ? 404 : 200,
      contentType: "application/json",
      body: JSON.stringify(body ?? {}),
    });
  });
  await page.goto("/");
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
  await page
    .getByLabel("Load a saved evaluation")
    .fill(evaluation.evaluation_id);
  await page.getByRole("button", { name: "Load", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name:
        scenario === "severe_applicable_flood"
          ? "Facility closure"
          : "Manual review required",
    }),
  ).toBeVisible();
  return state;
}

test("AI runs only on explicit request and preserves deterministic and human authority", async ({
  page,
}) => {
  const state = await setup(page);
  expect(state.posts).toEqual([]);
  state.hold = true;
  await page.getByRole("button", { name: "Generate AI Briefing" }).click();
  const panel = page.getByRole("region", { name: "AI-assisted explanation" });
  await expect(panel.getByRole("status")).toContainText(
    "Generating a briefing",
  );
  await expect(
    page.getByRole("button", { name: "Approve", exact: true }),
  ).toBeEnabled();
  await expect(
    page.getByRole("button", { name: "Generate AI Briefing" }),
  ).toBeDisabled();
  await expect.poll(() => state.posts.length).toBe(1);
  state.release();
  await expect(
    panel.getByText("VALIDATED agent execution", { exact: true }),
  ).toBeVisible();
  await expect(panel).toContainText("SIMULATED DEMO at evaluation");
  await expect(panel).toContainText(
    "AI-assisted validated briefing · deterministically composed from trusted evidence",
  );
  await expect(panel).toContainText("Human approval required");
  for (const title of [
    "Situation summary",
    "Operational implications",
    "Recommended response and rule rationale",
    "Suggested next steps",
    "Evidence limitations and provenance",
  ])
    await expect(
      panel.getByRole("heading", { name: title, exact: true }),
    ).toBeVisible();
  await expect(panel).toContainText(
    "7 ft gauge exceeds the 6 ft prototype telework threshold",
  );
  await expect(panel).toContainText(
    "standalone 8 ft closure threshold was not crossed",
  );
  await expect(
    panel
      .locator(".ai-briefing-badges")
      .getByText("FACILITY_CLOSURE", { exact: true }),
  ).toBeVisible();
  await expect(
    panel.getByText("Validation status", { exact: true }),
  ).not.toBeVisible();
  await expect(
    panel.getByText("Complete raw explanation", { exact: true }),
  ).not.toBeVisible();
  expect(await panel.innerText()).not.toMatch(
    /\b(None|null)\b|demo:nws|usgs:observation/,
  );
  await expect(panel).not.toContainText("hidden-test-config");
  expect(state.posts).toEqual([
    {
      path: `/api/evaluations/${state.briefing.evaluation_id}/ai-briefing`,
      body: {},
    },
  ]);
  await page.screenshot({
    path: "test-results/situation-briefing-mocked-desktop.png",
    fullPage: true,
  });
  await panel.screenshot({ path: "test-results/situation-briefing-panel.png" });
  await panel.getByText("Technical diagnostics", { exact: true }).click();
  await expect(
    panel.getByText("Validation status", { exact: true }),
  ).toBeVisible();
  await expect(panel).toContainText("Exact saved-result match confirmed");
  await panel.getByText("Complete raw explanation", { exact: true }).click();
  await expect(panel.locator(".ai-briefing-explanation p")).toBeVisible();
  await expect(panel.locator(".ai-briefing-explanation p")).toContainText(
    "observed None",
  );
  await panel.getByText("Technical diagnostics", { exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/situation-briefing-mocked-mobile.png",
    fullPage: true,
  });
});

test("fallback, unavailable credentials and timeout do not claim a successful AI briefing", async ({
  page,
}) => {
  const state = await setup(page);
  const panel = page.getByRole("region", { name: "AI-assisted explanation" });
  for (const [status, reason, validation] of [
    ["FALLBACK", "INVALID_MODEL_OUTPUT", "REJECTED"],
    ["UNAVAILABLE", "MISSING_CREDENTIALS", "NOT_RUN"],
    ["TIMEOUT", "MODEL_TIMEOUT", "NOT_RUN"],
  ] as const) {
    state.briefing = {
      ...state.briefing,
      status,
      reason,
      validation_status: validation,
      model_completed: status === "FALLBACK",
      tool_execution_confirmed: status === "FALLBACK",
      explanation_source: "DETERMINISTIC_FALLBACK",
    };
    await page.getByRole("button", { name: "Generate AI Briefing" }).click();
    await expect(panel.getByText(status, { exact: true })).toBeVisible();
    await expect(panel).toContainText("not a successful AI briefing");
    await expect(
      page.getByRole("heading", { name: "Facility closure" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Approve", exact: true }),
    ).toBeEnabled();
  }
});

test("mismatched output and offline responses remain errors, with no automatic retry", async ({
  page,
}) => {
  const state = await setup(page);
  state.briefing.authoritative_recommendation = "OPEN";
  const panel = page.getByRole("region", { name: "AI-assisted explanation" });
  await page.getByRole("button", { name: "Generate AI Briefing" }).click();
  await expect(panel.getByRole("alert")).toContainText("does not match");
  await expect(panel.getByText("VALIDATED", { exact: true })).toHaveCount(0);
  state.failure = true;
  await page.getByRole("button", { name: "Generate AI Briefing" }).click();
  await expect(panel.getByRole("alert")).toContainText("Cannot reach");
  expect(state.posts).toHaveLength(2);
});

test("server opt-in is required and older health responses remain safe", async ({
  page,
}) => {
  const state = await setup(page, false);
  await expect(
    page.getByRole("button", { name: "Generate AI Briefing" }),
  ).toBeDisabled();
  expect(state.posts).toHaveLength(0);
  await expect(
    page.getByRole("button", { name: "Approve", exact: true }),
  ).toBeEnabled();
});

test("older backend explanations remain collapsed while structured content is unavailable", async ({
  page,
}) => {
  const state = await setup(page);
  state.briefing.situation_briefing = null;
  await page.getByRole("button", { name: "Generate AI Briefing" }).click();
  const panel = page.getByRole("region", { name: "AI-assisted explanation" });
  await expect(panel).toContainText(
    "Structured briefing unavailable from this backend",
  );
  await expect(
    panel.getByText("Complete raw explanation", { exact: true }),
  ).not.toBeVisible();
  expect(await panel.innerText()).not.toMatch(/\b(None|null)\b|demo:nws/);
  await expect(
    page.getByRole("button", { name: "Approve", exact: true }),
  ).toBeEnabled();
});

for (const scenario of ["missing_evidence", "stale_evidence"] as const) {
  test(`${scenario} briefing requires review and makes no live or operating-posture claim`, async ({
    page,
  }) => {
    await setup(page, true, scenario);
    const panel = page.getByRole("region", { name: "AI-assisted explanation" });
    await page.getByRole("button", { name: "Generate AI Briefing" }).click();
    await expect(
      panel.getByText("VALIDATED agent execution", { exact: true }),
    ).toBeVisible();
    await expect(panel).toContainText(
      "REVIEW_REQUIRED; no recommended operating posture",
    );
    await expect(panel).toContainText("not current live facility conditions");
    await expect(panel).toContainText("has not selected an operating posture");
    expect(await panel.innerText()).not.toMatch(/\bLIVE\b|\b(None|null)\b/);
    await expect(
      page.getByRole("button", { name: "Acknowledge review" }),
    ).toBeEnabled();
  });
}
