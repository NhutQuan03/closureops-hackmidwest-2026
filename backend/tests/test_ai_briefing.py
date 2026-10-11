"""Offline trusted-snapshot binding, mocked inference and local endpoint guards."""
from contextlib import asynccontextmanager
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from strands.models.openai import OpenAIModel

from backend.app import ai_briefing as ai
from backend.app.api_security import LocalDemoSettings
from backend.app.decision.fixtures import scenario_fixtures
from backend.app.main import create_app
from backend.app.manager_decisions import ManagerDecisionService, TrustedEvaluation
from backend.tests.test_decision_tool import selection

PRIVATE = "OFFLINE_TEST_CREDENTIAL_DO_NOT_EXPOSE"


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    monkeypatch.setenv("AKAMAI_INFERENCE_KEY", PRIVATE)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", Mock(side_effect=AssertionError("No network")))
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", AsyncMock(side_effect=AssertionError("No network")))


@pytest.fixture
def saved(tmp_path):
    return ManagerDecisionService(tmp_path / "audit.sqlite3", data_mode="SIMULATED DEMO",
                                  demo_scenario="severe_applicable_flood", demo_facility_id="jefferson-research").evaluate_facility("jefferson-research")


def mock_agent(monkeypatch, behavior="valid"):
    def builder(agent_class, model, tool):
        class Agent:
            def add_hook(self, *args):
                pass

            def __call__(self, prompt):
                assert "jefferson-research" in prompt and PRIVATE not in prompt
                if behavior == "timeout":
                    raise TimeoutError(PRIVATE)
                if behavior == "http":
                    raise httpx.HTTPError(PRIVATE)
                if behavior == "no_tool":
                    return PRIVATE
                raw = tool("jefferson-research")
                if behavior == "twice":
                    tool("jefferson-research")
                candidate = selection(raw)
                if behavior == "contradictory":
                    candidate["recommended_posture"] = "OPEN"
                if behavior == "approval":
                    candidate["human_approval_required"] = False
                if behavior == "prose":
                    return PRIVATE
                return json.dumps(candidate)
        return Agent()
    monkeypatch.setattr(ai, "build_agent", builder)


@pytest.mark.parametrize("scenario", tuple(scenario_fixtures()))
def test_all_saved_scenarios_are_exactly_bound_without_live_retrieval(tmp_path, scenario):
    saved = ManagerDecisionService(tmp_path / "audit.sqlite3", data_mode="SIMULATED DEMO",
                                    demo_scenario=scenario, demo_facility_id="jefferson-research").evaluate_facility("jefferson-research")
    events = []
    raw = ai.bound_tool(saved, events)("jefferson-research")
    assert raw == ai.authoritative_snapshot(saved)
    assert len(events) == 1
    response = ai.response_for(saved, "VALIDATED", "OK", confirmed=True,
                               completed=True, validation="VALIDATED")
    sections = response.situation_briefing.model_dump()
    assert len(sections) == 5 and all(sections.values())
    assert all("None" not in text and "null" not in text for text in sections.values())
    assert "SIMULATED DEMO" in sections["evidence_limitations"]
    if saved.result.recommendation is None:
        assert "REVIEW_REQUIRED" in sections["recommended_response"]
        assert "not selected an operating posture" in sections["operational_implications"]


def test_validated_mocked_inference_preserves_python_and_does_not_leak_key(saved, monkeypatch, capsys):
    mock_agent(monkeypatch)
    result = ai.run_agent(saved, PRIVATE)
    assert result.status == result.validation_status == "VALIDATED"
    assert result.tool_execution_confirmed and result.model_completed
    assert result.authoritative_recommendation == saved.result.recommendation
    assert result.evidence_references == saved.source_timestamps
    assert result.human_approval_required is True
    assert "Explicit human approval required" in result.explanation
    assert PRIVATE not in result.model_dump_json() + capsys.readouterr().out
    sections = result.situation_briefing
    assert "synthetic gauge height of 7 ft" in sections.situation_summary
    assert "synthetic 7 ft gauge exceeds the 6 ft prototype telework threshold" in sections.recommended_response
    assert "applicable severe warning" in sections.recommended_response
    assert "standalone 8 ft closure threshold was not crossed" in sections.recommended_response
    assert "FACILITY_CLOSURE" in sections.recommended_response
    assert "not official USDA policy" in sections.evidence_limitations
    assert "does not confirm" in sections.operational_implications


