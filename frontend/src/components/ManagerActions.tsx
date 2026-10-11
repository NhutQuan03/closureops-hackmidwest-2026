import { useRef, useState } from "react";
import type { Evaluation, Posture, DecisionAction } from "../api/schemas";
import { decisionActionSchema, postureSchema } from "../api/schemas";
import type { useManagerWorkflow } from "../hooks/useManagerWorkflow";
import { formatTime } from "../lib/utils";
import { Button } from "./ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "./ui/dialog";

export function ManagerActions({
  evaluation,
  workflow,
  writesEnabled,
}: {
  evaluation: Evaluation | null;
  workflow: ReturnType<typeof useManagerWorkflow>;
  writesEnabled: boolean;
}) {
  const [action, setAction] = useState<DecisionAction["action"] | null>(null);
  const [posture, setPosture] = useState<Posture>("UNSCHEDULED_TELEWORK");
  const [reason, setReason] = useState("");
  const trigger = useRef<HTMLElement | null>(null);
  const review = evaluation?.result.evaluation_status === "REVIEW_REQUIRED";
  const ready = evaluation?.result.evaluation_status === "RECOMMENDATION_READY";
  const input =
    action === "OVERRIDE"
      ? { action, selected_posture: posture, reason: reason.trim() }
      : { action };
  const valid =
    decisionActionSchema.safeParse(input).success &&
    (action !== "OVERRIDE" || posture !== evaluation?.result.recommendation);
  function open(next: DecisionAction["action"]) {
    trigger.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    setReason("");
    setPosture(
      postureSchema.options.find(
        (p) => p !== evaluation?.result.recommendation,
      )!,
    );
    setAction(next);
  }
  async function confirm() {
    if (!valid || !workflow.canAct || workflow.pending) return;
    await workflow.submit(decisionActionSchema.parse(input));
    setAction(null);
  }
  return (
    <div className="manager-workflow">
      <div className="manager-actions">
        <Button
          variant="outline"
          disabled={!ready || !workflow.canAct}
          onClick={() => open("APPROVE")}
        >
          Approve
        </Button>
        <Button
          variant="outline"
          disabled={!ready || !workflow.canAct}
          onClick={() => open("OVERRIDE")}
        >
          Override
        </Button>
      </div>
      {review && (
        <Button
          className="review-button"
          variant="outline"
          disabled={!workflow.canAct}
          onClick={() => open("ACKNOWLEDGE_REVIEW")}
        >
          Acknowledge review
        </Button>
      )}
      <p className="control-note" role="status">
        {workflow.pending
          ? "Checking saved records or saving the explicit manager action…"
          : !writesEnabled
            ? "READ ONLY · Local demo writes disabled. Human action controls are unavailable."
            : workflow.decision
              ? "Saved human decision. The original engine recommendation remains above."
              : "Explicit human confirmation required. Synthetic records only; no real facility status changes."}
      </p>
      {workflow.error && (
        <div className="inline-error" role="alert">
          <p>{workflow.error}</p>
          <Button
            size="sm"
            variant="outline"
            disabled={workflow.pending}
            onClick={workflow.retry}
          >
            Check saved history
          </Button>
        </div>
      )}
      {workflow.decision && (
        <div className="saved-decision" role="status">
          <strong>Saved decision: {workflow.decision.manager_action}</strong>
          <p>
            Final manager posture:{" "}
            {workflow.decision.final_posture ??
              "None — review acknowledgment only"}
          </p>
          {workflow.decision.override_reason && (
            <p>Reason: {workflow.decision.override_reason}</p>
          )}
          <p className="record-id">
            Decision ID: {workflow.decision.decision_id}
          </p>
          <p>
            {workflow.decision.manager.display_name} ·{" "}
            {formatTime(workflow.decision.decision_timestamp)}
          </p>
          {workflow.decision.manager_action !== "ACKNOWLEDGE_REVIEW" &&
            !workflow.plan && (
              <Button
                size="sm"
                disabled={!workflow.canPrepare}
                onClick={() => void workflow.prepare()}
              >
                Prepare simulated notifications
              </Button>
            )}
        </div>
      )}
      <Dialog
        open={action !== null}
        onOpenChange={(open) => {
          if (!open && !workflow.pending) setAction(null);
        }}
      >
        <DialogContent
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            trigger.current?.focus();
          }}
        >
          <DialogTitle>Confirm manager action</DialogTitle>
          <DialogDescription>
            SIMULATED DEMO · The backend records an explicit human decision
            under its Synthetic Demo Manager identity. No real facility status
            changes or notifications occur.
          </DialogDescription>
          <p>{evaluation?.evidence_snapshot.facility.name}</p>
          <p className="record-id">
            Evaluation ID: {evaluation?.evaluation_id}
          </p>
          <p>
            Original deterministic recommendation:{" "}
            {evaluation?.result.recommendation ?? "None — REVIEW_REQUIRED"}
          </p>
          <p>
            Action: <strong>{action}</strong>
          </p>
          {action === "OVERRIDE" ? (
            <div className="override-fields">
              <label htmlFor="final-posture">Final manager posture</label>
              <select
                id="final-posture"
                value={posture}
                onChange={(e) => setPosture(e.target.value as Posture)}
                disabled={workflow.pending}
              >
                {postureSchema.options
                  .filter((p) => p !== evaluation?.result.recommendation)
                  .map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
              </select>
              <label htmlFor="override-reason">
                Override reason (required)
              </label>
              <textarea
                id="override-reason"
                required
                maxLength={500}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                disabled={workflow.pending}
              />
              <p>Final manager posture: {posture}</p>
            </div>
          ) : (
            <p>
              Final manager posture:{" "}
              {action === "APPROVE"
                ? evaluation?.result.recommendation
                : "None — acknowledgment records review only"}
            </p>
          )}
          <div className="manager-actions">
            <Button
              variant="outline"
              disabled={workflow.pending}
              onClick={() => setAction(null)}
            >
              Cancel
            </Button>
            <Button
              disabled={!valid || !workflow.canAct || workflow.pending}
              onClick={() => void confirm()}
            >
              {workflow.pending ? "Saving…" : "Confirm action"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
