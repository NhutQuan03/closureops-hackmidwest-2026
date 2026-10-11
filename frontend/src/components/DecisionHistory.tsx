import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Decision, NotificationPlan } from "../api/schemas";
import type { Resource } from "../hooks/useCommandCenter";
import { formatTime } from "../lib/utils";
import { EvaluationEvidence } from "./EvaluationEvidence";
import { NotificationPlanPanel } from "./NotificationPlanPanel";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader } from "./ui/card";

export function DecisionInspection({ id }: { id: string }) {
  const [decision, setDecision] = useState<Decision | null>(null);
  const [plan, setPlan] = useState<NotificationPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState(
    "Loading persisted decision and notification status…",
  );
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const saved = await api.decision(id, controller.signal);
        if (controller.signal.aborted) return;
        setDecision(saved);
        if (saved.manager_action === "ACKNOWLEDGE_REVIEW") {
          setStatus(
            "Not eligible: review acknowledgment has no operating posture.",
          );
          return;
        }
        try {
          const prepared = await api.notificationPlan(id, controller.signal);
          if (
            prepared.facility_id !== saved.facility_id ||
            prepared.final_posture !== saved.final_posture
          )
            throw new Error(
              "Saved notification plan does not match the persisted manager decision.",
            );
          if (!controller.signal.aborted) {
            setPlan(prepared);
            setStatus(prepared.status);
          }
        } catch (failure) {
          if (failure instanceof ApiError && failure.status === 404)
            setStatus("No notification plan recorded.");
          else throw failure;
        }
      } catch (failure) {
        if (!controller.signal.aborted) {
          setStatus("Notification status unavailable.");
          setError(
            failure instanceof Error ? failure.message : "History unavailable.",
          );
        }
      }
    }
    void load();
    return () => controller.abort();
  }, [id]);
  return (
    <Card className="decision-inspection">
      <CardHeader>
        <h2>Persisted manager decision</h2>
      </CardHeader>
      <CardContent>
        {error && (
          <p role="alert" className="inline-error">
            {error}
          </p>
        )}
        <p role="status">Notification status: {status}</p>
        {decision && (
          <>
            <p>
              {decision.evidence_snapshot.facility.name} · {decision.data_mode}
            </p>
            <p className="record-id">Evaluation ID: {decision.evaluation_id}</p>
            <p className="record-id">Decision ID: {decision.decision_id}</p>
            <p>
              Original deterministic recommendation:{" "}
              {decision.original_recommendation ?? "None — REVIEW_REQUIRED"}
            </p>
            <p>
              Final manager posture:{" "}
              {decision.final_posture ?? "None — review acknowledgment only"}
            </p>
            <p>
              Action: {decision.manager_action} ·{" "}
              {decision.manager.display_name}
            </p>
            <p>
              Override reason: {decision.override_reason ?? "Not applicable"}
            </p>
            <p>Decision timestamp: {formatTime(decision.decision_timestamp)}</p>
            <p>
              The engine recommendation and evidence are preserved separately
              from the explicit human decision.
            </p>
            <details>
              <summary>
                Evidence snapshot references & source timestamps
              </summary>
              <EvaluationEvidence evaluation={decision.evaluation} />
            </details>
          </>
        )}
        {plan && <NotificationPlanPanel plan={plan} />}
      </CardContent>
    </Card>
  );
}

export function DecisionHistory({
  resource,
  refresh,
  initialId = null,
  title = "Decision history",
  onInspect,
}: {
  resource: Resource<Decision[]>;
  refresh: () => void;
  initialId?: string | null;
  title?: string;
  onInspect?: (id: string) => void;
}) {
  const [id, setId] = useState<string | null>(initialId);
  return (
    <div className="history-workflow">
      <Card>
        <CardHeader>
          <h2>{title}</h2>
          <Button
            size="sm"
            variant="outline"
            onClick={refresh}
            disabled={resource.status === "loading"}
          >
            Refresh history
          </Button>
        </CardHeader>
        <CardContent>
          {resource.status === "loading" && (
            <p role="status">Loading saved audit records…</p>
          )}
          {resource.error && (
            <p role="alert" className="inline-error">
              {resource.error}
            </p>
          )}
          {resource.data?.length === 0 && (
            <p>
              No manager decisions recorded. Create an evaluation in Overview to
              begin.
            </p>
          )}
          {resource.data?.length === 100 && (
            <p>
              Showing the latest 100 decisions; older records are outside this
              list.
            </p>
          )}
          {resource.data?.map((record) => (
            <div className="history-row" key={record.decision_id}>
              <div>
                <strong>
                  {record.manager_action} ·{" "}
                  {record.final_posture ?? "REVIEW_REQUIRED — no posture"}
                </strong>
                <p>
                  {record.evidence_snapshot.facility.name} ·{" "}
                  {formatTime(record.decision_timestamp)}
                </p>
                <small className="record-id">{record.decision_id}</small>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() =>
                  onInspect
                    ? onInspect(record.decision_id)
                    : setId(record.decision_id)
                }
                aria-label={`Inspect ${record.decision_id}`}
              >
                Inspect
              </Button>
            </div>
          ))}
        </CardContent>
      </Card>
      {id && <DecisionInspection key={id} id={id} />}
    </div>
  );
}
