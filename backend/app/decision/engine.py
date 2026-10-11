"""Pure, deterministic prototype flood rules. No I/O, model calls, or writes."""

from __future__ import annotations

from datetime import datetime, timedelta

from .models import (
    DecisionInput, DecisionResult, EvaluationStatus, EvidenceReference,
    EvidenceSufficiency, OperatingPosture, SourceState, TriggeredRule,
)

FLOOD_EVENTS = frozenset({
    "Flood Warning", "Flash Flood Warning", "Flood Watch", "Flash Flood Watch", "Flood Advisory",
})
FLOOD_WARNINGS = frozenset({"Flood Warning", "Flash Flood Warning"})
LIMITATIONS = (
    "PROTOTYPE rules and site triggers are not official USDA policy or official USGS flood stages.",
    "Only configured flood exposure is evaluated; an OPEN recommendation is not a general safety finding.",
    "NWS point filtering establishes alert applicability to configured coordinates, not observed inundation.",
    "Gauge stage and endpoint trend support configured exposure assumptions; they do not prove flooding.",
    "Discharge is retained as a reference when supplied but does not select posture in prototype-flood-v1.",
    "Every recommendation requires explicit human approval; this engine changes no facility status.",
)


def _fresh(state: SourceState, timestamp: datetime | None, retrieved_at: datetime | None,
           now: datetime, max_age_minutes: int) -> bool:
    return (
        state in {SourceState.LIVE, SourceState.SIMULATED_DEMO}
        and timestamp is not None and retrieved_at is not None
        and timestamp <= retrieved_at <= now
        and now - timestamp <= timedelta(minutes=max_age_minutes)
        and now - retrieved_at <= timedelta(minutes=max_age_minutes)
    )


def _reference_state(state: SourceState, timestamp: datetime | None,
                     retrieved_at: datetime | None, now: datetime, max_age: int) -> SourceState:
    # Simulation provenance survives stale timestamps. The review rule explains age.
    if state != SourceState.LIVE:
        return state
    if timestamp is None or retrieved_at is None or not timestamp <= retrieved_at <= now:
        return SourceState.UNAVAILABLE
    return state if _fresh(state, timestamp, retrieved_at, now, max_age) else SourceState.STALE


def _references(request: DecisionInput) -> tuple[EvidenceReference, ...]:
    now, rules = request.evaluated_at, request.rules
    facility, exposure, nws, usgs = request.facility, request.exposure, request.nws, request.usgs
    refs = [EvidenceReference(
        reference_id="facility", source="FACILITY", source_reference=facility.source_reference,
        state=facility.data_source, observed_at=facility.source_timestamp,
    )]
    refs.append(EvidenceReference(
        reference_id="exposure", source="EXPOSURE",
        source_reference=exposure.source_reference if exposure else "input:exposure-missing",
        state=exposure.data_source if exposure else SourceState.UNAVAILABLE,
        observed_at=exposure.source_timestamp if exposure else None,
    ))
    nws_state = _reference_state(
        nws.evidence_status, nws.retrieved_at, nws.retrieved_at, now, rules.nws_max_age_minutes,
    ) if nws else SourceState.UNAVAILABLE
    refs.append(EvidenceReference(
        reference_id="nws", source="NWS",
        source_reference=nws.source_reference if nws else "input:nws-missing",
        state=nws_state, retrieved_at=nws.retrieved_at if nws else None,
    ))
    if nws:
        for index, alert in enumerate(nws.alerts):
            state = nws_state
            if state == SourceState.LIVE and not alert.effective <= now < alert.expires:
                state = SourceState.STALE
            refs.append(EvidenceReference(
                reference_id=f"nws:alert:{index}", source="NWS", source_reference=alert.alert_id,
                state=state, retrieved_at=nws.retrieved_at,
                valid_from=alert.effective, valid_until=alert.expires,
            ))
    if usgs:
        for index, observation in enumerate(usgs.observations):
            refs.append(EvidenceReference(
                reference_id=f"usgs:observation:{index}", source="USGS",
                source_reference=observation.source_reference,
                state=_reference_state(
                    observation.evidence_status, observation.observation_timestamp,
                    observation.retrieved_at, now, rules.usgs_max_age_minutes,
                ), observed_at=observation.observation_timestamp, retrieved_at=observation.retrieved_at,
            ))
    else:
        refs.append(EvidenceReference(
            reference_id="usgs", source="USGS", source_reference="input:usgs-missing",
            state=SourceState.UNAVAILABLE,
        ))
    trend = usgs.trend if usgs else None
    refs.append(EvidenceReference(
        reference_id="usgs:trend", source="USGS",
        source_reference=trend.source_reference if trend else "input:usgs-trend-missing",
        state=_reference_state(
            trend.evidence_status, trend.end_timestamp, trend.retrieved_at,
            now, rules.usgs_max_age_minutes,
        ) if trend else SourceState.UNAVAILABLE,
        observed_at=trend.end_timestamp if trend else None,
        retrieved_at=trend.retrieved_at if trend else None,
        valid_from=trend.start_timestamp if trend else None,
        valid_until=trend.end_timestamp if trend else None,
    ))
    return tuple(refs)


