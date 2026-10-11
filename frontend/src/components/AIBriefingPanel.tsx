import { useEffect, useRef, useState } from "react";
import { Sparkles } from "lucide-react";
import { api } from "../api/client";
import type { AIBriefing, Evaluation } from "../api/schemas";
import { formatTime } from "../lib/utils";
import { SourceLink } from "./EvidenceFeed";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";

const reasons: Record<AIBriefing["reason"], string> = {
  OK: "Agent selection validated against the saved Python result.",
  AI_DISABLED: "AI briefing is disabled on this backend.",
  MISSING_CREDENTIALS:
    "Backend inference credentials are unavailable. Configure them privately on the server.",
  UNSUPPORTED_SNAPSHOT:
    "The existing tool cannot reproduce this exact saved snapshot. No AI briefing was generated.",
  SNAPSHOT_MISMATCH:
    "The tool result differs from the saved evaluation. No AI briefing was accepted.",
  INVALID_MODEL_OUTPUT:
    "AI output was rejected. The deterministic fallback preserves the Python result.",
  TOOL_NOT_CONFIRMED:
    "An exact tool execution was not confirmed. No AI briefing was accepted.",
  MODEL_TIMEOUT:
    "Inference timed out. The deterministic recommendation remains available.",
  PROVIDER_ERROR:
    "Inference failed. The deterministic recommendation remains available.",
  DEPENDENCY_UNAVAILABLE: "The backend inference dependency is unavailable.",
  BUSY: "Another inference run is in progress. Retry after it finishes.",
};

const briefingSections = [
  ["situation_summary", "Situation summary"],
  ["operational_implications", "Operational implications"],
  ["recommended_response", "Recommended response and rule rationale"],
  ["suggested_next_steps", "Suggested next steps"],
  ["evidence_limitations", "Evidence limitations and provenance"],
] as const;

