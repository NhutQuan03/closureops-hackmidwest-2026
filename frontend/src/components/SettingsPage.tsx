import { RefreshCw, ShieldCheck } from "lucide-react";
import { API_BASE_URL } from "../api/client";
import type { Decision, Facility, Health } from "../api/schemas";
import type { Resource } from "../hooks/useCommandCenter";
import { useMotionPreference } from "../hooks/MotionPreference";
import {
  integrationStatuses,
  publicApiBaseUrl,
  type IntegrationStatus,
} from "../lib/settings";
import { formatTime } from "../lib/utils";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader } from "./ui/card";

function IntegrationCard({ integration }: { integration: IntegrationStatus }) {
  return (
    <Card className="integration-card">
      <CardHeader>
        <h3>{integration.name}</h3>
      </CardHeader>
      <CardContent>
        <Badge
          tone={
            integration.status === "AUDIT READ AVAILABLE" ? "green" : "neutral"
          }
        >
          {integration.status}
        </Badge>
        <p>{integration.description}</p>
        <p className="page-source">
          Source: {integration.source}
          <br />
          {integration.checkedAt
            ? `Read checked: ${formatTime(integration.checkedAt)}`
            : "Connectivity check: not performed"}
        </p>
      </CardContent>
    </Card>
  );
}

export function SettingsPage({
  health,
  facilities,
  audit,
  onRefresh,
}: {
  health: Resource<Health>;
  facilities: Resource<Facility[]>;
  audit: Resource<Decision[]>;
  onRefresh: () => void;
}) {
  const motion = useMotionPreference();
  const connected = health.status === "ready";
  const facility = facilities.data?.find(
    (item) => item.id === "jefferson-research",
  );
  const writes = connected
    ? health.data?.local_demo_writes_enabled === true
      ? "Enabled for local demo"
      : "Disabled · read only"
    : "Unavailable · not verified";
  return (
    <div className="operational-page settings-page">
      <Card>
        <CardHeader className="settings-section-header">
          <div>
            <h2>System Settings & Integrations</h2>
            <p>Local demo capabilities and browser preferences</p>
          </div>
          <Button
            variant="outline"
            onClick={onRefresh}
            disabled={health.status === "loading"}
          >
            <RefreshCw size={16} /> Refresh Status
          </Button>
        </CardHeader>
        <CardContent>
          <div className="settings-connection" role="status">
            <Badge
              tone={
                connected
                  ? "green"
                  : health.status === "loading"
                    ? "neutral"
                    : "red"
              }
            >
              {connected
                ? "API CONNECTED"
                : health.status === "loading"
                  ? "CHECKING API"
                  : "API UNAVAILABLE"}
            </Badge>
            <span>
              {connected
                ? "FastAPI health check succeeded."
                : health.status === "loading"
                  ? "Checking the FastAPI service…"
                  : "FastAPI could not be verified. Check the local server and Refresh Status."}
            </span>
          </div>
          {health.error && (
            <p role="alert" className="api-error">
              {health.error}
            </p>
          )}
          <dl className="detail-grid">
            <div>
              <dt>Configured API base URL</dt>
              <dd>{publicApiBaseUrl(API_BASE_URL)}</dd>
            </div>
            <div>
              <dt>Last successful health check</dt>
              <dd data-testid="last-successful-health">
                {health.successfulAt
                  ? formatTime(health.successfulAt)
                  : "No successful check this session"}
              </dd>
            </div>
            <div>
              <dt>Backend data mode</dt>
              <dd>
                {connected && health.data?.data_mode === "synthetic_demo"
                  ? "SIMULATED DEMO (synthetic_demo)"
                  : "Unavailable · not verified"}
              </dd>
            </div>
            <div>
              <dt>Local-demo write capability</dt>
              <dd data-testid="write-capability">{writes}</dd>
            </div>
          </dl>
          <p className="settings-safeguard">
            <ShieldCheck size={18} /> Connectivity and this advisory write
            capability do not establish authentication or authorization. The
            backend enforces local write guards; manager actions still require
            explicit human approval.
          </p>
          <p className="page-source">
            Source: GET /api/health · Last attempt:{" "}
            {formatTime(health.checkedAt)}. Timestamps use this browser’s clock.
          </p>
        </CardContent>
      </Card>
      <section aria-labelledby="integration-heading">
        <div className="settings-group-heading">
          <h2 id="integration-heading">Data sources & integrations</h2>
          <p>
            Configuration and available API reads; no external connectivity
            probes.
          </p>
        </div>
        <div className="settings-integrations">
          {integrationStatuses(audit).map((integration) => (
            <IntegrationCard key={integration.name} integration={integration} />
          ))}
        </div>
      </section>
      <div className="settings-bottom-grid">
        <Card>
          <CardHeader>
            <h2>Demo configuration</h2>
            <Badge tone="purple">SIMULATED DEMO</Badge>
          </CardHeader>
          <CardContent>
            {facilities.status === "loading" && (
              <p role="status">Loading synthetic facility configuration…</p>
            )}
            {facilities.status === "error" && (
              <p role="alert">
                Facility catalog unavailable. Refresh Status to retry.
              </p>
            )}
            {facility ? (
              <>
                <h3>{facility.name}</h3>
                <dl className="detail-grid">
                  <div>
                    <dt>Synthetic facility ID</dt>
                    <dd>{facility.id}</dd>
                  </div>
                  <div>
                    <dt>Synthetic location</dt>
                    <dd>
                      {facility.city}, {facility.state}, {facility.country}
                    </dd>
                  </div>
                  <div>
                    <dt>Synthetic coordinates</dt>
                    <dd>
                      {facility.coordinates.latitude},{" "}
                      {facility.coordinates.longitude}
                    </dd>
                  </div>
                </dl>
                <p className="page-source">
                  Source: {facility.source} ·{" "}
                  {formatTime(facility.source_timestamp)}
                  <br />
                  Catalog retrieved: {formatTime(facilities.checkedAt)}
                </p>
              </>
            ) : (
              facilities.status === "ready" && (
                <p>
                  Jefferson Research Facility is unavailable in the returned
                  catalog.
                </p>
              )
            )}
            <p>
              Prototype policy — not official USDA policy. Operating thresholds
              are defined by the backend and cannot be edited here.
            </p>
            <p>
              Human approval or override is required to finalize a synthetic
              operating posture. Review acknowledgments do not set a posture.
            </p>
            <p>
              No real notifications are sent. No real facility operating status
              is changed.
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <h2>Appearance & accessibility</h2>
          </CardHeader>
          <CardContent>
            <Badge tone="purple">Dark-purple theme</Badge>
            <label className="settings-motion-control">
              <input
                type="checkbox"
                aria-describedby="motion-description"
                checked={motion.preferReducedMotion}
                onChange={(event) =>
                  motion.setPreferReducedMotion(event.target.checked)
                }
              />
              Reduce optional mascot motion in this browser
            </label>
            <p id="motion-description">
              This preference uses static mascot artwork and removes mascot
              entrance animations. It is saved only in this browser.
              Operating-system reduced motion always takes precedence.
            </p>
            <dl className="detail-grid">
              <div>
                <dt>Operating-system preference</dt>
                <dd>
                  {motion.systemReducedMotion
                    ? "Reduce motion"
                    : "No reduced-motion preference"}
                </dd>
              </div>
              <div>
                <dt>Effective mascot motion</dt>
                <dd>
                  {motion.reducedMotion ? "Reduced motion" : "Default motion"}
                </dd>
              </div>
            </dl>
            {motion.storageUnavailable && (
              <p role="status">
                Browser storage is unavailable. This preference applies for this
                session only.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
