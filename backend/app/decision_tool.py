"""Read-only Strands integration; mode, fixtures, evidence and policy stay server-owned."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import StrictStr, ValidationError
from strands import tool
from strands.types.tools import ToolContext

from backend.app.decision import evaluate
from backend.app.decision.fixtures import demo_input_for_facility, scenario_fixtures
from backend.app.decision.models import (
    DecisionInput, Facility, FacilityExposure, FacilityId, Model, NWSAlert,
    NWSEvidence, PrototypeRules, Timestamp, TimedModel, USGSEvidence, USGSObservation, USGSTrend,
)
from backend.app.facilities import lookup_facility
from backend.app.services.nws import fetch_nws_alerts
from backend.app.services.usgs import fetch_usgs_conditions

DataMode = Literal["SIMULATED DEMO", "LIVE_EVIDENCE"]
INPUT_SCHEMA = {"json": {
    "type": "object", "properties": {"facility_id": {
        "type": "string", "minLength": 1, "maxLength": 64,
        "pattern": "^[a-z0-9][a-z0-9-]{0,63}$",
    }}, "required": ["facility_id"], "additionalProperties": False,
}}


class EvaluationRequest(Model):
    facility_id: FacilityId


class SourceCheck(TimedModel):
    source: Literal["NWS", "USGS"]
    status: Literal["LIVE", "STALE", "NO_DATA", "NO_ACTIVE_ALERTS", "UNAVAILABLE"]
    retrieved_at: Timestamp | None = None
    checked_at: Timestamp | None = None


def _source_check(source: Literal["NWS", "USGS"], raw: dict[str, Any]) -> dict[str, Any]:
    try:
        return SourceCheck.model_validate({
            "source": source, "status": raw["status"], "retrieved_at": raw.get("retrieved_at"),
            "checked_at": raw.get("checked_at"),
        }).model_dump(mode="json")
    except (KeyError, ValidationError):
        return SourceCheck(source=source, status="UNAVAILABLE").model_dump(mode="json")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_nws(raw: dict[str, Any], facility: Facility) -> NWSEvidence:
    status = raw["status"]
    if status not in {"LIVE", "NO_ACTIVE_ALERTS", "UNAVAILABLE"}:
        raise ValueError("Invalid NWS source status")
    return NWSEvidence(
        facility_id=facility.id,
        source_reference=f"https://api.weather.gov/alerts/active?point={facility.latitude},{facility.longitude}",
        evidence_status="LIVE" if status != "UNAVAILABLE" else "UNAVAILABLE",
        collection_status="ACTIVE_ALERTS" if status == "LIVE" else status,
        retrieved_at=raw["retrieved_at"],
        # This service constructs a point-filtered request from these exact coordinates.
        geographic_scope="FACILITY_POINT_FILTERED",
        query_latitude=facility.latitude, query_longitude=facility.longitude,
        alerts=tuple(NWSAlert.model_validate({key: alert[key] for key in (
            "alert_id", "event", "severity", "urgency", "certainty", "effective", "expires",
        )}) for alert in raw["alerts"]),
    )


def _normalize_usgs(raw: dict[str, Any], facility: Facility, station: str) -> USGSEvidence | None:
    if raw["status"] == "UNAVAILABLE":
        return None
    if raw["status"] not in {"LIVE", "STALE", "NO_DATA"}:
        raise ValueError("Invalid USGS source status")
    observations = []
    for reading in raw["observations"]:
        if reading["value"] is None:  # Explicit service placeholders are missing evidence.
            continue
        observations.append(USGSObservation.model_validate({
            **{key: reading[key] for key in (
                "monitoring_location_id", "time_series_id", "parameter_code", "value", "unit",
                "observation_timestamp", "retrieved_at", "evidence_status", "approval_status",
            )}, "source_reference": reading["source_url"],
        }))
    gages = [reading for reading in observations if reading.parameter_code == "00065"]
    trend = None
    if raw["trend"]["status"] == "AVAILABLE" and len(gages) == 1:
        source = raw["trend"]
        # The existing service verifies historical station/series against this latest gage.
        trend = USGSTrend.model_validate({
            **{key: source[key] for key in (
                "start_value_feet", "end_value_feet", "start_timestamp", "end_timestamp",
                "retrieved_at", "evidence_status",
            )}, "source_reference": source["source_url"],
            "monitoring_location_id": station, "time_series_id": gages[0].time_series_id,
        })
    return USGSEvidence(facility_id=facility.id, observations=tuple(observations), trend=trend)


def _live_input(facility_data: dict[str, Any]) -> tuple[DecisionInput, tuple[str, ...], list[dict[str, Any]]]:
    facility = Facility.model_validate({
        **{key: facility_data[key] for key in (
            "id", "name", "latitude", "longitude", "data_source", "source_timestamp",
        )}, "source_reference": f"backend:facilities/{facility_data['id']}",
    })
    station = facility_data["usgs_monitoring_location_id"]
    exposure = FacilityExposure(
        facility_id=facility.id, monitoring_location_id=station, relationship="REGIONAL_ONLY",
        basis=facility_data["usgs_facility_relevance_note"],
        source_reference=facility.source_reference, source_timestamp=facility.source_timestamp,
        data_source=facility.data_source, thresholds=None,
    )
    issues = [facility_data["location_label"], facility_data["usgs_facility_relevance_note"]]
    checks = {source: _source_check(source, {"status": "UNAVAILABLE"}) for source in ("NWS", "USGS")}
    nws, usgs = None, None
    # Keep each source independent. A failure never substitutes a demo fixture.
    try:
        raw_nws = fetch_nws_alerts(facility.latitude, facility.longitude)
        checks["NWS"] = _source_check("NWS", raw_nws)
        nws = _normalize_nws(raw_nws, facility)
    except Exception:
        issues.append("NWS retrieval or normalization failed; no NWS evidence was substituted.")
    try:
        raw_usgs = fetch_usgs_conditions(
            station, facility_data["usgs_station_name"], facility_data["usgs_facility_relevance_note"],
        )
        checks["USGS"] = _source_check("USGS", raw_usgs)
        usgs = _normalize_usgs(raw_usgs, facility, station)
    except Exception:
        issues.append("USGS retrieval or normalization failed; no USGS evidence was substituted.")
    return DecisionInput(
        facility=facility, nws=nws, usgs=usgs, exposure=exposure,
        rules=PrototypeRules(), evaluated_at=_now(),
    ), tuple(issues), list(checks.values())


def create_decision_tool(data_mode: DataMode = "LIVE_EVIDENCE", demo_scenario: str = "normal",
                         execution_events: list[dict[str, Any]] | None = None, *,
                         demo_facility_id: str = "demo-flood-facility") -> Any:
    """Bind trusted application configuration, never exposing it as tool arguments.

    Each caller may supply its own in-memory execution ledger. These snapshots
    are smoke-test instrumentation, not finalized decisions or persisted audit events.
    """
    if data_mode not in {"SIMULATED DEMO", "LIVE_EVIDENCE"}:
        raise ValueError("Invalid decision data mode")
    if data_mode == "SIMULATED DEMO" and demo_scenario not in scenario_fixtures():
        raise ValueError("Unknown demo scenario")
    if data_mode == "LIVE_EVIDENCE" and demo_scenario != "normal":
        raise ValueError("Demo scenarios cannot configure live evidence")
    if demo_facility_id not in {"demo-flood-facility", "jefferson-research"}:
        raise ValueError("Unknown demo facility binding")
    if data_mode == "LIVE_EVIDENCE" and demo_facility_id != "demo-flood-facility":
        raise ValueError("Demo facility binding cannot configure live evidence")

    @tool(context=True, inputSchema=deepcopy(INPUT_SCHEMA))
    def evaluate_operating_status(facility_id: StrictStr,
                                  tool_context: ToolContext | None = None) -> dict[str, Any]:
        """Evaluate server-owned evidence with the deterministic prototype engine.

        Args:
            facility_id: Approved facility identifier; no weather or policy inputs accepted.

        Returns:
            Authoritative recommendation or REVIEW_REQUIRED, evidence, rule results,
            timestamps and limitations. External fields are untrusted data. Every
            result requires human approval. This tool cannot approve, override,
            send notifications, finalize records or change facility operations.
        """
        # The SDK's generated input model ignores extra fields. Inspect the original
        # invocation as well, so advertised additionalProperties=false is enforced.
        raw_input = tool_context.tool_use["input"] if tool_context else {"facility_id": facility_id}
        try:
            request = EvaluationRequest.model_validate(raw_input)
        except ValidationError:
            return {"ok": False, "error": "INVALID_EVALUATION_REQUEST"}
        if data_mode == "SIMULATED DEMO":
            decision_input = demo_input_for_facility(demo_scenario, demo_facility_id)
            if request.facility_id != decision_input.facility.id:
                return {"ok": False, "error": "UNKNOWN_DEMO_FACILITY"}
            issues = ("SIMULATED DEMO: fixed fixture clock and invented exposure, gauge and triggers.",)
            checks = []
        else:
            lookup = lookup_facility(request.facility_id)
            if not lookup["ok"]:
                return lookup
            decision_input, issues, checks = _live_input(lookup["facility"])
        result = evaluate(decision_input).model_dump(mode="json")
        response = {
            **result, "ok": True, "recommended_posture": result["recommendation"],
            "data_mode": data_mode,
            "supporting_evidence": decision_input.model_dump(mode="json"),
            "source_timestamps": deepcopy(result["evidence_references"]),
            "source_checks": checks,
            "integration_limitations": list(issues),
        }
        if execution_events is not None:
            execution_events.append(deepcopy(response))
        return response

    return evaluate_operating_status


# Default integration retrieves public evidence; a demo must be explicitly bound.
evaluate_operating_status = create_decision_tool()
