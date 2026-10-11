"""Local simulated preparation from immutable SQLite manager decisions only.

The local FastAPI adapter exposes preparation routes. No agent registration,
model generation or messaging transport exists.
The only request field is a decision ID; posture and facility come from saved history.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Annotated, Iterator, Literal
from uuid import uuid4

from pydantic import Field, StrictStr, TypeAdapter, field_validator, model_validator

from backend.app.decision.models import EvaluationStatus, FacilityId, Model, OperatingPosture, Text, Timestamp
from backend.app.employee_impact import Count, EmployeeGroup, resolve_employee_impact
from backend.app.manager_decisions import (
    DEFAULT_DATABASE, AuditStorageError, DecisionId, DecisionRecord, ManagerAction, ManagerDecisionService,
)

NotificationPlanId = Annotated[StrictStr, Field(pattern=r"^notification_[0-9a-f]{32}$")]
MessageText = Annotated[StrictStr, Field(min_length=1, max_length=2048)]


class NotificationPlanRequest(Model):
    decision_id: DecisionId


def _instruction(posture: OperatingPosture, group: EmployeeGroup) -> str:
    if group == EmployeeGroup.ESSENTIAL_PERSONNEL:
        return ("Contact authorized management to confirm your assignment and access authorization "
                "before any travel or facility entry. Essential designation alone does not authorize entry.")
    if posture == OperatingPosture.OPEN:
        return "Follow your normal onsite schedule."
    if posture == OperatingPosture.DELAYED_ARRIVAL:
        return ("Hold onsite arrival until authorized management confirms the revised arrival time. "
                "No revised arrival time is recorded in this decision.")
    if posture == OperatingPosture.UNSCHEDULED_TELEWORK:
        if group == EmployeeGroup.TELEWORK_ELIGIBLE:
            return "Work remotely for the demonstration shift; do not report onsite."
        return "Do not report onsite; contact authorized management for work instructions."
    if posture == OperatingPosture.FACILITY_CLOSURE:
        return "Do not report to or enter the facility. Await authorized management instructions for work assignments."
    raise ValueError("Unsupported finalized posture")


def render_notification(facility_name: str, posture: OperatingPosture,
                        group: EmployeeGroup, decision_id: str) -> str:
    # Task 8A records no operating effective time. Neither decision_timestamp,
    # normal opening, fixture time nor NWS alert effective time is a substitute.
    return (f"SIMULATED DEMO | Facility: {facility_name} | Final operating posture: {posture.value} | "
            f"Effective time: not recorded | Employee group: {group.value} | "
            f"Instruction: {_instruction(posture, group)} | Decision reference: {decision_id}")


class GroupNotification(Model):
    group: EmployeeGroup
    count: Count
    message: MessageText
    route: Literal["simulated"] = "simulated"
    status: Literal["GENERATED_SIMULATED"] = "GENERATED_SIMULATED"


class NotificationPlan(Model):
    notification_plan_id: NotificationPlanId
    decision_id: DecisionId
    facility_id: FacilityId
    facility_name: Text
    final_posture: OperatingPosture
    # No manager operating effective time exists in the current audit schema.
    effective_at: Literal[None] = None
    group_counts: dict[EmployeeGroup, Count]
    total_assigned: Count
    total_scheduled: Count
    total_unscheduled: Count
    total_affected: Count
    messages: tuple[GroupNotification, ...]
    roster_source: Literal["ClosureOps synthetic demonstration shift fixture"]
    roster_source_timestamp: Timestamp
    template_version: Literal["task8b-v1"] = "task8b-v1"
    status: Literal["GENERATED_SIMULATED"] = "GENERATED_SIMULATED"
    created_at: Timestamp
    data_mode: Literal["SIMULATED DEMO"] = "SIMULATED DEMO"

    @field_validator("created_at", "roster_source_timestamp", mode="before")
    @classmethod
    def timestamp_type(cls, value: object) -> object:
        if not isinstance(value, (str, datetime)):
            raise ValueError("Expected an aware datetime or ISO timestamp")
        return value

    @model_validator(mode="after")
    def consistent_plan(self) -> NotificationPlan:
        if (set(self.group_counts) != set(EmployeeGroup)
                or sum(self.group_counts.values()) != self.total_affected
                or self.total_affected != self.total_scheduled
                or self.total_assigned != self.total_scheduled + self.total_unscheduled):
            raise ValueError("Notification totals must match computed scheduled groups")
        if tuple(message.group for message in self.messages) != tuple(EmployeeGroup):
            raise ValueError("Each employee group must have exactly one message")
        for message in self.messages:
            if (message.count != self.group_counts[message.group]
                    or message.message != render_notification(
                        self.facility_name, self.final_posture, message.group, self.decision_id)):
                raise ValueError("Messages must preserve the deterministic approved-posture template")
        return self


class NotificationPlanError(ValueError):
    pass


class DuplicateNotificationPlan(NotificationPlanError):
    pass


class NotificationPlanNotFound(NotificationPlanError):
    pass


class NotificationPlanService:
    """In-process LOCAL DEMO ONLY; database path is trusted application configuration.

    A plan records aggregate counts and exact prepared messages, not individual
    contact preferences or delivery. Reopening a plan never reloads the roster,
    regenerates messages, evaluates weather or changes a historical decision.
    """

    def __init__(self, database_path: Path = DEFAULT_DATABASE) -> None:
        self._decisions = ManagerDecisionService(database_path)
        self._database_path = Path(database_path).resolve()
        with self._connection() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS simulated_notification_plans (
                    notification_plan_id TEXT PRIMARY KEY,
                    decision_id TEXT NOT NULL UNIQUE REFERENCES manager_decisions(decision_id),
                    plan_json TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS notification_plans_no_update
                BEFORE UPDATE ON simulated_notification_plans BEGIN
                    SELECT RAISE(ABORT, 'Notification plan history is immutable');
                END;
                CREATE TRIGGER IF NOT EXISTS notification_plans_no_delete
                BEFORE DELETE ON simulated_notification_plans BEGIN
                    SELECT RAISE(ABORT, 'Notification plan history is immutable');
                END;
                CREATE TRIGGER IF NOT EXISTS notification_plans_no_replace
                BEFORE INSERT ON simulated_notification_plans
                WHEN EXISTS (SELECT 1 FROM simulated_notification_plans
                    WHERE decision_id = NEW.decision_id OR notification_plan_id = NEW.notification_plan_id)
                BEGIN SELECT RAISE(ABORT, 'A notification plan already exists'); END;
                CREATE TRIGGER IF NOT EXISTS notification_plans_require_final_posture
                BEFORE INSERT ON simulated_notification_plans
                WHEN NOT EXISTS (
                    SELECT 1 FROM manager_decisions d WHERE d.decision_id = NEW.decision_id
                    AND json_extract(d.record_json, '$.manager_action') IN ('APPROVE', 'OVERRIDE')
                    AND json_extract(d.record_json, '$.evaluation_status') = 'RECOMMENDATION_READY'
                    AND json_extract(d.record_json, '$.decision_id') = NEW.decision_id
                    AND json_extract(NEW.plan_json, '$.decision_id') = NEW.decision_id
                    AND json_extract(NEW.plan_json, '$.notification_plan_id') = NEW.notification_plan_id
                    AND json_extract(NEW.plan_json, '$.facility_id') = json_extract(d.record_json, '$.facility_id')
                    AND json_extract(NEW.plan_json, '$.final_posture') = json_extract(d.record_json, '$.final_posture')
                    AND json_extract(NEW.plan_json, '$.data_mode') = 'SIMULATED DEMO'
                    AND json_extract(NEW.plan_json, '$.status') = 'GENERATED_SIMULATED'
                )
                BEGIN SELECT RAISE(ABORT, 'Notification plan must match a finalized manager posture'); END;
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
            raise AuditStorageError("Local notification audit storage failed; no plan was confirmed") from error

    def _trusted_decision(self, decision_id: str) -> DecisionRecord:
        record = self._decisions.get_decision(decision_id)
        if (record.decision_id != decision_id
                or record.evaluation != self._decisions.get_evaluation(record.evaluation_id)):
            raise NotificationPlanError("Stored decision does not match trusted evaluation history")
        if (record.manager_action not in {ManagerAction.APPROVE, ManagerAction.OVERRIDE}
                or record.evaluation_status != EvaluationStatus.RECOMMENDATION_READY
                or record.final_posture is None):
            raise NotificationPlanError("Only finalized APPROVE or OVERRIDE decisions can prepare notifications")
        return record

    def prepare(self, request: NotificationPlanRequest) -> NotificationPlan:
        """Persist one deterministic simulated plan; never accepts facility/posture overrides."""
        # Revalidate the raw fields: model_dump can silently omit fields injected
        # through model_copy/model_construct, which must also be rejected here.
        request = NotificationPlanRequest.model_validate(vars(request))
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            record = self._trusted_decision(request.decision_id)
            if connection.execute(
                "SELECT 1 FROM simulated_notification_plans WHERE decision_id = ?", (record.decision_id,),
            ).fetchone():
                raise DuplicateNotificationPlan("A simulated notification plan already exists for this decision")
            impact = resolve_employee_impact(record.facility_id)
            if impact.facility_id != record.facility_id:
                raise NotificationPlanError("Employee impact must match the finalized decision facility")
            plan = NotificationPlan(
                notification_plan_id=f"notification_{uuid4().hex}", decision_id=record.decision_id,
                facility_id=record.facility_id, facility_name=record.evidence_snapshot.facility.name,
                final_posture=record.final_posture, group_counts=impact.group_counts,
                total_assigned=impact.total_assigned, total_scheduled=impact.total_scheduled,
                total_unscheduled=impact.total_unscheduled, total_affected=impact.total_affected,
                messages=tuple(GroupNotification(
                    group=group.group, count=group.count,
                    message=render_notification(record.evidence_snapshot.facility.name,
                                                record.final_posture, group.group, record.decision_id),
                ) for group in impact.groups),
                roster_source=impact.source, roster_source_timestamp=impact.source_timestamp,
                created_at=datetime.now(timezone.utc),
            )
            connection.execute(
                "INSERT INTO simulated_notification_plans (notification_plan_id, decision_id, plan_json) VALUES (?, ?, ?)",
                (plan.notification_plan_id, plan.decision_id, plan.model_dump_json()),
            )
        return plan

    def _reconstruct(self, row: tuple[str, str, str] | None) -> NotificationPlan:
        if row is None:
            raise NotificationPlanNotFound("Simulated notification plan not found")
        plan = NotificationPlan.model_validate_json(row[2])
        record = self._trusted_decision(row[1])
        if (plan.notification_plan_id != row[0] or plan.decision_id != row[1]
                or plan.facility_id != record.facility_id or plan.final_posture != record.final_posture
                or plan.facility_name != record.evidence_snapshot.facility.name
                or plan.created_at < record.decision_timestamp):
            raise NotificationPlanError("Stored plan does not match finalized manager history")
        return plan

    def get_plan(self, notification_plan_id: str) -> NotificationPlan:
        notification_plan_id = TypeAdapter(NotificationPlanId).validate_python(notification_plan_id)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT notification_plan_id, decision_id, plan_json FROM simulated_notification_plans "
                "WHERE notification_plan_id = ?", (notification_plan_id,),
            ).fetchone()
        return self._reconstruct(row)

    def get_plan_for_decision(self, decision_id: str) -> NotificationPlan:
        decision_id = TypeAdapter(DecisionId).validate_python(decision_id)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT notification_plan_id, decision_id, plan_json FROM simulated_notification_plans "
                "WHERE decision_id = ?", (decision_id,),
            ).fetchone()
        return self._reconstruct(row)
