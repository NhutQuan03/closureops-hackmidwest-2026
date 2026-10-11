import type { Evaluation } from "../api/schemas";
import { formatTime } from "../lib/utils";
import { EvidenceFeed, SourceLink } from "./EvidenceFeed";
import { Badge } from "./ui/badge";

export function EvaluationEvidence({ evaluation }: { evaluation: Evaluation }) {
  const { nws, usgs, exposure } = evaluation.evidence_snapshot;
  const simulated = evaluation.data_mode === "SIMULATED DEMO";
  return (
    <div className="evaluation-evidence">
      <div className="page-notice">
        <Badge tone={simulated ? "purple" : "blue"}>
          {simulated ? "SIMULATED DEMO" : "SAVED PUBLIC OBSERVATIONS"}
        </Badge>
        <strong>
          {simulated
            ? "Historical simulated evidence"
            : "Historical public evidence"}
        </strong>
        <p>
          No current live alert feed is applied to this evaluation. These
          records have not been refreshed.
        </p>
        <p>
          Related facility: {evaluation.evidence_snapshot.facility.name} ·{" "}
          {evaluation.result.facility_id}
        </p>
        <p className="record-id">Evaluation ID: {evaluation.evaluation_id}</p>
        <p>
          Evaluated: {formatTime(evaluation.result.evaluated_at)} ·{" "}
          {evaluation.result.evidence_sufficiency}
        </p>
        <p>{evaluation.result.rules.policy_label}</p>
      </div>
      <EvidenceFeed evaluation={evaluation} />
      <section
        className="detail-section"
        aria-label="NWS acquisition and warnings"
      >
        <h3>NWS acquisition & warnings</h3>
        {nws ? (
          <>
            <p>
              Recorded acquisition: <Badge>{nws.collection_status}</Badge> ·
              Provenance: {nws.evidence_status}
            </p>
            <p>
              Geographic scope: {nws.geographic_scope}. Query point:{" "}
              {nws.query_latitude}, {nws.query_longitude}.
            </p>
            <p>Retrieved: {formatTime(nws.retrieved_at)}</p>
            {nws.alerts.map((alert) => (
              <article className="source-record" key={alert.alert_id}>
                <h4>{alert.event}</h4>
                <p>
                  Severity: {alert.severity} · Urgency: {alert.urgency} ·
                  Certainty: {alert.certainty}
                </p>
                <p>
                  Valid from {formatTime(alert.effective)} through{" "}
                  {formatTime(alert.expires)}
                </p>
                <p className="record-id">Alert reference: {alert.alert_id}</p>
              </article>
            ))}
            <p className="record-id">
              Source reference: {nws.source_reference}
            </p>
            <SourceLink reference={nws.source_reference} />
          </>
        ) : (
          <p>
            NWS evidence unavailable: no acquisition or warning snapshot
            recorded.
          </p>
        )}
      </section>
      <section
        className="detail-section"
        aria-label="USGS observations and trends"
      >
        <h3>USGS observations & trends</h3>
        {!usgs?.observations.length && (
          <p>USGS observations unavailable in this evaluation.</p>
        )}
        {usgs?.observations.map((observation) => (
          <article
            className="source-record"
            key={`${observation.time_series_id}-${observation.observation_timestamp}`}
          >
            <h4>
              {observation.parameter_code === "00065"
                ? "Gauge height"
                : "Streamflow"}
              : {observation.value} {observation.unit}
            </h4>
            <p>
              {observation.monitoring_location_id} · Series{" "}
              {observation.time_series_id} · {observation.approval_status}
            </p>
            <p>Recorded provenance: {observation.evidence_status}</p>
            <p>
              Observed: {formatTime(observation.observation_timestamp)} ·
              Retrieved: {formatTime(observation.retrieved_at)}
            </p>
            <p className="record-id">
              Source reference: {observation.source_reference}
            </p>
            <SourceLink reference={observation.source_reference} />
          </article>
        ))}
        {usgs?.trend ? (
          <article className="source-record">
            <h4>Recorded gauge trend</h4>
            <p>
              {usgs.trend.monitoring_location_id} · Series{" "}
              {usgs.trend.time_series_id}
            </p>
            <p>
              {usgs.trend.start_value_feet} ft at{" "}
              {formatTime(usgs.trend.start_timestamp)} →{" "}
              {usgs.trend.end_value_feet} ft at{" "}
              {formatTime(usgs.trend.end_timestamp)}
            </p>
            <p>
              Retrieved: {formatTime(usgs.trend.retrieved_at)} · Recorded
              provenance: {usgs.trend.evidence_status}
            </p>
            <p className="record-id">
              Source reference: {usgs.trend.source_reference}
            </p>
            <SourceLink reference={usgs.trend.source_reference} />
          </article>
        ) : (
          <p>No gauge trend recorded.</p>
        )}
        <p>
          Regional gauge readings do not establish facility or access-route
          flooding.
        </p>
      </section>
      <section className="detail-section">
        <h3>Source freshness & attribution</h3>
        {evaluation.source_timestamps.map((reference) => (
          <div className="reference-detail" key={reference.reference_id}>
            <strong>
              {reference.source} · {reference.reference_id}
            </strong>
            <Badge>RECORDED {reference.state}</Badge>
            <p>
              Observed: {formatTime(reference.observed_at)}
              <br />
              Retrieved: {formatTime(reference.retrieved_at)}
              <br />
              Validity: {formatTime(reference.valid_from)} —{" "}
              {formatTime(reference.valid_until)}
            </p>
            <p className="record-id">
              Source reference: {reference.source_reference}
            </p>
            <SourceLink reference={reference.source_reference} />
          </div>
        ))}
      </section>
      <section className="detail-section">
        <h3>Acquisition checks</h3>
        {evaluation.source_checks.length ? (
          evaluation.source_checks.map((check) => (
            <p key={check.source}>
              {check.source}: RECORDED {check.status} · Checked{" "}
              {formatTime(check.checked_at)} · Retrieved{" "}
              {formatTime(check.retrieved_at)}
            </p>
          ))
        ) : (
          <p>No acquisition checks recorded for this fixture.</p>
        )}
      </section>
      <section className="detail-section">
        <h3>Evidence limitations</h3>
        {[
          ...evaluation.result.limitations,
          ...evaluation.integration_limitations,
        ].map((limitation, index) => (
          <p key={index}>{limitation}</p>
        ))}
        {exposure && (
          <p>
            Recorded association: {exposure.relationship}. {exposure.basis} ·{" "}
            {exposure.data_source}
          </p>
        )}
        {evaluation.result.triggered_rules.map((rule) => (
          <p key={rule.rule_id}>
            <strong>{rule.rule_id}:</strong> {rule.reason}
          </p>
        ))}
      </section>
    </div>
  );
}
