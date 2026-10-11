import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { evaluationSchema, healthSchema } from "../../src/api/schemas";

const apiOrigin = "http://127.0.0.1:8001";

function assertNoCredentialFields(value: unknown): void {
  if (value && typeof value === "object") {
    for (const [key, child] of Object.entries(value)) {
      if (
        /^(api[_-]?key|access[_-]?token|refresh[_-]?token|password|private[_-]?key|aws[_-]?secret[_-]?access[_-]?key)$/i.test(
          key,
        )
      )
        throw new Error(
          "Unexpected credential field in browser API response (value suppressed).",
        );
      assertNoCredentialFields(child);
    }
  }
  if (
    typeof value === "string" &&
    /\bAKIA[0-9A-Z]{16}\b|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/.test(
      value,
    )
  )
    throw new Error(
      "Unexpected credential pattern in browser API response (value suppressed).",
    );
}

async function openLiveDashboard(page: Page) {
  const healthResponse = page.waitForResponse(`${apiOrigin}/api/health`);
  await page.goto("/");
  const health = await healthResponse;
  expect(health.status()).toBe(200);
  expect(healthSchema.parse(await health.json()).status).toBe("ok");
  expect(health.headers()["access-control-allow-origin"]).toBe(
    "http://127.0.0.1:5173",
  );
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Local API unavailable.", { exact: true }),
  ).toHaveCount(0);
  await expect(page.getByLabel("Selected facility")).toHaveValue(
    "jefferson-research",
  );
}

async function assertArtwork(page: Page, state: string, filename: string) {
  const mascot = page.locator(".recommendation-card .assistant-mascot");
  await expect(mascot).toHaveAttribute("data-state", state);
  const image = mascot.locator("img");
  await expect(image).toHaveAttribute("src", `/mascot/${filename}`);
  await expect
    .poll(() => image.evaluate((el) => (el as HTMLImageElement).naturalWidth))
    .toBeGreaterThan(0);
}

async function loadActualEvaluation(
  page: Page,
  status: "RECOMMENDATION_READY" | "REVIEW_REQUIRED",
) {
  // Only IDs are local. Evidence/results must come from the real running API.
  // Missing preparation or an unavailable/wrong server makes the check fail.
  const ids = JSON.parse(
    readFileSync(
      new URL(
        "../../../backend/data/command-center-verification.ids.json",
        import.meta.url,
      ),
      "utf8",
    ),
  ) as Record<string, string>;
  const id =
    ids[
      status === "REVIEW_REQUIRED"
        ? "missing_evidence"
        : "severe_applicable_flood"
    ];
  expect(id).toMatch(/^eval_[0-9a-f]{32}$/);
  const response = page.waitForResponse(`${apiOrigin}/api/evaluations/${id}`);
  await page.getByLabel("Load a saved evaluation").fill(id);
  await page.getByRole("button", { name: "Load", exact: true }).click();
  const evaluationResponse = await response;
  expect(evaluationResponse.status()).toBe(200);
  const payload: unknown = await evaluationResponse.json();
  assertNoCredentialFields(payload);
  return evaluationSchema.parse(payload);
}

