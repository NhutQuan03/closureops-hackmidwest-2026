import type { NationalAlert, NationalAlerts } from "../api/schemas";

export function nationalFeedState(
  feed: NationalAlerts,
  now: number,
  failed = false,
): NationalAlerts["status"] {
  if (failed) return "STALE";
  if (feed.status === "UNAVAILABLE") return "UNAVAILABLE";
  const until = Date.parse(feed.fresh_until ?? "");
  const retrieved = Date.parse(feed.retrieved_at ?? "");
  if (!Number.isFinite(until) || until <= now || retrieved > now + 60_000)
    return "STALE";
  if (
    feed.status === "LIVE" &&
    !feed.alerts.some(
      (alert) => nationalAlertState(alert, "LIVE", now) === "LIVE",
    )
  )
    return "STALE";
  return feed.status;
}

export function nationalAlertState(
  alert: NationalAlert,
  feedState: NationalAlerts["status"],
  now: number,
): "LIVE" | "STALE" {
  return feedState === "LIVE" &&
    alert.status === "LIVE" &&
    Date.parse(alert.expires ?? "") > now &&
    (!alert.sent || Date.parse(alert.sent) <= now + 60_000)
    ? "LIVE"
    : "STALE";
}
