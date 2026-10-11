"""SIMULATED DEMO fixtures: invented facility, gauge, readings, and triggers.

USGS-00000000 is a synthetic identifier, not a configured live monitoring site.
Never feed these fixtures into retrieval services or label them as live evidence.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Literal

from .models import (
    DecisionInput, EvaluationStatus, Model, OperatingPosture,
)

DEMO_TIME = datetime(2026, 10, 10, 18, 0, tzinfo=timezone.utc)


class DemoScenario(Model):
    label: Literal["SIMULATED DEMO"] = "SIMULATED DEMO"
    input: DecisionInput
    expected_recommendation: OperatingPosture | None
    expected_status: EvaluationStatus


def normal_input() -> DecisionInput:
    """Fresh within the synthetic evaluation clock, never a live observation."""
    return DecisionInput.model_validate({
        "evaluated_at": DEMO_TIME,
        "facility": {
            "id": "demo-flood-facility", "name": "SIMULATED DEMO Flood Facility",
            "latitude": 38.9517, "longitude": -92.3341,
            "data_source": "SIMULATED DEMO", "source_timestamp": DEMO_TIME,
            "source_reference": "demo:facility",
        },
        "exposure": {
            "facility_id": "demo-flood-facility", "monitoring_location_id": "USGS-00000000",
            "relationship": "ACCESS_ROUTE",
            "basis": "SIMULATED DEMO assumption: invented gauge associated with an invented vulnerable access route.",
            "source_reference": "demo:exposure-assumption", "source_timestamp": DEMO_TIME,
            "data_source": "SIMULATED DEMO",
            "thresholds": {"delayed_arrival_feet": 4.0, "telework_feet": 6.0, "closure_feet": 8.0},
        },
        "rules": {},
        "nws": {
            "facility_id": "demo-flood-facility", "source_reference": "demo:nws-point-collection",
            "evidence_status": "SIMULATED DEMO", "collection_status": "NO_ACTIVE_ALERTS",
            "retrieved_at": DEMO_TIME, "geographic_scope": "FACILITY_POINT_FILTERED",
            "query_latitude": 38.9517, "query_longitude": -92.3341, "alerts": [],
        },
        "usgs": {
            "facility_id": "demo-flood-facility",
            "observations": [{
                "monitoring_location_id": "USGS-00000000", "time_series_id": "demo-height",
                "parameter_code": "00065", "value": 2.0, "unit": "ft",
                "observation_timestamp": DEMO_TIME, "retrieved_at": DEMO_TIME,
                "evidence_status": "SIMULATED DEMO", "source_reference": "demo:usgs-height",
                "approval_status": "Provisional",
            }],
            "trend": {
                "monitoring_location_id": "USGS-00000000", "time_series_id": "demo-height",
                "start_value_feet": 2.0, "end_value_feet": 2.0,
                "start_timestamp": DEMO_TIME - timedelta(hours=2), "end_timestamp": DEMO_TIME,
                "retrieved_at": DEMO_TIME, "evidence_status": "SIMULATED DEMO",
                "source_reference": "demo:usgs-trend",
            },
        },
    })


def scenario_fixtures() -> dict[str, DemoScenario]:
    """Return independent fixtures with explicit expected outcomes for smoke tests."""
    normal = normal_input().model_dump(mode="json")

    def raised_stage(value: float, change: float = 0.5) -> dict:
        payload = deepcopy(normal)
        payload["usgs"]["observations"][0]["value"] = value
        payload["usgs"]["trend"].update(start_value_feet=value - change, end_value_feet=value)
        return payload

    delay, telework, severe = raised_stage(4.0), raised_stage(6.0), raised_stage(7.0, 2.0)
    warning = {
        "alert_id": "demo:nws-severe-warning", "event": "Flash Flood Warning",
        "severity": "Severe", "urgency": "Immediate", "certainty": "Observed",
        "effective": (DEMO_TIME - timedelta(minutes=30)).isoformat(),
        "expires": (DEMO_TIME + timedelta(hours=2)).isoformat(),
    }
    severe["nws"].update(collection_status="ACTIVE_ALERTS", alerts=[warning])
    missing = deepcopy(normal)
    missing["usgs"] = None
    stale = deepcopy(normal)
    stale["evaluated_at"] = (DEMO_TIME + timedelta(hours=3)).isoformat()
    conflicting = deepcopy(normal)
    conflicting["nws"].update(collection_status="ACTIVE_ALERTS", alerts=[warning])
    fixtures = {}
    for name, payload, recommendation in (
        ("normal", normal, OperatingPosture.OPEN),
        ("delayed_arrival", delay, OperatingPosture.DELAYED_ARRIVAL),
        ("unscheduled_telework", telework, OperatingPosture.UNSCHEDULED_TELEWORK),
        ("severe_applicable_flood", severe, OperatingPosture.FACILITY_CLOSURE),
        ("missing_evidence", missing, None),
        ("stale_evidence", stale, None),
        ("conflicting_evidence", conflicting, None),
    ):
        fixtures[name] = DemoScenario(
            input=DecisionInput.model_validate(payload), expected_recommendation=recommendation,
            expected_status=EvaluationStatus.RECOMMENDATION_READY if recommendation else EvaluationStatus.REVIEW_REQUIRED,
        )
    return fixtures


def demo_input_for_facility(scenario: str, facility_id: str) -> DecisionInput:
    """Bind existing simulated evidence to an explicitly configured demo facility.

    Jefferson's binding is an invented scenario, not its real USGS association or
    established exposure. Values, prototype thresholds and fixture clock are unchanged.
    This is server configuration, never an import of client-authored evidence.
    """
    original = scenario_fixtures()[scenario].input
    if facility_id == "demo-flood-facility":
        return original
    if facility_id != "jefferson-research":
        raise ValueError("Unknown demo facility binding")
    payload = original.model_dump(mode="python")
    payload["facility"].update(
        id=facility_id, name="Jefferson Research Facility",
        source_reference="demo:jefferson-research/facility",
    )
    for key in ("exposure", "nws", "usgs"):
        if payload[key] is not None:
            payload[key]["facility_id"] = facility_id
    payload["exposure"].update(
        basis="SIMULATED DEMO only: invented Jefferson access-route exposure and gauge; not the configured regional USGS association.",
        source_reference="demo:jefferson-research/invented-exposure",
    )
    return DecisionInput.model_validate(payload)
