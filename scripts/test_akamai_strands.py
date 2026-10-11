"""Smoke test Akamai hosted inference through AWS Strands Agents SDK.

This script intentionally attaches no tools to the agent. It only verifies that
Strands can call the Akamai workshop OpenAI-compatible chat endpoint.
"""

from __future__ import annotations

import os
import sys
from typing import Any


BASE_URL = "https://ws.akamai-workshops.com/v1"
MODEL_ID = "hackathon-chat"
TIMEOUT_SECONDS = 30
MAX_OUTPUT_TOKENS = 150
API_KEY_ENV_VAR = "AKAMAI_INFERENCE_KEY"
TEST_PROMPT = "Reply with exactly: ClosureOps Akamai connection successful."


def load_strands_classes() -> tuple[type[Any], type[Any]] | None:
    try:
        from strands import Agent
        from strands.models.openai import OpenAIModel
    except ImportError as error:
        missing_module = getattr(error, "name", None) or "required Strands/OpenAI dependency"
        print(f"Missing dependency: {missing_module}")
        print("Install Strands OpenAI support before running this smoke test.")
        print("No inference request was sent.")
        return None

    class AkamaiOpenAIModel(OpenAIModel):
        """Omit unsupported empty tool fields while preserving SDK formatting."""

        def format_request(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            request = super().format_request(*args, **kwargs)
            if not request.get("tools"):
                request.pop("tools", None)
                request.pop("tool_choice", None)
            return request

    return Agent, AkamaiOpenAIModel


def read_api_key() -> str | None:
    api_key = os.environ.get(API_KEY_ENV_VAR, "").strip()
    if not api_key:
        print(f"Missing required environment variable: {API_KEY_ENV_VAR}")
        print("No inference request was sent.")
        return None

    return api_key


def build_model(openai_model: type[Any], api_key: str,
                max_output_tokens: int = MAX_OUTPUT_TOKENS) -> Any:
    """Build the smoke model; callers may explicitly budget longer responses."""
    if type(max_output_tokens) is not int or max_output_tokens <= 0:
        raise ValueError("max_output_tokens must be a positive integer")
    return openai_model(
        client_args={
            "api_key": api_key,
            "base_url": BASE_URL,
            "max_retries": 0,
            "timeout": TIMEOUT_SECONDS,
        },
        model_id=MODEL_ID,
        params={
            "max_tokens": max_output_tokens,
        },
        stream=False,
    )


def get_http_status_code(error: Exception) -> int | None:
    for attribute in ("status_code", "status"):
        value = getattr(error, attribute, None)
        if isinstance(value, int):
            return value

    response = getattr(error, "response", None)
    value = getattr(response, "status_code", None)
    if isinstance(value, int):
        return value

    return None


def get_error_category(error: Exception) -> str:
    status_code = get_http_status_code(error)
    error_name = type(error).__name__.lower()

    if "timeout" in error_name:
        return "timeout"
    if "rate" in error_name or status_code == 429:
        return "rate_limited"
    if status_code in {401, 403} or "authentication" in error_name or "permission" in error_name:
        return "authentication_or_permission"
    if "connection" in error_name or "connect" in error_name or "network" in error_name:
        return "network_error"
    if status_code is not None and 400 <= status_code < 500:
        return "client_error"
    if status_code is not None and 500 <= status_code < 600:
        return "server_error"

    return "api_error"


def get_sanitized_error_field(error: Exception, field_name: str) -> str | None:
    value = getattr(error, field_name, None)
    if value is None:
        body = getattr(error, "body", None)
        if isinstance(body, dict):
            value = body.get(field_name)
            nested_error = body.get("error")
            if value is None and isinstance(nested_error, dict):
                value = nested_error.get(field_name)

    if value is None or not isinstance(value, (str, int, float, bool)):
        return None

    text = str(value).strip()
    if not text or any(ord(character) < 32 for character in text):
        return None

    return text[:80]


def print_sanitized_api_failure(error: Exception) -> None:
    status_code = get_http_status_code(error)
    status_text = str(status_code) if status_code is not None else "unavailable"
    print(f"API failure category: {get_error_category(error)}")
    print(f"HTTP status code: {status_text}")
    if status_code == 400:
        provider_code = get_sanitized_error_field(error, "code")
        provider_parameter = get_sanitized_error_field(error, "param")
        provider_category = get_sanitized_error_field(error, "type")
        if provider_code:
            print(f"Provider error code: {provider_code}")
        if provider_parameter:
            print(f"Provider parameter: {provider_parameter}")
        if provider_category:
            print(f"Provider error category: {provider_category}")


def main(argv: list[str]) -> int:
    check_only = "--check" in argv
    loaded = load_strands_classes()
    if loaded is None:
        return 2

    agent_class, openai_model_class = loaded

    if check_only:
        model = build_model(openai_model_class, api_key="not-a-real-key")
        agent_class(model=model, tools=[], callback_handler=None)
        print("Import and configuration check passed.")
        print("No inference request was sent.")
        return 0

    api_key = read_api_key()
    if api_key is None:
        return 2

    model = build_model(openai_model_class, api_key)
    agent = agent_class(model=model, tools=[], callback_handler=None)

    try:
        result = agent(TEST_PROMPT)
    except Exception as error:
        print_sanitized_api_failure(error)
        return 1

    returned_text = str(result).strip()
    print("Returned text:")
    print(returned_text)
    print(f"Nonempty response received: {bool(returned_text)}")

    return 0 if returned_text else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
