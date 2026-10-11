import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../src/api/client";
import {
  decisionActionSchema,
  notificationPlanSchema,
} from "../../src/api/schemas";
import fixtures from "../fixtures/api.json";

afterEach(() => vi.unstubAllGlobals());
const response = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
describe("manager API boundary", () => {
  it("checks backend write capability and submits only the allowlisted action", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        response({ ...fixtures.health, local_demo_writes_enabled: true }),
      )
      .mockResolvedValueOnce(response(fixtures.audit[0], 201));
    vi.stubGlobal("fetch", fetch);
    await api.decide(fixtures.audit[0].evaluation_id, { action: "APPROVE" });
    expect(fetch.mock.calls[1][1]).toMatchObject({
      method: "POST",
      credentials: "omit",
      body: '{"action":"APPROVE"}',
    });
  });
  it("fails closed when writes are disabled or capability is missing", async () => {
    for (const health of [
      { ...fixtures.health, local_demo_writes_enabled: false },
      { status: "ok", service: "closureops-api", data_mode: "synthetic_demo" },
    ]) {
      const fetch = vi.fn().mockResolvedValue(response(health));
      vi.stubGlobal("fetch", fetch);
      await expect(
        api.createEvaluation("jefferson-research", "normal"),
      ).rejects.toMatchObject({ status: 403 });
      expect(fetch).toHaveBeenCalledTimes(1);
    }
  });
  it("rejects identity injection, missing override reasons and control characters", () => {
    for (const input of [
      { action: "APPROVE", manager: "fake" },
      { action: "OVERRIDE", selected_posture: "OPEN" },
      { action: "OVERRIDE", selected_posture: "OPEN", reason: "   " },
      { action: "OVERRIDE", selected_posture: "OPEN", reason: "x\ny" },
    ])
      expect(decisionActionSchema.safeParse(input).success).toBe(false);
  });
  it("rejects real delivery and inconsistent employee totals", () => {
    expect(
      notificationPlanSchema.safeParse(fixtures.notification_plan).success,
    ).toBe(true);
    expect(
      notificationPlanSchema.safeParse({
        ...fixtures.notification_plan,
        total_assigned: 0,
      }).success,
    ).toBe(false);
    expect(
      notificationPlanSchema.safeParse({
        ...fixtures.notification_plan,
        messages: fixtures.notification_plan.messages.map((m) => ({
          ...m,
          route: "email",
        })),
      }).success,
    ).toBe(false);
  });
  it("does not retry a failed human write automatically", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        response({ ...fixtures.health, local_demo_writes_enabled: true }),
      )
      .mockRejectedValueOnce(new Error("connection lost"));
    vi.stubGlobal("fetch", fetch);
    await expect(
      api.decide(fixtures.audit[0].evaluation_id, { action: "APPROVE" }),
    ).rejects.toThrow("Cannot reach");
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});
