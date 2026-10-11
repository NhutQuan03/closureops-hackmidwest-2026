"""Local application service for synthetic manager actions, never an agent tool.

Only evaluate_facility can register trusted evaluations. Manager requests contain
an ID and an explicit action, never evidence, policy, identity, or a recommendation.
The local FastAPI adapter exposes application routes, never agent registrations.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
import sqlite3
from typing import Annotated, Iterator, Literal
from uuid import uuid4

from pydantic import Field, StrictStr, TypeAdapter, field_validator, model_validator

from backend.app.decision.models import (
    DecisionInput, DecisionResult, EvaluationStatus, EvidenceReference, FacilityId,
    Model, OperatingPosture, Text, Timestamp,
)
from backend.app.decision_tool import DataMode, SourceCheck, create_decision_tool

DEFAULT_DATABASE = Path(__file__).resolve().parents[1] / "data" / "manager-decisions.sqlite3"
EvaluationId = Annotated[StrictStr, Field(pattern=r"^eval_[0-9a-f]{32}$")]
DecisionId = Annotated[StrictStr, Field(pattern=r"^decision_[0-9a-f]{32}$")]


class ManagerAction(StrEnum):
    APPROVE = "APPROVE"
    OVERRIDE = "OVERRIDE"
    ACKNOWLEDGE_REVIEW = "ACKNOWLEDGE_REVIEW"


class DemoManager(Model):
    id: Literal["demo-manager"] = "demo-manager"
    display_name: Literal["Synthetic Demo Manager"] = "Synthetic Demo Manager"
    synthetic: Literal[True] = True


class ManagerDecisionRequest(Model):
    evaluation_id: EvaluationId
    action: ManagerAction
    selected_posture: OperatingPosture | None = None
    reason: Text | None = None

    @model_validator(mode="after")
    def action_fields(self) -> ManagerDecisionRequest:
        if self.action == ManagerAction.OVERRIDE:
            if self.selected_posture is None or self.reason is None:
                raise ValueError("Override requires a supported posture and a reason (1-500 characters)")
        elif self.selected_posture is not None or self.reason is not None:
            raise ValueError("Only an override accepts a selected posture or reason")
        return self


class TrustedEvaluation(Model):
    evaluation_id: EvaluationId
    data_mode: DataMode
    evidence_snapshot: DecisionInput
    result: DecisionResult
    source_timestamps: tuple[EvidenceReference, ...]
    source_checks: tuple[SourceCheck, ...]
    integration_limitations: tuple[Text, ...]

    @model_validator(mode="after")
    def snapshot_consistency(self) -> TrustedEvaluation:
        if (self.result.facility_id != self.evidence_snapshot.facility.id
                or self.result.evaluated_at != self.evidence_snapshot.evaluated_at
                or self.result.rules != self.evidence_snapshot.rules
                or self.source_timestamps != self.result.evidence_references):
            raise ValueError("Evaluation snapshot is inconsistent")
        return self


class DecisionRecord(Model):
    decision_id: DecisionId
    evaluation_id: EvaluationId
    facility_id: FacilityId
    evaluation_status: EvaluationStatus
    original_recommendation: OperatingPosture | None
    manager_action: ManagerAction
    final_posture: OperatingPosture | None
    override_reason: Text | None
    manager: DemoManager
    evidence_snapshot: DecisionInput
    source_timestamps: tuple[EvidenceReference, ...]
    data_mode: DataMode
    decision_timestamp: Timestamp
    # Includes historical thresholds, fired rules, limitations and approval flag.
    evaluation: TrustedEvaluation

    @field_validator("decision_timestamp", mode="before")
    @classmethod
    def timestamp_type(cls, value: object) -> object:
        if not isinstance(value, (str, datetime)):
            raise ValueError("Expected an aware datetime or ISO timestamp")
        return value

    @model_validator(mode="after")
    def historical_consistency(self) -> DecisionRecord:
        evaluation = self.evaluation
        result = evaluation.result
        if (self.evaluation_id != evaluation.evaluation_id
                or self.facility_id != result.facility_id
                or self.evaluation_status != result.evaluation_status
                or self.original_recommendation != result.recommendation
                or self.evidence_snapshot != evaluation.evidence_snapshot
                or self.source_timestamps != evaluation.source_timestamps
                or self.data_mode != evaluation.data_mode):
            raise ValueError("Decision must preserve the original evaluation")
        _validate_action(result, self.manager_action, self.final_posture, self.override_reason)
        return self


class ManagerDecisionError(ValueError):
    """An action cannot be recorded; no finalized history has changed."""


class EvaluationNotFound(ManagerDecisionError):
    pass


class DecisionNotFound(ManagerDecisionError):
    pass


class DuplicateDecision(ManagerDecisionError):
    pass


class AuditStorageError(RuntimeError):
    pass


def _validate_action(result: DecisionResult, action: ManagerAction,
                     final_posture: OperatingPosture | None, reason: str | None) -> None:
    if result.human_approval_required is not True:
        raise ManagerDecisionError("Evaluation must require human approval")
    if result.evaluation_status == EvaluationStatus.REVIEW_REQUIRED:
        if action != ManagerAction.ACKNOWLEDGE_REVIEW or final_posture is not None or reason is not None:
            raise ManagerDecisionError("REVIEW_REQUIRED has no recommendation; acknowledge review only")
    elif action == ManagerAction.APPROVE:
        if final_posture != result.recommendation or reason is not None:
            raise ManagerDecisionError("Approval must preserve the recommended posture")
    elif action == ManagerAction.OVERRIDE:
        if final_posture is None or final_posture == result.recommendation or reason is None:
            raise ManagerDecisionError("Override requires a different supported posture and a reason")
    else:
        raise ManagerDecisionError("Only REVIEW_REQUIRED can be acknowledged")


class ManagerDecisionService:
    """In-process local demo boundary; a demo identity is not authentication.

    Do not expose this service on public routes without backend authorization.
    Database paths and evaluation mode/scenario are trusted application settings.
    No method imports a client evaluation, edits records, changes facility status,
    or sends notifications. Existing agent tools are unchanged.
    """

    def __init__(self, database_path: Path = DEFAULT_DATABASE, *,
                 data_mode: DataMode = "SIMULATED DEMO", demo_scenario: str = "normal",
                 demo_facility_id: str = "demo-flood-facility") -> None:
        self._evaluate = create_decision_tool(data_mode, demo_scenario, demo_facility_id=demo_facility_id)
        self._database_path = Path(database_path).resolve()
        if any(part.lower() in {"frontend", "public"} for part in self._database_path.parts):
            raise ValueError("Audit database must be outside frontend/public directories")
        try:
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise AuditStorageError("Cannot create the local audit directory") from error
        with self._connection() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS manager_evaluations (
                    evaluation_id TEXT PRIMARY KEY,
                    snapshot_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS manager_decisions (
                    decision_id TEXT PRIMARY KEY,
                    evaluation_id TEXT NOT NULL UNIQUE REFERENCES manager_evaluations(evaluation_id),
                    record_json TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS evaluations_no_update
                BEFORE UPDATE ON manager_evaluations BEGIN
                    SELECT RAISE(ABORT, 'Evaluation history is immutable');
                END;
                CREATE TRIGGER IF NOT EXISTS evaluations_no_delete
                BEFORE DELETE ON manager_evaluations BEGIN
                    SELECT RAISE(ABORT, 'Evaluation history is immutable');
                END;
                CREATE TRIGGER IF NOT EXISTS evaluations_no_replace
                BEFORE INSERT ON manager_evaluations
                WHEN EXISTS (SELECT 1 FROM manager_evaluations WHERE evaluation_id = NEW.evaluation_id)
                BEGIN SELECT RAISE(ABORT, 'Evaluation history is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS decisions_no_update
                BEFORE UPDATE ON manager_decisions BEGIN
                    SELECT RAISE(ABORT, 'Decision history is immutable');
                END;
                CREATE TRIGGER IF NOT EXISTS decisions_no_delete
                BEFORE DELETE ON manager_decisions BEGIN
                    SELECT RAISE(ABORT, 'Decision history is immutable');
                END;
                CREATE TRIGGER IF NOT EXISTS decisions_no_replace
                BEFORE INSERT ON manager_decisions
                WHEN EXISTS (SELECT 1 FROM manager_decisions
                             WHERE decision_id = NEW.decision_id OR evaluation_id = NEW.evaluation_id)
                BEGIN SELECT RAISE(ABORT, 'A final decision already exists'); END;
            """)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        try:
            connection = sqlite3.connect(self._database_path, timeout=5)
            try:
                connection.execute("PRAGMA foreign_keys = ON")
                with connection:
                    yield connection
            finally:
                connection.close()
        except sqlite3.Error as error:
            raise AuditStorageError("Local audit storage failed; no action was confirmed") from error

    def evaluate_facility(self, facility_id: str) -> TrustedEvaluation:
        """Generate and persist an evaluation through the existing trusted tool.

        The public method accepts only a facility ID. An agent response, a prior
        smoke-test ledger, or a client-authored snapshot cannot be registered here.
        """
        raw = self._evaluate(facility_id)
        if raw.get("ok") is not True:
            raise ManagerDecisionError(raw.get("error", "Evaluation failed"))
        result = DecisionResult.model_validate({key: raw[key] for key in DecisionResult.model_fields})
        evaluation = TrustedEvaluation(
            evaluation_id=f"eval_{uuid4().hex}", data_mode=raw["data_mode"],
            evidence_snapshot=DecisionInput.model_validate(raw["supporting_evidence"]),
            result=result, source_timestamps=raw["source_timestamps"],
            source_checks=raw["source_checks"], integration_limitations=raw["integration_limitations"],
        )
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO manager_evaluations (evaluation_id, snapshot_json) VALUES (?, ?)",
                (evaluation.evaluation_id, evaluation.model_dump_json()),
            )
        return evaluation

    def get_evaluation(self, evaluation_id: str) -> TrustedEvaluation:
        evaluation_id = TypeAdapter(EvaluationId).validate_python(evaluation_id)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT snapshot_json FROM manager_evaluations WHERE evaluation_id = ?", (evaluation_id,),
            ).fetchone()
        if row is None:
            raise EvaluationNotFound("No trusted evaluation exists for this ID")
        return TrustedEvaluation.model_validate_json(row[0])

    def record_decision(self, request: ManagerDecisionRequest) -> DecisionRecord:
        """Record a validated explicit local manager action, once per evaluation."""
        # Revalidate even model_construct/model_copy objects before any write.
        request = ManagerDecisionRequest.model_validate(request.model_dump(mode="python", warnings=False))
        evaluation = self.get_evaluation(request.evaluation_id)
        result = evaluation.result
        final_posture = result.recommendation if request.action == ManagerAction.APPROVE else request.selected_posture
        _validate_action(result, request.action, final_posture, request.reason)
        record = DecisionRecord(
            decision_id=f"decision_{uuid4().hex}", evaluation_id=evaluation.evaluation_id,
            facility_id=result.facility_id, evaluation_status=result.evaluation_status,
            original_recommendation=result.recommendation, manager_action=request.action,
            final_posture=final_posture, override_reason=request.reason, manager=DemoManager(),
            evidence_snapshot=evaluation.evidence_snapshot, source_timestamps=evaluation.source_timestamps,
            data_mode=evaluation.data_mode, decision_timestamp=datetime.now(timezone.utc), evaluation=evaluation,
        )
        with self._connection() as connection:
            # BEGIN IMMEDIATE serializes competing writers; UNIQUE remains the
            # database-level guard across service instances and process restarts.
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute(
                "SELECT 1 FROM manager_decisions WHERE evaluation_id = ?", (evaluation.evaluation_id,),
            ).fetchone():
                raise DuplicateDecision("A final manager action already exists for this evaluation")
            connection.execute(
                "INSERT INTO manager_decisions (decision_id, evaluation_id, record_json) VALUES (?, ?, ?)",
                (record.decision_id, record.evaluation_id, record.model_dump_json()),
            )
        return record

    def get_decision(self, decision_id: str) -> DecisionRecord:
        decision_id = TypeAdapter(DecisionId).validate_python(decision_id)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT record_json FROM manager_decisions WHERE decision_id = ?", (decision_id,),
            ).fetchone()
        if row is None:
            raise DecisionNotFound("Decision not found")
        return DecisionRecord.model_validate_json(row[0])

    def list_history(self, *, facility_id: str | None = None, limit: int = 100) -> tuple[DecisionRecord, ...]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("History limit must be an integer between 1 and 100")
        if facility_id is not None:
            facility_id = TypeAdapter(FacilityId).validate_python(facility_id)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT d.record_json FROM manager_decisions d "
                "JOIN manager_evaluations e ON e.evaluation_id = d.evaluation_id "
                "WHERE (? IS NULL OR json_extract(e.snapshot_json, '$.result.facility_id') = ?) "
                "ORDER BY d.rowid DESC LIMIT ?", (facility_id, facility_id, limit),
            ).fetchall()
        return tuple(DecisionRecord.model_validate_json(row[0]) for row in rows)
