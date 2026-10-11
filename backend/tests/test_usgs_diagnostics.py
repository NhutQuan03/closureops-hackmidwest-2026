"""Offline diagnostic checks with real Strands and mocked external transports."""

import asyncio
from contextlib import asynccontextmanager
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from backend.app import usgs_tool
from backend.app.facility_tool import get_facility
from backend.app.nws_tool import get_nws_alerts
from backend.tests.test_nws import alert_collection
from backend.tests.test_usgs import fetch, history, latest, mock_usgs  # noqa: F401
from scripts import test_usgs_facility_tool as smoke
from scripts.test_akamai_strands import build_model, load_strands_classes
from scripts.usgs_diagnostics import USGSDiagnostics, result_profile, safe_error

SECRET = "PRIVATE_SENTINEL_DO_NOT_PRINT"


@pytest.fixture(autouse=True)
def block_real_network(monkeypatch):
    """Fail closed even if a test accidentally misses a transport mock."""
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", Mock(side_effect=AssertionError("No network")))
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request",
                        AsyncMock(side_effect=AssertionError("No network")))


def records(capsys) -> list[dict]:
    output = capsys.readouterr()
    assert SECRET not in output.out + output.err
    return [json.loads(line[5:]) for line in output.out.splitlines() if line.startswith("DIAG ")]


def completion(*, tool_call=False, arguments=None, malformed=False):
    call = SimpleNamespace(id="offline-call", function=SimpleNamespace(
        name="get_usgs_conditions", arguments=arguments or json.dumps({"facility_id": smoke.FACILITY_ID}),
    ))
    message = SimpleNamespace(content=None if tool_call else SECRET, tool_calls=[call] if tool_call else [])
    return SimpleNamespace(choices=[SimpleNamespace(message=message,
                          finish_reason="tool_calls" if tool_call else "stop")],
                          usage=SimpleNamespace() if malformed else None)


def install_inference(monkeypatch, responses):
    """Keep real adapter formatting/response parsing; replace only the transport."""
    create = AsyncMock(side_effect=responses)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    @asynccontextmanager
    async def offline_client(self):
        yield client

    from strands.models.openai import OpenAIModel
    monkeypatch.setattr(OpenAIModel, "_get_client", offline_client)
    monkeypatch.setattr(smoke, "read_api_key", lambda: "not-a-real-key")
    return create


def test_complete_lifecycle_and_exact_tool_content(mock_usgs, monkeypatch, capsys):
    mock_usgs()
    create = install_inference(monkeypatch, [completion(tool_call=True), completion()])
    assert smoke.main(["--agent", "--diagnose"]) == 0
    events = records(capsys)
    assert [(event["stage"], event["state"]) for event in events] == [
        ("model_request_1", "started"), ("model_request_1", "completed"),
        ("tool_dispatch", "started"), ("get_usgs_conditions", "entered"),
        ("get_usgs_conditions", "completed"), ("tool_result_serialization", "completed"),
        ("tool_result_wrapping", "completed"), ("model_request_2", "started"),
        ("model_request_2", "completed"), ("agent_response", "completed"),
    ]
    evidence = fetch()
    text = json.dumps(evidence, ensure_ascii=False)
    formatted = create.await_args_list[1].kwargs
    tool_message = next(message for message in formatted["messages"] if message["role"] == "tool")
    assert tool_message["content"] == text
    assert events[5]["result_type"] == "dict"
    assert events[5]["serialized_bytes"] == events[6]["text_content_bytes"] == len(text.encode("utf-8"))
    assert all(call.kwargs["max_tokens"] == 1024 and call.kwargs["stream"] is False
               for call in create.await_args_list)
    assert formatted["tools"][0]["function"]["name"] == "get_usgs_conditions"
    assert create.await_count == 2


class PrivateProviderError(Exception):
    status_code = 503
    body = {"error": {"message": SECRET, "param": SECRET}}
    request = {"Authorization": SECRET}


@pytest.mark.parametrize("second_request", [False, True])
def test_model_failure_stage_and_sanitization(mock_usgs, monkeypatch, capsys, second_request):
    mock_usgs()
    responses = ([completion(tool_call=True)] if second_request else []) + [PrivateProviderError(SECRET)]
    create = install_inference(monkeypatch, responses)
    assert smoke.main(["--agent", "--diagnose"]) == 1
    events = records(capsys)
    failed = events[-1]
    assert failed == {
        "stage": "agent_response", "state": "failed",
        "failed_stage": f"model_request_{2 if second_request else 1}",
        "exception_class": "EventLoopException" if second_request else "PrivateProviderError",
        "error_category": "server_error", "http_status": 503,
        **({"cause_exception_class": "PrivateProviderError"} if second_request else {}),
    }
    assert create.await_count == (2 if second_request else 1)
    assert len(usgs_tool.execution_events) == int(second_request)


