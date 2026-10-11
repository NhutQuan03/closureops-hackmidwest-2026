import { afterEach, describe, expect, it, vi } from "vitest";
import fixtures from "../fixtures/api.json";
import { api } from "../../src/api/client";
import { aiBriefingSchema, evaluationSchema } from "../../src/api/schemas";
import { briefingFixture } from "../fixtures/ai-briefing";

const evaluation = evaluationSchema.parse(
  fixtures.evaluations.severe_applicable_flood,
);
const health = {
  ...fixtures.health,
  local_demo_writes_enabled: true,
  ai_briefing_enabled: true,
};
const response = (body: unknown) =>
  new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
  });
afterEach(() => vi.unstubAllGlobals());

describe("explicit AI briefing requests", () => {
  it("sends only an empty body to the persisted ID after rechecking local capability", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response(health))
      .mockResolvedValueOnce(
        response({
          ...briefingFixture(evaluation),
          api_key: "hidden-test-field",
        }),
      );
    vi.stubGlobal("fetch", fetch);
    const result = await api.generateBriefing(evaluation);
    expect(fetch.mock.calls[1][0]).toBe(
      `http://127.0.0.1:8001/api/evaluations/${evaluation.evaluation_id}/ai-briefing`,
    );
    expect(fetch.mock.calls[1][1]).toMatchObject({
      method: "POST",
      body: "{}",
      credentials: "omit",
    });
    expect(JSON.stringify(result)).not.toContain("hidden-test-field");
  });
  it("makes no inference request if opt-in is missing or revoked", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(response({ ...health, ai_briefing_enabled: false }));
    vi.stubGlobal("fetch", fetch);
    await expect(api.generateBriefing(evaluation)).rejects.toMatchObject({
      status: 403,
    });
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it.each([
    "authoritative_recommendation",
    "evaluation_id",
    "facility_id",
    "data_mode",
    "evidence_references",
  ])("rejects a changed %s", async (field) => {
    const altered = {
      ...briefingFixture(evaluation),
      [field]:
        field === "authoritative_recommendation"
          ? "OPEN"
          : field === "evaluation_id"
            ? `eval_${"b".repeat(32)}`
            : field === "facility_id"
              ? "other"
              : field === "data_mode"
                ? "LIVE_EVIDENCE"
                : [],
    };
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response(health))
      .mockResolvedValueOnce(response(altered));
    vi.stubGlobal("fetch", fetch);
    await expect(api.generateBriefing(evaluation)).rejects.toThrow(
      "does not match",
    );
  });
  it("does not let fallback or missing tool execution claim a validated AI run", () => {
    const result = briefingFixture(evaluation);
    expect(
      aiBriefingSchema.safeParse({ ...result, tool_execution_confirmed: false })
        .success,
    ).toBe(false);
    expect(
      aiBriefingSchema.safeParse({ ...result, status: "FALLBACK" }).success,
    ).toBe(false);
    expect(
      aiBriefingSchema.safeParse({ ...result, human_approval_required: false })
        .success,
    ).toBe(false);
  });
  it("does not retry provider failures or disclose error bodies", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response(health))
      .mockResolvedValueOnce(
        new Response("PRIVATE_TEST_ERROR", { status: 504 }),
      );
    vi.stubGlobal("fetch", fetch);
    await expect(api.generateBriefing(evaluation)).rejects.toThrow(
      "API request failed (504)",
    );
    expect(fetch).toHaveBeenCalledTimes(2);
  });
  it("loads five backend-composed sections with the correct combined flood rationale", () => {
    const result = briefingFixture(evaluation);
    const sections = result.situation_briefing!;
    expect(Object.keys(sections)).toHaveLength(5);
    expect(sections.recommended_response).toContain(
      "7 ft gauge exceeds the 6 ft prototype telework threshold",
    );
    expect(sections.recommended_response).toContain(
      "standalone 8 ft closure threshold was not crossed",
    );
    expect(sections.evidence_limitations).toContain("SIMULATED DEMO");
    expect(Object.values(sections).join(" ")).not.toMatch(/\b(None|null)\b/);
    expect(
      aiBriefingSchema.safeParse({
        ...result,
        situation_briefing: { ...sections, arbitrary_model_prose: "Close now" },
      }).success,
    ).toBe(false);
  });
  it.each([
    "missing_evidence",
    "stale_evidence",
    "conflicting_evidence",
  ] as const)("retains review and simulated provenance for %s", (scenario) => {
    const evaluation = evaluationSchema.parse(fixtures.evaluations[scenario]);
    const result = briefingFixture(evaluation);
    expect(result.authoritative_recommendation).toBeNull();
    expect(result.situation_briefing!.recommended_response).toContain(
      "REVIEW_REQUIRED",
    );
    expect(result.situation_briefing!.evidence_limitations).toContain(
      "not current live facility conditions",
    );
  });
  it("accepts older responses without using the raw explanation as the concise briefing", () => {
    const { situation_briefing, ...older } = briefingFixture(evaluation);
    expect(situation_briefing).not.toBeNull();
    expect(aiBriefingSchema.parse(older).situation_briefing).toBeNull();
  });
});
