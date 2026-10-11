import { describe, expect, it } from "vitest";
import { api } from "../../src/api/client";

// Optional smoke checks against a running local Task 9A server. GET only.
describe("running local API", () => {
  it("validates health", async () => {
    expect((await api.health()).status).toBe("ok");
  });
  it("validates the canonical synthetic facility catalog", async () => {
    const facilities = await api.facilities();
    expect(facilities.map((f) => f.id)).toContain("jefferson-research");
    expect(facilities.every((f) => f.data_label === "SIMULATED DEMO")).toBe(
      true,
    );
  });
  it("validates the seven scenario catalog entries", async () => {
    const scenarios = await api.scenarios();
    expect(scenarios).toHaveLength(7);
    expect(
      scenarios.find((s) => s.scenario_id === "missing_evidence")
        ?.expected_recommendation,
    ).toBeNull();
  });
  it("validates saved audit records and retrieves their original evaluations", async () => {
    const records = await api.audit();
    expect(Array.isArray(records)).toBe(true);
    if (records[0]) {
      const evaluation = await api.evaluation(records[0].evaluation_id);
      expect(evaluation.result.recommendation).toBe(
        records[0].original_recommendation,
      );
    }
  });
});