def evaluate(request: DecisionInput) -> DecisionResult:
    """Evaluate normalized input at an explicit time, without consulting a clock.

    Configuration must come from trusted application code, not external text or
    model output. All review guards precede posture rules; first matching posture
    wins in closure, telework, delay, open order. See docs/decision-engine.md.
    """
    # Revalidate even model_construct/model_copy inputs; never bypass the schema.
    request = DecisionInput.model_validate(request.model_dump(warnings=False))
    now, facility, exposure = request.evaluated_at, request.facility, request.exposure
    nws, usgs, rules = request.nws, request.usgs, request.rules
    refs = _references(request)
    triggered: list[TriggeredRule] = []

    def trigger(rule_id: str, reason: str, *reference_ids: str) -> None:
        triggered.append(TriggeredRule(
            rule_id=rule_id, reason=reason, evidence_reference_ids=reference_ids,
        ))

    def result(posture: OperatingPosture | None,
               sufficiency: EvidenceSufficiency = EvidenceSufficiency.SUFFICIENT) -> DecisionResult:
        states = {ref.state for ref in refs}
        label = "SIMULATED DEMO" if SourceState.SIMULATED_DEMO in states else (
            "STALE" if SourceState.STALE in states else
            "UNAVAILABLE" if states & {SourceState.UNAVAILABLE, SourceState.NO_DATA} else "LIVE"
        )
        limitations = LIMITATIONS
        if label == "SIMULATED DEMO":
            limitations += ("SIMULATED DEMO: synthetic configuration or evidence is present; this is not a live facility decision.",)
        return DecisionResult(
            facility_id=facility.id, recommendation=posture,
            evaluation_status=EvaluationStatus.RECOMMENDATION_READY if posture else EvaluationStatus.REVIEW_REQUIRED,
            evidence_sufficiency=sufficiency, data_label=label, evaluated_at=now,
            rules=rules, thresholds=exposure.thresholds if exposure else None,
            triggered_rules=tuple(triggered), evidence_references=refs,
            reasons=tuple(rule.reason for rule in triggered), limitations=limitations,
        )

    if facility.source_timestamp > now:
        trigger("REVIEW_CONFIGURATION_TIME", "Facility configuration timestamp is in the future.", "facility")
    if exposure is None:
        trigger("REVIEW_EXPOSURE_MISSING", "Documented facility flood exposure and site-specific triggers are required.", "exposure")
    elif (
        exposure.facility_id != facility.id or exposure.relationship == "REGIONAL_ONLY"
        or exposure.thresholds is None or exposure.source_timestamp > now
    ):
        trigger("REVIEW_EXPOSURE_UNSUPPORTED", "Exposure must match the facility, document facility/access-route relevance, and define site triggers.", "facility", "exposure")

    if nws is None:
        trigger("REVIEW_NWS_MISSING", "NWS evidence is missing.", "nws")
    else:
        if (nws.facility_id != facility.id or nws.geographic_scope != "FACILITY_POINT_FILTERED"
                or nws.query_latitude != facility.latitude or nws.query_longitude != facility.longitude):
            trigger("REVIEW_NWS_APPLICABILITY", "NWS collection is not point-filtered at the selected facility's configured coordinates.", "facility", "nws")
        if (nws.collection_status == "UNAVAILABLE" or not _fresh(
            nws.evidence_status, nws.retrieved_at, nws.retrieved_at, now, rules.nws_max_age_minutes,
        )):
            trigger("REVIEW_NWS_FRESHNESS", "NWS evidence is unavailable, explicitly stale, future-dated, or older than the prototype retrieval window.", "nws")
        for index, alert in enumerate(nws.alerts):
            ref_id = f"nws:alert:{index}"
            if not alert.effective <= now < alert.expires:
                trigger("REVIEW_NWS_VALIDITY", "An alert is outside its effective-inclusive, expiry-exclusive validity interval.", ref_id)
            if alert.event not in FLOOD_EVENTS:
                trigger("REVIEW_UNSUPPORTED_HAZARD", "An active hazard is outside this flood-only prototype; manual review is required.", ref_id)
            if (alert.severity == "Unknown" or alert.urgency not in {"Immediate", "Expected"}
                    or alert.certainty not in {"Observed", "Likely", "Possible"}):
                trigger("REVIEW_ALERT_UNCERTAINTY", "Alert severity, urgency, or certainty cannot support this prototype recommendation.", ref_id)

    stages = [] if usgs is None else [
        (index, observation) for index, observation in enumerate(usgs.observations)
        if observation.parameter_code == "00065"
    ]
    if usgs is None:
        trigger("REVIEW_USGS_MISSING", "USGS evidence is missing.", "usgs")
    elif usgs.facility_id != facility.id:
        trigger("REVIEW_USGS_FACILITY", "USGS evidence is associated with a different facility.", "facility", "exposure")
    if len(stages) != 1:
        trigger("REVIEW_GAGE_MISSING_OR_AMBIGUOUS", "Exactly one usable gage-height series is required.", "exposure", "usgs:trend")
    else:
        index, stage = stages[0]
        stage_ref = f"usgs:observation:{index}"
        if exposure and stage.monitoring_location_id != exposure.monitoring_location_id:
            trigger("REVIEW_GAGE_ASSOCIATION", "Gage height is not from the explicitly configured exposure station.", "exposure", stage_ref)
        if not _fresh(stage.evidence_status, stage.observation_timestamp, stage.retrieved_at, now, rules.usgs_max_age_minutes):
            trigger("REVIEW_GAGE_FRESHNESS", "Gage height is unavailable, explicitly stale, future-dated, or older than the prototype observation window.", stage_ref)
    trend = usgs.trend if usgs else None
    if trend is None:
        trigger("REVIEW_TREND_MISSING", "A validated one-to-three-hour observed gage-height trend is required.", "usgs:trend")
    else:
        if not _fresh(trend.evidence_status, trend.end_timestamp, trend.retrieved_at, now, rules.usgs_max_age_minutes):
            trigger("REVIEW_TREND_FRESHNESS", "The trend endpoint or retrieval is unavailable, stale, or future-dated.", "usgs:trend")
        if len(stages) == 1:
            index, stage = stages[0]
            if (trend.monitoring_location_id != stage.monitoring_location_id
                    or trend.time_series_id != stage.time_series_id
                    or trend.end_timestamp != stage.observation_timestamp
                    or trend.end_value_feet != stage.value):
                trigger("REVIEW_CONFLICTING_HISTORY", "Trend station, series, timestamp, or end value contradicts the latest gage height.", f"usgs:observation:{index}", "usgs:trend")
    if triggered:
        conflicting = any(rule.rule_id == "REVIEW_CONFLICTING_HISTORY" for rule in triggered)
        return result(None, EvidenceSufficiency.CONFLICTING if conflicting else EvidenceSufficiency.INSUFFICIENT)

    # Review guards establish these invariants without filling in absent data.
    assert exposure and exposure.thresholds and nws and trend and len(stages) == 1
    thresholds = exposure.thresholds
    index, stage = stages[0]
    stage_refs = ("exposure", f"usgs:observation:{index}", "usgs:trend")
    warning_refs = tuple(
        f"nws:alert:{index}" for index, alert in enumerate(nws.alerts)
        if alert.event in FLOOD_WARNINGS and alert.severity in {"Severe", "Extreme"}
        and alert.certainty in {"Observed", "Likely"}
    )
    if warning_refs and stage.value < thresholds.delayed_arrival_feet and trend.change_feet <= 0:
        trigger("REVIEW_CONFLICTING_SIGNALS", "An applicable severe flood warning conflicts with a below-trigger, non-rising associated gage; neither signal is discarded.", *warning_refs, *stage_refs)
        return result(None, EvidenceSufficiency.CONFLICTING)

    if stage.value >= thresholds.closure_feet:
        trigger("PROTOTYPE_CLOSURE_STAGE", f"Associated gage height {stage.value:g} ft meets the prototype closure trigger {thresholds.closure_feet:g} ft.", *stage_refs)
        return result(OperatingPosture.FACILITY_CLOSURE)
    if warning_refs and stage.value >= thresholds.telework_feet:
        trigger("PROTOTYPE_CLOSURE_WARNING_AND_STAGE", f"Applicable severe flood warning plus associated gage height {stage.value:g} ft at/above the prototype telework trigger {thresholds.telework_feet:g} ft supports conservative closure.", *warning_refs, *stage_refs)
        return result(OperatingPosture.FACILITY_CLOSURE)
    if stage.value >= thresholds.telework_feet or warning_refs:
        reason = (
            f"Associated gage height {stage.value:g} ft meets the prototype telework trigger {thresholds.telework_feet:g} ft."
            if stage.value >= thresholds.telework_feet else
            f"An applicable severe flood warning supports precautionary telework; gage height {stage.value:g} ft has endpoint change {trend.change_feet:g} ft."
        )
        trigger("PROTOTYPE_TELEWORK", reason, *warning_refs, *stage_refs)
        return result(OperatingPosture.UNSCHEDULED_TELEWORK)
    if stage.value >= thresholds.delayed_arrival_feet or trend.change_feet >= rules.rising_change_feet or nws.alerts:
        causes = []
        if stage.value >= thresholds.delayed_arrival_feet:
            causes.append(f"gage height {stage.value:g} ft meets delay trigger {thresholds.delayed_arrival_feet:g} ft")
        if trend.change_feet >= rules.rising_change_feet:
            causes.append(f"observed endpoint rise {trend.change_feet:g} ft meets rise trigger {rules.rising_change_feet:g} ft")
        if nws.alerts:
            causes.append("an applicable flood alert is active")
        trigger("PROTOTYPE_DELAY", "Prototype delay is supported because " + "; ".join(causes) + ".", "nws", *stage_refs)
        return result(OperatingPosture.DELAYED_ARRIVAL)
    trigger("PROTOTYPE_OPEN_SUPPORTED", f"Fresh applicable NWS collection has no active alerts; documented exposure, stage {stage.value:g} ft below {thresholds.delayed_arrival_feet:g} ft, and endpoint change {trend.change_feet:g} ft below {rules.rising_change_feet:g} ft support OPEN for this flood-only prototype.", "nws", *stage_refs)
    return result(OperatingPosture.OPEN)
