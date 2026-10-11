import { z } from "zod";

// Read models follow the Pydantic response models. Unknown fields are stripped,
// and every field used to display evidence or operating status is validated.
const text = z.string().min(1).max(500);
const reference = z.string().min(1).max(2048);
const timestamp = z.iso.datetime({ offset: true });
const facilityId = z.string().regex(/^[a-z0-9][a-z0-9-]{0,63}$/);
export const evaluationIdSchema = z.string().regex(/^eval_[0-9a-f]{32}$/);
export const decisionIdSchema = z.string().regex(/^decision_[0-9a-f]{32}$/);
export const postureSchema = z.enum([
  "OPEN",
  "DELAYED_ARRIVAL",
  "UNSCHEDULED_TELEWORK",
  "FACILITY_CLOSURE",
]);
const posture = postureSchema;
const evaluationStatus = z.enum(["RECOMMENDATION_READY", "REVIEW_REQUIRED"]);
const sufficiency = z.enum(["SUFFICIENT", "INSUFFICIENT", "CONFLICTING"]);
const state = z.enum([
  "LIVE",
  "STALE",
  "SIMULATED DEMO",
  "UNAVAILABLE",
  "NO_DATA",
]);
const configurationLabel = z.enum(["CONFIGURED", "SIMULATED DEMO"]);
const dataMode = z.enum(["SIMULATED DEMO", "LIVE_EVIDENCE"]);
const thresholds = z.object({
  delayed_arrival_feet: z.number().min(0).max(1000),
  telework_feet: z.number().min(0).max(1000),
  closure_feet: z.number().min(0).max(1000),
});
const rules = z.object({
  version: z.literal("prototype-flood-v1"),
  policy_label: z.literal("PROTOTYPE - NOT OFFICIAL USDA POLICY"),
  nws_max_age_minutes: z.number().int().min(1).max(1440),
  usgs_max_age_minutes: z.number().int().min(1).max(1440),
  rising_change_feet: z.number().positive().max(1000),
});
export const healthSchema = z.object({
  status: z.literal("ok"),
  service: z.literal("closureops-api"),
  data_mode: z.literal("synthetic_demo"),
  local_demo_writes_enabled: z.boolean().default(false),
  ai_briefing_enabled: z.boolean().default(false),
});
export const facilitySchema = z.object({
  id: facilityId,
  name: text,
  city: text,
  state: text,
  country: z.literal("US"),
  timezone: text,
  coordinates: z.object({
    latitude: z.number().min(-90).max(90),
    longitude: z.number().min(-180).max(180),
  }),
  operating_status: z.literal("open"),
  operating_status_scope: text,
  data_mode: z.literal("synthetic_demo"),
  data_label: z.literal("SIMULATED DEMO"),
  source: z.literal("ClosureOps synthetic facility fixture"),
  source_timestamp: timestamp,
  decision_authority: text,
  current_note: text,
  last_reviewed_at: timestamp,
});
export const scenarioSchema = z
  .object({
    scenario_id: z.string().regex(/^[a-z][a-z0-9_]{0,63}$/),
    facility_id: facilityId,
    data_label: z.literal("SIMULATED DEMO"),
    disclosure: text,
    source: z.literal("ClosureOps trusted synthetic scenario fixture"),
    source_timestamp: timestamp,
    evaluation_clock: timestamp,
    expected_recommendation: posture.nullable(),
    expected_status: evaluationStatus,
  })
  .refine(
    (s) =>
      (s.expected_status === "RECOMMENDATION_READY") ===
      (s.expected_recommendation !== null),
  );
