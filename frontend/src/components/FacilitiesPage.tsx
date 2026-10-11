import { lazy, Suspense } from "react";
import type { Evaluation, Facility, Scenario } from "../api/schemas";
import type { Resource } from "../hooks/useCommandCenter";
import { formatTime } from "../lib/utils";
import { SourceLink } from "./EvidenceFeed";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader } from "./ui/card";

const FacilityMap = lazy(() => import("./FacilityMap"));

export function FacilitiesPage({
  resource,
  selected,
  evaluation,
  scenarios,
  onSelect,
  onEvaluate,
  onAlerts,
}: {
  resource: Resource<Facility[]>;
  selected: Facility | null;
  evaluation: Evaluation | null;
  scenarios: Resource<Scenario[]>;
  onSelect: (id: string) => void;
  onEvaluate: () => void;
  onAlerts: () => void;
}) {
  const exposure = evaluation?.evidence_snapshot.exposure;
  return (
    <div className="operational-page facilities-page">
      {resource.status === "loading" && (
        <p role="status" className="page-notice">
          Loading facility catalog…
        </p>
      )}
      {resource.error && (
        <p role="alert" className="api-error">
          Facility details unavailable. {resource.error} Use Refresh API to
          retry.
        </p>
      )}
      {resource.status === "ready" && !resource.data?.length && (
        <Card className="page-empty">
          <h2>No facilities returned</h2>
          <p>
            The catalog contains no selectable facilities. Use Refresh API to
            retry.
          </p>
        </Card>
      )}
      {selected && (
        <div className="facility-detail-grid">
          <div className="page-stack">
            <Card>
              <CardHeader>
                <h2>Facility details</h2>
                <Badge tone="purple">{selected.data_label}</Badge>
              </CardHeader>
              <CardContent>
                <h3>{selected.name}</h3>
                <dl className="detail-grid">
                  <div>
                    <dt>Facility ID</dt>
                    <dd>{selected.id}</dd>
                  </div>
                  <div>
                    <dt>Synthetic location</dt>
                    <dd>
                      {selected.city}, {selected.state}, {selected.country}
                    </dd>
                  </div>
                  <div>
                    <dt>Coordinates</dt>
                    <dd>
                      {selected.coordinates.latitude},{" "}
                      {selected.coordinates.longitude}
                    </dd>
                  </div>
                  <div>
                    <dt>Timezone</dt>
                    <dd>{selected.timezone}</dd>
                  </div>
                  <div>
                    <dt>Initial synthetic catalog status</dt>
                    <dd>{selected.operating_status}</dd>
                  </div>
                  <div>
                    <dt>Last catalog review</dt>
                    <dd>{formatTime(selected.last_reviewed_at)}</dd>
                  </div>
                </dl>
                <p>{selected.operating_status_scope}</p>
                <p>{selected.decision_authority}</p>
                <p className="page-source">
                  Source: {selected.source} ·{" "}
                  {formatTime(selected.source_timestamp)}
                  <br />
                  Catalog retrieved: {formatTime(resource.checkedAt)}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <h2>Configuration & exposure</h2>
              </CardHeader>
              <CardContent>
                <p>{selected.current_note}</p>
                {exposure ? (
                  <div className="source-record">
                    <Badge
                      tone={
                        exposure.data_source === "SIMULATED DEMO"
                          ? "purple"
                          : "neutral"
                      }
                    >
                      {exposure.data_source}
                    </Badge>
                    <p>
                      Configuration from saved evaluation{" "}
                      {evaluation?.evaluation_id}; it does not describe current
                      conditions.
                    </p>
                    <dl className="detail-grid">
                      <div>
                        <dt>Associated gauge</dt>
                        <dd>{exposure.monitoring_location_id}</dd>
                      </div>
                      <div>
                        <dt>Relationship</dt>
                        <dd>{exposure.relationship}</dd>
                      </div>
                    </dl>
                    <p>{exposure.basis}</p>
                    {exposure.thresholds && (
                      <p>
                        Prototype operating triggers: delayed arrival{" "}
                        {exposure.thresholds.delayed_arrival_feet} ft; telework{" "}
                        {exposure.thresholds.telework_feet} ft; closure{" "}
                        {exposure.thresholds.closure_feet} ft.
                      </p>
                    )}
                    <p>{evaluation?.result.rules.policy_label}</p>
                    <p className="page-source">
                      Configuration timestamp:{" "}
                      {formatTime(exposure.source_timestamp)}
                    </p>
                    <SourceLink reference={exposure.source_reference} />
                  </div>
                ) : (
                  <p>
                    Detailed gauge association and thresholds are unavailable in
                    the catalog. Load a saved evaluation to inspect its
                    configuration.
                  </p>
                )}
                <p>
                  Regional gauges do not establish facility or access-route
                  flooding. Synthetic coordinates are a reference location.
                </p>
              </CardContent>
            </Card>
          </div>
          <div className="page-stack">
            <Suspense
              fallback={
                <Card className="map-loading">Loading map component…</Card>
              }
            >
              <FacilityMap
                facilities={resource.data ?? []}
                selected={selected}
                onSelect={onSelect}
              />
            </Suspense>
            <Card>
              <CardHeader>
                <h2>Saved evaluation</h2>
              </CardHeader>
              <CardContent>
                {evaluation ? (
                  <>
                    <Badge
                      tone={
                        evaluation.data_mode === "SIMULATED DEMO"
                          ? "purple"
                          : "blue"
                      }
                    >
                      {evaluation.data_mode === "SIMULATED DEMO"
                        ? "SIMULATED DEMO"
                        : "SAVED PUBLIC EVIDENCE"}
                    </Badge>
                    <p className="record-id">
                      Evaluation ID: {evaluation.evaluation_id}
                    </p>
                    <p>
                      {evaluation.result.evaluation_status} ·{" "}
                      {evaluation.result.evidence_sufficiency}
                    </p>
                    <p>
                      Deterministic recommendation:{" "}
                      {evaluation.result.recommendation ??
                        "None — manual review required"}
                    </p>
                    <p className="page-source">
                      Evaluated: {formatTime(evaluation.result.evaluated_at)}.
                      Historical evidence has not been refreshed.
                    </p>
                    <Button variant="outline" onClick={onAlerts}>
                      Inspect saved evidence
                    </Button>
                  </>
                ) : (
                  <p>No saved evaluation loaded for this facility.</p>
                )}
                <div className="page-actions">
                  <Button onClick={onEvaluate}>Open Decision Queue</Button>
                </div>
                <p>
                  Choose a supported demo scenario there. Only an explicit human
                  action can finalize a decision.
                </p>
                {scenarios.status === "loading" && (
                  <p role="status">Loading supported scenarios…</p>
                )}
                {scenarios.error && (
                  <p role="alert">
                    Demo scenario catalog unavailable. {scenarios.error}
                  </p>
                )}
                {scenarios.data && (
                  <p>
                    {
                      scenarios.data.filter(
                        (s) => s.facility_id === selected.id,
                      ).length
                    }{" "}
                    supported demo scenarios in the loaded catalog.
                  </p>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
