// Offline synthetic UI fixture only. Application code never imports it.
import {
  aiBriefingSchema,
  type AIBriefing,
  type Evaluation,
} from "../../src/api/schemas";
import briefings from "./situation-briefings.json" with { type: "json" };

export function briefingFixture(evaluation: Evaluation): AIBriefing {
  const saved = Object.values(briefings).find(
    (briefing) => briefing.evaluation_id === evaluation.evaluation_id,
  );
  if (!saved)
    throw new Error("No offline briefing fixture for this evaluation");
  return aiBriefingSchema.parse(saved);
}
