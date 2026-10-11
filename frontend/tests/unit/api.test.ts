import { afterEach, describe, expect, it, vi } from "vitest";
import fixtures from "../fixtures/api.json";
import { api, API_BASE_URL, validateApiBaseUrl } from "../../src/api/client";
import {
  decisionSchema,
  evaluationSchema,
  facilitySchema,
  scenarioSchema,
} from "../../src/api/schemas";
import {
  confirmedClosures,
  mascotState,
  recommendationTitle,
} from "../../src/lib/dashboard";
import { sourceUrl } from "../../src/lib/utils";

const facility = facilitySchema.parse(fixtures.facilities[0]);
const review = evaluationSchema.parse(fixtures.evaluations.missing_evidence);
const closure = evaluationSchema.parse(
  fixtures.evaluations.severe_applicable_flood,
);
const decision = decisionSchema.parse(fixtures.audit[0]);
afterEach(() => vi.unstubAllGlobals());

describe("backend response contract", () => {
  it("accepts the actual facility and seven scenario responses", () => {
    fixtures.facilities.forEach((f) =>
      expect(facilitySchema.safeParse(f).success).toBe(true),
    );
    fixtures.scenarios.forEach((s) =>
      expect(scenarioSchema.safeParse(s).success).toBe(true),
    );
  });
  it.each(Object.entries(fixtures.evaluations))(
    "accepts the actual %s evaluation",
    (_, value) => {
      expect(evaluationSchema.safeParse(value).success).toBe(true);
    },
  );
  it("rejects an OPEN posture attached to REVIEW_REQUIRED", () => {
    const fixture = fixtures.evaluations.missing_evidence;
    const invalid = {
      ...fixture,
      result: { ...fixture.result, recommendation: "OPEN" },
    };
    expect(evaluationSchema.safeParse(invalid).success).toBe(false);
  });
  it("rejects insufficient evidence attached to a ready recommendation", () => {
    const invalid = structuredClone(
      fixtures.evaluations.severe_applicable_flood,
    );
    invalid.result.evidence_sufficiency = "INSUFFICIENT";
    expect(evaluationSchema.safeParse(invalid).success).toBe(false);
  });
  it("rejects a snapshot for a different facility", () => {
    const invalid = structuredClone(fixtures.evaluations.normal);
    invalid.evidence_snapshot.facility.id = "another-facility";
    expect(evaluationSchema.safeParse(invalid).success).toBe(false);
  });
  it("rejects invalid coordinates and missing source timestamps", () => {
    expect(
      facilitySchema.safeParse({
        ...fixtures.facilities[0],
        coordinates: { latitude: 200, longitude: 0 },
      }).success,
    ).toBe(false);
    expect(
      facilitySchema.safeParse({
        ...fixtures.facilities[0],
        source_timestamp: null,
      }).success,
    ).toBe(false);
  });
  it("rejects unauthoritative manager decisions", () => {
    expect(
      decisionSchema.safeParse({
        ...fixtures.audit[0],
        manager_action: "ACKNOWLEDGE_REVIEW",
      }).success,
    ).toBe(false);
  });
});

describe("read-only API client", () => {
  it("defaults to the current API and rejects the legacy port", () => {
    expect(API_BASE_URL).toBe("http://127.0.0.1:8001");
    expect(validateApiBaseUrl(API_BASE_URL)).toBe(API_BASE_URL);
    expect(() => validateApiBaseUrl("http://127.0.0.1:8000")).toThrow(
      "legacy API",
    );
    expect(() => validateApiBaseUrl("http://localhost:8000")).toThrow(
      "restart Vite",
    );
  });
  it("sends GET with no credentials and validates data", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(fixtures.facilities), {
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    expect(await api.facilities()).toEqual([facility]);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      method: "GET",
      credentials: "omit",
    });
  });
  it("rejects invalid responses before displaying them", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response('[{"id":"unsafe"}]', {
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    await expect(api.facilities()).rejects.toThrow("expected schema");
  });
  it("does not treat an empty catalog as a network failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("[]", {
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    expect(await api.facilities()).toEqual([]);
  });
  it("rejects non-JSON and malformed JSON", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response("<html>offline</html>", {
          headers: { "Content-Type": "text/html" },
        }),
      )
      .mockResolvedValueOnce(
        new Response("{broken", {
          headers: { "Content-Type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.health()).rejects.toThrow("response format");
    await expect(api.health()).rejects.toThrow("response is invalid");
  });
  it("reports offline errors without leaking exception content", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("private internal detail")),
    );
    await expect(api.health()).rejects.toThrow("Cannot reach the local API");
  });
  it("honors rate-limit guidance without automatic retries", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response("{}", { status: 429, headers: { "Retry-After": "30" } }),
      );
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.health()).rejects.toMatchObject({
      status: 429,
      retryAfter: 30,
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it("rejects user-controlled path input before fetching", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.evaluation("../../settings")).rejects.toThrow(
      "evaluation ID",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("explains missing saved records", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("{}", { status: 404 })),
    );
    await expect(api.evaluation(review.evaluation_id)).rejects.toThrow(
      "Saved record not found",
    );
  });
});

