import {
  ArrowRight,
  Check,
  ChevronDown,
  ClipboardCheck,
  FileSearch,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import type { Decision, Evaluation, Facility } from "../api/schemas";
import { mascotState, recommendationTitle } from "../lib/dashboard";
import { formatTime } from "../lib/utils";
import { AssistantMascot, mascotStateLabels } from "./AssistantMascot";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader } from "./ui/card";
import type { FormEvent } from "react";
import type { useManagerWorkflow } from "../hooks/useManagerWorkflow";
import { ManagerActions } from "./ManagerActions";
import { AIBriefingPanel } from "./AIBriefingPanel";

interface Props {
  facility: Facility | null;
  evaluation: Evaluation | null;
  records: Decision[] | null;
  loading: boolean;
  error: string | null;
  evaluationId: string;
  onIdChange: (id: string) => void;
  onLoad: (event: FormEvent) => void;
  onReview: () => void;
  workflow: ReturnType<typeof useManagerWorkflow>;
  writesEnabled: boolean;
  aiBriefingEnabled: boolean;
}
export function RecommendationPanel({
  facility,
  evaluation,
  records,
  loading,
  error,
  evaluationId,
  onIdChange,
  onLoad,
  onReview,
  workflow,
  writesEnabled,
  aiBriefingEnabled,
}: Props) {
  const result = evaluation?.result;
  const assistantState = mascotState(evaluation, loading, records);
  const recorded = records?.find(
    (d) => d.evaluation_id === evaluation?.evaluation_id,
  );
  const tone =
    result?.evaluation_status === "REVIEW_REQUIRED"
      ? "amber"
      : result?.recommendation === "FACILITY_CLOSURE"
        ? "red"
        : result?.recommendation === "OPEN"
          ? "green"
          : "purple";
  return (
    <Card
      className="recommendation-card"
      aria-labelledby="recommendation-title"
    >
      <CardHeader>
        <h2 id="recommendation-title">
          <Sparkles size={18} /> Deterministic recommendation
        </h2>
        <Badge tone="purple">SNOOPY</Badge>
      </CardHeader>
      <CardContent>
        <div className="mascot-stage">
          <AssistantMascot state={assistantState} />
          <span className="mascot-caption">
            {mascotStateLabels[assistantState]}
          </span>
          {assistantState === "high_risk" && (
            <span className="mascot-workflow-note">
              {recorded
                ? "Manager action recorded; hazard evidence remains unchanged"
                : "Human approval required"}
            </span>
          )}
        </div>
        <div className="recommendation-status">
          <Badge tone={tone}>
            <ClipboardCheck size={12} />
            {loading
              ? "CHECKING TRUSTED DEMO EVIDENCE"
              : (result?.evaluation_status ?? "NO EVALUATION LOADED")}
          </Badge>
        </div>
        <h3
          className="recommendation-posture"
          id="operating-recommendation"
          tabIndex={-1}
        >
          {recommendationTitle(evaluation)}
        </h3>
        <p className="recommendation-facility">
          {facility?.name ?? "Select an available facility"}
        </p>
        <p className="recommendation-copy">
          {result
            ? result.reasons.join(" ")
            : "Choose a supported demo scenario and evaluate, or load a saved backend evaluation."}
        </p>
        <div className="recommendation-facts">
          <div>
            <span>Evidence sufficiency</span>
            <strong>{result?.evidence_sufficiency ?? "Unavailable"}</strong>
          </div>
          <div>
            <span>Operating authority</span>
            <strong>
              <ShieldCheck size={13} /> Human manager
            </strong>
          </div>
        </div>
        {result && (
          <div className="rule-summary">
            <details>
              <summary>
                <span className="small-label">Triggered prototype rules</span>
                <ChevronDown size={12} />
              </summary>
              <div className="rule-reasons">
                {result.triggered_rules.map((rule) => (
                  <p key={rule.rule_id}>{rule.reason}</p>
                ))}
              </div>
            </details>
            <div className="rule-tokens">
              {result.triggered_rules.map((rule) => (
                <p key={rule.rule_id}>
                  <Check size={12} />
                  <strong>{rule.rule_id}</strong>
                </p>
              ))}
            </div>
            <small>{result.rules.policy_label}</small>
          </div>
        )}
        <div className="explanation-note">
          <Sparkles size={14} />
          <span>
            {result
              ? "Deterministic engine explanation. Generate AI Briefing is a separate, explicit inference request."
              : "The Python engine selects posture. AI can explain validated evidence."}
          </span>
        </div>
        <Button
          className="review-button"
          disabled={!evaluation}
          onClick={onReview}
        >
          <FileSearch size={16} /> Review Evidence <ArrowRight size={15} />
        </Button>
        <ManagerActions
          evaluation={evaluation}
          workflow={workflow}
          writesEnabled={writesEnabled}
        />
        <AIBriefingPanel
          key={evaluation?.evaluation_id ?? "no-evaluation"}
          evaluation={evaluation}
          enabled={aiBriefingEnabled}
        />
        {recorded && (
          <p className="recorded-note">
            Recorded synthetic action: {recorded.manager_action} ·{" "}
            {formatTime(recorded.decision_timestamp)}. This panel preserves the
            original engine result.
          </p>
        )}
        {evaluation && (
          <p className="record-id">Evaluation ID: {evaluation.evaluation_id}</p>
        )}
        {result && (
          <details className="evaluation-limitations">
            <summary>Recommendation limitations</summary>
            {[
              ...result.limitations,
              ...evaluation!.integration_limitations,
            ].map((limit, index) => (
              <p key={index}>{limit}</p>
            ))}
          </details>
        )}
        <form className="evaluation-form" onSubmit={onLoad}>
          <label htmlFor="evaluation-id">
            Load a saved evaluation <span>READ ONLY</span>
          </label>
          <div>
            <input
              id="evaluation-id"
              value={evaluationId}
              onChange={(e) => onIdChange(e.target.value)}
              placeholder="eval_…"
              maxLength={37}
              autoComplete="off"
              spellCheck={false}
              disabled={!facility || loading || workflow.pending}
              aria-describedby="evaluation-help"
            />
            <Button
              size="sm"
              variant="outline"
              type="submit"
              disabled={
                !facility || !evaluationId.trim() || loading || workflow.pending
              }
            >
              {loading ? "Loading…" : "Load"}
            </Button>
          </div>
          <p id="evaluation-help">
            Use an ID from the existing local API workflow.
          </p>
          {error && (
            <p className="inline-error" role="alert">
              {error}
            </p>
          )}
        </form>
        <p className="source-note">
          {evaluation ? (
            <>
              Source: saved Python engine result ·{" "}
              {formatTime(result?.evaluated_at)}
              <br />
              {evaluation.data_mode === "SIMULATED DEMO"
                ? "SIMULATED DEMO · Fixed fixture clock"
                : "Saved snapshot · Not refreshed"}{" "}
              · {result?.data_label} at evaluation
            </>
          ) : (
            "Source: no evaluation loaded · Timestamp unavailable"
          )}
        </p>
      </CardContent>
    </Card>
  );
}