def test_second_response_parsing_failure_without_http_status(mock_usgs, monkeypatch, capsys):
    mock_usgs()
    install_inference(monkeypatch, [completion(tool_call=True), completion(malformed=True)])
    assert smoke.main(["--agent", "--diagnose"]) == 1
    failed = records(capsys)[-1]
    assert failed["failed_stage"] == "model_request_2"
    assert failed["exception_class"] == "EventLoopException"
    assert failed["cause_exception_class"] == "AttributeError"
    assert failed["http_status"] == "unavailable" and failed["error_category"] == "api_error"


def test_tool_exception_is_reported_even_when_strands_catches_it(monkeypatch, capsys):
    monkeypatch.setattr(usgs_tool, "fetch_usgs_conditions", Mock(side_effect=PrivateProviderError(SECRET)))
    install_inference(monkeypatch, [completion(tool_call=True), completion()])
    assert smoke.main(["--agent", "--diagnose"]) == 1
    events = records(capsys)
    failed = [event for event in events if event["state"] == "failed"]
    assert failed == [{"stage": "get_usgs_conditions", "state": "failed",
                       "exception_class": "PrivateProviderError", "error_category": "server_error", "http_status": 503}]
    assert not any(event["stage"] == "tool_result_serialization" for event in events)


def test_invalid_tool_input_never_claims_function_entry(monkeypatch, capsys):
    install_inference(monkeypatch, [completion(tool_call=True, arguments='{"unexpected": 1}'), completion()])
    assert smoke.main(["--agent", "--diagnose"]) == 1
    events = records(capsys)
    assert not any(event["stage"] == "get_usgs_conditions" for event in events)
    assert any(event["stage"] == "tool_dispatch" and event["state"] == "failed" for event in events)


def test_wrapper_preserves_spec_result_and_adapter_request(mock_usgs, capsys):
    mock_usgs()
    diagnostics = USGSDiagnostics()
    wrapped = diagnostics.wrap_tool(usgs_tool.get_usgs_conditions)
    assert wrapped.tool_spec == usgs_tool.get_usgs_conditions.tool_spec
    assert wrapped(smoke.FACILITY_ID) == fetch()
    agent_class, model_class = load_strands_classes()
    model = build_model(model_class, "not-a-real-key")
    original = smoke.build_agent(agent_class, model)
    observed = smoke.build_agent(agent_class, model, diagnostics)
    assert original.tool_names == observed.tool_names == ["get_usgs_conditions"]
    assert original.system_prompt == observed.system_prompt
    kwargs = dict(messages=[{"role": "user", "content": [{"text": "Offline"}]}], system_prompt=original.system_prompt)
    assert model.format_request(tool_specs=[wrapped.tool_spec], **kwargs) == model.format_request(
        tool_specs=[usgs_tool.get_usgs_conditions.tool_spec], **kwargs)
    records(capsys)


def test_serialization_diagnostic_never_changes_result_or_sdk_fallback(monkeypatch, capsys):
    non_json_result = {"private": object()}
    monkeypatch.setattr(usgs_tool, "fetch_usgs_conditions", lambda *args: {**non_json_result, "status": "LIVE"})
    wrapped = USGSDiagnostics().wrap_tool(usgs_tool.get_usgs_conditions)
    result = wrapped(smoke.FACILITY_ID)
    assert result["private"] is non_json_result["private"]
    events = records(capsys)
    assert events[-1]["stage"] == "tool_result_serialization"
    assert events[-1]["exception_class"] == "TypeError"
    # Exercise real SDK wrapping too: its str fallback is retained.
    tool_use = {"toolUseId": "offline", "name": "get_usgs_conditions", "input": {"facility_id": smoke.FACILITY_ID}}

    async def invoke():
        return [event async for event in wrapped.stream(tool_use, {})]

    assert asyncio.run(invoke())[-1].tool_result["status"] == "success"
    records(capsys)


def test_profile_only_emits_counts_and_utf8_size():
    result = {SECRET: [None, True, 4, 1.5, "\u2014" + SECRET]}
    profile = result_profile(result)
    assert SECRET not in json.dumps(profile)
    assert profile["serialized_bytes"] == len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    assert profile["max_depth"] == 2 and profile["max_list_length"] == 5
    assert profile["value_type_counts"] == {"dict": 1, "list": 1, "str": 1, "int": 1,
                                            "float": 1, "bool": 1, "null": 1, "other": 0}


