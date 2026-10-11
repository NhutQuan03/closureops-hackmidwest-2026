import {
  useCallback,
  useEffect,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import { api } from "../api/client";
import type { Decision, Facility, Health, Scenario } from "../api/schemas";

export interface Resource<T> {
  status: "loading" | "ready" | "error";
  data: T | null;
  error: string | null;
  checkedAt: string | null;
  successfulAt?: string | null;
}
const loading = <T>(): Resource<T> => ({
  status: "loading",
  data: null,
  error: null,
  checkedAt: null,
  successfulAt: null,
});
export function useCommandCenter() {
  const [attempt, setAttempt] = useState(0);
  const [health, setHealth] = useState<Resource<Health>>(loading);
  const [facilities, setFacilities] = useState<Resource<Facility[]>>(loading);
  const [scenarios, setScenarios] = useState<Resource<Scenario[]>>(loading);
  const [audit, setAudit] = useState<Resource<Decision[]>>(loading);
  useEffect(() => {
    const controller = new AbortController();
    async function load<T>(
      request: (signal: AbortSignal) => Promise<T>,
      setter: Dispatch<SetStateAction<Resource<T>>>,
    ) {
      setter((previous) => ({ ...previous, status: "loading", error: null }));
      try {
        const data = await request(controller.signal);
        if (!controller.signal.aborted) {
          const checkedAt = new Date().toISOString();
          setter({
            status: "ready",
            data,
            error: null,
            checkedAt,
            successfulAt: checkedAt,
          });
        }
      } catch (error) {
        if (!controller.signal.aborted)
          setter((previous) => ({
            status: "error",
            data: null,
            error:
              error instanceof Error ? error.message : "API data unavailable.",
            checkedAt: new Date().toISOString(),
            successfulAt: previous.successfulAt,
          }));
      }
    }
    void Promise.allSettled([
      load(api.health, setHealth),
      load(api.facilities, setFacilities),
      load(api.scenarios, setScenarios),
      load(api.audit, setAudit),
    ]);
    return () => controller.abort();
  }, [attempt]);
  const refreshAudit = useCallback(async () => {
    setAudit((previous) => ({ ...previous, status: "loading", error: null }));
    try {
      const data = await api.audit();
      setAudit({
        status: "ready",
        data,
        error: null,
        checkedAt: new Date().toISOString(),
      });
    } catch (error) {
      setAudit({
        status: "error",
        data: null,
        error: error instanceof Error ? error.message : "History unavailable.",
        checkedAt: new Date().toISOString(),
      });
    }
  }, []);
  return {
    health,
    facilities,
    scenarios,
    audit,
    refreshAudit,
    refresh: useCallback(() => setAttempt((a) => a + 1), []),
  };
}