const evidenceReference = z.object({
  reference_id: reference,
  source: z.enum(["FACILITY", "EXPOSURE", "NWS", "USGS"]),
  source_reference: reference,
  state: z.enum([...state.options, "CONFIGURED"]),
  observed_at: timestamp.nullable(),
  retrieved_at: timestamp.nullable(),
  valid_from: timestamp.nullable(),
  valid_until: timestamp.nullable(),
});
const alert = z.object({
  alert_id: reference,
  event: text,
  severity: z.enum(["Extreme", "Severe", "Moderate", "Minor", "Unknown"]),
  urgency: z.enum(["Immediate", "Expected", "Future", "Past", "Unknown"]),
  certainty: z.enum(["Observed", "Likely", "Possible", "Unlikely", "Unknown"]),
  effective: timestamp,
  expires: timestamp,
});
const observation = z
  .object({
    monitoring_location_id: z.string().regex(/^USGS-[0-9]{8,15}$/),
    time_series_id: z.string().regex(/^[a-zA-Z0-9-]{1,64}$/),
    parameter_code: z.enum(["00065", "00060"]),
    value: z.number(),
    unit: z.enum(["ft", "ft^3/s"]),
    observation_timestamp: timestamp,
    retrieved_at: timestamp,
    evidence_status: state,
    source_reference: reference,
    approval_status: z.enum(["Approved", "Provisional"]),
  })
  .refine((o) => o.unit === (o.parameter_code === "00065" ? "ft" : "ft^3/s"));
const snapshot = z.object({
  facility: z.object({
    id: facilityId,
    name: text,
    latitude: z.number().min(-90).max(90),
    longitude: z.number().min(-180).max(180),
    data_source: configurationLabel,
    source_timestamp: timestamp,
    source_reference: reference,
  }),
  nws: z
    .object({
      facility_id: facilityId,
      source: z.literal("NWS"),
      source_reference: reference,
      evidence_status: state,
      collection_status: z.enum([
        "ACTIVE_ALERTS",
        "NO_ACTIVE_ALERTS",
        "UNAVAILABLE",
      ]),
      retrieved_at: timestamp.nullable(),
      geographic_scope: z.enum([
        "FACILITY_POINT_FILTERED",
        "REGIONAL",
        "UNKNOWN",
      ]),
      query_latitude: z.number().min(-90).max(90),
      query_longitude: z.number().min(-180).max(180),
      alerts: z.array(alert).max(100),
    })
    .nullable(),
  usgs: z
    .object({
      facility_id: facilityId,
      source: z.literal("USGS"),
      observations: z.array(observation).max(20),
      trend: z
        .object({
          monitoring_location_id: z.string(),
          time_series_id: z.string(),
          start_value_feet: z.number(),
          end_value_feet: z.number(),
          start_timestamp: timestamp,
          end_timestamp: timestamp,
          retrieved_at: timestamp,
          evidence_status: state,
          source_reference: reference,
        })
        .nullable(),
    })
    .nullable(),
  exposure: z
    .object({
      facility_id: facilityId,
      monitoring_location_id: z.string(),
      relationship: z.enum(["REGIONAL_ONLY", "ACCESS_ROUTE", "FACILITY"]),
      basis: text,
      source_reference: reference,
      source_timestamp: timestamp,
      data_source: configurationLabel,
      thresholds: thresholds.nullable(),
    })
    .nullable(),
  rules,
  evaluated_at: timestamp,
});
const result = z
  .object({
    facility_id: facilityId,
    recommendation: posture.nullable(),
    evaluation_status: evaluationStatus,
    evidence_sufficiency: sufficiency,
    data_label: z.enum(["LIVE", "STALE", "UNAVAILABLE", "SIMULATED DEMO"]),
    evaluated_at: timestamp,
    rules,
    thresholds: thresholds.nullable(),
    triggered_rules: z.array(
      z.object({
        rule_id: text,
        reason: text,
        evidence_reference_ids: z.array(reference).max(125),
      }),
    ),
    evidence_references: z.array(evidenceReference),
    reasons: z.array(text),
    limitations: z.array(text),
    human_approval_required: z.literal(true),
  })
  .refine((r) => {
    const ready = r.evaluation_status === "RECOMMENDATION_READY";
    return (
      ready === (r.recommendation !== null) &&
      ready === (r.evidence_sufficiency === "SUFFICIENT")
    );
  });