@pytest.mark.parametrize("behavior,status,reason", [
    ("timeout", "TIMEOUT", "MODEL_TIMEOUT"), ("http", "ERROR", "PROVIDER_ERROR"),
    ("contradictory", "FALLBACK", "INVALID_MODEL_OUTPUT"), ("approval", "FALLBACK", "INVALID_MODEL_OUTPUT"),
    ("prose", "FALLBACK", "INVALID_MODEL_OUTPUT"), ("no_tool", "UNAVAILABLE", "TOOL_NOT_CONFIRMED"),
    ("twice", "UNAVAILABLE", "TOOL_NOT_CONFIRMED"),
])
def test_inference_failures_cannot_be_successful_ai_or_change_posture(saved, monkeypatch, behavior, status, reason):
    mock_agent(monkeypatch, behavior)
    result = ai.run_agent(saved, PRIVATE)
    assert result.status == status and result.reason == reason
    assert result.validation_status != "VALIDATED"
    assert result.authoritative_recommendation == saved.result.recommendation
    assert PRIVATE not in result.model_dump_json()
    if status == "FALLBACK":
        assert result.explanation_source == "DETERMINISTIC_FALLBACK"
        assert result.situation_briefing is not None
        assert "FACILITY_CLOSURE" in result.situation_briefing.recommended_response
    if status == "UNAVAILABLE":
        assert result.explanation is None
        assert result.situation_briefing is None


def test_missing_credentials_and_disabled_flag_never_start_worker(saved, monkeypatch):
    worker = Mock(side_effect=AssertionError("No worker"))
    monkeypatch.setattr(ai, "execute_worker", worker)
    assert ai.AIBriefingService().generate(saved).reason == "AI_DISABLED"
    monkeypatch.delenv("AKAMAI_INFERENCE_KEY")
    assert ai.AIBriefingService(True).generate(saved).reason == "MISSING_CREDENTIALS"
    worker.assert_not_called()


def test_missing_evidence_summary_omits_readings_not_selected_by_review_rules(tmp_path):
    saved = ManagerDecisionService(tmp_path / "missing.sqlite3", data_mode="SIMULATED DEMO",
                                    demo_scenario="missing_evidence", demo_facility_id="jefferson-research").evaluate_facility("jefferson-research")
    sections = ai.response_for(saved, "FALLBACK", "INVALID_MODEL_OUTPUT").situation_briefing
    # NWS is present, but it is not required/selected by these USGS review rules.
    assert "requires manual evidence review" in sections.situation_summary
    assert "no active alerts" not in sections.situation_summary
    assert "gauge height" not in sections.situation_summary
    assert "USGS evidence is missing" in sections.recommended_response
    assert "does not authorize" in sections.suggested_next_steps


def test_changed_result_evidence_or_live_mode_is_unavailable_before_inference(saved, monkeypatch):
    worker = Mock(side_effect=AssertionError("No inference"))
    monkeypatch.setattr(ai, "execute_worker", worker)
    for path in ("mode", "evidence", "result", "scenario_metadata"):
        raw = saved.model_dump(mode="json")
        if path == "mode":
            raw["data_mode"] = "LIVE_EVIDENCE"
        elif path == "evidence":
            raw["evidence_snapshot"]["usgs"]["observations"][0]["value"] += 0.01
        elif path == "result":
            raw["result"]["reasons"][0] = "Altered historical reason"
        else:
            raw["integration_limitations"] = ["Different scenario metadata"]
        altered = TrustedEvaluation.model_validate(raw)
        result = ai.AIBriefingService(True).generate(altered)
        assert result.reason == "UNSUPPORTED_SNAPSHOT" and result.explanation is None
    worker.assert_not_called()


