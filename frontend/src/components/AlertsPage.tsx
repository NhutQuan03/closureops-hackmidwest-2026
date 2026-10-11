import { useState } from "react";
import type { Decision, Evaluation } from "../api/schemas";
import type { Resource } from "../hooks/useCommandCenter";
import { formatTime } from "../lib/utils";
import { EvaluationEvidence } from "./EvaluationEvidence";
import { LiveNwsAlerts } from "./LiveNwsAlerts";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader } from "./ui/card";

export function AlertsPage({
  evaluations,
  current,
  audit,
  onEvaluate,
}: {
  evaluations: Evaluation[];
  current: Evaluation | null;
  audit: Resource<Decision[]>;
  onEvaluate: () => void;
}) {
  const [chosenId, setChosenId] = useState("");
  const selected =
    evaluations.find((e) => e.evaluation_id === chosenId) ??
    current ??
    evaluations[0];
  return (
    <div className="operational-page alerts-page">
      <LiveNwsAlerts />
      <Card>
        <CardHeader>
          <h2>Saved evidence & alerts</h2>
          <Button variant="outline" onClick={onEvaluate}>
            Open Decision Queue
          </Button>
        </CardHeader>
        <CardContent>
          <p>
            This view contains saved evaluations for the selected facility.
            Simulated warnings are historical demo evidence, never current live
            warnings.
          </p>
          <p>
            The nationwide NWS feed above is separate. Current facility-specific
            NWS / USGS conditions are not acquired by these saved evaluations.
          </p>
          <p className="page-source">
            Sources: loaded evaluation and GET /api/audit (up to 100 decisions).
            Audit retrieved: {formatTime(audit.checkedAt)}
          </p>
          {audit.status === "loading" && (
            <p role="status">
              Loading saved evaluation records from audit history…
            </p>
          )}
          {audit.error && (
            <p role="alert" className="inline-error">
              Saved history unavailable. {audit.error} Use Refresh API to retry.
              A separately loaded evaluation remains available.
            </p>
          )}
          {evaluations.length > 0 && (
            <div className="page-select">
              <label htmlFor="alerts-evaluation">
                Saved evaluation for evidence
              </label>
              <select
                id="alerts-evaluation"
                value={selected?.evaluation_id ?? ""}
                onChange={(event) => setChosenId(event.target.value)}
              >
                {evaluations.map((e) => (
                  <option value={e.evaluation_id} key={e.evaluation_id}>
                    {e.evaluation_id} · {formatTime(e.result.evaluated_at)}
                  </option>
                ))}
              </select>
            </div>
          )}
        </CardContent>
      </Card>
      {selected ? (
        <EvaluationEvidence evaluation={selected} />
      ) : (
        <Card className="page-empty">
          <h2>No saved evaluation available</h2>
          <p>
            Evaluate a supported demo scenario in Decision Queue, or load a
            saved evaluation ID in Overview. Nothing here establishes current
            weather conditions.
          </p>
          <Button onClick={onEvaluate}>Choose a demo scenario</Button>
        </Card>
      )}
    </div>
  );
}
