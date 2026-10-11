"""Explicit local inference bound to an immutable persisted evaluation.

Reuse the tested Strands agent, Akamai compatibility model, and briefing validator.
Untrusted model prose, exceptions, credentials and traces never enter responses.
"""
from __future__ import annotations

from datetime import datetime, timezone
import multiprocessing
import os
from time import monotonic
from threading import BoundedSemaphore
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.decision.fixtures import demo_input_for_facility, scenario_fixtures
from backend.app.decision.models import EvidenceReference, FacilityId, OperatingPosture, Timestamp
from backend.app.decision_briefing import render_briefing, validate_briefing
from backend.app.decision_tool import create_decision_tool
from backend.app.manager_decisions import EvaluationId, TrustedEvaluation
from backend.app.situation_briefing import SituationBriefing, compose_situation_briefing
from scripts.test_akamai_decision_tool import MAX_OUTPUT_TOKENS, build_agent
from scripts.test_akamai_strands import API_KEY_ENV_VAR, build_model, get_error_category, load_strands_classes

REQUEST_TIMEOUT_SECONDS = 90
MAX_SNAPSHOT_BYTES = 512 * 1024


class AIBriefingResponse(BaseModel):
    # Only backend-rendered explanation may contain line breaks; request models
    # retain the existing stricter input policy.
    model_config = ConfigDict(extra="forbid", frozen=True)
    evaluation_id: EvaluationId
    facility_id: FacilityId
    facility_name: str = Field(min_length=1, max_length=500)
    data_mode: Literal["SIMULATED DEMO", "LIVE_EVIDENCE"]
    data_label: str = Field(min_length=1, max_length=100)
    authoritative_recommendation: OperatingPosture | None
    human_approval_required: Literal[True] = True
    generated_at: Timestamp
    evaluated_at: Timestamp
    status: Literal["VALIDATED", "FALLBACK", "UNAVAILABLE", "TIMEOUT", "ERROR"]
    validation_status: Literal["VALIDATED", "REJECTED", "NOT_RUN"]
    model_completed: bool
    tool_execution_confirmed: bool
    explanation_source: Literal["VALIDATED_RULES", "DETERMINISTIC_FALLBACK", "NONE"]
    explanation: str | None = Field(default=None, max_length=65536)
    situation_briefing: SituationBriefing | None = None
    reason: Literal["OK", "AI_DISABLED", "MISSING_CREDENTIALS", "UNSUPPORTED_SNAPSHOT",
                    "SNAPSHOT_MISMATCH", "INVALID_MODEL_OUTPUT", "TOOL_NOT_CONFIRMED",
                    "MODEL_TIMEOUT", "PROVIDER_ERROR", "DEPENDENCY_UNAVAILABLE", "BUSY"]
    evidence_references: tuple[EvidenceReference, ...]

    @model_validator(mode="after")
    def validation_consistency(self) -> AIBriefingResponse:
        if self.status == "VALIDATED" and not (
            self.validation_status == "VALIDATED" and self.model_completed
            and self.tool_execution_confirmed and self.reason == "OK"
            and self.explanation_source == "VALIDATED_RULES" and self.explanation
        ):
            raise ValueError("Inconsistent briefing validation")
        if self.status != "VALIDATED" and (self.validation_status == "VALIDATED" or self.explanation_source == "VALIDATED_RULES"):
            raise ValueError("Unvalidated briefing cannot claim validation")
        if (self.explanation_source == "NONE") != (self.explanation is None):
            raise ValueError("Inconsistent explanation source")
        if (self.situation_briefing is None) != (self.explanation is None):
            raise ValueError("Inconsistent situation briefing")
        return self


class SnapshotMismatch(ValueError):
    pass


def authoritative_snapshot(evaluation: TrustedEvaluation) -> dict[str, Any]:
    result = evaluation.result.model_dump(mode="json")
    return {
        **result, "ok": True, "recommended_posture": result["recommendation"],
        "data_mode": evaluation.data_mode,
        "supporting_evidence": evaluation.evidence_snapshot.model_dump(mode="json"),
        "source_timestamps": [reference.model_dump(mode="json") for reference in evaluation.source_timestamps],
        "source_checks": [check.model_dump(mode="json") for check in evaluation.source_checks],
        "integration_limitations": list(evaluation.integration_limitations),
    }


