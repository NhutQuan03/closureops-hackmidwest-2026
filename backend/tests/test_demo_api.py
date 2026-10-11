"""Task 9A offline HTTP vertical workflow, security and exact SQLite reconstruction."""

from dataclasses import replace
import socket
import sys
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.api_security import LocalDemoSettings, REACT_ORIGINS
from backend.app.decision.fixtures import demo_input_for_facility, scenario_fixtures
from backend.app.decision.engine import evaluate as evaluate_engine
from backend.app.decision.models import DecisionInput
from backend.app.employee_impact import SyntheticRoster, group_scheduled_employees
from backend.app.employee_notifications import NotificationPlanService
from backend.app.main import create_app
from backend.app.manager_decisions import AuditStorageError, ManagerDecisionRequest, ManagerDecisionService

FACILITY = "jefferson-research"
EVALUATION_URL = "/api/evaluations"
EVALUATION_BODY = {"facility_id": FACILITY, "scenario_id": "severe_applicable_flood"}
UNKNOWN_EVALUATION = "eval_" + "0" * 32
UNKNOWN_DECISION = "decision_" + "0" * 32


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    blocked = Mock(side_effect=AssertionError("Task 9A must not use network, inference or delivery"))
    original_connect = socket.socket.connect

    def guarded_connect(connection, address):
        # Windows asyncio constructs a private loopback socketpair for its own
        # wake-up pipe. Permit only that stdlib call, never application sockets.
        caller = sys._getframe(1)
        if caller.f_code.co_name == "_fallback_socketpair" and caller.f_globals.get("__name__") == "socket":
            return original_connect(connection, address)
        return blocked(connection, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", AsyncMock(side_effect=blocked.side_effect))


@pytest.fixture
def settings(tmp_path):
    return LocalDemoSettings(writes_enabled=True, database_path=tmp_path / "audit.sqlite3")


def local_client(settings, **kwargs):
    return TestClient(create_app(settings), base_url="http://127.0.0.1:8000",
                      client=("127.0.0.1", 50000), **kwargs)


@pytest.fixture
def client(settings):
    with local_client(settings) as instance:
        yield instance


def evaluation(client, scenario="severe_applicable_flood"):
    response = client.post(EVALUATION_URL, json={"facility_id": FACILITY, "scenario_id": scenario})
    assert response.status_code == 201, response.text
    assert response.headers["Location"] == f"/api/evaluations/{response.json()['evaluation_id']}"
    return response.json()


def decision(client, saved_evaluation, **action):
    response = client.post(f"/api/evaluations/{saved_evaluation['evaluation_id']}/decisions", json=action)
    assert response.status_code == 201, response.text
    assert response.headers["Location"] == f"/api/decisions/{response.json()['decision_id']}"
    return response.json()


def plan(client, saved_decision):
    response = client.post(f"/api/decisions/{saved_decision['decision_id']}/notification-plans", json={})
    assert response.status_code == 201, response.text
    return response.json()


def assert_error(response, status, code=None):
    assert response.status_code == status, response.text
    assert set(response.json()) == {"error"}
    assert set(response.json()["error"]) == {"code", "message"}
    if code:
        assert response.json()["error"]["code"] == code


def test_health_facility_and_local_swagger(client):
    assert client.get("/api/health").json() == {
        "status": "ok", "service": "closureops-api", "data_mode": "synthetic_demo",
        "local_demo_writes_enabled": True,
        "ai_briefing_enabled": False,
    }
    facilities = client.get("/api/facilities").json()
    assert len(facilities) == 1 and facilities[0]["id"] == FACILITY
    assert facilities[0]["data_label"] == "SIMULATED DEMO"
    assert facilities[0]["source_timestamp"] == "2026-10-10T18:00:00Z"
    assert "invented" in facilities[0]["current_note"]
    assert client.get(f"/api/facilities/{FACILITY}").json() == facilities[0]
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert schema["components"]["schemas"]["CreateEvaluationRequest"]["additionalProperties"] is False
    assert schema["paths"]["/api/evaluations"]["post"]["responses"]["422"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse",
    }
    assert "manager_id" not in schema["components"]["schemas"]["DecisionActionRequest"]["properties"]
    assert client.get("/api/health").headers["x-content-type-options"] == "nosniff"


def test_readonly_health_reports_disabled_writes(settings):
    with local_client(replace(settings, writes_enabled=False)) as client:
        assert client.get("/api/health").json()["local_demo_writes_enabled"] is False
        assert_error(client.post(EVALUATION_URL, json=EVALUATION_BODY), 403, "DEMO_WRITES_DISABLED")


def test_allowlisted_scenarios_disclose_jefferson_binding(client):
    scenarios = client.get("/api/demo/scenarios").json()
    assert {entry["scenario_id"] for entry in scenarios} == set(scenario_fixtures())
    assert all(entry["facility_id"] == FACILITY and entry["data_label"] == "SIMULATED DEMO" for entry in scenarios)
    assert all("USGS-00000000" in entry["disclosure"] and "invented" in entry["disclosure"] for entry in scenarios)
    severe = next(entry for entry in scenarios if entry["scenario_id"] == "severe_applicable_flood")
    assert severe["expected_recommendation"] == "FACILITY_CLOSURE"


@pytest.mark.parametrize("scenario", list(scenario_fixtures()))
def test_evaluation_uses_exact_trusted_fixture_and_retrieves_it(client, settings, scenario):
    saved = evaluation(client, scenario)
    fixture = scenario_fixtures()[scenario]
    assert saved["evidence_snapshot"] == demo_input_for_facility(scenario, FACILITY).model_dump(mode="json")
    assert saved["result"]["recommendation"] == fixture.expected_recommendation
    assert saved["result"]["evaluation_status"] == fixture.expected_status
    assert saved["data_mode"] == saved["result"]["data_label"] == "SIMULATED DEMO"
    assert saved["result"]["rules"]["policy_label"] == "PROTOTYPE - NOT OFFICIAL USDA POLICY"
    assert all(ref["state"] != "LIVE" for ref in saved["source_timestamps"])
    assert saved["result"]["human_approval_required"] is True
    assert saved["source_checks"] == []  # no live acquisition was performed
    assert client.get(f"/api/evaluations/{saved['evaluation_id']}").json() == saved
    assert ManagerDecisionService(settings.database_path).get_evaluation(saved["evaluation_id"]).model_dump(mode="json") == saved


def test_complete_approval_plan_audit_and_restart_reconstruction(client, settings):
    saved = evaluation(client)
    finalized = decision(client, saved, action="APPROVE")
    assert finalized["original_recommendation"] == finalized["final_posture"] == "FACILITY_CLOSURE"
    assert finalized["evaluation"] == saved
    assert finalized["manager"] == {"id": "demo-manager", "display_name": "Synthetic Demo Manager", "synthetic": True}
    prepared = plan(client, finalized)
    assert prepared["total_assigned"] == 54
    assert prepared["total_scheduled"] == prepared["total_affected"] == 47
    assert prepared["total_unscheduled"] == 7
    assert prepared["group_counts"] == {"TELEWORK_ELIGIBLE": 31, "STANDARD_ONSITE": 10, "ESSENTIAL_PERSONNEL": 6}
    assert prepared["final_posture"] == finalized["final_posture"]
    assert prepared["effective_at"] is None
    assert prepared["status"] == "GENERATED_SIMULATED"
    assert prepared["data_mode"] == "SIMULATED DEMO"
    assert prepared["decision_id"] == finalized["decision_id"]
    assert len(prepared["messages"]) == 3
    assert all(message["route"] == "simulated" and message["status"] == "GENERATED_SIMULATED" for message in prepared["messages"])
    assert all("SIMULATED DEMO" in message["message"] and "Effective time: not recorded" in message["message"]
               and finalized["decision_id"] in message["message"] for message in prepared["messages"])
    reopened = local_client(settings)
    assert reopened.get(f"/api/evaluations/{saved['evaluation_id']}").json() == saved
    assert reopened.get(f"/api/decisions/{finalized['decision_id']}").json() == finalized
    assert reopened.get(f"/api/decisions/{finalized['decision_id']}/notification-plan").json() == prepared
    assert reopened.get("/api/audit").json() == [finalized]
    assert reopened.get("/api/audit", params={"facility_id": FACILITY, "limit": 1}).json() == [finalized]
    assert NotificationPlanService(settings.database_path).get_plan(prepared["notification_plan_id"]).model_dump(mode="json") == prepared
    assert client.get("/api/facilities").json()[0]["operating_status"] == "open"  # catalog fixture is unchanged


def test_api_counts_come_from_existing_roster_resolver(client, monkeypatch):
    empty = group_scheduled_employees(SyntheticRoster(facility_id=FACILITY, employees=()))
    resolver = Mock(return_value=empty)
    monkeypatch.setattr("backend.app.employee_notifications.resolve_employee_impact", resolver)
    prepared = plan(client, decision(client, evaluation(client), action="APPROVE"))
    resolver.assert_called_once_with(FACILITY)
    assert prepared["total_assigned"] == prepared["total_affected"] == prepared["total_unscheduled"] == 0
    assert all(count == 0 for count in prepared["group_counts"].values())
    assert all(message["count"] == 0 for message in prepared["messages"])


@pytest.mark.parametrize("source_state", ["LIVE", "STALE"])
def test_historical_source_states_and_no_active_alerts_are_preserved(client, settings, source_state):
    # Simulate prior trusted server acquisition, never submit evidence to HTTP.
    payload = demo_input_for_facility("normal", FACILITY).model_dump(mode="python")
    payload["nws"]["evidence_status"] = source_state
    payload["usgs"]["observations"][0]["evidence_status"] = source_state
    payload["usgs"]["trend"]["evidence_status"] = source_state
    evidence = DecisionInput.model_validate(payload)
    result = evaluate_engine(evidence).model_dump(mode="json")
    service = ManagerDecisionService(settings.database_path, data_mode="LIVE_EVIDENCE")
    service._evaluate = Mock(return_value={
        **result, "ok": True, "data_mode": "LIVE_EVIDENCE",
        "supporting_evidence": evidence.model_dump(mode="json"),
        "source_timestamps": result["evidence_references"],
        "source_checks": [
            {"source": "NWS", "status": "NO_ACTIVE_ALERTS", "retrieved_at": "2026-10-10T18:00:00Z"},
            {"source": "USGS", "status": source_state, "retrieved_at": "2026-10-10T18:00:00Z"},
        ], "integration_limitations": ["Historical mocked acquisition with synthetic facility configuration."],
    })
    saved = service.evaluate_facility(FACILITY)
    action = "APPROVE" if source_state == "LIVE" else "ACKNOWLEDGE_REVIEW"
    finalized = service.record_decision(ManagerDecisionRequest(evaluation_id=saved.evaluation_id, action=action))
    restored = client.get(f"/api/evaluations/{saved.evaluation_id}").json()
    assert restored == saved.model_dump(mode="json")
    assert restored["data_mode"] == "LIVE_EVIDENCE"
    assert restored["result"]["data_label"] == "SIMULATED DEMO"
    assert restored["evidence_snapshot"]["nws"]["collection_status"] == "NO_ACTIVE_ALERTS"
    assert restored["source_checks"][0]["status"] == "NO_ACTIVE_ALERTS"
    assert next(ref for ref in restored["source_timestamps"] if ref["reference_id"] == "nws")["state"] == source_state
    assert client.get("/api/audit").json() == [finalized.model_dump(mode="json")]


@pytest.mark.parametrize("posture", ["OPEN", "DELAYED_ARRIVAL", "UNSCHEDULED_TELEWORK"])
def test_override_messages_use_final_human_posture(client, posture):
    saved = evaluation(client)
    finalized = decision(client, saved, action="OVERRIDE", selected_posture=posture,
                         reason="  Synthetic manager confirmed alternate arrangements.  ")
    prepared = plan(client, finalized)
    assert finalized["original_recommendation"] == "FACILITY_CLOSURE"
    assert finalized["override_reason"] == "Synthetic manager confirmed alternate arrangements."
    assert finalized["final_posture"] == prepared["final_posture"] == posture
    assert all(f"Final operating posture: {posture}" in item["message"] for item in prepared["messages"])


def test_review_acknowledgment_has_no_posture_or_notification_plan(client):
    saved = evaluation(client, "missing_evidence")
    url = f"/api/evaluations/{saved['evaluation_id']}/decisions"
    assert_error(client.post(url, json={"action": "APPROVE"}), 409, "ACTION_NOT_ALLOWED")
    assert_error(client.post(url, json={"action": "OVERRIDE", "selected_posture": "OPEN", "reason": "Review"}), 409)
    finalized = decision(client, saved, action="ACKNOWLEDGE_REVIEW")
    assert finalized["evaluation_status"] == "REVIEW_REQUIRED"
    assert finalized["original_recommendation"] is finalized["final_posture"] is None
    assert_error(client.post(f"/api/decisions/{finalized['decision_id']}/notification-plans", json={}), 409)
    assert_error(client.get(f"/api/decisions/{finalized['decision_id']}/notification-plan"), 404)


def test_duplicate_decision_and_plan_rejected_without_history_changes(client):
    saved = evaluation(client)
    finalized = decision(client, saved, action="APPROVE")
    prepared = plan(client, finalized)
    assert_error(client.post(f"/api/evaluations/{saved['evaluation_id']}/decisions", json={"action": "APPROVE"}), 409, "ALREADY_FINALIZED")
    assert_error(client.post(f"/api/decisions/{finalized['decision_id']}/notification-plans", json={}), 409, "ALREADY_FINALIZED")
    assert client.get("/api/audit").json() == [finalized]
    assert client.get(f"/api/decisions/{finalized['decision_id']}/notification-plan").json() == prepared


@pytest.mark.parametrize("payload", [
    {}, {"action": "WRONG"}, {"action": "OVERRIDE"},
    {"action": "OVERRIDE", "selected_posture": "OPEN"},
    {"action": "OVERRIDE", "selected_posture": "OPEN", "reason": " "},
    {"action": "OVERRIDE", "selected_posture": "OPEN", "reason": "x" * 501},
    {"action": "OVERRIDE", "selected_posture": "REVIEW_REQUIRED", "reason": "Review"},
    {"action": "OVERRIDE", "selected_posture": "OPEN", "reason": "bad\nreason"},
    {"action": "APPROVE", "selected_posture": "OPEN"},
    {"action": "APPROVE", "reason": "Not an override"},
    {"action": "APPROVE", "manager_id": "fake"},
    {"action": "APPROVE", "evaluation_id": UNKNOWN_EVALUATION},
    {"action": "APPROVE", "evidence_snapshot": {}},
    {"action": "APPROVE", "facility_id": "demo-flood-facility"},
])
def test_invalid_action_fields_rejected_before_any_final_record(client, payload):
    saved = evaluation(client)
    assert_error(client.post(f"/api/evaluations/{saved['evaluation_id']}/decisions", json=payload), 422, "INVALID_REQUEST")
    assert client.get("/api/audit").json() == []


@pytest.mark.parametrize("action", [
    {"action": "ACKNOWLEDGE_REVIEW"},
    {"action": "OVERRIDE", "selected_posture": "FACILITY_CLOSURE", "reason": "Same posture"},
])
def test_service_semantics_are_preserved(client, action):
    saved = evaluation(client)
    assert_error(client.post(f"/api/evaluations/{saved['evaluation_id']}/decisions", json=action), 409)


@pytest.mark.parametrize("field,value", [
    ("weather", {}), ("evidence_snapshot", {}), ("supporting_evidence", {}),
    ("nws", {}), ("usgs", {}), ("recommendation", "OPEN"), ("thresholds", {}),
    ("data_mode", "LIVE_EVIDENCE"), ("manager_id", "fake"), ("evaluated_at", "2026-10-10T18:00:00Z"),
])
def test_evidence_and_policy_injection_rejected(client, settings, field, value):
    response = client.post(EVALUATION_URL, json={**EVALUATION_BODY, field: value})
    assert_error(response, 422, "INVALID_REQUEST")
    assert not settings.database_path.exists()


@pytest.mark.parametrize("payload,status", [
    ({}, 422), ({"facility_id": FACILITY}, 422),
    ({**EVALUATION_BODY, "facility_id": "bad/id"}, 422),
    ({**EVALUATION_BODY, "facility_id": 42}, 422),
    ({**EVALUATION_BODY, "scenario_id": True}, 422),
    ({**EVALUATION_BODY, "scenario_id": "bad/scenario"}, 422),
    ({**EVALUATION_BODY, "scenario_id": "x" * 65}, 422),
    ({**EVALUATION_BODY, "scenario_id": "unknown"}, 404),
    ({**EVALUATION_BODY, "facility_id": "demo-flood-facility"}, 404),
    ({**EVALUATION_BODY, "facility_id": "jefferson-research-facility"}, 404),
    ({**EVALUATION_BODY, "facility_id": "unknown"}, 404),
])
def test_invalid_or_unknown_evaluation_identifiers(client, settings, payload, status):
    assert_error(client.post(EVALUATION_URL, json=payload), status)
    assert not settings.database_path.exists()


@pytest.mark.parametrize("url,method,body,status", [
    ("/api/evaluations/not-an-id", "GET", None, 422),
    (f"/api/evaluations/{UNKNOWN_EVALUATION}", "GET", None, 404),
    (f"/api/evaluations/{UNKNOWN_EVALUATION}/decisions", "POST", {"action": "APPROVE"}, 404),
    ("/api/decisions/not-an-id", "GET", None, 422),
    (f"/api/decisions/{UNKNOWN_DECISION}", "GET", None, 404),
    (f"/api/decisions/{UNKNOWN_DECISION}/notification-plans", "POST", {}, 404),
    (f"/api/decisions/{UNKNOWN_DECISION}/notification-plan", "GET", None, 404),
    ("/api/audit?limit=101", "GET", None, 422),
    ("/api/audit?limit=0", "GET", None, 422),
    ("/api/audit?facility_id=unknown", "GET", None, 404),
])
def test_untrusted_ids_and_bounded_audit_queries(client, url, method, body, status):
    assert_error(client.request(method, url, json=body), status)


@pytest.mark.parametrize("field,value", [
    ("facility_id", "demo-flood-facility"), ("final_posture", "OPEN"),
    ("decision_id", UNKNOWN_DECISION), ("total_assigned", 500),
    ("message", "Send it"), ("send", True), ("effective_at", "2026-10-10T18:00:00Z"),
])
def test_notification_injection_rejected(client, field, value):
    finalized = decision(client, evaluation(client), action="APPROVE")
    assert_error(client.post(f"/api/decisions/{finalized['decision_id']}/notification-plans", json={field: value}), 422)
    assert_error(client.get(f"/api/decisions/{finalized['decision_id']}/notification-plan"), 404)


@pytest.mark.parametrize("origin", ["https://attacker.example", "null", "http://localhost:5174", "http://localhost:5173.attacker.example"])
def test_unapproved_browser_origin_cannot_write(client, settings, origin):
    response = client.post(EVALUATION_URL, json=EVALUATION_BODY, headers={"Origin": origin})
    assert_error(response, 403, "ORIGIN_NOT_ALLOWED")
    assert "access-control-allow-origin" not in response.headers
    assert not settings.database_path.exists()


@pytest.mark.parametrize("origin", [*REACT_ORIGINS, "http://127.0.0.1:8000"])
def test_approved_browser_origins_allow_full_workflow(client, origin):
    client.headers["Origin"] = origin
    prepared = plan(client, decision(client, evaluation(client), action="APPROVE"))
    assert prepared["status"] == "GENERATED_SIMULATED"


def test_cors_preflight_and_cors_is_not_write_authorization(client, settings):
    headers = {"Origin": REACT_ORIGINS[0], "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "Content-Type"}
    response = client.options(EVALUATION_URL, headers=headers)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == REACT_ORIGINS[0]
    assert "access-control-allow-credentials" not in response.headers
    assert client.options(EVALUATION_URL, headers={**headers, "Origin": "https://attacker.example"}).status_code == 400
    disabled = local_client(replace(settings, writes_enabled=False))
    assert_error(disabled.post(EVALUATION_URL, json=EVALUATION_BODY, headers={"Origin": REACT_ORIGINS[0]}), 403, "DEMO_WRITES_DISABLED")


@pytest.mark.parametrize("path,body", [
    (EVALUATION_URL, EVALUATION_BODY),
    (f"/api/evaluations/{UNKNOWN_EVALUATION}/decisions", {"action": "APPROVE"}),
    (f"/api/decisions/{UNKNOWN_DECISION}/notification-plans", {}),
])
def test_all_write_routes_default_disabled(settings, path, body):
    disabled = local_client(replace(settings, writes_enabled=False))
    assert_error(disabled.post(path, json=body), 403, "DEMO_WRITES_DISABLED")
    assert not settings.database_path.exists()


@pytest.mark.parametrize("headers", [
    {"Host": "evil.example"}, {"X-Forwarded-For": "127.0.0.1"},
    {"Forwarded": "for=127.0.0.1"}, {"X-Forwarded-Host": "localhost"},
])
def test_host_and_forwarding_guards(client, settings, headers):
    assert_error(client.post(EVALUATION_URL, json=EVALUATION_BODY, headers=headers), 403)
    assert not settings.database_path.exists()


def test_remote_peer_rejected_even_with_spoofed_local_host(settings):
    remote = TestClient(create_app(settings), base_url="http://127.0.0.1:8000", client=("203.0.113.10", 50000))
    assert_error(remote.post(EVALUATION_URL, json=EVALUATION_BODY), 403, "LOCAL_ONLY")
    assert_error(remote.get("/api/audit"), 403)
    assert not settings.database_path.exists()


def test_cross_site_without_origin_rejected(client):
    assert_error(client.post(EVALUATION_URL, json=EVALUATION_BODY, headers={"Sec-Fetch-Site": "cross-site"}), 403)


@pytest.mark.parametrize("environment,bind", [("production", "127.0.0.1"), ("public", "127.0.0.1"), ("local_demo", "0.0.0.0")])
@pytest.mark.parametrize("enabled", [False, True])
def test_public_or_production_configuration_fails_closed(settings, environment, bind, enabled):
    with pytest.raises(ValueError, match="requires backend authentication"):
        create_app(replace(settings, environment=environment, bind_host=bind, writes_enabled=enabled))
    assert not settings.database_path.exists()


def test_environment_defaults_and_explicit_opt_in(monkeypatch):
    for name in ("CLOSUREOPS_LOCAL_DEMO_WRITES", "CLOSUREOPS_ENVIRONMENT", "CLOSUREOPS_BIND_HOST", "CLOSUREOPS_DEMO_DATABASE"):
        monkeypatch.delenv(name, raising=False)
    assert LocalDemoSettings.from_environment().writes_enabled is False
    monkeypatch.setenv("CLOSUREOPS_LOCAL_DEMO_WRITES", "true")
    assert LocalDemoSettings.from_environment().writes_enabled is True
    monkeypatch.setenv("CLOSUREOPS_ENVIRONMENT", "production")
    with pytest.raises(ValueError):
        create_app()
    monkeypatch.setenv("CLOSUREOPS_LOCAL_DEMO_WRITES", "maybe")
    with pytest.raises(ValueError, match="must be true or false"):
        LocalDemoSettings.from_environment()


def test_json_only_upload_absent_and_body_size_enforced(client, settings):
    assert_error(client.post(EVALUATION_URL, content=b"{bad json", headers={"Content-Type": "application/json"}), 422)
    assert_error(client.post(EVALUATION_URL, content="x", headers={"Content-Type": "text/plain"}), 415)
    assert_error(client.post(EVALUATION_URL, files={"file": ("data.txt", b"untrusted")}), 415)
    assert_error(client.post("/api/upload", json={}), 404)
    assert "/api/upload" not in client.get("/openapi.json").json()["paths"]
    assert_error(client.post(EVALUATION_URL, content=b"x" * (16 * 1024 + 1), headers={"Content-Type": "application/json"}), 413)
    # Streaming body without Content-Length, and dishonest small Content-Length.
    for headers in ({}, {"Content-Length": "1"}):
        assert_error(client.post(EVALUATION_URL, content=iter([b"x" * 9000, b"x" * 9000]),
                                 headers={"Content-Type": "application/json", **headers}), 413)
    assert not settings.database_path.exists()


def test_rate_limits_and_retry_after(client, monkeypatch):
    clock = Mock(return_value=0.0)
    monkeypatch.setattr("backend.app.api_security.monotonic", clock)
    for _ in range(120):
        assert client.get("/api/health").status_code == 200
    rejected = client.get("/api/health")
    assert_error(rejected, 429, "RATE_LIMITED")
    assert rejected.headers["Retry-After"] == "60"
    assert client.get("/api/facilities").status_code == 200
    clock.return_value = 60.0
    assert client.get("/api/health").status_code == 200


@pytest.mark.parametrize("path,body,limit", [
    (EVALUATION_URL, {**EVALUATION_BODY, "scenario_id": "unknown"}, 20),
    (f"/api/evaluations/{UNKNOWN_EVALUATION}/decisions", {"action": "APPROVE"}, 10),
    (f"/api/decisions/{UNKNOWN_DECISION}/notification-plans", {}, 10),
])
def test_write_routes_are_rate_limited(client, path, body, limit):
    for _ in range(limit):
        assert client.post(path, json=body).status_code == 404
    assert_error(client.post(path, json=body), 429, "RATE_LIMITED")


def test_storage_failures_are_redacted(settings, monkeypatch):
    def fail(*args, **kwargs):
        raise AuditStorageError("sentinel-private-path-and-credential")
    monkeypatch.setattr(ManagerDecisionService, "evaluate_facility", fail)
    response = local_client(settings).post(EVALUATION_URL, json=EVALUATION_BODY)
    assert_error(response, 503, "AUDIT_UNAVAILABLE")
    assert "sentinel" not in response.text


def test_unexpected_failures_are_redacted(settings, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("sentinel-private-path-and-credential")
    monkeypatch.setattr(ManagerDecisionService, "evaluate_facility", fail)
    response = local_client(settings, raise_server_exceptions=False).post(EVALUATION_URL, json=EVALUATION_BODY)
    assert_error(response, 500, "INTERNAL_ERROR")
    assert "sentinel" not in response.text