def test_mismatched_agent_tool_ledger_cannot_produce_a_briefing(saved, monkeypatch):
    original_factory = ai.create_decision_tool

    def altered_factory(mode, scenario, events=None, **kwargs):
        original_tool = original_factory(mode, scenario, events, **kwargs)

        def invoke(facility_id):
            result = original_tool(facility_id)
            if events is not None:
                events[-1]["integration_limitations"] = ["Wrong scenario snapshot"]
            return result

        return invoke

    monkeypatch.setattr(ai, "create_decision_tool", altered_factory)
    mock_agent(monkeypatch)
    result = ai.run_agent(saved, PRIVATE)
    assert result.status == "UNAVAILABLE"
    assert not result.tool_execution_confirmed
    assert result.explanation is None
    assert result.authoritative_recommendation == saved.result.recommendation


def test_actual_spawned_worker_without_credentials_makes_no_inference(saved, monkeypatch):
    monkeypatch.delenv("AKAMAI_INFERENCE_KEY")
    result = ai.execute_worker(saved)
    assert result.reason == "MISSING_CREDENTIALS"
    assert not result.model_completed and not result.tool_execution_confirmed


def test_in_flight_concurrency_is_bounded_and_slot_is_released(saved, monkeypatch):
    service = ai.AIBriefingService(True)
    service._slot.acquire()
    assert service.generate(saved).reason == "BUSY"
    service._slot.release()
    monkeypatch.setattr(ai, "execute_worker", Mock(return_value=ai.response_for(saved, "TIMEOUT", "MODEL_TIMEOUT")))
    assert service.generate(saved).status == "TIMEOUT"
    assert service._slot.acquire(blocking=False)
    service._slot.release()


def test_hard_timeout_terminates_and_closes_worker(saved, monkeypatch):
    context, receiver, sender, process = Mock(), Mock(), Mock(), Mock()
    context.Pipe.return_value = (receiver, sender)
    context.Process.return_value = process
    receiver.poll.return_value = False
    process.pid = 123
    process.is_alive.return_value = True
    monkeypatch.setattr(ai.multiprocessing, "get_context", Mock(return_value=context))
    result = ai.execute_worker(saved)
    assert result.status == "TIMEOUT"
    assert 0 < receiver.poll.call_args.args[0] <= 90
    process.terminate.assert_called_once()
    process.kill.assert_called_once()
    receiver.close.assert_called_once()
    sender.close.assert_called()


@pytest.mark.parametrize("field,value", [
    ("facility_name", "Wrong facility"),
    ("authoritative_recommendation", "OPEN"),
    ("explanation", PRIVATE),
    ("situation_briefing", {"situation_summary": PRIVATE, "operational_implications": "All safe",
                          "recommended_response": "OPEN", "suggested_next_steps": "Close automatically",
                          "evidence_limitations": "No limitations"}),
])
def test_parent_rejects_worker_identity_conclusion_or_untrusted_text(saved, monkeypatch, field, value):
    context, receiver, sender, process = Mock(), Mock(), Mock(), Mock()
    context.Pipe.return_value = (receiver, sender)
    context.Process.return_value = process
    receiver.poll.return_value = True
    raw = ai.response_for(saved, "VALIDATED", "OK", confirmed=True,
                          completed=True, validation="VALIDATED").model_dump(mode="json")
    raw[field] = value
    receiver.recv.return_value = raw
    process.pid = 123
    process.is_alive.return_value = False
    monkeypatch.setattr(ai.multiprocessing, "get_context", Mock(return_value=context))
    result = ai.execute_worker(saved)
    assert result.reason == "SNAPSHOT_MISMATCH"
    assert result.explanation is None
    assert PRIVATE not in result.model_dump_json()