export function AIBriefingPanel({
  evaluation,
  enabled,
}: {
  evaluation: Evaluation | null;
  enabled: boolean;
}) {
  const [briefing, setBriefing] = useState<AIBriefing | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  async function generate() {
    if (!evaluation || !enabled || request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setPending(true);
    setError(null);
    setBriefing(null);
    try {
      const result = await api.generateBriefing(evaluation, controller.signal);
      if (!controller.signal.aborted) setBriefing(result);
    } catch (failure) {
      if (!controller.signal.aborted)
        setError(
          failure instanceof Error
            ? failure.message
            : "AI briefing unavailable.",
        );
    } finally {
      if (!controller.signal.aborted) {
        setPending(false);
        request.current = null;
      }
    }
  }
  return (
    <section className="ai-briefing-panel" aria-label="AI-assisted explanation">
      <div className="ai-briefing-heading">
        <h3>AI-assisted explanation</h3>
        <Button
          variant="outline"
          size="sm"
          disabled={!evaluation || !enabled || pending}
          onClick={() => void generate()}
        >
          <Sparkles size={14} />
          Generate AI Briefing
        </Button>
      </div>
      <p>
        Briefing from saved evidence. The Python engine recommends; a human
        manager makes the final decision.
      </p>
      {!enabled && (
        <p>
          AI briefing is unavailable until the local backend enables inference.
          Inference requires an explicit button action.
        </p>
      )}
      {pending && (
        <p role="status">
          Generating a briefing from the saved evaluation with Strands and
          Akamai… This can take up to 90 seconds. Manager controls remain
          available.
        </p>
      )}
      {error && (
        <p role="alert" className="inline-error">
          {error} No AI briefing was accepted. The deterministic workflow
          remains available.
        </p>
      )}
      {briefing && (
        <div className="ai-briefing-result">
          <div className="ai-briefing-badges">
            <Badge tone={briefing.status === "VALIDATED" ? "green" : "amber"}>
              {briefing.status === "VALIDATED"
                ? "VALIDATED agent execution"
                : briefing.status}
            </Badge>
            <Badge tone="purple">{briefing.data_label} at evaluation</Badge>
            <Badge tone="purple">
              {briefing.authoritative_recommendation ??
                "REVIEW_REQUIRED · no posture"}
            </Badge>
          </div>
          <p className="ai-briefing-facility">{briefing.facility_name}</p>
          {briefing.status !== "VALIDATED" && <p>{reasons[briefing.reason]}</p>}
          <p className="ai-explanation-source">
            {briefing.explanation_source === "VALIDATED_RULES"
              ? "AI-assisted validated briefing · deterministically composed from trusted evidence"
              : briefing.explanation_source === "DETERMINISTIC_FALLBACK"
                ? "DETERMINISTIC FALLBACK · not a successful AI briefing"
                : "No explanation generated"}
          </p>
          <p className="ai-briefing-human">
            Human approval required. The recommendation is not a final manager
            decision.
          </p>
          {briefing.situation_briefing ? (
            <div className="ai-situation-sections">
              {briefingSections.map(([key, title]) => (
                <div className="ai-situation-section" key={key}>
                  <h4>{title}</h4>
                  <p>{briefing.situation_briefing![key]}</p>
                </div>
              ))}
            </div>
          ) : (
            briefing.explanation && (
              <p>
                Structured briefing unavailable from this backend. Restart with
                the updated briefing service; the saved deterministic
                recommendation remains available.
              </p>
            )
          )}
          <p className="source-note">
            Source: saved Python evaluation ·{" "}
            {formatTime(briefing.evaluated_at)}
            <br />
            Briefing response: {formatTime(briefing.generated_at)}. Evidence was
            not refreshed.
          </p>
          <details className="ai-briefing-diagnostics">
            <summary>Technical diagnostics</summary>
            <p>{reasons[briefing.reason]}</p>
            <dl className="ai-briefing-facts">
              <div>
                <dt>Evaluated facility</dt>
                <dd>
                  {briefing.facility_name} ({briefing.facility_id})
                </dd>
              </div>
              <div>
                <dt>Authoritative deterministic recommendation</dt>
                <dd>
                  {briefing.authoritative_recommendation ??
                    "REVIEW_REQUIRED · no posture"}
                </dd>
              </div>
              <div>
                <dt>Validation status</dt>
                <dd>{briefing.validation_status}</dd>
              </div>
              <div>
                <dt>Agent tool execution</dt>
                <dd>
                  {briefing.tool_execution_confirmed
                    ? "Exact saved-result match confirmed"
                    : "Not confirmed"}
                </dd>
              </div>
              <div>
                <dt>Model response completed</dt>
                <dd>
                  {briefing.model_completed
                    ? "Yes · subject to validation above"
                    : "Not confirmed"}
                </dd>
              </div>
            </dl>
            <p>
              Explicit human approval required. No operating posture, manager
              decision, or notification plan was changed.
            </p>
            {briefing.explanation && (
              <details className="ai-briefing-explanation">
                <summary>Complete raw explanation</summary>
                <p>{briefing.explanation}</p>
              </details>
            )}
            <details>
              <summary>Evidence references from the saved evaluation</summary>
              {briefing.evidence_references.map((reference) => (
                <div
                  className="ai-briefing-reference"
                  key={reference.reference_id}
                >
                  <strong>
                    {reference.reference_id} · {reference.source} ·{" "}
                    {reference.state}
                  </strong>
                  <p>
                    {reference.source_reference}
                    <br />
                    Observed: {formatTime(reference.observed_at)} · Retrieved:{" "}
                    {formatTime(reference.retrieved_at)}
                  </p>
                  <SourceLink reference={reference.source_reference} />
                </div>
              ))}
            </details>
            <p>
              Evaluation ID: {briefing.evaluation_id}
              <br />
              Explanation source: {briefing.explanation_source}
            </p>
          </details>
        </div>
      )}
    </section>
  );
}
