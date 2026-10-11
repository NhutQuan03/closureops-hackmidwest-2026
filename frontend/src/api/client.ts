import { z } from "zod";
import {
  decisionSchema,
  decisionActionSchema,
  decisionIdSchema,
  evaluationIdSchema,
  evaluationSchema,
  facilitySchema,
  healthSchema,
  notificationPlanSchema,
  nationalAlertsSchema,
  aiBriefingSchema,
  type Evaluation,
  scenarioSchema,
  type DecisionAction,
} from "./schemas";

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8001"
).replace(/\/$/, "");
export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly retryAfter?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function validateApiBaseUrl(baseUrl: string): string {
  // Docker builds explicitly set an empty base: fixed /api routes are same-origin.
  if (baseUrl === "") return baseUrl;
  const url = new URL(baseUrl);
  if (url.port === "8000")
    throw new ApiError(
      "Port 8000 hosts the legacy API. Set VITE_API_BASE_URL=http://127.0.0.1:8001 and restart Vite.",
    );
  return baseUrl;
}

export async function readApi<T>(
  path: string,
  schema: z.ZodType<T>,
  signal?: AbortSignal,
  body?: object,
  timeoutMs = 10000,
): Promise<T> {
  const timeout = AbortSignal.timeout(timeoutMs);
  try {
    const response = await fetch(`${validateApiBaseUrl(API_BASE_URL)}${path}`, {
      method: body ? "POST" : "GET",
      headers: {
        Accept: "application/json",
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
      credentials: "omit",
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    });
    if (!response.ok) {
      const retryAfter =
        Number(response.headers.get("Retry-After")) || undefined;
      throw new ApiError(
        response.status === 429
          ? `API rate limit reached. Retry${retryAfter ? ` after ${retryAfter} seconds` : " shortly"}.`
          : response.status === 403
            ? "Local demo writes are unavailable or this request is not authorized. Refresh API after checking the local server configuration."
            : response.status === 409
              ? "A record already exists or this action is not allowed. Check persisted history before retrying."
              : response.status === 404
                ? "Saved record not found. Check the evaluation ID."
                : `API request failed (${response.status}).`,
        response.status,
        retryAfter,
      );
    }
    if (!response.headers.get("Content-Type")?.includes("application/json"))
      throw new ApiError("API returned an unexpected response format.");
    const parsed = schema.safeParse(await response.json());
    if (!parsed.success)
      throw new ApiError(
        "API response does not match the expected schema. Data was not displayed.",
      );
    return parsed.data;
  } catch (error) {
    if (signal?.aborted) throw error;
    if (error instanceof ApiError) throw error;
    if (timeout.aborted)
      throw new ApiError(
        "API request timed out. Check the local FastAPI server.",
      );
    throw new ApiError(
      "Cannot reach the local API, or its response is invalid. Start FastAPI and retry.",
    );
  }
}

async function writeApi<T>(
  path: string,
  schema: z.ZodType<T>,
  body: object,
): Promise<T> {
  // Capability is advisory. The backend still enforces every local write guard.
  const health = await api.health();
  if (!health.local_demo_writes_enabled)
    throw new ApiError(
      "Local demo writes are disabled. Restart the backend with the documented local flag, then Refresh API.",
      403,
    );
  return readApi(path, schema, undefined, body);
}

// Fixed workflow routes only; no credentials, identity, evidence or delivery options.
export const api = {
  generateBriefing: async (evaluation: Evaluation, signal?: AbortSignal) => {
    evaluationIdSchema.parse(evaluation.evaluation_id);
    const health = await api.health(signal);
    if (!health.local_demo_writes_enabled || !health.ai_briefing_enabled)
      throw new ApiError(
        "AI briefing is disabled on this local backend. Enable the documented server opt-in and Refresh API.",
        403,
      );
    const briefing = await readApi(
      `/api/evaluations/${evaluation.evaluation_id}/ai-briefing`,
      aiBriefingSchema,
      signal,
      {},
      105000,
    );
    if (
      briefing.evaluation_id !== evaluation.evaluation_id ||
      briefing.facility_id !== evaluation.result.facility_id ||
      briefing.facility_name !== evaluation.evidence_snapshot.facility.name ||
      briefing.data_mode !== evaluation.data_mode ||
      briefing.data_label !== evaluation.result.data_label ||
      briefing.evaluated_at !== evaluation.result.evaluated_at ||
      briefing.authoritative_recommendation !==
        evaluation.result.recommendation ||
      JSON.stringify(briefing.evidence_references) !==
        JSON.stringify(evaluation.source_timestamps)
    )
      throw new ApiError(
        "AI briefing does not match the loaded authoritative evaluation. Nothing was displayed.",
      );
    return briefing;
  },
  nationalNws: (signal?: AbortSignal) =>
    readApi(
      "/api/nws/alerts/active",
      nationalAlertsSchema,
      signal,
      undefined,
      45000,
    ),
  health: (signal?: AbortSignal) =>
    readApi("/api/health", healthSchema, signal),
  facilities: (signal?: AbortSignal) =>
    readApi("/api/facilities", z.array(facilitySchema).max(100), signal),
  scenarios: (signal?: AbortSignal) =>
    readApi("/api/demo/scenarios", z.array(scenarioSchema).max(100), signal),
  audit: (signal?: AbortSignal) =>
    readApi("/api/audit?limit=100", z.array(decisionSchema).max(100), signal),
  evaluation: (id: string, signal?: AbortSignal) => {
    if (!evaluationIdSchema.safeParse(id).success)
      return Promise.reject(
        new ApiError(
          "Use an evaluation ID in the format eval_ followed by 32 lowercase hexadecimal characters.",
        ),
      );
    return readApi(
      `/api/evaluations/${encodeURIComponent(id)}`,
      evaluationSchema,
      signal,
    ).then((e) => {
      if (e.evaluation_id !== id)
        throw new ApiError("Saved evaluation ID mismatch.");
      return e;
    });
  },
  createEvaluation: (facilityId: string, scenarioId: string) => {
    const input = scenarioSchema.shape;
    const body = {
      facility_id: input.facility_id.parse(facilityId),
      scenario_id: input.scenario_id.parse(scenarioId),
    };
    return writeApi("/api/evaluations", evaluationSchema, body).then((e) => {
      if (
        e.result.facility_id !== facilityId ||
        e.data_mode !== "SIMULATED DEMO"
      )
        throw new ApiError(
          "Returned evaluation does not match this demo facility.",
        );
      return e;
    });
  },
  decide: (id: string, action: DecisionAction) => {
    evaluationIdSchema.parse(id);
    return writeApi(
      `/api/evaluations/${id}/decisions`,
      decisionSchema,
      decisionActionSchema.parse(action),
    ).then((d) => {
      if (d.evaluation_id !== id)
        throw new ApiError("Saved decision does not match the evaluation.");
      return d;
    });
  },
  decision: (id: string, signal?: AbortSignal) => {
    decisionIdSchema.parse(id);
    return readApi(`/api/decisions/${id}`, decisionSchema, signal).then((d) => {
      if (d.decision_id !== id)
        throw new ApiError("Saved decision ID mismatch.");
      return d;
    });
  },
  notificationPlan: (id: string, signal?: AbortSignal) => {
    decisionIdSchema.parse(id);
    return readApi(
      `/api/decisions/${id}/notification-plan`,
      notificationPlanSchema,
      signal,
    ).then((p) => {
      if (p.decision_id !== id)
        throw new ApiError("Saved plan does not match the decision.");
      return p;
    });
  },
  createNotificationPlan: (id: string) => {
    decisionIdSchema.parse(id);
    return writeApi(
      `/api/decisions/${id}/notification-plans`,
      notificationPlanSchema,
      {},
    ).then((p) => {
      if (p.decision_id !== id)
        throw new ApiError("Saved plan does not match the decision.");
      return p;
    });
  },
};
