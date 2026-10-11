import { CloudRain, ExternalLink, Radio, Waves } from "lucide-react";
import { useId } from "react";
import type { Evaluation } from "../api/schemas";
import { formatTime, sourceUrl } from "../lib/utils";
import { Badge } from "./ui/badge";
import { Card, CardHeader } from "./ui/card";

interface EvidenceItem {
  id: string;
  source: "NWS" | "USGS";
  title: string;
  detail: string;
  state: string;
  timestamp: string | null;
  reference: string;
}
export function evidenceItems(evaluation: Evaluation): EvidenceItem[] {
  const { nws, usgs } = evaluation.evidence_snapshot;
  const items: EvidenceItem[] = [];
  if (nws) {
    if (!nws.alerts.length)
      items.push({
        id: "nws-collection",
        source: "NWS",
        title:
          nws.collection_status === "NO_ACTIVE_ALERTS"
            ? "No active alerts in snapshot"
            : "NWS collection unavailable",
        detail: nws.geographic_scope.replaceAll("_", " ").toLowerCase(),
        state: nws.evidence_status,
        timestamp: nws.retrieved_at,
        reference: nws.source_reference,
      });
    for (const a of nws.alerts)
      items.push({
        id: a.alert_id,
        source: "NWS",
        title: a.event,
        detail: `${a.severity} · ${a.certainty} · Valid ${formatTime(a.effective)} through ${formatTime(a.expires)}`,
        state: nws.evidence_status,
        timestamp: nws.retrieved_at,
        reference: nws.source_reference,
      });
  }
  for (const o of usgs?.observations ?? [])
    items.push({
      id: `${o.time_series_id}-${o.observation_timestamp}`,
      source: "USGS",
      title: `${o.parameter_code === "00065" ? "Gauge height" : "Streamflow"}: ${o.value} ${o.unit}`,
      detail: `${o.monitoring_location_id} · ${o.approval_status} · Retrieved ${formatTime(o.retrieved_at)}`,
      state: o.evidence_status,
      timestamp: o.observation_timestamp,
      reference: o.source_reference,
    });
  return items.sort((a, b) =>
    (b.timestamp ?? "").localeCompare(a.timestamp ?? ""),
  );
}
export function SourceLink({ reference }: { reference: string }) {
  const url = sourceUrl(reference);
  return url ? (
    <a
      className="source-link"
      href={url}
      target="_blank"
      rel="noopener noreferrer"
    >
      Supporting source <ExternalLink size={11} />
    </a>
  ) : (
    <span className="fixture-reference">Reference: {reference}</span>
  );
}
export function EvidenceFeed({
  evaluation,
  onReview,
}: {
  evaluation: Evaluation | null;
  onReview?: () => void;
}) {
  const items = evaluation ? evidenceItems(evaluation) : [];
  const headingId = useId();
  return (
    <Card className="evidence-card" aria-labelledby={headingId}>
      <CardHeader>
        <h2 id={headingId}>
          <Radio size={17} /> Recent evidence
        </h2>
        {onReview && (
          <button
            className="text-action"
            disabled={!evaluation}
            onClick={onReview}
          >
            Inspect
          </button>
        )}
      </CardHeader>
      {evaluation ? (
        <>
          <div className="evidence-feed">
            {items.length ? (
              items.map((item) => (
                <article className="evidence-item" key={item.id}>
                  <span
                    className={`evidence-icon ${item.source === "USGS" ? "blue" : "amber"}`}
                  >
                    {item.source === "USGS" ? (
                      <Waves size={20} />
                    ) : (
                      <CloudRain size={20} />
                    )}
                  </span>
                  <div>
                    <h3>{item.title}</h3>
                    <p>{item.detail}</p>
                    <div className="evidence-meta">
                      <strong>{item.source}</strong>
                      <time dateTime={item.timestamp ?? undefined}>
                        {formatTime(item.timestamp)}
                      </time>
                    </div>
                    <Badge
                      tone={
                        item.state === "SIMULATED DEMO"
                          ? "purple"
                          : item.state === "UNAVAILABLE" ||
                              item.state === "NO_DATA"
                            ? "neutral"
                            : "amber"
                      }
                    >
                      {item.state === "LIVE"
                        ? "RECORDED LIVE · SAVED SNAPSHOT"
                        : item.state}
                    </Badge>
                    <p className="freshness-note">
                      Snapshot state: {item.state}. Not refreshed.
                    </p>
                    <SourceLink reference={item.reference} />
                  </div>
                </article>
              ))
            ) : (
              <div className="evidence-empty">
                <Radio size={25} />
                <strong>No source observations recorded</strong>
                <p>
                  The saved evaluation contains no NWS alerts or USGS
                  observations.
                </p>
              </div>
            )}
          </div>
          <p className="source-note">
            Saved evaluation · {formatTime(evaluation.result.evaluated_at)}
            <br />
            Snapshot evidence does not establish current conditions.
          </p>
        </>
      ) : (
        <>
          <div className="evidence-empty">
            <span className="empty-orbit">
              <Radio size={27} />
            </span>
            <strong>Evidence starts with an evaluation</strong>
            <p>
              Load a saved evaluation to inspect source observations and the
              rules behind a recommendation.
            </p>
          </div>
          <div className="awaiting-source">
            <CloudRain size={17} />
            <span>
              NWS alerts<small>Timestamp unavailable</small>
            </span>
            <Badge>UNAVAILABLE</Badge>
          </div>
          <div className="awaiting-source">
            <Waves size={17} />
            <span>
              USGS observations<small>Timestamp unavailable</small>
            </span>
            <Badge>UNAVAILABLE</Badge>
          </div>
          <p className="source-note">
            No live-weather read endpoint is available in the local demo API.
          </p>
        </>
      )}
    </Card>
  );
}
