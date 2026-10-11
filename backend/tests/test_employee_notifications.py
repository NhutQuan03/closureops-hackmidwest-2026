"""Offline Task 8B grouping, trusted manager authority and immutable plan audit."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import socket
import sqlite3
from unittest.mock import AsyncMock, Mock

import httpx
from pydantic import ValidationError
import pytest

from backend.app import decision_tool, employee_notifications as notifications
from backend.app.decision.fixtures import demo_input_for_facility, scenario_fixtures
from backend.app.decision.models import OperatingPosture
from backend.app.employee_impact import (
    EmployeeGroup, EmployeeImpactError, SyntheticEmployee, SyntheticRoster,
    group_scheduled_employees, load_facility_roster, resolve_employee_impact,
)
from backend.app.employee_notifications import (
    DuplicateNotificationPlan, NotificationPlan, NotificationPlanError, NotificationPlanNotFound,
    NotificationPlanRequest, NotificationPlanService,
)
from backend.app.main import app
from backend.app.manager_decisions import (
    AuditStorageError, DecisionNotFound, ManagerDecisionRequest, ManagerDecisionService,
)
from scripts import test_employee_notifications as smoke

FACILITY = "jefferson-research"


@pytest.fixture(autouse=True)
def no_external_calls(monkeypatch):
    blocked = Mock(side_effect=AssertionError("No external network or delivery calls permitted"))
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", AsyncMock(side_effect=blocked.side_effect))
    monkeypatch.setattr(decision_tool, "fetch_nws_alerts", blocked)
    monkeypatch.setattr(decision_tool, "fetch_usgs_conditions", blocked)
    yield blocked
    blocked.assert_not_called()


@pytest.fixture
def database(tmp_path):
    return tmp_path / "audit.sqlite3"


def finalize(database, scenario="severe_applicable_flood", *, override=None):
    managers = ManagerDecisionService(database, demo_scenario=scenario, demo_facility_id=FACILITY)
    evaluation = managers.evaluate_facility(FACILITY)
    request = ManagerDecisionRequest(
        evaluation_id=evaluation.evaluation_id,
        action="OVERRIDE" if override else "APPROVE",
        selected_posture=override, reason="Synthetic manager verified alternate operating arrangements." if override else None,
    )
    return managers, evaluation, managers.record_decision(request)


def prepare(database, record):
    return NotificationPlanService(database).prepare(NotificationPlanRequest(decision_id=record.decision_id))


def synthetic_employee(index, **changes):
    return SyntheticEmployee.model_validate({
        "employee_id": f"synthetic-test-{index}", "synthetic_name": f"Synthetic Employee {index}",
        "role": "Synthetic support", "facility_id": FACILITY, "scheduled_today": True,
        "essential_employee": False, "telework_eligible": False, "notification_preference": "onscreen",
        **changes,
    })


def test_demo_roster_and_exclusive_group_counts():
    roster = load_facility_roster(FACILITY)
    assert roster == load_facility_roster(FACILITY)
    assert len(roster.employees) == 54
    assert sum(employee.scheduled_today for employee in roster.employees) == 47
    assert sum(employee.scheduled_today and employee.telework_eligible for employee in roster.employees) == 31
    assert sum(employee.scheduled_today and employee.essential_employee for employee in roster.employees) == 6
    assert all(employee.synthetic_name.startswith("Synthetic Employee") for employee in roster.employees)
    assert all(employee.data_mode == "SIMULATED DEMO" for employee in roster.employees)
    impact = resolve_employee_impact(FACILITY)
    assert impact.total_assigned == 54
    assert impact.total_scheduled == impact.total_affected == 47
    assert impact.total_unscheduled == 7
    assert impact.group_counts == {"TELEWORK_ELIGIBLE": 31, "STANDARD_ONSITE": 10, "ESSENTIAL_PERSONNEL": 6}
    ids = [employee_id for group in impact.groups for employee_id in group.employee_ids]
    assert len(ids) == len(set(ids)) == 47
    assert set(ids) == {employee.employee_id for employee in roster.employees if employee.scheduled_today}
    assert not set(ids) & {employee.employee_id for employee in roster.employees if not employee.scheduled_today}
    assert impact.source_timestamp == roster.source_timestamp
    assert impact.source == roster.source and impact.data_mode == "SIMULATED DEMO"


def test_precedence_and_computed_counts_for_arbitrary_roster():
    employees = (
        synthetic_employee(1, essential_employee=True, telework_eligible=True),
        synthetic_employee(2, telework_eligible=True), synthetic_employee(3),
        synthetic_employee(4, scheduled_today=False, essential_employee=True),
    )
    impact = group_scheduled_employees(SyntheticRoster(facility_id=FACILITY, employees=employees))
    assert impact.group_counts == {group: 1 for group in EmployeeGroup}
    assert impact.total_assigned == 4 and impact.total_affected == 3 and impact.total_unscheduled == 1
    assert impact.groups[0].employee_ids == (employees[0].employee_id,)


def test_empty_roster():
    impact = group_scheduled_employees(SyntheticRoster(facility_id=FACILITY, employees=()))
    assert impact.total_assigned == impact.total_affected == impact.total_scheduled == impact.total_unscheduled == 0
    assert impact.group_counts == {group: 0 for group in EmployeeGroup}


@pytest.mark.parametrize("employees", [
    (synthetic_employee(1), synthetic_employee(1)),
    (synthetic_employee(1, facility_id="another-facility"),),
])
def test_invalid_roster_rejected(employees):
    with pytest.raises(ValidationError):
        SyntheticRoster(facility_id=FACILITY, employees=employees)


def test_constructed_roster_cannot_bypass_validation():
    with pytest.raises(ValidationError):
        group_scheduled_employees(SyntheticRoster.model_construct(
            facility_id=FACILITY, employees=(synthetic_employee(1), synthetic_employee(1)),
        ))


@pytest.mark.parametrize("facility_id", [None, 1, "", "a\n", "../file", "X", "x" * 65])
def test_invalid_facility_ids_rejected(facility_id):
    with pytest.raises(ValidationError):
        resolve_employee_impact(facility_id)


@pytest.mark.parametrize("facility_id", ["unknown", "demo-flood-facility"])
def test_unknown_roster_facility_rejected(facility_id):
    with pytest.raises(EmployeeImpactError):
        resolve_employee_impact(facility_id)


@pytest.mark.parametrize("scenario", tuple(scenario_fixtures()))
def test_jefferson_binding_keeps_prototype_evidence_and_thresholds(scenario):
    original = scenario_fixtures()[scenario].input
    bound = demo_input_for_facility(scenario, FACILITY)
    assert bound.facility.id == bound.exposure.facility_id == bound.nws.facility_id == FACILITY
    assert bound.facility.name == "Jefferson Research Facility"
    assert bound.facility.data_source == "SIMULATED DEMO"
    assert bound.exposure.thresholds == original.exposure.thresholds
    assert bound.exposure.monitoring_location_id == "USGS-00000000"
    assert "invented" in bound.exposure.basis and "not the configured regional USGS" in bound.exposure.basis
    assert bound.evaluated_at == original.evaluated_at and bound.rules == original.rules
    assert (bound.usgs.observations if bound.usgs else None) == (original.usgs.observations if original.usgs else None)
    assert scenario_fixtures()[scenario].input == original


@pytest.mark.parametrize("mode,binding", [
    ("SIMULATED DEMO", "unknown"), ("LIVE_EVIDENCE", FACILITY),
])
def test_demo_binding_cannot_configure_live_or_unknown_facility(database, mode, binding):
    with pytest.raises(ValueError):
        ManagerDecisionService(database, data_mode=mode, demo_facility_id=binding)


@pytest.mark.parametrize("scenario,posture", [
    ("normal", "OPEN"), ("delayed_arrival", "DELAYED_ARRIVAL"),
    ("unscheduled_telework", "UNSCHEDULED_TELEWORK"), ("severe_applicable_flood", "FACILITY_CLOSURE"),
])
def test_approved_postures_templates_and_simulated_status(database, scenario, posture):
    managers, evaluation, record = finalize(database, scenario)
    before = datetime.now(timezone.utc)
    plan = prepare(database, record)
    assert plan.final_posture == record.final_posture == posture
    assert plan.group_counts == {"TELEWORK_ELIGIBLE": 31, "STANDARD_ONSITE": 10, "ESSENTIAL_PERSONNEL": 6}
    assert plan.total_assigned == 54 and plan.total_affected == plan.total_scheduled == 47 and plan.total_unscheduled == 7
    assert plan.status == "GENERATED_SIMULATED" and plan.data_mode == "SIMULATED DEMO"
    assert before <= plan.created_at <= datetime.now(timezone.utc)
    assert plan.effective_at is None
    for message in plan.messages:
        assert "Jefferson Research Facility" in message.message
        assert f"Final operating posture: {posture}" in message.message
        assert message.group in message.message and record.decision_id in message.message
        assert "SIMULATED DEMO" in message.message and "Effective time: not recorded" in message.message
        assert "Instruction:" in message.message
        assert message.status == "GENERATED_SIMULATED" and message.route == "simulated"
        assert evaluation.evidence_snapshot.evaluated_at.isoformat() not in message.message
    essential = plan.messages[0].message
    assert "authorized management" in essential and "before any travel or facility entry" in essential
    assert "does not authorize entry" in essential
    assert managers.get_decision(record.decision_id) == record
    if posture == "OPEN":
        assert "normal onsite schedule" in plan.messages[1].message
    elif posture == "DELAYED_ARRIVAL":
        assert all("Hold onsite arrival" in message.message for message in plan.messages[1:])
        assert all("No revised arrival time is recorded" in message.message for message in plan.messages[1:])
    elif posture == "UNSCHEDULED_TELEWORK":
        assert "Work remotely" in plan.messages[1].message
        assert "Do not report onsite; contact authorized management" in plan.messages[2].message
    else:
        assert all("Do not report to or enter the facility" in message.message for message in plan.messages[1:])


@pytest.mark.parametrize("posture", tuple(OperatingPosture))
def test_override_final_posture_controls_notifications(database, posture):
    scenario = "severe_applicable_flood" if posture == "OPEN" else "normal"
    _, _, record = finalize(database, scenario, override=posture)
    assert record.original_recommendation != posture
    plan = prepare(database, record)
    assert plan.final_posture == posture
    assert all(f"Final operating posture: {posture}" in message.message for message in plan.messages)


@pytest.mark.parametrize("scenario", ["missing_evidence", "stale_evidence", "conflicting_evidence"])
def test_review_acknowledgment_rejected(database, scenario):
    managers = ManagerDecisionService(database, demo_scenario=scenario, demo_facility_id=FACILITY)
    evaluation = managers.evaluate_facility(FACILITY)
    record = managers.record_decision(ManagerDecisionRequest(
        evaluation_id=evaluation.evaluation_id, action="ACKNOWLEDGE_REVIEW",
    ))
    with pytest.raises(NotificationPlanError, match="Only finalized"):
        prepare(database, record)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM simulated_notification_plans").fetchone()[0] == 0
    assert managers.get_decision(record.decision_id) == record


@pytest.mark.parametrize("decision_id", [None, 1, "", "decision_bad", "a\n", "' OR 1=1 --", "eval_" + "a" * 32])
def test_invalid_or_unfinalized_decision_ids_rejected(decision_id):
    with pytest.raises(ValidationError):
        NotificationPlanRequest(decision_id=decision_id)


def test_missing_and_unfinalized_decision_rejected(database):
    managers = ManagerDecisionService(database, demo_facility_id=FACILITY)
    evaluation = managers.evaluate_facility(FACILITY)
    service = NotificationPlanService(database)
    with pytest.raises(ValidationError):
        NotificationPlanRequest(decision_id=evaluation.evaluation_id)
    # A valid-looking decision ID manufactured from an evaluation is still absent.
    with pytest.raises(DecisionNotFound):
        service.prepare(NotificationPlanRequest(decision_id=evaluation.evaluation_id.replace("eval_", "decision_")))
    with pytest.raises(DecisionNotFound):
        service.prepare(NotificationPlanRequest(decision_id="decision_" + "0" * 32))


@pytest.mark.parametrize("field,value", [
    ("facility_id", "another-facility"), ("final_posture", "OPEN"),
    ("decision", {"manager_action": "APPROVE", "final_posture": "OPEN"}),
    ("effective_at", "2026-10-10T21:00:00Z"), ("message", "Travel into the closed facility."),
    ("manager_action", "APPROVE"), ("group_counts", {"TELEWORK_ELIGIBLE": 99}),
])
def test_client_substitution_and_fabricated_decisions_rejected(database, field, value):
    _, _, record = finalize(database)
    payload = {"decision_id": record.decision_id, field: value}
    with pytest.raises(ValidationError):
        NotificationPlanRequest.model_validate(payload)
    bypass = NotificationPlanRequest.model_construct(**payload)
    # model_construct discards extras; inject them to exercise service revalidation.
    bypass.__dict__[field] = value
    with pytest.raises(ValidationError):
        NotificationPlanService(database).prepare(bypass)


def test_fabricated_record_object_not_accepted(database):
    _, _, record = finalize(database)
    with pytest.raises(ValidationError):
        NotificationPlanService(database).prepare(record)


def test_duplicate_rejected_across_restart_and_exact_reconstruction(database, monkeypatch):
    managers, evaluation, record = finalize(database)
    with sqlite3.connect(database) as connection:
        original_evaluations = connection.execute("SELECT * FROM manager_evaluations").fetchall()
        original_decisions = connection.execute("SELECT * FROM manager_decisions").fetchall()
    plan = prepare(database, record)
    monkeypatch.setattr(notifications, "resolve_employee_impact", Mock(side_effect=AssertionError("No roster reload")))
    monkeypatch.setattr(ManagerDecisionService, "evaluate_facility", Mock(side_effect=AssertionError("No re-evaluation")))
    service = NotificationPlanService(database)
    assert service.get_plan(plan.notification_plan_id) == plan
    assert service.get_plan_for_decision(record.decision_id).model_dump_json() == plan.model_dump_json()
    with pytest.raises(DuplicateNotificationPlan):
        service.prepare(NotificationPlanRequest(decision_id=record.decision_id))
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT * FROM manager_evaluations").fetchall() == original_evaluations
        assert connection.execute("SELECT * FROM manager_decisions").fetchall() == original_decisions
        assert connection.execute("SELECT COUNT(*) FROM simulated_notification_plans").fetchone()[0] == 1
        assert connection.execute("SELECT plan_json FROM simulated_notification_plans").fetchone()[0] == plan.model_dump_json()
    assert managers.get_decision(record.decision_id) == record
    assert managers.get_evaluation(evaluation.evaluation_id) == evaluation


def test_competing_preparations_create_only_one_plan(database):
    _, _, record = finalize(database)
    services = [NotificationPlanService(database), NotificationPlanService(database)]

    def attempt(service):
        try:
            return service.prepare(NotificationPlanRequest(decision_id=record.decision_id))
        except DuplicateNotificationPlan:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, services))
    assert sum(result is not None for result in results) == 1


@pytest.mark.parametrize("statement", [
    "UPDATE simulated_notification_plans SET plan_json = '{}' WHERE notification_plan_id = ?",
    "DELETE FROM simulated_notification_plans WHERE notification_plan_id = ?",
    "INSERT OR REPLACE INTO simulated_notification_plans SELECT * FROM simulated_notification_plans WHERE notification_plan_id = ?",
])
def test_notification_history_is_immutable(database, statement):
    _, _, record = finalize(database)
    plan = prepare(database, record)
    with sqlite3.connect(database) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(statement, (plan.notification_plan_id,))
    assert NotificationPlanService(database).get_plan(plan.notification_plan_id) == plan


@pytest.mark.parametrize("field,value", [("facility_id", "wrong-facility"), ("final_posture", "OPEN"),
                                        ("status", "DELIVERED"), ("decision_id", "decision_" + "f" * 32)])
def test_database_rejects_inconsistent_plan_link(database, field, value):
    _, _, record = finalize(database)
    service = NotificationPlanService(database)
    plan = prepare(database, record)
    # A new decision provides an unused linkage; inconsistent raw inserts fail too.
    _, _, other = finalize(database)
    payload = plan.model_dump(mode="json")
    payload.update(decision_id=other.decision_id, notification_plan_id="notification_" + "f" * 32)
    payload[field] = value
    with sqlite3.connect(database) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO simulated_notification_plans VALUES (?, ?, ?)",
                (payload["notification_plan_id"], other.decision_id, json.dumps(payload)),
            )
    with pytest.raises(NotificationPlanNotFound):
        service.get_plan_for_decision(other.decision_id)


@pytest.mark.parametrize("field,value", [("total_affected", 99), ("effective_at", "2026-10-10T21:00:00Z"),
                                        ("status", "DELIVERED"), ("created_at", 1)])
def test_strict_plan_schema_rejects_invalid_totals_times_delivery(database, field, value):
    _, _, record = finalize(database)
    payload = prepare(database, record).model_dump(mode="json")
    payload[field] = value
    with pytest.raises(ValidationError):
        NotificationPlan.model_validate(payload)


def test_unapproved_message_instructions_rejected(database):
    _, _, record = finalize(database)
    payload = prepare(database, record).model_dump(mode="json")
    payload["messages"][0]["message"] = "Travel immediately to the closed facility."
    with pytest.raises(ValidationError, match="deterministic"):
        NotificationPlan.model_validate(payload)


def test_empty_roster_plan_is_safe(database, monkeypatch):
    _, _, record = finalize(database)
    empty = group_scheduled_employees(SyntheticRoster(facility_id=FACILITY, employees=()))
    monkeypatch.setattr(notifications, "resolve_employee_impact", lambda facility_id: empty)
    plan = prepare(database, record)
    assert plan.total_affected == 0 and all(message.count == 0 for message in plan.messages)
    assert NotificationPlanService(database).get_plan(plan.notification_plan_id) == plan


def test_invalid_or_missing_plan_ids(database):
    service = NotificationPlanService(database)
    with pytest.raises(ValidationError):
        service.get_plan("../secret")
    with pytest.raises(NotificationPlanNotFound):
        service.get_plan("notification_" + "0" * 32)
    with pytest.raises(NotificationPlanNotFound):
        service.get_plan_for_decision("decision_" + "0" * 32)


def test_unsupported_decision_facility_is_not_substituted(database):
    managers = ManagerDecisionService(database)
    evaluation = managers.evaluate_facility("demo-flood-facility")
    record = managers.record_decision(ManagerDecisionRequest(evaluation_id=evaluation.evaluation_id, action="APPROVE"))
    with pytest.raises(EmployeeImpactError):
        prepare(database, record)


def test_http_writes_are_local_guarded_and_no_upload_delivery_or_agent_tools_added():
    from backend.app.api_security import LocalDemoGuard, LocalDemoSettings
    assert any(middleware.cls is LocalDemoGuard for middleware in app.user_middleware)
    assert LocalDemoSettings().writes_enabled is False
    paths = app.openapi()["paths"]
    assert all(not (set(methods) & {"put", "patch", "delete"}) for methods in paths.values())
    assert not any("upload" in path for path in paths)
    assert not hasattr(notifications, "tool") and not hasattr(notifications, "send")
    assert not hasattr(NotificationPlanService, "send")


@pytest.mark.parametrize("directory", ["frontend", "public"])
def test_notification_database_cannot_be_public(tmp_path, directory):
    with pytest.raises(ValueError, match="outside"):
        NotificationPlanService(tmp_path / directory / "audit.sqlite3")


def test_storage_failure_is_controlled(tmp_path):
    occupied = tmp_path / "file"
    occupied.write_text("not a directory")
    with pytest.raises(AuditStorageError):
        NotificationPlanService(occupied / "audit.sqlite3")


def test_smoke_complete_synthetic_sequence_and_repeated_runs(database, capsys):
    for _ in range(2):
        assert smoke.main(["--action", "approve", "--database", str(database)]) == 0
    output = capsys.readouterr().out
    assert "PASS | Plan persisted and exactly reconstructed" in output
    assert "54 assigned | 47 scheduled/affected | 7 unscheduled/excluded" in output
    assert "TELEWORK_ELIGIBLE: 31" in output and "STANDARD_ONSITE: 10" in output and "ESSENTIAL_PERSONNEL: 6" in output
    assert "GENERATED_SIMULATED" in output and "No external delivery calls" in output
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM manager_decisions").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM simulated_notification_plans").fetchone()[0] == 2


def test_smoke_requires_explicit_approval(database, capsys):
    assert smoke.main(["--database", str(database)]) == 0
    assert "Select --action approve" in capsys.readouterr().out
    assert ManagerDecisionService(database).list_history() == ()


def test_smoke_handles_storage_failure(tmp_path, capsys):
    occupied = tmp_path / "file"
    occupied.write_text("not a directory")
    assert smoke.main(["--action", "approve", "--database", str(occupied / "audit.sqlite3")]) == 1
    assert "FAIL |" in capsys.readouterr().out
