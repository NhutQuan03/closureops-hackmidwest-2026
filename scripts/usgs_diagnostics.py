"""Opt-in smoke-test metadata only; never emit evidence or provider payloads."""

from __future__ import annotations

from functools import wraps
import json
from typing import Any

from scripts.test_akamai_strands import get_error_category, get_http_status_code


def safe_error(error: Exception) -> dict[str, object]:
    """Read bounded exception chains, never messages, bodies or request state."""
    current = error
    seen: set[int] = set()
    status_error: Exception | None = None
    for _ in range(8):
        seen.add(id(current))
        status = get_http_status_code(current)
        if status_error is None and type(status) is int and 100 <= status <= 599:
            status_error = current
        nested = (getattr(current, "original_exception", None) or current.__cause__ or current.__context__)
        if not isinstance(nested, Exception) or id(nested) in seen:
            break
        current = nested
    classified = status_error or current
    status = get_http_status_code(classified)
    metadata: dict[str, object] = {
        "exception_class": type(error).__name__,
        "error_category": get_error_category(classified),
        "http_status": status if type(status) is int and 100 <= status <= 599 else "unavailable",
    }
    if current is not error:
        metadata["cause_exception_class"] = type(current).__name__
    return metadata


def result_profile(result: object) -> dict[str, object]:
    """Measure the SDK's JSON-to-text UTF-8 representation, without emitting it.

    Counts describe values only; no dictionary keys or external strings escape.
    This is tool content size, not the full HTTP request size or a token estimate.
    """
    kinds = {kind: 0 for kind in ("dict", "list", "str", "int", "float", "bool", "null", "other")}
    max_depth = 0
    max_list_length = 0

    def visit(value: object, depth: int) -> None:
        nonlocal max_depth, max_list_length
        kind = "null" if value is None else type(value).__name__
        kinds[kind if kind in kinds else "other"] += 1
        max_depth = max(max_depth, depth)
        if isinstance(value, dict):
            for child in value.values():
                visit(child, depth + 1)
        elif isinstance(value, list):
            max_list_length = max(max_list_length, len(value))
            for child in value:
                visit(child, depth + 1)

    serialized = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
    visit(result, 0)
    return {
        "result_type": type(result).__name__ if type(result).__name__ in kinds else "other",
        "serialized_bytes": len(serialized.encode("utf-8")),
        "value_type_counts": kinds,
        "max_depth": max_depth,
        "max_list_length": max_list_length,
    }


class USGSDiagnostics:
    """Observe SDK lifecycle boundaries without changing tools or model settings."""

    def __init__(self) -> None:
        self.model_calls = 0
        self.tool_entered = False
        self.active_stage = "agent_setup"
        self.failed_stage: str | None = None

    def emit(self, stage: str, state: str, **metadata: object) -> None:
        print("DIAG " + json.dumps({"stage": stage, "state": state, **metadata}), flush=True)

    def fail(self, stage: str, error: Exception) -> None:
        self.failed_stage = stage
        self.emit(stage, "failed", **safe_error(error))

    def wrap_tool(self, original: Any) -> Any:
        from strands import tool

        # Copy function metadata only. Copying the decorated tool's __dict__
        # would overwrite the new SDK wrapper's callable with the original.
        @wraps(original, updated=())
        def observed(facility_id: str) -> dict[str, object]:
            self.tool_entered = True
            self.active_stage = "get_usgs_conditions"
            self.emit(self.active_stage, "entered")
            try:
                result = original(facility_id)
            except Exception as error:
                self.fail(self.active_stage, error)
                raise
            self.emit(self.active_stage, "completed")
            self.active_stage = "tool_result_serialization"
            try:
                self.emit(self.active_stage, "completed", **result_profile(result))
            except Exception as error:
                # Measurement must not replace the SDK's existing serialization
                # fallback or modify the returned evidence to hide an error.
                self.fail(self.active_stage, error)
            self.active_stage = "tool_result_wrapping"
            return result

        spec = original.tool_spec
        return tool(name=spec["name"], description=spec["description"],
                    inputSchema=spec["inputSchema"])(observed)

    def attach(self, agent: Any) -> None:
        from strands.hooks import (
            AfterModelCallEvent, AfterToolCallEvent, BeforeModelCallEvent, BeforeToolCallEvent,
        )

        agent.add_hook(self.before_model, BeforeModelCallEvent)
        agent.add_hook(self.after_model, AfterModelCallEvent)
        agent.add_hook(self.before_tool, BeforeToolCallEvent)
        agent.add_hook(self.after_tool, AfterToolCallEvent)

    def before_model(self, event: Any) -> None:
        self.failed_stage = None
        self.model_calls += 1
        self.active_stage = f"model_request_{self.model_calls}"
        self.emit(self.active_stage, "started")

    def after_model(self, event: Any) -> None:
        stage = f"model_request_{self.model_calls}"
        if event.exception is not None:
            self.fail(stage, event.exception)
        else:
            self.emit(stage, "completed")
            self.active_stage = "agent_response"
            self.failed_stage = None

    def before_tool(self, event: Any) -> None:
        self.failed_stage = None
        self.tool_entered = False
        self.active_stage = "tool_dispatch"
        self.emit(self.active_stage, "started")

    def after_tool(self, event: Any) -> None:
        if event.exception is not None:
            # Strands can convert an exception into a tool error instead of
            # raising it to the script. Do not read the error content/message.
            stage = "tool_result_wrapping" if self.tool_entered else "tool_dispatch"
            if self.failed_stage != "get_usgs_conditions":
                self.fail(stage, event.exception)
            return
        if event.result.get("status") != "success":
            self.fail("tool_dispatch", RuntimeError())
            return
        blocks = event.result["content"]
        text_blocks = [block["text"] for block in blocks if "text" in block]
        self.emit("tool_result_wrapping", "completed", result_type="dict",
                  content_blocks=len(blocks), text_blocks=len(text_blocks),
                  text_content_bytes=sum(len(text.encode("utf-8")) for text in text_blocks))
        self.active_stage = "agent_response"
        self.failed_stage = None

    def completed(self) -> None:
        self.emit("agent_response", "completed")

    def failed(self, error: Exception) -> None:
        self.emit("agent_response", "failed", failed_stage=self.failed_stage or self.active_stage,
                  **safe_error(error))