describe("dashboard integrity", () => {
  it("never renders REVIEW_REQUIRED as OPEN", () => {
    expect(recommendationTitle(review)).toBe("Manual review required");
    expect(mascotState(review, false, [])).toBe("review_required");
  });
  it("does not infer a recommendation from the facility catalog", () => {
    expect(recommendationTitle(null)).toBe("Awaiting evaluation");
    expect(mascotState(null, false, [])).toBe("idle");
  });
  it("uses only verified workflow states for the mascot", () => {
    expect(mascotState(null, true, [])).toBe("monitoring");
    expect(mascotState(closure, false, [])).toBe("high_risk");
    expect(mascotState(closure, false, [decision])).toBe("high_risk");
  });
  it("keeps acquisition and review states ahead of hazard presentation", () => {
    expect(mascotState(closure, true, [decision])).toBe("monitoring");
    expect(
      mascotState(review, false, [
        { ...decision, evaluation_id: review.evaluation_id },
      ]),
    ).toBe("review_required");
  });
  it("does not infer high risk from explanation prose", () => {
    const normal = evaluationSchema.parse(fixtures.evaluations.normal);
    normal.result.reasons = ["Severe flood danger, high risk, closure"];
    expect(mascotState(normal, false, [])).toBe("awaiting_approval");
    expect(
      mascotState(normal, false, [
        { ...decision, evaluation_id: normal.evaluation_id },
      ]),
    ).toBe("resolved");
  });
  it("requires simulated provenance for the simulated high-risk artwork", () => {
    expect(
      mascotState({ ...closure, data_mode: "LIVE_EVIDENCE" }, false, []),
    ).toBe("awaiting_approval");
    expect(
      mascotState(
        { ...closure, result: { ...closure.result, data_label: "LIVE" } },
        false,
        [],
      ),
    ).toBe("awaiting_approval");
  });
  it("counts manager-confirmed closures rather than engine recommendations", () => {
    expect(confirmedClosures([], [facility])).toBe(0);
    expect(confirmedClosures([decision], [facility])).toBe(1);
    expect(confirmedClosures(null, [facility])).toBeNull();
    expect(confirmedClosures([decision], null)).toBeNull();
  });
  it("uses the latest finalized posture without counting historical closures twice", () => {
    const opened = {
      ...decision,
      decision_timestamp: "2027-01-01T00:00:00Z",
      final_posture: "OPEN" as const,
    };
    expect(confirmedClosures([decision, opened], [facility])).toBe(0);
    expect(confirmedClosures([decision, decision], [facility])).toBe(1);
  });
  it("does not let a review acknowledgment erase the last confirmed posture", () => {
    const ack = {
      ...decision,
      manager_action: "ACKNOWLEDGE_REVIEW" as const,
      final_posture: null,
      decision_timestamp: "2027-01-01T00:00:00Z",
    };
    expect(confirmedClosures([decision, ack], [facility])).toBe(1);
  });
  it("does not publish a total from a capped history response", () => {
    expect(confirmedClosures(Array(100).fill(decision), [facility])).toBeNull();
  });
  it("links only HTTPS official NWS/USGS hosts", () => {
    expect(sourceUrl("https://api.weather.gov/alerts")).toBe(
      "https://api.weather.gov/alerts",
    );
    expect(
      sourceUrl(
        "https://waterdata.usgs.gov/monitoring-location/USGS-06910230/",
      ),
    ).not.toBeNull();
    [
      "javascript:alert(1)",
      "http://api.weather.gov",
      "https://api.weather.gov.evil.com",
      "https://user:pass@api.weather.gov",
      "demo:nws",
    ].forEach((url) => expect(sourceUrl(url)).toBeNull());
  });
});