export const evaluationSchema = z
  .object({
    evaluation_id: evaluationIdSchema,
    data_mode: dataMode,
    evidence_snapshot: snapshot,
    result,
    source_timestamps: z.array(evidenceReference),
    source_checks: z.array(
      z.object({
        source: z.enum(["NWS", "USGS"]),
        status: z.enum([
          "LIVE",
          "STALE",
          "NO_DATA",
          "NO_ACTIVE_ALERTS",
          "UNAVAILABLE",
        ]),
        checked_at: timestamp.nullable(),
        retrieved_at: timestamp.nullable(),
      }),
    ),
    integration_limitations: z.array(text),
  })
  .refine(
    (e) =>
      e.result.facility_id === e.evidence_snapshot.facility.id &&
      e.result.evaluated_at === e.evidence_snapshot.evaluated_at &&
      JSON.stringify(e.result.evidence_references) ===
        JSON.stringify(e.source_timestamps) &&
      JSON.stringify(e.result.rules) ===
        JSON.stringify(e.evidence_snapshot.rules),
  );
export const decisionSchema = z
  .object({
    decision_id: decisionIdSchema,
    evaluation_id: evaluationIdSchema,
    facility_id: facilityId,
    evaluation_status: evaluationStatus,
    original_recommendation: posture.nullable(),
    manager_action: z.enum(["APPROVE", "OVERRIDE", "ACKNOWLEDGE_REVIEW"]),
    final_posture: posture.nullable(),
    override_reason: text.nullable(),
    manager: z.object({
      id: z.literal("demo-manager"),
      display_name: z.literal("Synthetic Demo Manager"),
      synthetic: z.literal(true),
    }),
    evidence_snapshot: snapshot,
    source_timestamps: z.array(evidenceReference),
    data_mode: dataMode,
    decision_timestamp: timestamp,
    evaluation: evaluationSchema,
  })
  .refine((d) => {
    const r = d.evaluation.result;
    if (
      d.evaluation_id !== d.evaluation.evaluation_id ||
      d.facility_id !== r.facility_id ||
      d.evaluation_status !== r.evaluation_status ||
      d.original_recommendation !== r.recommendation ||
      d.data_mode !== d.evaluation.data_mode ||
      JSON.stringify(d.evidence_snapshot) !==
        JSON.stringify(d.evaluation.evidence_snapshot) ||
      JSON.stringify(d.source_timestamps) !==
        JSON.stringify(d.evaluation.source_timestamps)
    )
      return false;
    if (d.manager_action === "ACKNOWLEDGE_REVIEW")
      return (
        r.evaluation_status === "REVIEW_REQUIRED" &&
        d.final_posture === null &&
        d.override_reason === null
      );
    if (r.evaluation_status !== "RECOMMENDATION_READY") return false;
    if (d.manager_action === "APPROVE")
      return d.final_posture === r.recommendation && d.override_reason === null;
    return (
      d.final_posture !== null &&
      d.final_posture !== r.recommendation &&
      d.override_reason !== null
    );
  });
export type Facility = z.infer<typeof facilitySchema>;
export type Scenario = z.infer<typeof scenarioSchema>;
export type Health = z.infer<typeof healthSchema>;
export type Evaluation = z.infer<typeof evaluationSchema>;
export type Decision = z.infer<typeof decisionSchema>;
export type EvidenceReference = z.infer<typeof evidenceReference>;

