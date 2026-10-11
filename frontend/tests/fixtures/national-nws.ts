// Synthetic offline test data only; never imported by application code.
import type { NationalAlerts } from "../../src/api/schemas";

export function nationalFixture(now = Date.now()): NationalAlerts {
  const retrieved = new Date(now).toISOString();
  return {
    ok: true,
    status: "LIVE",
    source: "NWS",
    scope: "NATIONWIDE",
    source_url: "https://api.weather.gov/alerts/active",
    facility_applicability: "NOT_ASSESSED",
    retrieved_at: retrieved,
    checked_at: retrieved,
    fresh_until: new Date(now + 300_000).toISOString(),
    collection_limited: true,
    selection_limit: 5,
    examined_count: 20,
    error: null,
    alerts: [
      {
        alert_id: "urn:synthetic-offline-test",
        source_url: "https://api.weather.gov/alerts/urn:synthetic-offline-test",
        event: "Synthetic nationwide test warning",
        severity: "Severe",
        urgency: "Immediate",
        certainty: "Observed",
        affected_area: "Synthetic nationwide test area",
        sent: new Date(now - 60_000).toISOString(),
        effective: retrieved,
        expires: new Date(now + 3_600_000).toISOString(),
        status: "LIVE",
        source: "NWS",
        retrieved_at: retrieved,
      },
    ],
  };
}
