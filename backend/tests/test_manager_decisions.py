"""Offline Task 8A application boundary and immutable historical records."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import sqlite3
from unittest.mock import Mock

from pydantic import ValidationError
import pytest

from backend.app import decision_tool
from backend.app.decision.fixtures import scenario_fixtures
from backend.app.decision.models import OperatingPosture
from backend.app.main import app
from backend.app.manager_decisions import (
    AuditStorageError, DecisionNotFound, DuplicateDecision, EvaluationNotFound,
    ManagerDecisionError, ManagerDecisionRequest, ManagerDecisionService,
)
from scripts import test_manager_decision as smoke


@pytest.fixture
def service(tmp_path):
    return ManagerDecisionService(tmp_path / "audit.sqlite3", demo_scenario="severe_applicable_flood")


def request(evaluation, action="APPROVE", **kwargs):
    return ManagerDecisionRequest(evaluation_id=evaluation.evaluation_id, action=action, **kwargs)


@pytest.mark.parametrize("scenario", ["normal", "delayed_arrival", "unscheduled_telework", "severe_applicable_flood"])
def test_valid_approval_preserves_every_supported_recommendation(tmp_path, scenario):
    service = ManagerDecisionService(tmp_path / "audit.sqlite3", demo_scenario=scenario)
    evaluation = service.evaluate_facility("demo-flood-facility")
    before = datetime.now(timezone.utc)
    record = service.record_decision(request(evaluation))
    assert record.manager_action == "APPROVE"
    assert record.final_posture == record.original_recommendation == scenario_fixtures()[scenario].expected_recommendation
    assert record.evaluation_status == "RECOMMENDATION_READY"
    assert record.evaluation.result.human_approval_required is True
    assert record.override_reason is None
    assert record.manager.id == "demo-manager" and record.manager.synthetic is True
    assert record.manager.display_name == "Synthetic Demo Manager"
    assert before <= record.decision_timestamp <= datetime.now(timezone.utc)
    assert record.facility_id == evaluation.result.facility_id
    assert record.data_mode == "SIMULATED DEMO"
    assert service.get_decision(record.decision_id) == record


@pytest.mark.parametrize("posture", ["OPEN", "DELAYED_ARRIVAL", "UNSCHEDULED_TELEWORK"])
def test_valid_override_preserves_engine_output(service, posture):
    evaluation = service.evaluate_facility("demo-flood-facility")
    original = evaluation.model_dump(mode="json")
    record = service.record_decision(request(
        evaluation, "OVERRIDE", selected_posture=posture, reason="  Staff will use another verified access route.  ",
    ))
    assert record.original_recommendation == "FACILITY_CLOSURE"
    assert record.final_posture == posture and record.manager_action == "OVERRIDE"
    assert record.override_reason == "Staff will use another verified access route."
    assert record.evaluation.model_dump(mode="json") == original
    assert service.get_evaluation(evaluation.evaluation_id).model_dump(mode="json") == original
    assert record.evaluation.result.thresholds == evaluation.evidence_snapshot.exposure.thresholds


@pytest.mark.parametrize("reason", [None, "", "   ", "x" * 501, "a\n", "a\x00", "a\x7f", 17])
def test_missing_or_invalid_override_reason_rejected(service, reason):
    evaluation = service.evaluate_facility("demo-flood-facility")
    with pytest.raises(ValidationError):
        request(evaluation, "OVERRIDE", selected_posture="OPEN", reason=reason)
    assert service.list_history() == ()


@pytest.mark.parametrize("reason", ["x", "x" * 500, "Verified route; human review — synthetic only."])
def test_override_reason_boundaries_and_unicode(service, reason):
    evaluation = service.evaluate_facility("demo-flood-facility")
    assert service.record_decision(request(
        evaluation, "OVERRIDE", selected_posture="OPEN", reason=reason,
    )).override_reason == reason


@pytest.mark.parametrize("posture", [None, "CLOSED", "REVIEW_REQUIRED", "INSUFFICIENT_EVIDENCE", "", 1])
def test_unsupported_operating_posture_rejected(service, posture):
    evaluation = service.evaluate_facility("demo-flood-facility")
    with pytest.raises(ValidationError):
        request(evaluation, "OVERRIDE", selected_posture=posture, reason="Human choice")
    assert service.list_history() == ()


def test_override_must_choose_a_different_posture(service):
    evaluation = service.evaluate_facility("demo-flood-facility")
    with pytest.raises(ManagerDecisionError, match="different"):
        service.record_decision(request(evaluation, "OVERRIDE", selected_posture="FACILITY_CLOSURE", reason="Same"))
    assert service.list_history() == ()


@pytest.mark.parametrize("scenario", ["missing_evidence", "stale_evidence", "conflicting_evidence"])
def test_review_requires_acknowledgment_not_approval_or_override(tmp_path, scenario):
    service = ManagerDecisionService(tmp_path / "audit.sqlite3", demo_scenario=scenario)
    evaluation = service.evaluate_facility("demo-flood-facility")
    for action, fields in [("APPROVE", {}), ("OVERRIDE", {"selected_posture": "OPEN", "reason": "Manual choice"})]:
        with pytest.raises(ManagerDecisionError, match="no recommendation"):
            service.record_decision(request(evaluation, action, **fields))
    assert service.list_history() == ()
    record = service.record_decision(request(evaluation, "ACKNOWLEDGE_REVIEW"))
    assert record.manager_action == "ACKNOWLEDGE_REVIEW"
    assert record.original_recommendation is record.final_posture is record.override_reason is None
    assert record.evaluation_status == "REVIEW_REQUIRED"
    assert record.evidence_snapshot == evaluation.evidence_snapshot
    with pytest.raises(DuplicateDecision):
        service.record_decision(request(evaluation, "ACKNOWLEDGE_REVIEW"))


def test_ready_evaluation_cannot_be_acknowledged(service):
    evaluation = service.evaluate_facility("demo-flood-facility")
    with pytest.raises(ManagerDecisionError, match="Only REVIEW_REQUIRED"):
        service.record_decision(request(evaluation, "ACKNOWLEDGE_REVIEW"))


@pytest.mark.parametrize("field,value", [
    ("evidence_snapshot", {}), ("recommendation", "OPEN"), ("thresholds", {}),
    ("manager", {"id": "admin"}), ("manager_id", "admin"), ("human_approval_required", False),
    ("decision_timestamp", "2000-01-01T00:00:00Z"), ("data_mode", "LIVE_EVIDENCE"),
])
def test_client_cannot_supply_authoritative_fields(service, field, value):
    evaluation = service.evaluate_facility("demo-flood-facility")
    with pytest.raises(ValidationError):
        ManagerDecisionRequest.model_validate({"evaluation_id": evaluation.evaluation_id, "action": "APPROVE", field: value})
    assert service.list_history() == ()


@pytest.mark.parametrize("action,fields", [
    ("APPROVE", {"selected_posture": "OPEN"}), ("APPROVE", {"reason": "Override in disguise"}),
    ("ACKNOWLEDGE_REVIEW", {"selected_posture": "OPEN"}), ("MANUAL_DECISION", {"reason": "Not implemented"}),
    ("approve", {}), (None, {}),
])
def test_explicit_action_schema(service, action, fields):
    evaluation = service.evaluate_facility("demo-flood-facility")
    with pytest.raises(ValidationError):
        request(evaluation, action, **fields)


def test_duplicate_final_decision_survives_restart_and_preserves_first_action(service, tmp_path):
    evaluation = service.evaluate_facility("demo-flood-facility")
    first = service.record_decision(request(evaluation))
    restarted = ManagerDecisionService(tmp_path / "audit.sqlite3")
    with pytest.raises(DuplicateDecision):
        restarted.record_decision(request(evaluation, "OVERRIDE", selected_posture="OPEN", reason="Second decision"))
    assert restarted.list_history() == (first,)
    assert restarted.get_evaluation(evaluation.evaluation_id) == evaluation


def test_competing_writers_can_finalize_only_once(service, tmp_path):
    evaluation = service.evaluate_facility("demo-flood-facility")
    other = ManagerDecisionService(tmp_path / "audit.sqlite3")

    def finalize(writer):
        try:
            return writer.record_decision(request(evaluation))
        except DuplicateDecision:
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        records = list(executor.map(finalize, [service, other]))
    assert sum(record is not None for record in records) == 1
    assert len(service.list_history()) == 1


def test_exact_historical_evidence_reconstruction_without_fetch_or_reevaluation(service, tmp_path, monkeypatch):
    evaluation = service.evaluate_facility("demo-flood-facility")
    record = service.record_decision(request(evaluation))
    original_input = scenario_fixtures()["severe_applicable_flood"].input.model_dump(mode="json")
    forbidden = Mock(side_effect=AssertionError("Historical retrieval must not fetch or evaluate"))
    monkeypatch.setattr(decision_tool, "fetch_nws_alerts", forbidden)
    monkeypatch.setattr(decision_tool, "fetch_usgs_conditions", forbidden)
    monkeypatch.setattr(decision_tool, "evaluate", forbidden)
    restarted = ManagerDecisionService(tmp_path / "audit.sqlite3")
    restored = restarted.get_decision(record.decision_id)
    assert restored.model_dump(mode="json") == record.model_dump(mode="json")
    assert restored.evidence_snapshot.model_dump(mode="json") == original_input
    assert restored.source_timestamps == evaluation.result.evidence_references
    assert restored.evaluation.source_checks == evaluation.source_checks
    assert restored.evaluation.integration_limitations == evaluation.integration_limitations
    assert restarted.get_evaluation(evaluation.evaluation_id) == evaluation
    forbidden.assert_not_called()


@pytest.mark.parametrize("table", ["manager_evaluations", "manager_decisions"])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE", "REPLACE"])
def test_database_blocks_modification_deletion_and_replacement(service, tmp_path, table, operation):
    evaluation = service.evaluate_facility("demo-flood-facility")
    record = service.record_decision(request(evaluation))
    # SQL below is test-controlled. Application queries remain parameterized.
    with sqlite3.connect(tmp_path / "audit.sqlite3") as connection:
        with pytest.raises(sqlite3.IntegrityError):
            if operation == "UPDATE":
                field = "snapshot_json" if table == "manager_evaluations" else "record_json"
                connection.execute(f"UPDATE {table} SET {field} = ?", ("{}",))
            elif operation == "DELETE":
                connection.execute(f"DELETE FROM {table}")
            else:
                connection.execute(f"INSERT OR REPLACE INTO {table} SELECT * FROM {table}")
    assert service.get_evaluation(evaluation.evaluation_id) == evaluation
    assert service.get_decision(record.decision_id) == record


def test_returned_records_are_frozen_and_copies_cannot_change_history(service):
    evaluation = service.evaluate_facility("demo-flood-facility")
    record = service.record_decision(request(evaluation))
    with pytest.raises(ValidationError):
        record.final_posture = OperatingPosture.OPEN
    with pytest.raises(ValidationError):
        record.evidence_snapshot.usgs.observations[0].value = 999.0
    tampered = record.model_dump(mode="json")
    tampered["evidence_snapshot"]["usgs"]["observations"][0]["value"] = 999.0
    assert service.get_decision(record.decision_id) == record
    assert service.get_evaluation(evaluation.evaluation_id) == evaluation


@pytest.mark.parametrize("identifier", ["", "../audit", "eval_x", "eval_" + "0" * 32 + "\n", "' OR 1=1 --", 123, None])
def test_invalid_evaluation_ids_rejected(service, identifier):
    with pytest.raises(ValidationError):
        service.get_evaluation(identifier)
    with pytest.raises(ValidationError):
        ManagerDecisionRequest(evaluation_id=identifier, action="APPROVE")


def test_untrusted_ids_and_unpersisted_tool_outputs_cannot_be_decided(service, tmp_path):
    # A valid deterministic output from elsewhere is not a persisted evaluation.
    raw = decision_tool.create_decision_tool("SIMULATED DEMO")("demo-flood-facility")
    assert raw["ok"] is True
    with pytest.raises(EvaluationNotFound):
        service.record_decision(ManagerDecisionRequest(evaluation_id="eval_" + "0" * 32, action="APPROVE"))
    other = ManagerDecisionService(tmp_path / "other.sqlite3")
    foreign = other.evaluate_facility("demo-flood-facility")
    with pytest.raises(EvaluationNotFound):
        service.record_decision(request(foreign))
    assert service.list_history() == ()


@pytest.mark.parametrize("value", [False, 1, "true"])
def test_trusted_result_must_require_human_approval(service, value):
    raw = decision_tool.create_decision_tool("SIMULATED DEMO")("demo-flood-facility")
    raw["human_approval_required"] = value
    service._evaluate = Mock(return_value=raw)
    with pytest.raises(ValidationError):
        service.evaluate_facility("demo-flood-facility")
    assert service.list_history() == ()


def test_bypassed_request_validation_is_rechecked(service):
    evaluation = service.evaluate_facility("demo-flood-facility")
    forged = request(evaluation).model_copy(update={"selected_posture": "OPEN"})
    with pytest.raises(ValidationError):
        service.record_decision(forged)
    assert service.list_history() == ()


def test_source_metadata_and_live_mode_survive_persistence(service, tmp_path):
    # Mock only trusted backend acquisition output, never client evidence.
    raw = deepcopy(decision_tool.create_decision_tool("SIMULATED DEMO", "missing_evidence")("demo-flood-facility"))
    raw["data_mode"] = "LIVE_EVIDENCE"
    raw["source_checks"] = [{"source": "USGS", "status": "UNAVAILABLE", "checked_at": "2026-10-10T18:00:00Z"}]
    service._evaluate = Mock(return_value=raw)
    evaluation = service.evaluate_facility("demo-flood-facility")
    record = service.record_decision(request(evaluation, "ACKNOWLEDGE_REVIEW"))
    restored = ManagerDecisionService(tmp_path / "audit.sqlite3").get_decision(record.decision_id)
    assert restored.data_mode == "LIVE_EVIDENCE"
    assert restored.evaluation.result.data_label == "SIMULATED DEMO"
    assert restored.evaluation.source_checks[0].status == "UNAVAILABLE"
    assert restored.evidence_snapshot.usgs is None


def test_history_filter_order_and_missing_decision(service):
    first = service.record_decision(request(service.evaluate_facility("demo-flood-facility")))
    second = service.record_decision(request(service.evaluate_facility("demo-flood-facility")))
    assert service.list_history() == (second, first)
    assert service.list_history(limit=1, facility_id="demo-flood-facility") == (second,)
    assert service.list_history(facility_id="other") == ()
    with pytest.raises(DecisionNotFound):
        service.get_decision("decision_" + "0" * 32)


@pytest.mark.parametrize("limit", [0, 101, True, "10", 1.0])
def test_history_limits(service, limit):
    with pytest.raises(ValueError):
        service.list_history(limit=limit)


def test_database_kept_outside_frontend_public(tmp_path):
    for folder in ["frontend", "public", "PUBLIC"]:
        with pytest.raises(ValueError, match="outside"):
            ManagerDecisionService(tmp_path / folder / "audit.sqlite3")


def test_invalid_facility_does_not_register_evaluation(service, tmp_path):
    with pytest.raises(ManagerDecisionError):
        service.evaluate_facility("unknown")
    with sqlite3.connect(tmp_path / "audit.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM manager_evaluations").fetchone()[0] == 0


def test_storage_failure_is_actionable_without_success(service, tmp_path):
    service._database_path = tmp_path  # A directory cannot be opened as a database.
    with pytest.raises(AuditStorageError, match="no action was confirmed"):
        service.evaluate_facility("demo-flood-facility")


def test_no_agent_approval_and_http_writes_require_local_guard():
    tool = decision_tool.create_decision_tool("SIMULATED DEMO")
    assert tool.tool_name == "evaluate_operating_status"
    assert set(tool.tool_spec["inputSchema"]["json"]["properties"]) == {"facility_id"}
    # Task 9A adds application HTTP writes; agent capabilities remain read-only.
    from backend.app.api_security import LocalDemoGuard, LocalDemoSettings
    assert any(middleware.cls is LocalDemoGuard for middleware in app.user_middleware)
    assert LocalDemoSettings().writes_enabled is False


@pytest.mark.parametrize("args,expected", [
    ([], "no manager decision recorded"),
    (["--action", "approve"], "APPROVE"),
    (["--action", "override", "--posture", "OPEN", "--reason", "Verified synthetic alternate route"], "OVERRIDE"),
    (["--scenario", "missing_evidence", "--action", "acknowledge-review"], "ACKNOWLEDGE_REVIEW"),
])
def test_offline_smoke_uses_only_synthetic_evidence(tmp_path, monkeypatch, capsys, args, expected):
    monkeypatch.setattr(smoke, "ManagerDecisionService", lambda **kwargs: ManagerDecisionService(tmp_path / "smoke.sqlite3", **kwargs))
    forbidden = Mock(side_effect=AssertionError("No public source requests"))
    monkeypatch.setattr(decision_tool, "fetch_nws_alerts", forbidden)
    monkeypatch.setattr(decision_tool, "fetch_usgs_conditions", forbidden)
    assert smoke.main(args) == 0
    output = capsys.readouterr().out
    assert "SIMULATED DEMO" in output and expected in output
    forbidden.assert_not_called()


@pytest.mark.parametrize("args", [
    ["--action", "override"], ["--action", "override", "--posture", "OPEN"],
    ["--action", "override", "--posture", "OPEN", "--reason", "   "],
    ["--action", "approve", "--reason", "Disallowed"],
])
def test_smoke_invalid_arguments_do_not_touch_storage(monkeypatch, args):
    forbidden = Mock(side_effect=AssertionError("Do not create storage"))
    monkeypatch.setattr(smoke, "ManagerDecisionService", forbidden)
    with pytest.raises(SystemExit) as error:
        smoke.main(args)
    assert error.value.code == 2
    forbidden.assert_not_called()


def test_smoke_rejects_review_approval(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(smoke, "ManagerDecisionService", lambda **kwargs: ManagerDecisionService(tmp_path / "smoke.sqlite3", **kwargs))
    assert smoke.main(["--scenario", "missing_evidence", "--action", "approve"]) == 1
    assert "no recommendation" in capsys.readouterr().out