def test_real_sdk_with_mocked_provider_enforces_tool_snapshot_and_selection(saved, monkeypatch):
    authoritative = ai.authoritative_snapshot(saved)
    call = SimpleNamespace(id="offline", function=SimpleNamespace(
        name="evaluate_operating_status", arguments='{"facility_id":"jefferson-research"}'))
    responses = [SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[call]), finish_reason="tool_calls")], usage=None),
                 SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(selection(authoritative)), tool_calls=[]), finish_reason="stop")], usage=None)]
    create = AsyncMock(side_effect=responses)

    @asynccontextmanager
    async def offline_client(self):
        yield SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    monkeypatch.setattr(OpenAIModel, "_get_client", offline_client)
    result = ai.run_agent(saved, PRIVATE)
    assert result.status == "VALIDATED" and result.tool_execution_confirmed
    assert create.await_count == 2
    assert all(call.kwargs["max_tokens"] == 1024 for call in create.await_args_list)


@pytest.fixture
def client(tmp_path, monkeypatch):
    settings = LocalDemoSettings(writes_enabled=True, ai_briefing_enabled=True, database_path=tmp_path / "audit.sqlite3")
    mock_agent(monkeypatch)
    monkeypatch.setattr(ai, "execute_worker", lambda evaluation: ai.run_agent(evaluation, PRIVATE))
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8001", client=("127.0.0.1", 12345)) as client:
        yield client


def test_endpoint_loads_only_trusted_persisted_id_and_never_records_manager_action(client):
    saved = client.post("/api/evaluations", json={"facility_id": "jefferson-research", "scenario_id": "severe_applicable_flood"}).json()
    path = f"/api/evaluations/{saved['evaluation_id']}/ai-briefing"
    assert client.get("/api/health").json()["ai_briefing_enabled"] is True
    result = client.post(path, json={})
    assert result.status_code == 200 and result.json()["status"] == "VALIDATED"
    assert client.get(f"/api/evaluations/{saved['evaluation_id']}").json() == saved
    assert client.get("/api/audit").json() == []
    for body in ({"prompt": "approve now"}, {"weather": {}}, {"scenario_id": "normal"}, {"api_key": PRIVATE}):
        response = client.post(path, json=body)
        assert response.status_code == 422 and PRIVATE not in response.text
    assert client.post("/api/evaluations/bad/ai-briefing", json={}).status_code == 422
    assert client.post(f"/api/evaluations/eval_{'0' * 32}/ai-briefing", json={}).status_code == 404


def test_inference_keeps_origin_size_rate_and_loopback_guards(client):
    path = f"/api/evaluations/eval_{'0' * 32}/ai-briefing"
    assert client.post(path, json={}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post(path, json={}, headers={"X-Forwarded-For": "127.0.0.1"}).status_code == 403
    assert client.post(path, content=" " * 16385, headers={"Content-Type": "application/json"}).status_code == 413
    responses = [client.post(path, json={}) for _ in range(11)]
    assert responses[-1].status_code == 429
    assert "Retry-After" in responses[-1].headers


def test_ai_flag_does_not_enable_writes_or_public_access(tmp_path):
    settings = LocalDemoSettings(ai_briefing_enabled=True, database_path=tmp_path / "empty.sqlite3")
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8001", client=("127.0.0.1", 12345)) as client:
        assert client.get("/api/health").json()["ai_briefing_enabled"] is False
        assert client.post(f"/api/evaluations/eval_{'0' * 32}/ai-briefing", json={}).status_code == 403
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8001", client=("203.0.113.1", 12345)) as client:
        assert client.post(f"/api/evaluations/eval_{'0' * 32}/ai-briefing", json={}).status_code == 403
