import type { Decision, Evaluation, Facility } from "../api/schemas";
import type { MascotState } from "../components/AssistantMascot";

export function confirmedClosures(
  records: Decision[] | null,
  facilities: Facility[] | null,
): number | null {
  // The route is capped at 100 without a total/pagination contract. At the cap,
  // completeness is unknown; never use a partial history as a facility total.
  if (!records || !facilities || records.length === 100) return null;
  const latest = new Map<string, Decision>();
  for (const record of records) {
    if (record.manager_action === "ACKNOWLEDGE_REVIEW") continue;
    const prior = latest.get(record.facility_id);
    if (
      !prior ||
      Date.parse(record.decision_timestamp) >
        Date.parse(prior.decision_timestamp)
    )
      latest.set(record.facility_id, record);
  }
  return facilities.filter(
    (f) => latest.get(f.id)?.final_posture === "FACILITY_CLOSURE",
  ).length;
}
export function recommendationTitle(evaluation: Evaluation | null): string {
  if (!evaluation) return "Awaiting evaluation";
  if (evaluation.result.evaluation_status === "REVIEW_REQUIRED")
    return "Manual review required";
  return {
    OPEN: "Remain open",
    DELAYED_ARRIVAL: "Delayed arrival",
    UNSCHEDULED_TELEWORK: "Unscheduled telework",
    FACILITY_CLOSURE: "Facility closure",
  }[evaluation.result.recommendation!];
}
export function mascotState(
  evaluation: Evaluation | null,
  loading: boolean,
  records: Decision[] | null,
): MascotState {
  if (loading) return "monitoring";
  if (!evaluation) return "idle";
  if (evaluation.result.evaluation_status === "REVIEW_REQUIRED")
    return "review_required";
  // Display the validated engine posture, never severity inferred from prose.
  // A manager record does not establish that the underlying hazard has ended.
  if (
    evaluation.data_mode === "SIMULATED DEMO" &&
    evaluation.result.data_label === "SIMULATED DEMO" &&
    evaluation.result.evaluation_status === "RECOMMENDATION_READY" &&
    evaluation.result.evidence_sufficiency === "SUFFICIENT" &&
    evaluation.result.recommendation === "FACILITY_CLOSURE"
  )
    return "high_risk";
  if (records?.some((d) => d.evaluation_id === evaluation.evaluation_id))
    return "resolved";
  return "awaiting_approval";
}