test("real API connection, catalogs, synthetic map, and initial Snoopy artwork", async ({
  page,
}) => {
  const requests: { origin: string; path: string; method: string }[] = [];
  const errors: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/api/"))
      requests.push({
        origin: url.origin,
        path: url.pathname,
        method: request.method(),
      });
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await openLiveDashboard(page);
  await assertArtwork(page, "idle", "snoopy-idle.png");
  await expect(page.locator(".demo-banner")).toContainText("SIMULATED DEMO");
  await expect(page.locator(".map-facility-label")).toContainText(
    "Jefferson Research Facility",
  );
  await expect(page.locator(".map-context")).toContainText("SIMULATED DEMO");
  await expect(page.locator(".coordinates")).toContainText("38.9517");
  await expect(page.locator(".coordinates")).toContainText("92.3341");
  await page
    .getByRole("button", {
      name: "Select Jefferson Research Facility, SIMULATED DEMO location",
      exact: true,
    })
    .click();
  await expect(page.getByLabel("Selected facility")).toHaveValue(
    "jefferson-research",
  );
  await page.getByText("Demo scenario catalog", { exact: true }).click();
  await expect(page.locator(".scenario-list")).toContainText(
    "severe applicable flood",
  );
  await expect(page.locator(".scenario-list")).toContainText("REVIEW_REQUIRED");
  await page.getByText("Demo scenario catalog", { exact: true }).click();
  for (const action of ["Approve", "Override"])
    await expect(
      page.getByRole("button", { name: action, exact: true }),
    ).toBeDisabled();
  expect(requests.map((r) => r.path)).toEqual(
    expect.arrayContaining([
      "/api/health",
      "/api/facilities",
      "/api/demo/scenarios",
      "/api/audit",
    ]),
  );
  expect(
    requests.every((r) => r.origin === apiOrigin && r.method === "GET"),
  ).toBe(true);
  expect(errors).toEqual([]);
  for (const path of [
    "/api/health",
    "/api/facilities",
    "/api/demo/scenarios",
    "/api/audit",
  ]) {
    const response = await page.request.get(`${apiOrigin}${path}`);
    expect(response.status()).toBe(200);
    assertNoCredentialFields(await response.json());
  }
  await page.screenshot({
    path: "test-results/live/overview-idle.png",
    fullPage: true,
  });
});

test("saved simulated closure selects high-risk Snoopy and requires human approval", async ({
  page,
}) => {
  await openLiveDashboard(page);
  const evaluation = await loadActualEvaluation(page, "RECOMMENDATION_READY");
  expect(evaluation.data_mode).toBe("SIMULATED DEMO");
  expect(evaluation.result.recommendation).toBe("FACILITY_CLOSURE");
  expect(evaluation.result.evidence_sufficiency).toBe("SUFFICIENT");
  await expect(
    page.getByRole("heading", { name: "Facility closure", exact: true }),
  ).toBeVisible();
  await assertArtwork(page, "high_risk", "snoopy-high-risk.png");
  await expect(page.locator(".mascot-workflow-note")).toContainText(
    "Human approval required",
  );
  await expect(page.locator(".recommendation-card")).toContainText(
    "SIMULATED DEMO",
  );
  for (const action of ["Approve", "Override"])
    await expect(
      page.getByRole("button", { name: action, exact: true }),
    ).toBeDisabled();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "test-results/live/overview-high-risk.png",
    fullPage: true,
  });
});

test("real saved REVIEW_REQUIRED never becomes OPEN and evidence remains inspectable", async ({
  page,
}) => {
  await openLiveDashboard(page);
  const evaluation = await loadActualEvaluation(page, "REVIEW_REQUIRED");
  expect(evaluation.result.recommendation).toBeNull();
  await expect(
    page.getByRole("heading", { name: "Manual review required" }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Remain open" })).toHaveCount(
    0,
  );
  await assertArtwork(page, "review_required", "snoopy-idle.png");
  for (const action of ["Approve", "Override"])
    await expect(
      page.getByRole("button", { name: action, exact: true }),
    ).toBeDisabled();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "test-results/live/overview-review.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Review Evidence", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Evaluation evidence" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
});

test("real mobile dashboard has static reduced-motion artwork and usable navigation", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await openLiveDashboard(page);
  await assertArtwork(page, "idle", "snoopy-idle.png");
  expect(
    await page
      .locator(".recommendation-card .assistant-mascot")
      .evaluate((el) => getComputedStyle(el).animationName),
  ).toBe("none");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Facilities", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Facility details" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Overview", exact: true })
    .click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/live/overview-mobile.png",
    fullPage: true,
  });
});
