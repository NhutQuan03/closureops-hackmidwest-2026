"""Validate agent selections against an actual engine result; render trusted text."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import Field, ValidationError

from backend.app.decision.models import (
    EvaluationStatus, EvidenceSufficiency, FacilityId, Model, OperatingPosture, Reference, Text,
)
from backend.app.decision_tool import DataMode


class BriefingSelection(Model):
    facility_id: FacilityId
    evaluation_status: EvaluationStatus
    recommended_posture: OperatingPosture | None
    evidence_sufficiency: EvidenceSufficiency
    data_mode: DataMode
    human_approval_required: Literal[True]
    rule_ids: tuple[Text, ...] = Field(min_length=1, max_length=125)
    evidence_reference_ids: tuple[Reference, ...] = Field(min_length=1, max_length=125)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate briefing field")
        result[key] = value
    return result


def validate_briefing(text: str, authoritative: dict[str, Any]) -> bool:
    """Accept schema-valid selections only when all authoritative conclusions match."""
    if len(text.encode("utf-8")) > 16 * 1024:
        return False
    try:
        raw = json.loads(text, object_pairs_hook=_unique_object)
        if not isinstance(raw, dict) or raw.get("human_approval_required") is not True:
            return False
        selection = BriefingSelection.model_validate(raw)
    except (ValueError, TypeError, ValidationError, RecursionError):
        return False
    selected = selection.model_dump(mode="json")
    for field in ("facility_id", "evaluation_status", "recommended_posture", "evidence_sufficiency",
                  "data_mode", "human_approval_required"):
        if selected[field] != authoritative[field]:
            return False
    rules = {rule["rule_id"] for rule in authoritative["triggered_rules"]}
    references = {ref["reference_id"] for ref in authoritative["evidence_references"]}
    required_refs = {ref for rule in authoritative["triggered_rules"] for ref in rule["evidence_reference_ids"]}
    return (
        len(set(selection.rule_ids)) == len(selection.rule_ids)
        and set(selection.rule_ids) == rules
        and len(set(selection.evidence_reference_ids)) == len(selection.evidence_reference_ids)
        and required_refs <= set(selection.evidence_reference_ids) <= references
    )


def render_briefing(authoritative: dict[str, Any]) -> str:
    """Use only backend evidence/reasons; unvalidated model prose is never displayed."""
    posture = authoritative["recommended_posture"] or "REVIEW_REQUIRED (no recommended posture)"
    lines = [
        f"Facility: {authoritative['facility_id']} | {authoritative['data_mode']} | {authoritative['data_label']}",
        f"Recommended posture: {posture}",
        f"Evidence sufficiency: {authoritative['evidence_sufficiency']} | evaluated {authoritative['evaluated_at']}",
        "Explicit human approval required. No facility operating status was changed.",
    ]
    for rule in authoritative["triggered_rules"]:
        lines.append(f"{rule['rule_id']}: {rule['reason']}")
    for ref in authoritative["evidence_references"]:
        lines.append(f"{ref['reference_id']} | {ref['source']} | {ref['state']} | {ref['source_reference']} | "
                     f"observed {ref['observed_at']} | retrieved {ref['retrieved_at']} | "
                     f"valid {ref['valid_from']} through {ref['valid_until']}")
    for check in authoritative["source_checks"]:
        lines.append(f"{check['source']} acquisition status {check['status']} | "
                     f"checked {check['checked_at']} | retrieved {check['retrieved_at']}")
    lines.extend(authoritative["limitations"])
    lines.extend(authoritative["integration_limitations"])
    return "\n".join(lines)