export const decisionActionSchema = z.discriminatedUnion("action", [
  z.object({ action: z.literal("APPROVE") }).strict(),
  z.object({ action: z.literal("ACKNOWLEDGE_REVIEW") }).strict(),
  z
    .object({
      action: z.literal("OVERRIDE"),
      selected_posture: posture,
      reason: text
        .trim()
        .min(1)
        .refine((value) =>
          [...value].every(
            (char) => char.charCodeAt(0) >= 32 && char.charCodeAt(0) !== 127,
          ),
        ),
    })
    .strict(),
]);
export type DecisionAction = z.infer<typeof decisionActionSchema>;
export type Posture = z.infer<typeof postureSchema>;
const count = z.number().int().nonnegative();
const group = z.enum([
  "ESSENTIAL_PERSONNEL",
  "TELEWORK_ELIGIBLE",
  "STANDARD_ONSITE",
]);
export const notificationPlanSchema = z
  .object({
    notification_plan_id: z.string().regex(/^notification_[0-9a-f]{32}$/),
    decision_id: decisionIdSchema,
    facility_id: facilityId,
    facility_name: text,
    final_posture: posture,
    effective_at: z.null(),
    group_counts: z
      .object({
        ESSENTIAL_PERSONNEL: count,
        TELEWORK_ELIGIBLE: count,
        STANDARD_ONSITE: count,
      })
      .strict(),
    total_assigned: count,
    total_scheduled: count,
    total_unscheduled: count,
    total_affected: count,
    messages: z
      .array(
        z.object({
          group,
          count,
          message: z.string().min(1).max(2048),
          route: z.literal("simulated"),
          status: z.literal("GENERATED_SIMULATED"),
        }),
      )
      .length(3),
    roster_source: z.literal(
      "ClosureOps synthetic demonstration shift fixture",
    ),
    roster_source_timestamp: timestamp,
    template_version: z.literal("task8b-v1"),
    status: z.literal("GENERATED_SIMULATED"),
    created_at: timestamp,
    data_mode: z.literal("SIMULATED DEMO"),
  })
  .refine(
    (p) =>
      p.total_assigned === p.total_scheduled + p.total_unscheduled &&
      p.total_affected === p.total_scheduled &&
      Object.values(p.group_counts).reduce((sum, n) => sum + n, 0) ===
        p.total_affected &&
      new Set(p.messages.map((m) => m.group)).size === 3 &&
      p.messages.every((m) => m.count === p.group_counts[m.group]),
  );
export type NotificationPlan = z.infer<typeof notificationPlanSchema>;

const officialNwsAlertUrl = reference.refine((value) => {
  try {
    const url = new URL(value);
    return (
      url.protocol === "https:" &&
      url.hostname === "api.weather.gov" &&
      (!url.port || url.port === "443") &&
      !url.username &&
      !url.password &&
      !url.search &&
      !url.hash &&
      url.pathname.startsWith("/alerts/") &&
      url.pathname.length > 8
    );
  } catch {
    return false;
  }
});
export const nationalAlertSchema = z.object({
  alert_id: reference,
  source_url: officialNwsAlertUrl,
  event: text,
  severity: z
    .enum(["Extreme", "Severe", "Moderate", "Minor", "Unknown"])
    .nullable(),
  urgency: z
    .enum(["Immediate", "Expected", "Future", "Past", "Unknown"])
    .nullable(),
  certainty: z
    .enum(["Observed", "Likely", "Possible", "Unlikely", "Unknown"])
    .nullable(),
  affected_area: z.string().max(100_000).nullable(),
  sent: timestamp.nullable(),
  effective: timestamp.nullable(),
  expires: timestamp.nullable(),
  status: z.enum(["LIVE", "STALE"]),
  source: z.literal("NWS"),
  retrieved_at: timestamp,
});
export const nationalAlertsSchema = z
  .object({
    ok: z.boolean(),
    status: z.enum(["LIVE", "STALE", "NO_ACTIVE_ALERTS", "UNAVAILABLE"]),
    source: z.literal("NWS"),
    scope: z.literal("NATIONWIDE"),
    source_url: z.literal("https://api.weather.gov/alerts/active"),
    facility_applicability: z.literal("NOT_ASSESSED"),
    retrieved_at: timestamp.nullable(),
    checked_at: timestamp,
    fresh_until: timestamp.nullable(),
    alerts: z.array(nationalAlertSchema).max(5),
    selection_limit: z.literal(5),
    collection_limited: z.boolean(),
    examined_count: z.number().int().min(0).max(5000),
    error: text.nullable(),
  })
  .superRefine((feed, ctx) => {
    const invalid =
      feed.ok !== (feed.status !== "UNAVAILABLE") ||
      (feed.status === "LIVE" &&
        (!feed.retrieved_at || !feed.fresh_until || !feed.alerts.length)) ||
      (feed.status === "NO_ACTIVE_ALERTS" &&
        (!feed.retrieved_at ||
          !feed.fresh_until ||
          feed.alerts.length > 0 ||
          feed.collection_limited ||
          feed.examined_count > 0)) ||
      (feed.status === "UNAVAILABLE" && feed.alerts.length > 0) ||
      feed.alerts.some(
        (alert) =>
          alert.retrieved_at !== feed.retrieved_at ||
          (alert.status === "LIVE" &&
            (feed.status !== "LIVE" || !alert.expires)),
      );
    if (invalid)
      ctx.addIssue({
        code: "custom",
        message: "Inconsistent national alert provenance",
      });
  });
