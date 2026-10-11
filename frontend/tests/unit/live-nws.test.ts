import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import { nationalAlertsSchema } from "../../src/api/schemas";
import { nationalAlertState, nationalFeedState } from "../../src/lib/liveNws";
import { nationalFixture } from "../fixtures/national-nws";

afterEach(() => vi.unstubAllGlobals());
const now = Date.parse("2026-10-11T06:00:00Z");
describe("national NWS provenance and freshness", () => {
  it("expires a successful retrieval and never keeps LIVE after refresh failure", () => {
    const feed = nationalFixture(now);
    expect(nationalFeedState(feed, now)).toBe("LIVE");
    expect(nationalFeedState(feed, now + 300_000)).toBe("STALE");
    expect(nationalFeedState(feed, now, true)).toBe("STALE");
    expect(
      nationalFeedState(
        {
          ...feed,
          alerts: [{ ...feed.alerts[0], expires: new Date(now).toISOString() }],
        },
        now,
      ),
    ).toBe("STALE");
    expect(nationalAlertState(feed.alerts[0], "STALE", now)).toBe("STALE");
    expect(
      nationalAlertState(
        { ...feed.alerts[0], expires: new Date(now).toISOString() },
        "LIVE",
        now,
      ),
    ).toBe("STALE");
  });
  it("does not treat missing or future timestamps as verified current evidence", () => {
    const feed = nationalFixture(now);
    expect(
      nationalFeedState(
        { ...feed, retrieved_at: new Date(now + 120_000).toISOString() },
        now,
      ),
    ).toBe("STALE");
    expect(nationalFeedState({ ...feed, fresh_until: null }, now)).toBe(
      "STALE",
    );
    expect(
      nationalAlertState({ ...feed.alerts[0], expires: null }, "LIVE", now),
    ).toBe("STALE");
  });
  it("accepts an empty complete collection but rejects partial no-alert claims", () => {
    const feed = {
      ...nationalFixture(now),
      status: "NO_ACTIVE_ALERTS",
      alerts: [],
      collection_limited: false,
      examined_count: 0,
    };
    expect(nationalAlertsSchema.safeParse(feed).success).toBe(true);
    expect(
      nationalAlertsSchema.safeParse({ ...feed, collection_limited: true })
        .success,
    ).toBe(false);
    expect(
      nationalAlertsSchema.safeParse({ ...feed, examined_count: 1 }).success,
    ).toBe(false);
  });
  it("rejects arbitrary URLs, inconsistent provenance and excess selections", () => {
    const feed = nationalFixture(now);
    expect(
      nationalAlertsSchema.safeParse({
        ...feed,
        alerts: [
          { ...feed.alerts[0], source_url: "https://untrusted.example/" },
        ],
      }).success,
    ).toBe(false);
    expect(
      nationalAlertsSchema.safeParse({ ...feed, status: "STALE" }).success,
    ).toBe(false);
    expect(
      nationalAlertsSchema.safeParse({
        ...feed,
        alerts: Array(6).fill(feed.alerts[0]),
      }).success,
    ).toBe(false);
    expect(
      nationalAlertsSchema.safeParse({
        ...feed,
        facility_applicability: "APPLIES",
      }).success,
    ).toBe(false);
  });
  it("calls only the fixed read-only national endpoint", async () => {
    const fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(nationalFixture()), {
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetch);
    await api.nationalNws();
    expect(fetch.mock.calls[0][0]).toBe(
      "http://127.0.0.1:8001/api/nws/alerts/active",
    );
    expect(fetch.mock.calls[0][1].method).toBe("GET");
    expect(fetch.mock.calls[0][1].credentials).toBe("omit");
  });
});
