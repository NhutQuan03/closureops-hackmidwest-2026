"""Concise deterministic composition; never select posture or accept model prose."""

from typing import Annotated

from pydantic import Field, StrictStr

from backend.app.decision.models import Model, SourceState
from backend.app.manager_decisions import TrustedEvaluation

Paragraph = Annotated[StrictStr, Field(min_length=1, max_length=1600)]


class SituationBriefing(Model):
    situation_summary: Paragraph
    operational_implications: Paragraph
    recommended_response: Paragraph
    suggested_next_steps: Paragraph
    evidence_limitations: Paragraph


def compose_situation_briefing(evaluation: TrustedEvaluation) -> SituationBriefing:
    """Explain the saved result using only evidence required by its fired rules.

    The existing AI validator requires every fired rule and every reference it
    uses. This subset is therefore always agent-selected on a validated run.
    Fallback composition uses the same saved Python rules, without an AI claim.
    No policy is re-evaluated here, and optional unselected readings are omitted.
    """
    result, evidence = evaluation.result, evaluation.evidence_snapshot
    references = {ref for rule in result.triggered_rules for ref in rule.evidence_reference_ids}
    alerts = [] if evidence.nws is None else [
        alert for index, alert in enumerate(evidence.nws.alerts)
        if f"nws:alert:{index}" in references
    ]
    stages = [] if evidence.usgs is None else [
        stage for index, stage in enumerate(evidence.usgs.observations)
        if stage.parameter_code == "00065" and f"usgs:observation:{index}" in references
    ]
    facts = []
    if alerts:
        alert = alerts[0]
        facts.append(f"a {alert.severity} {alert.event}")
    elif "nws" in references and evidence.nws and evidence.nws.collection_status == "NO_ACTIVE_ALERTS":
        facts.append("no active alerts in the saved NWS collection")
    if len(stages) == 1:
        stage = stages[0]
        qualifier = "synthetic" if stage.evidence_status == SourceState.SIMULATED_DEMO else "saved"
        facts.append(f"a {qualifier} gauge height of {stage.value:g} ft")
    summary = f"Saved {result.data_label} evaluation for {evidence.facility.name}"
    summary += " includes " + " and ".join(facts) + "." if facts else " requires manual evidence review."

    if result.recommendation is None:
        implications = f"Evidence is {result.evidence_sufficiency.value.lower()}. The Python engine has not selected an operating posture."
        response = "REVIEW_REQUIRED; no recommended operating posture. "
        steps = "Review the evidence gaps and resolve the reported issues before evaluating again. A review acknowledgment does not authorize an operating change or a notification plan."
    else:
        implications = "The selected evidence does not confirm facility or access-route flooding."
        if "exposure" in references and evidence.exposure:
            relation = {"ACCESS_ROUTE": "access-route", "FACILITY": "facility", "REGIONAL_ONLY": "regional"}[evidence.exposure.relationship]
            qualifier = "synthetic" if evidence.exposure.data_source == SourceState.SIMULATED_DEMO else "configured"
            implications = f"This evaluation uses a {qualifier} {relation} exposure assumption. " + implications
        response = f"{result.recommendation.value} is the authoritative Python recommendation. "
        steps = "Review the evidence and rule rationale, then explicitly approve or override the recommendation. An override requires a reason. Notification planning remains simulated and follows a finalized manager decision."

    combined = any(rule.rule_id == "PROTOTYPE_CLOSURE_WARNING_AND_STAGE" for rule in result.triggered_rules)
    if combined and len(stages) == 1 and result.thresholds:
        stage, thresholds = stages[0], result.thresholds
        comparison = "exceeds" if stage.value > thresholds.telework_feet else "meets"
        qualifier = "synthetic " if stage.evidence_status == SourceState.SIMULATED_DEMO else ""
        response += (
            f"The {qualifier}{stage.value:g} ft gauge {comparison} the {thresholds.telework_feet:g} ft prototype telework threshold. "
            "Combined with the applicable severe warning, this supports conservative closure. "
        )
        if stage.value < thresholds.closure_feet:
            response += f"The standalone {thresholds.closure_feet:g} ft closure threshold was not crossed."
    else:
        response += " ".join(rule.reason for rule in result.triggered_rules[:2])
        if len(result.triggered_rules) > 2:
            response += " Additional review causes are available in technical diagnostics."

    provenance = (
        "SIMULATED DEMO: synthetic configuration or evidence; not current live facility conditions. "
        if result.data_label == "SIMULATED DEMO" else f"{result.data_label} at the saved evaluation; current conditions are not established. "
    )
    provenance += "Saved evidence has not been refreshed. Gauge readings do not prove flooding. Prototype rules are not official USDA policy."
    return SituationBriefing(
        situation_summary=summary, operational_implications=implications,
        recommended_response=response, suggested_next_steps=steps,
        evidence_limitations=provenance,
    )
