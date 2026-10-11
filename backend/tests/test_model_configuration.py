"""Offline token budgets and entrypoints; no credentials or network access."""

from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from strands.models.openai import OpenAIModel

from backend.app.facility_tool import get_facility
from scripts import test_akamai_facility_tool as facility
from scripts import test_akamai_strands as akamai
from scripts import test_nws_facility_tool as nws
from scripts import test_usgs_facility_tool as usgs


@pytest.fixture(autouse=True)
def block_real_network(monkeypatch):
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request",
                        Mock(side_effect=AssertionError("No network")))
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request",
                        AsyncMock(side_effect=AssertionError("No network")))


@pytest.mark.parametrize("tokens", [150, 1024])
@pytest.mark.parametrize("tools", [None, [], [get_facility.tool_spec]])
def test_token_limits_preserve_adapter_formatting(tokens, tools):
    _, model_class = akamai.load_strands_classes()
    model = akamai.build_model(model_class, "not-a-real-key", max_output_tokens=tokens)
    original = akamai.build_model(OpenAIModel, "not-a-real-key", max_output_tokens=tokens)
    kwargs = dict(messages=[{"role": "user", "content": [{"text": "Offline"}]}],
                  tool_specs=tools, system_prompt="Read only", tool_choice={"auto": {}})
    expected = original.format_request(**kwargs)
    if not tools:
        expected.pop("tools", None)
        expected.pop("tool_choice", None)
    actual = model.format_request(**kwargs)
    assert actual == expected
    assert actual["max_tokens"] == tokens
    assert actual["stream"] is False
    assert model.client_args == {
        "api_key": "not-a-real-key", "base_url": akamai.BASE_URL,
        "max_retries": 0, "timeout": 30,
    }


@pytest.mark.parametrize("tokens", [0, -1, True, False, None, "1024", 1024.0])
def test_invalid_token_limit_rejected_before_model_construction(tokens):
    constructor = Mock(side_effect=AssertionError("Model must not be constructed"))
    with pytest.raises(ValueError, match="max_output_tokens must be a positive integer"):
        akamai.build_model(constructor, "not-a-real-key", max_output_tokens=tokens)
    constructor.assert_not_called()


@pytest.mark.parametrize("module,tokens,agent_args", [
    (akamai, 150, []), (facility, 150, []),
    (nws, 150, ["--agent"]), (usgs, 1024, ["--agent"]),
    (usgs, 1024, ["--agent", "--diagnose"]),
])
@pytest.mark.parametrize("check_only", [True, False])
def test_script_entrypoint_token_budget(monkeypatch, capsys, module, tokens, agent_args, check_only):
    agent_class, model_class = akamai.load_strands_classes()
    # Keep real construction/registration; prevent invoking any model or tool.
    invoke = Mock(return_value="Offline response")
    monkeypatch.setattr(agent_class, "__call__", invoke)
    constructor = Mock(wraps=model_class)
    monkeypatch.setattr(module, "load_strands_classes", lambda: (agent_class, constructor))
    key_reader = Mock(side_effect=AssertionError("No credentials")) if check_only else Mock(
        return_value="not-a-real-key")
    monkeypatch.setattr(module, "read_api_key", key_reader)
    result = module.main(["--check"] if check_only else agent_args)
    assert result == (0 if check_only or module is akamai else 1)
    constructor.assert_called_once()
    assert constructor.call_args.kwargs["params"] == {"max_tokens": tokens}
    assert constructor.call_args.kwargs["stream"] is False
    if check_only:
        key_reader.assert_not_called()
        invoke.assert_not_called()
    else:
        key_reader.assert_called_once_with()
        invoke.assert_called_once()
    capsys.readouterr()
