import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import fixtures from "../fixtures/api.json";
import { evaluationSchema } from "../../src/api/schemas";
import { EvidenceFeed } from "../../src/components/EvidenceFeed";

describe("saved source display", () => {
  it("keeps simulated evidence labeled and includes its original timestamp", () => {
    const evaluation = evaluationSchema.parse(
      fixtures.evaluations.severe_applicable_flood,
    );
    const html = renderToStaticMarkup(
      createElement(EvidenceFeed, { evaluation, onReview: () => {} }),
    );
    expect(html).toContain("SIMULATED DEMO");
    expect(html).toContain("2026-10-10T18:00:00Z");
    expect(html).toContain("USGS-00000000");
    expect(html).not.toContain("STALE · SAVED SNAPSHOT");
  });
  it("preserves an explicitly recorded STALE source state", () => {
    const evaluation = evaluationSchema.parse(fixtures.evaluations.normal);
    evaluation.evidence_snapshot.nws!.evidence_status = "STALE";
    const html = renderToStaticMarkup(
      createElement(EvidenceFeed, { evaluation, onReview: () => {} }),
    );
    expect(html).toContain("Snapshot state: STALE");
    expect(html).toContain("Not refreshed.");
  });
  it("never presents historical LIVE source state as refreshed live evidence", () => {
    const evaluation = evaluationSchema.parse(fixtures.evaluations.normal);
    evaluation.evidence_snapshot.nws!.evidence_status = "LIVE";
    const html = renderToStaticMarkup(
      createElement(EvidenceFeed, { evaluation, onReview: () => {} }),
    );
    expect(html).toContain("RECORDED LIVE · SAVED SNAPSHOT");
    expect(html).toContain("Snapshot state: LIVE");
    expect(html).toContain("Not refreshed.");
  });
});
