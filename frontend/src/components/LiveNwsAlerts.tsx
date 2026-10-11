import { useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import { api } from "../api/client";
import type { NationalAlerts } from "../api/schemas";
import { nationalAlertState, nationalFeedState } from "../lib/liveNws";
import { formatTime } from "../lib/utils";
import { SourceLink } from "./EvidenceFeed";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader } from "./ui/card";

export function LiveNwsAlerts() {
  const [feed, setFeed] = useState<NationalAlerts | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [failedLastAttempt, setFailedLastAttempt] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const request = useRef<AbortController | null>(null);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 15_000);
    return () => {
      window.clearInterval(timer);
      request.current?.abort();
    };
  }, []);
  async function refresh() {
    if (request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setError(null);
    try {
      const next = await api.nationalNws(controller.signal);
      if (controller.signal.aborted) return;
      if (next.status === "UNAVAILABLE") {
        setFailedLastAttempt(true);
        setError(
          "NWS collection unavailable or incomplete. No current alert claims can be made.",
        );
        setFeed((previous) => (previous?.ok ? previous : next));
      } else {
        setFeed(next);
        setFailedLastAttempt(false);
      }
    } catch (failure) {
      if (!controller.signal.aborted) {
        setFailedLastAttempt(true);
        setError(
          failure instanceof Error ? failure.message : "NWS data unavailable.",
        );
      }
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
        setNow(Date.now());
        request.current = null;
      }
    }
  }
  const state = feed
    ? nationalFeedState(feed, now, failedLastAttempt && feed.ok)
    : null;
  return (
    <Card className="live-nws-panel" aria-labelledby="live-nws-heading">
      <CardHeader className="live-nws-header">
        <div>
          <h2 id="live-nws-heading">Nationwide NWS active alerts</h2>
          <p>
            Current public weather evidence · separate from facility evaluations
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => void refresh()}
          disabled={loading}
        >
          <RefreshCw size={16} />
          Refresh Live NWS
        </Button>
      </CardHeader>
      <CardContent>
        <p>
          These nationwide alerts are not applied to Jefferson Research
          Facility. Geographic applicability is NOT ASSESSED. This feed does not
          change recommendations, manager decisions, or facility operations.
        </p>
        {loading && (
          <p role="status">
            Retrieving actual active alerts from the national NWS collection…
          </p>
        )}
        {error && (
          <p role="alert" className="api-error">
            {error} Use Refresh Live NWS to retry. Any retained alerts are
            STALE.
          </p>
        )}
        {!feed && !loading && !error && (
          <p className="page-notice">
            Not checked yet. Select Refresh Live NWS to retrieve actual
            nationwide alerts.
          </p>
        )}
        {feed && (
          <>
            <Badge
              tone={
                state === "LIVE"
                  ? "green"
                  : state === "STALE"
                    ? "amber"
                    : "neutral"
              }
            >
              {state}
            </Badge>
            <p className="page-source">
              Source: National Weather Service · Retrieved:{" "}
              {formatTime(feed.retrieved_at)}
              <br />
              NWS check: {formatTime(feed.checked_at)} · Freshness deadline:{" "}
              {formatTime(feed.fresh_until)}
            </p>
            <SourceLink reference={feed.source_url} />
            {state === "NO_ACTIVE_ALERTS" && (
              <p>
                No active actual alerts were returned by the complete national
                collection at retrieval. This is not proof of safe facility
                operations.
              </p>
            )}
            {state === "STALE" && (
              <p>
                Current conditions are unverified. Retrieval freshness or alert
                validity has elapsed, is unavailable, or the refresh failed.
              </p>
            )}
            {feed.alerts.length > 0 && (
              <p>
                Showing {feed.alerts.length} selected alerts (maximum{" "}
                {feed.selection_limit}) from {feed.examined_count} examined
                records.{" "}
                {feed.collection_limited
                  ? "Selection or collection is limited; this is not a complete nationwide alert list. Pagination links are not followed."
                  : "This describes only the collection returned at retrieval."}
              </p>
            )}
            <div className="live-nws-grid">
              {feed.alerts.map((alert) => {
                const alertState = nationalAlertState(alert, state!, now);
                return (
                  <article
                    className="source-record live-nws-alert"
                    key={alert.alert_id}
                  >
                    <div className="live-nws-alert-heading">
                      <h3>{alert.event}</h3>
                      <Badge tone={alertState === "LIVE" ? "green" : "amber"}>
                        {alertState}
                      </Badge>
                    </div>
                    <dl className="detail-grid">
                      <div>
                        <dt>Severity</dt>
                        <dd>{alert.severity ?? "Unavailable"}</dd>
                      </div>
                      <div>
                        <dt>Urgency</dt>
                        <dd>{alert.urgency ?? "Unavailable"}</dd>
                      </div>
                      <div>
                        <dt>Certainty</dt>
                        <dd>{alert.certainty ?? "Unavailable"}</dd>
                      </div>
                    </dl>
                    <p>Affected area: {alert.affected_area || "Unavailable"}</p>
                    <dl className="detail-grid">
                      <div>
                        <dt>Sent</dt>
                        <dd>{formatTime(alert.sent)}</dd>
                      </div>
                      <div>
                        <dt>Effective</dt>
                        <dd>{formatTime(alert.effective)}</dd>
                      </div>
                      <div>
                        <dt>Expires</dt>
                        <dd>{formatTime(alert.expires)}</dd>
                      </div>
                    </dl>
                    <p className="page-source">
                      Source: {alert.source} · Retrieved:{" "}
                      {formatTime(alert.retrieved_at)}
                    </p>
                    <SourceLink reference={alert.source_url} />
                  </article>
                );
              })}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
