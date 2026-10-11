import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type {
  Decision,
  DecisionAction,
  Evaluation,
  NotificationPlan,
} from "../api/schemas";

async function existingPlan(decision: Decision, signal?: AbortSignal) {
  if (decision.manager_action === "ACKNOWLEDGE_REVIEW") return null;
  try {
    const plan = await api.notificationPlan(decision.decision_id, signal);
    if (
      plan.facility_id !== decision.facility_id ||
      plan.final_posture !== decision.final_posture
    )
      throw new Error(
        "Saved plan does not match the persisted manager posture.",
      );
    return plan;
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export function useManagerWorkflow(
  evaluation: Evaluation | null,
  writesEnabled: boolean,
) {
  const id = evaluation?.evaluation_id;
  const currentId = useRef(id);
  currentId.current = id;
  const lock = useRef(false);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [plan, setPlan] = useState<NotificationPlan | null>(null);
  const [checked, setChecked] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [denied, setDenied] = useState(false);
  const [attempt, setAttempt] = useState(0);

  const reconcile = useCallback(
    async (signal?: AbortSignal) => {
      if (!id) return null;
      const records = await api.audit(signal);
      const saved = records.find((d) => d.evaluation_id === id);
      if (!saved && records.length === 100)
        throw new Error(
          "History is capped at 100 records. Cannot verify whether this evaluation was finalized. Use a new evaluation.",
        );
      const exact = saved
        ? await api.decision(saved.decision_id, signal)
        : null;
      if (currentId.current !== id || signal?.aborted) return null;
      setDecision(exact);
      setChecked(true);
      if (exact) {
        const savedPlan = await existingPlan(exact, signal);
        if (currentId.current === id && !signal?.aborted) setPlan(savedPlan);
      }
      return exact;
    },
    [id],
  );

  useEffect(() => {
    const controller = new AbortController();
    setDecision(null);
    setPlan(null);
    setChecked(false);
    setError(null);
    setDenied(false);
    setPending(Boolean(id));
    if (id)
      void reconcile(controller.signal)
        .catch((error) => {
          if (!controller.signal.aborted)
            setError(
              error instanceof Error ? error.message : "History unavailable.",
            );
        })
        .finally(() => {
          if (!controller.signal.aborted) setPending(false);
        });
    return () => controller.abort();
  }, [id, reconcile, attempt]);

  async function submit(action: DecisionAction) {
    if (
      !id ||
      !writesEnabled ||
      denied ||
      !checked ||
      decision ||
      pending ||
      lock.current
    )
      return;
    lock.current = true;
    setPending(true);
    setError(null);
    try {
      const saved = await api.decide(id, action);
      if (currentId.current === id) {
        setDecision(saved);
        setChecked(true);
      }
    } catch (failure) {
      if (currentId.current !== id) return;
      if (failure instanceof ApiError && failure.status === 403)
        setDenied(true);
      setChecked(false);
      // A timeout/409 can follow a successful commit. Read persisted history;
      // never resubmit an uncertain human action automatically.
      try {
        const saved = await reconcile();
        if (!saved)
          setError(
            `${failure instanceof Error ? failure.message : "Decision not confirmed."} No saved decision found. Review before trying again.`,
          );
      } catch {
        setChecked(false);
        setError(
          "Decision outcome is unconfirmed. Check saved history before trying again.",
        );
      }
    } finally {
      lock.current = false;
      if (currentId.current === id) setPending(false);
    }
  }

  async function prepare() {
    if (
      !decision ||
      decision.manager_action === "ACKNOWLEDGE_REVIEW" ||
      !writesEnabled ||
      denied ||
      pending ||
      lock.current
    )
      return;
    lock.current = true;
    setPending(true);
    setError(null);
    try {
      const saved = await existingPlan(decision);
      const prepared =
        saved ?? (await api.createNotificationPlan(decision.decision_id));
      if (currentId.current === id) setPlan(prepared);
    } catch (failure) {
      if (currentId.current !== id) return;
      if (failure instanceof ApiError && failure.status === 403)
        setDenied(true);
      try {
        const saved = await existingPlan(decision);
        if (saved) setPlan(saved);
        else
          setError(
            `${failure instanceof Error ? failure.message : "Plan unavailable."} No saved plan found; preparation can be retried explicitly.`,
          );
      } catch {
        setError(
          "Plan outcome is unconfirmed. Check saved history before trying again.",
        );
      }
    } finally {
      lock.current = false;
      if (currentId.current === id) setPending(false);
    }
  }

  const visibleDecision = decision?.evaluation_id === id ? decision : null;
  return {
    decision: visibleDecision,
    plan: plan?.decision_id === visibleDecision?.decision_id ? plan : null,
    pending,
    error,
    submit,
    prepare,
    canAct: Boolean(
      id && checked && writesEnabled && !denied && !decision && !pending,
    ),
    canPrepare: Boolean(
      visibleDecision &&
      visibleDecision.manager_action !== "ACKNOWLEDGE_REVIEW" &&
      writesEnabled &&
      !denied &&
      !pending,
    ),
    retry: () => {
      if (!lock.current) setAttempt((n) => n + 1);
    },
  };
}
