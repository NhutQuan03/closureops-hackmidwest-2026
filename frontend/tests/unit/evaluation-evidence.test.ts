import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import fixtures from "../fixtures/api.json";
import { evaluationSchema } from "../../src/api/schemas";
import { EvaluationEvidence } from "../../src/components/EvaluationEvidence";

describe("historical evidence details", () => {
  it("shows simulated warnings, observations, trend timestamps and original references", () => {
    const evaluation = evaluationSchema.parse(
      fixtures.evaluations.severe_applicable_flood,
    );
    const html = renderToStaticMarkup(
      createElement(EvaluationEvidence, { evaluation }),
    );
    expect(html).toContain("Historical simulated evidence");
    expect(html).toContain("Severity: Severe");
    expect(html).toContain("Recorded gauge trend");
    expect(html).toContain("Observed:");
    expect(html).toContain("Validity:");
    expect(html).toContain("Regional gauge readings do not establish");
    expect(html).not.toContain('href="demo:');
  });
  it.each(["LIVE", "STALE"] as const)(
    "preserves recorded %s public evidence while disclosing it is historical",
    (state) => {
      const evaluation = evaluationSchema.parse(fixtures.evaluations.normal);
      evaluation.data_mode = "LIVE_EVIDENCE";
      evaluation.evidence_snapshot.nws!.evidence_status = state;
      evaluation.evidence_snapshot.nws!.source_reference =
        "https://api.weather.gov/alerts/active?point=38.9517,-92.3341";
      evaluation.source_checks = [
        {
          source: "NWS",
          status: state,
          checked_at: null,
          retrieved_at: evaluation.result.evaluated_at,
        },
      ];
      const html = renderToStaticMarkup(
        createElement(EvaluationEvidence, { evaluation }),
      );
      expect(html).toContain("SAVED PUBLIC OBSERVATIONS");
      expect(html).toContain("Historical public evidence");
      expect(html).toContain(`RECORDED ${state}`);
      expect(html).toContain("No current live alert feed");
      expect(html).toContain('href="https://api.weather.gov/alerts/active');
    },
  );
  it("shows missing acquisition and rejects untrusted source links", () => {
    const evaluation = evaluationSchema.parse(
      fixtures.evaluations.missing_evidence,
    );
    evaluation.evidence_snapshot.nws = null;
    evaluation.source_timestamps[0].source_reference =
      "https://untrusted.example/instructions";
    const html = renderToStaticMarkup(
      createElement(EvaluationEvidence, { evaluation }),
    );
    expect(html).toContain("NWS evidence unavailable");
    expect(html).toContain("USGS observations unavailable");
    expect(html).not.toContain('href="https://untrusted.example');
    expect(html).not.toContain(">Inspect<");
  });
});
