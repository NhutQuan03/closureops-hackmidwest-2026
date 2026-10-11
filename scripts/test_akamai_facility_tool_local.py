"""Offline checks only: no authenticated requests or provider access."""

import contextlib
import io
from unittest.mock import patch

import pytest
from strands.models.openai import OpenAIModel

from backend.app.facilities import lookup_facility
from backend.app.facility_tool import execution_events, get_facility
from scripts import test_akamai_facility_tool as smoke
from scripts.test_akamai_strands import build_model, load_strands_classes


def test_valid_lookup_and_copy() -> None:
    result = lookup_facility("jefferson-research")
    assert result["ok"] is True
    facility = result["facility"]
    assert facility["name"] == "Jefferson Research Facility"
    assert (facility["city"], facility["state"]) == ("Columbia", "Missouri")
    assert facility["normal_opening"] == "07:30"
    assert facility["criticality"] == "standard"
    assert facility["data_source"] == "SIMULATED DEMO"
    facility["name"] = "Changed copy"
    assert lookup_facility("jefferson-research")["facility"]["name"] == "Jefferson Research Facility"


@pytest.mark.parametrize("value", ["", "../secret", "x" * 65, "a\n", "UPPER", None, 12])
def test_invalid_ids(value: object) -> None:
    assert lookup_facility(value) == {"ok": False, "error": "INVALID_FACILITY_ID"}


def test_unknown_id() -> None:
    assert lookup_facility("unknown") == {"ok": False, "error": "UNKNOWN_FACILITY_ID"}


def test_execution_record() -> None:
    execution_events.clear()
    get_facility("unknown")
    assert not execution_events
    assert get_facility("jefferson-research")["ok"] is True
    assert execution_events == [{"tool": "get_facility", "facility_id": "jefferson-research"}]


def test_registration_and_nonempty_specs() -> None:
    agent_class, model_class = load_strands_classes()
    model = build_model(model_class, "not-a-real-key")
    agent = smoke.build_agent(agent_class, model)
    assert agent.tool_names == ["get_facility"]
    spec = get_facility.tool_spec
    assert spec["inputSchema"]["json"]["required"] == ["facility_id"]
    messages = [{"role": "user", "content": [{"text": "Offline"}]}]
    original = build_model(OpenAIModel, "not-a-real-key")
    for choice in (None, {"auto": {}}, {"any": {}}, {"tool": {"name": "get_facility"}}):
        kwargs = dict(messages=messages, tool_specs=[spec], system_prompt="Read only", tool_choice=choice)
        actual = model.format_request(**kwargs)
        assert actual == original.format_request(**kwargs)
        assert actual["tools"][0]["function"]["name"] == "get_facility"


@pytest.mark.parametrize("execute,expected", [(False, 1), (True, 0)])
def test_plausible_answer_requires_real_execution(execute: bool, expected: int) -> None:
    def fake_agent(prompt: str) -> str:
        if execute:
            get_facility("jefferson-research")
        return "Jefferson Research Facility, Columbia, Missouri, 07:30, SIMULATED DEMO"

    with patch.object(smoke, "read_api_key", return_value="not-a-real-key"), patch.object(
        smoke, "build_agent", return_value=fake_agent
    ):
        assert smoke.main([]) == expected


def test_failure_sanitization_and_no_fallback() -> None:
    class ProviderError(Exception):
        status_code = 400
        body = {"error": {"param": "tools[0].function", "message": "SECRET", "type": "SECRET"}}

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        smoke.print_safe_failure(ProviderError("SECRET"))
    assert "SECRET" not in output.getvalue()
    assert "HTTP status: 400" in output.getvalue()
    assert "Provider parameter: tools" in output.getvalue()
    with patch.object(smoke, "read_api_key", return_value="not-a-real-key"), patch.object(
        smoke, "build_agent", side_effect=ProviderError("SECRET")
    ) as factory:
        assert smoke.main([]) == 1
        assert factory.call_count == 1