def bound_tool(evaluation: TrustedEvaluation, events: list[dict[str, Any]]) -> Any:
    """Only exact known synthetic snapshots can be reproduced by the existing tool.

    Live acquisition would fetch new timestamps/evidence, so it is intentionally
    unsupported here. No client prompt, scenario, policy or evidence is accepted.
    """
    facility_id = evaluation.result.facility_id
    if evaluation.data_mode != "SIMULATED DEMO" or facility_id != "jefferson-research":
        raise SnapshotMismatch()
    matches = [name for name in scenario_fixtures()
               if demo_input_for_facility(name, facility_id) == evaluation.evidence_snapshot]
    if len(matches) != 1:
        raise SnapshotMismatch()
    tool = create_decision_tool("SIMULATED DEMO", matches[0], events, demo_facility_id=facility_id)
    # This preflight is deterministic; it is not confirmation of an agent tool call.
    preflight = create_decision_tool("SIMULATED DEMO", matches[0], demo_facility_id=facility_id)
    if preflight(facility_id) != authoritative_snapshot(evaluation):
        raise SnapshotMismatch()
    return tool


def response_for(evaluation: TrustedEvaluation, status: str, reason: str, *,
                 confirmed: bool = False, completed: bool = False,
                 validation: str = "NOT_RUN", fallback: bool = True) -> AIBriefingResponse:
    validated = status == "VALIDATED"
    text = render_briefing(authoritative_snapshot(evaluation)) if validated or fallback else None
    return AIBriefingResponse(
        evaluation_id=evaluation.evaluation_id, facility_id=evaluation.result.facility_id,
        facility_name=evaluation.evidence_snapshot.facility.name,
        data_mode=evaluation.data_mode, data_label=evaluation.result.data_label,
        authoritative_recommendation=evaluation.result.recommendation,
        generated_at=datetime.now(timezone.utc), evaluated_at=evaluation.result.evaluated_at,
        status=status, reason=reason, validation_status=validation,
        model_completed=completed, tool_execution_confirmed=confirmed,
        explanation_source="VALIDATED_RULES" if validated else "DETERMINISTIC_FALLBACK" if fallback else "NONE",
        explanation=text, evidence_references=evaluation.source_timestamps,
        situation_briefing=compose_situation_briefing(evaluation) if text is not None else None,
    )


def run_agent(evaluation: TrustedEvaluation, key: str) -> AIBriefingResponse:
    """Run only the tested agent/model and verify its request-local execution ledger."""
    from strands.hooks import BeforeModelCallEvent, BeforeToolCallEvent

    events: list[dict[str, Any]] = []
    try:
        tool = bound_tool(evaluation, events)
    except SnapshotMismatch:
        return response_for(evaluation, "UNAVAILABLE", "UNSUPPORTED_SNAPSHOT", fallback=False)
    authoritative = authoritative_snapshot(evaluation)
    completed = False
    try:
        loaded = load_strands_classes()
        if loaded is None:
            return response_for(evaluation, "UNAVAILABLE", "DEPENDENCY_UNAVAILABLE")
        agent_class, model_class = loaded
        agent = build_agent(agent_class, build_model(model_class, key, max_output_tokens=MAX_OUTPUT_TOKENS), tool)

        def enforce_binding(event: Any) -> None:
            if events and (len(events) != 1 or events[0] != authoritative):
                raise SnapshotMismatch()
            if isinstance(event, BeforeToolCallEvent):
                if (events or event.tool_use["name"] != "evaluate_operating_status"
                        or event.tool_use["input"] != {"facility_id": evaluation.result.facility_id}):
                    raise SnapshotMismatch()

        agent.add_hook(enforce_binding, BeforeToolCallEvent)
        agent.add_hook(enforce_binding, BeforeModelCallEvent)
        output = str(agent(
            f'Call evaluate_operating_status exactly once with facility_id="{evaluation.result.facility_id}". '
            "Return the required JSON selection unchanged from that trusted tool. Human approval remains required."
        ))
        completed = True
        if len(events) != 1 or events[0] != authoritative:
            return response_for(evaluation, "UNAVAILABLE", "TOOL_NOT_CONFIRMED", completed=True, fallback=False)
        if not validate_briefing(output, authoritative):
            return response_for(evaluation, "FALLBACK", "INVALID_MODEL_OUTPUT", confirmed=True,
                                completed=True, validation="REJECTED")
        return response_for(evaluation, "VALIDATED", "OK", confirmed=True, completed=True, validation="VALIDATED")
    except SnapshotMismatch:
        return response_for(evaluation, "UNAVAILABLE", "SNAPSHOT_MISMATCH", completed=completed, fallback=False)
    except Exception as error:
        # Categorize using exception type/status only, never its message or provider body.
        timeout = isinstance(error, TimeoutError) or get_error_category(error) == "timeout"
        confirmed = len(events) == 1 and events[0] == authoritative
        return response_for(evaluation, "TIMEOUT" if timeout else "ERROR",
                            "MODEL_TIMEOUT" if timeout else "PROVIDER_ERROR", confirmed=confirmed)