def test_offline_comparison_of_normalized_tool_results(mock_usgs, capsys):
    mock_usgs(handler=lambda request: httpx.Response(200, json=(
        alert_collection() if request.url.host == "api.weather.gov" else
        latest() if "latest-continuous" in request.url.path else history()
    )))
    profiles = {"facility": result_profile(get_facility(smoke.FACILITY_ID)),
                "nws_one_synthetic_alert": result_profile(get_nws_alerts(smoke.FACILITY_ID)),
                "usgs_two_synthetic_observations_and_trend": result_profile(fetch())}
    mock_usgs(handler=lambda request: httpx.Response(200, json={"type": "FeatureCollection", "features": []}))
    profiles["nws_no_synthetic_alerts"] = result_profile(get_nws_alerts(smoke.FACILITY_ID))
    assert {profile["result_type"] for profile in profiles.values()} == {"dict"}
    assert profiles["usgs_two_synthetic_observations_and_trend"]["serialized_bytes"] > profiles["facility"]["serialized_bytes"]
    print("OFFLINE SYNTHETIC COMPARISON " + json.dumps(profiles))
    output = capsys.readouterr().out
    assert SECRET not in output
    # Forward safe aggregate measurements when pytest is run with -s.
    print(output, end="")


def test_diagnose_requires_explicit_mode(monkeypatch):
    monkeypatch.setattr(smoke, "read_api_key", Mock(side_effect=AssertionError("No credentials")))
    monkeypatch.setattr(smoke, "build_model", Mock(side_effect=AssertionError("No model")))
    with pytest.raises(SystemExit) as error:
        smoke.main(["--diagnose"])
    assert error.value.code == 2


def test_check_diagnose_remains_offline(monkeypatch, capsys):
    monkeypatch.setattr(smoke, "read_api_key", Mock(side_effect=AssertionError("No credentials")))
    assert smoke.main(["--check", "--diagnose"]) == 0
    assert not records(capsys)


def test_default_mode_has_no_diagnostic_output(mock_usgs, monkeypatch, capsys):
    mock_usgs()
    install_inference(monkeypatch, [completion(tool_call=True), completion()])
    assert smoke.main(["--agent"]) == 0
    assert not records(capsys)


def test_setup_and_final_response_failures(monkeypatch, capsys):
    monkeypatch.setattr(smoke, "read_api_key", lambda: "not-a-real-key")
    monkeypatch.setattr(smoke, "build_model", Mock(side_effect=PrivateProviderError(SECRET)))
    assert smoke.main(["--agent", "--diagnose"]) == 1
    assert records(capsys)[-1]["failed_stage"] == "agent_setup"
    diagnostics = USGSDiagnostics()
    diagnostics.active_stage = "agent_response"
    diagnostics.failed(ValueError(SECRET))
    assert records(capsys)[-1]["failed_stage"] == "agent_response"


def test_recovered_tool_error_does_not_mislabel_later_final_response_failure(capsys):
    diagnostics = USGSDiagnostics()
    diagnostics.fail("get_usgs_conditions", ValueError(SECRET))
    diagnostics.before_model(SimpleNamespace())
    diagnostics.after_model(SimpleNamespace(exception=None))
    diagnostics.failed(TypeError(SECRET))
    assert records(capsys)[-1]["failed_stage"] == "agent_response"


def test_safe_errors_reject_invalid_status_and_messages():
    error = PrivateProviderError(SECRET)
    error.status_code = SECRET
    assert safe_error(error)["http_status"] == "unavailable"
    assert SECRET not in json.dumps(safe_error(error))


def test_safe_error_chain_is_bounded_and_cycle_safe():
    outer = RuntimeError(SECRET)
    inner = PrivateProviderError(SECRET)
    outer.__cause__ = inner
    inner.__cause__ = outer
    assert safe_error(outer) == {"exception_class": "RuntimeError", "cause_exception_class": "PrivateProviderError",
                                 "error_category": "server_error", "http_status": 503}


def test_strands_wrapping_failure_is_distinct_from_function_failure(mock_usgs, monkeypatch, capsys):
    from strands.tools.decorator import DecoratedFunctionTool
    mock_usgs()
    install_inference(monkeypatch, [completion(tool_call=True), completion()])
    monkeypatch.setattr(DecoratedFunctionTool, "_wrap_tool_result", Mock(side_effect=PrivateProviderError(SECRET)))
    # Strands may continue after a tool error. Preserve the existing smoke
    # test's exit criteria while still recording the failed wrapping stage.
    assert smoke.main(["--agent", "--diagnose"]) == 0
    events = records(capsys)
    assert any(event["stage"] == "get_usgs_conditions" and event["state"] == "completed" for event in events)
    assert any(event["stage"] == "tool_result_wrapping" and event["state"] == "failed" for event in events)


def test_diagnostics_preserve_tool_budget(mock_usgs, monkeypatch, capsys):
    mock_usgs()
    create = install_inference(monkeypatch, [completion(tool_call=True)] * 3 + [completion()])
    assert smoke.main(["--agent", "--diagnose"]) == 1
    events = records(capsys)
    assert len(usgs_tool.execution_events) == 2
    assert create.await_count == 3
    assert events[-1]["failed_stage"] == "tool_budget"
