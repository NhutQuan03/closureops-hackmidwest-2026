import { describe, expect, it } from "vitest";
import fixtures from "../fixtures/api.json";
import { decisionSchema, evaluationSchema } from "../../src/api/schemas";
import { savedEvaluations, summarizeDecisions } from "../../src/lib/reports";

const approved = decisionSchema.parse(fixtures.audit[0]);
const override = decisionSchema.parse({
  ...fixtures.audit[0],
  decision_id: `decision_${"b".repeat(32)}`,
  manager_action: "OVERRIDE",
  final_posture: "UNSCHEDULED_TELEWORK",
  override_reason: "Synthetic alternate arrangements confirmed.",
});
const missing = evaluationSchema.parse(fixtures.evaluations.missing_evidence);
const review = decisionSchema.parse({
  ...fixtures.audit[0],
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

describe("loaded audit report", () => {
  it("counts approval, override and review separately without treating review as a posture", () => {
    const report = summarizeDecisions([approved, override, review]);
    expect({
      total: report.total,
      approvals: report.approvals,
      overrides: report.overrides,
      reviews: report.reviews,
    }).toEqual({ total: 3, approvals: 1, overrides: 1, reviews: 1 });
    expect(report.transitions).toContainEqual({
      original: "FACILITY_CLOSURE",
      final: "UNSCHEDULED_TELEWORK",
      count: 1,
    });
    expect(report.transitions).toContainEqual({
      original: "None — review required",
      final: "None — review acknowledged",
      count: 1,
    });
  });
  it("counts distinct decision IDs, groups repeated transitions and sorts by decision time", () => {
    const later = {
      ...approved,
      decision_id: `decision_${"d".repeat(32)}`,
      decision_timestamp: "2026-10-11T18:00:00Z",
    };
    const report = summarizeDecisions([approved, later, approved]);
    expect(report.total).toBe(2);
    expect(report.decisions[0]).toEqual(later);
    expect(report.transitions).toEqual([
      { original: "FACILITY_CLOSURE", final: "FACILITY_CLOSURE", count: 2 },
    ]);
  });
  it("supports empty and capped loaded responses without claiming completeness", () => {
    expect(summarizeDecisions([]).total).toBe(0);
    const records = Array.from({ length: 100 }, (_, i) => ({
      ...approved,
      decision_id: `decision_${i.toString(16).padStart(32, "0")}`,
    }));
    expect(summarizeDecisions(records).approvals).toBe(100);
  });
  it("selects only matching saved evaluations and deduplicates audit/current snapshots", () => {
    expect(
      savedEvaluations(
        approved.evaluation,
        [approved, override, review],
        approved.facility_id,
      ),
    ).toHaveLength(2);
    expect(savedEvaluations(null, [approved], "missing-facility")).toEqual([]);
    expect(savedEvaluations(missing, null, missing.result.facility_id)).toEqual(
      [missing],
    );
  });
});