def briefing_worker(snapshot_json: str, sender: Any) -> None:
    """Spawned process owns provider credentials and can be forcibly timed out."""
    import logging

    logging.disable(logging.CRITICAL)
    try:
        evaluation = TrustedEvaluation.model_validate_json(snapshot_json)
        key = os.environ.get(API_KEY_ENV_VAR, "").strip()
        result = run_agent(evaluation, key) if key else response_for(evaluation, "UNAVAILABLE", "MISSING_CREDENTIALS")
        sender.send(result.model_dump(mode="json"))
    except Exception:
        # Even unexpected child failures must not print provider exceptions or traces.
        try:
            sender.send(None)
        except Exception:
            pass
    finally:
        sender.close()


def execute_worker(evaluation: TrustedEvaluation) -> AIBriefingResponse:
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=briefing_worker, args=(evaluation.model_dump_json(), sender), daemon=True)
    started = monotonic()
    try:
        process.start()
        sender.close()
        if not receiver.poll(max(0, REQUEST_TIMEOUT_SECONDS - (monotonic() - started))):
            return response_for(evaluation, "TIMEOUT", "MODEL_TIMEOUT")
        result = AIBriefingResponse.model_validate(receiver.recv())
        if (result.evaluation_id != evaluation.evaluation_id or result.facility_id != evaluation.result.facility_id
                or result.facility_name != evaluation.evidence_snapshot.facility.name
                or result.data_mode != evaluation.data_mode or result.data_label != evaluation.result.data_label
                or result.evaluated_at != evaluation.result.evaluated_at
                or result.authoritative_recommendation != evaluation.result.recommendation
                or result.evidence_references != evaluation.source_timestamps
                or result.situation_briefing != (compose_situation_briefing(evaluation) if result.explanation is not None else None)
                or (result.explanation is not None and result.explanation != render_briefing(authoritative_snapshot(evaluation)))):
            return response_for(evaluation, "UNAVAILABLE", "SNAPSHOT_MISMATCH", fallback=False)
        return result
    except Exception:
        return response_for(evaluation, "ERROR", "PROVIDER_ERROR")
    finally:
        if process.pid is not None:
            if process.is_alive():
                process.terminate()
            process.join(timeout=5)
            if process.is_alive():
                process.kill()
                process.join(timeout=5)
            process.close()
        receiver.close()
        sender.close()


class AIBriefingService:
    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self._slot = BoundedSemaphore(1)

    def generate(self, evaluation: TrustedEvaluation) -> AIBriefingResponse:
        if not self.enabled:
            return response_for(evaluation, "UNAVAILABLE", "AI_DISABLED")
        if len(evaluation.model_dump_json().encode("utf-8")) > MAX_SNAPSHOT_BYTES:
            return response_for(evaluation, "UNAVAILABLE", "UNSUPPORTED_SNAPSHOT", fallback=False)
        try:
            bound_tool(evaluation, [])
        except SnapshotMismatch:
            return response_for(evaluation, "UNAVAILABLE", "UNSUPPORTED_SNAPSHOT", fallback=False)
        if not os.environ.get(API_KEY_ENV_VAR, "").strip():
            return response_for(evaluation, "UNAVAILABLE", "MISSING_CREDENTIALS")
        if not self._slot.acquire(blocking=False):
            return response_for(evaluation, "UNAVAILABLE", "BUSY")
        try:
            return execute_worker(evaluation)
        finally:
            self._slot.release()