export type NationalAlerts = z.infer<typeof nationalAlertsSchema>;
export type NationalAlert = z.infer<typeof nationalAlertSchema>;

export const situationBriefingSchema = z
  .object({
    situation_summary: z.string().min(1).max(1600),
    operational_implications: z.string().min(1).max(1600),
    recommended_response: z.string().min(1).max(1600),
    suggested_next_steps: z.string().min(1).max(1600),
    evidence_limitations: z.string().min(1).max(1600),
  })
  .strict();

export const aiBriefingSchema = z
  .object({
    evaluation_id: evaluationIdSchema,
    facility_id: facilityId,
    facility_name: text,
    data_mode: dataMode,
    data_label: z.enum(["LIVE", "STALE", "UNAVAILABLE", "SIMULATED DEMO"]),
    authoritative_recommendation: posture.nullable(),
    human_approval_required: z.literal(true),
    generated_at: timestamp,
    evaluated_at: timestamp,
    status: z.enum([
      "VALIDATED",
      "FALLBACK",
      "UNAVAILABLE",
      "TIMEOUT",
      "ERROR",
    ]),
    validation_status: z.enum(["VALIDATED", "REJECTED", "NOT_RUN"]),
    model_completed: z.boolean(),
    tool_execution_confirmed: z.boolean(),
    explanation_source: z.enum([
      "VALIDATED_RULES",
      "DETERMINISTIC_FALLBACK",
      "NONE",
    ]),
    explanation: z.string().min(1).max(65536).nullable(),
    situation_briefing: situationBriefingSchema.nullable().default(null),
    reason: z.enum([
      "OK",
      "AI_DISABLED",
      "MISSING_CREDENTIALS",
      "UNSUPPORTED_SNAPSHOT",
      "SNAPSHOT_MISMATCH",
      "INVALID_MODEL_OUTPUT",
      "TOOL_NOT_CONFIRMED",
      "MODEL_TIMEOUT",
      "PROVIDER_ERROR",
      "DEPENDENCY_UNAVAILABLE",
      "BUSY",
    ]),
    evidence_references: z.array(evidenceReference).max(125),
  })
  .refine((briefing) => {
    const validated = briefing.status === "VALIDATED";
    return (
      (validated
        ? briefing.validation_status === "VALIDATED" &&
          briefing.model_completed &&
          briefing.tool_execution_confirmed &&
          briefing.reason === "OK" &&
          briefing.explanation_source === "VALIDATED_RULES" &&
          briefing.explanation !== null
        : briefing.validation_status !== "VALIDATED" &&
          briefing.explanation_source !== "VALIDATED_RULES") &&
      (briefing.explanation_source === "NONE") ===
        (briefing.explanation === null) &&
      (briefing.situation_briefing === null || briefing.explanation !== null)
    );
  });
export type AIBriefing = z.infer<typeof aiBriefingSchema>;
