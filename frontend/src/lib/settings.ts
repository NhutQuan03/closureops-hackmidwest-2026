import type { Decision } from "../api/schemas";
import type { Resource } from "../hooks/useCommandCenter";

// The API base URL is public configuration. Never display URL credentials or query values.
export function publicApiBaseUrl(value: string): string {
  if (value === "") return "Same origin · /api";
  try {
    const url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol)) return "Invalid API URL";
    return `${url.origin}${url.pathname.replace(/\/$/, "")}`;
  } catch {
    return "Invalid API URL";
  }
}

export interface IntegrationStatus {
  name: string;
  status: string;
  description: string;
  source: string;
  checkedAt?: string | null;
}

export function integrationStatuses(
  audit: Resource<Decision[]>,
): IntegrationStatus[] {
  return [
    {
      name: "NWS weather alerts",
      status: "NATIONWIDE READ AVAILABLE · NOT CHECKED HERE",
      description:
        "Alerts can retrieve actual national active alerts through the read-only NWS endpoint. Settings does not probe NWS connectivity. Nationwide alerts are not applied to the synthetic facility; saved warnings retain their historical provenance.",
      source: "API capability · GET /api/nws/alerts/active",
    },
    {
      name: "USGS water observations",
      status: "CURRENT FEED UNAVAILABLE",
      description:
        "Read observations from saved evaluations only. There is no current USGS feed endpoint. Regional gauge readings do not prove facility flooding.",
      source: "Local-demo API contract · no current-feed endpoint",
    },
    {
      name: "AWS Strands Agents",
      status: "LOCAL BRIEFING AGENT · OPT-IN REQUIRED",
      description:
        "Trusted demo evaluations use a read-only SDK tool. An explicitly enabled local briefing endpoint reuses the tested Strands agent for an exact saved snapshot. Settings does not check model connectivity.",
      source: "API capability · POST /api/evaluations/{id}/ai-briefing",
    },
    {
      name: "Akamai inference",
      status: "LOCAL BRIEFING ADAPTER · NOT CHECKED HERE",
      description:
        "Explicit local briefing requests use the existing Akamai compatibility adapter. Credentials stay on the backend. Server opt-in is required; Settings performs no authenticated inference or connectivity probe.",
      source: "Documented local briefing configuration · no provider probe",
    },
    {
      name: "OpenFreeMap",
      status: "CONFIGURED · NOT CHECKED HERE",
      description:
        "MapLibre uses https://tiles.openfreemap.org/styles/dark without an API key. Provider availability is handled by the map, including an unavailable-basemap fallback.",
      source: "Frontend map configuration · no provider probe on Settings",
    },
    {
      name: "SQLite audit storage",
      status:
        audit.status === "ready"
          ? "AUDIT READ AVAILABLE"
          : audit.status === "loading"
            ? "CHECKING AUDIT READ"
            : "AUDIT READ UNAVAILABLE",
      description:
        "SQLite is the documented local audit store. Status reflects GET /api/audit only, not a database diagnostic or a test of write access.",
      source: "Documented backend configuration · GET /api/audit?limit=100",
      checkedAt: audit.checkedAt,
    },
  ];
}
