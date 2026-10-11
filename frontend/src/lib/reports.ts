import type { Decision, Evaluation } from "../api/schemas";

export function savedEvaluations(
  current: Evaluation | null,
  records: Decision[] | null,
  facilityId: string | undefined,
): Evaluation[] {
  const evaluations = new Map<string, Evaluation>();
  for (const record of records ?? []) {
    if (record.facility_id === facilityId)
      evaluations.set(record.evaluation_id, record.evaluation);
  }
  if (current?.result.facility_id === facilityId && current)
    evaluations.set(current.evaluation_id, current);
  return [...evaluations.values()].sort(
    (a, b) =>
      Date.parse(b.result.evaluated_at) - Date.parse(a.result.evaluated_at) ||
      a.evaluation_id.localeCompare(b.evaluation_id),
  );
}

export function summarizeDecisions(records: Decision[]) {
  const decisions = [
    ...new Map(records.map((record) => [record.decision_id, record])).values(),
  ].sort(
    (a, b) =>
      Date.parse(b.decision_timestamp) - Date.parse(a.decision_timestamp) ||
      a.decision_id.localeCompare(b.decision_id),
  );
  const transitions = new Map<
    string,
    { original: string; final: string; count: number }
  >();
  for (const decision of decisions) {
    const original =
      decision.original_recommendation ?? "None — review required";
    const final = decision.final_posture ?? "None — review acknowledged";
    const key = `${original}/${final}`;
    const row = transitions.get(key);
    if (row) row.count++;
    else transitions.set(key, { original, final, count: 1 });
  }
  return {
    decisions,
    total: decisions.length,
    approvals: decisions.filter((d) => d.manager_action === "APPROVE").length,
    overrides: decisions.filter((d) => d.manager_action === "OVERRIDE").length,
    reviews: decisions.filter((d) => d.manager_action === "ACKNOWLEDGE_REVIEW")
      .length,
    transitions: [...transitions.values()],
  };
}
