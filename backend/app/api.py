"""Thin JSON adapter around trusted evaluation, manager and notification services."""

from typing import Annotated, Callable, Literal

from fastapi import APIRouter, Body, HTTPException, Query, Response
from pydantic import Field

from backend.app.decision.fixtures import demo_input_for_facility, scenario_fixtures
from backend.app.decision.models import (
    EvaluationStatus, FacilityId, Model, OperatingPosture, Text, Timestamp,
)
from backend.app.employee_notifications import (
    NotificationPlan, NotificationPlanRequest, NotificationPlanService,
)
from backend.app.facilities import lookup_facility
from backend.app.ai_briefing import AIBriefingResponse, AIBriefingService
from backend.app.national_nws import NationalAlertsResponse
from backend.app.services.nws import fetch_national_nws_alerts
from backend.app.manager_decisions import (
    DecisionId, DecisionRecord, EvaluationId, ManagerAction, ManagerDecisionRequest,
    ManagerDecisionService, TrustedEvaluation,
)

WORKFLOW_FACILITY = "jefferson-research"
# Read compatibility only. This is explicitly an old API alias, never a fixture binding.
LEGACY_FACILITY_ALIAS = "jefferson-research-facility"
ScenarioId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$", strict=True)]
DISCLOSURE = "SIMULATED DEMO: invented Jefferson access-route exposure and USGS-00000000 gauge; not its regional live USGS association."


class HealthResponse(Model):
    status: Literal["ok"] = "ok"
    service: Literal["closureops-api"] = "closureops-api"
    data_mode: Literal["synthetic_demo"] = "synthetic_demo"
    local_demo_writes_enabled: bool = False
    ai_briefing_enabled: bool = False


class Coordinates(Model):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class FacilityResponse(Model):
    id: FacilityId
    name: Text
    city: Text
    state: Text
    country: Literal["US"] = "US"
    timezone: Text
    coordinates: Coordinates
    operating_status: Literal["open"] = "open"
    operating_status_scope: Text = "Initial synthetic catalog status; use decision history for finalized synthetic postures."
    data_mode: Literal["synthetic_demo"] = "synthetic_demo"
    data_label: Literal["SIMULATED DEMO"] = "SIMULATED DEMO"
    source: Literal["ClosureOps synthetic facility fixture"] = "ClosureOps synthetic facility fixture"
    source_timestamp: Timestamp
    decision_authority: Text = "Human approval/override records synthetic decisions only; no real facility status changes."
    current_note: Text = DISCLOSURE
    last_reviewed_at: Timestamp


class ScenarioResponse(Model):
    scenario_id: ScenarioId
    facility_id: FacilityId = WORKFLOW_FACILITY
    data_label: Literal["SIMULATED DEMO"] = "SIMULATED DEMO"
    disclosure: Text = DISCLOSURE
    source: Literal["ClosureOps trusted synthetic scenario fixture"] = "ClosureOps trusted synthetic scenario fixture"
    source_timestamp: Timestamp
    evaluation_clock: Timestamp
    expected_recommendation: OperatingPosture | None
    expected_status: EvaluationStatus


class CreateEvaluationRequest(Model):
    facility_id: FacilityId
    scenario_id: ScenarioId


class DecisionActionRequest(Model):
    action: ManagerAction
    selected_posture: OperatingPosture | None = None
    reason: Text | None = None

    def for_evaluation(self, evaluation_id: str) -> ManagerDecisionRequest:
        # Reuse the existing action-specific validator; no parallel decision policy.
        return ManagerDecisionRequest(evaluation_id=evaluation_id, **self.model_dump())


class EmptyRequest(Model):
    """Notification preparation accepts {} only; the persisted ID comes from the path."""


class ErrorDetail(Model):
    code: str
    message: str


class ErrorResponse(Model):
    error: ErrorDetail


def _facility() -> FacilityResponse:
    data = lookup_facility(WORKFLOW_FACILITY)["facility"]
    return FacilityResponse(
        id=data["id"], name=data["name"], city=data["city"], state="MO",
        timezone=data["timezone"],
        coordinates=Coordinates(latitude=data["latitude"], longitude=data["longitude"]),
        source_timestamp=data["source_timestamp"], last_reviewed_at=data["source_timestamp"],
    )


def create_router(managers: Callable[..., ManagerDecisionService],
                  notifications: Callable[[], NotificationPlanService],
                  *, writes_enabled: bool = False, ai_briefing_enabled: bool = False) -> APIRouter:
    briefings = AIBriefingService(enabled=ai_briefing_enabled)
    router = APIRouter(prefix="/api", responses={
        status: {"model": ErrorResponse} for status in (403, 404, 409, 413, 415, 422, 429, 500, 503)
    })

    @router.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(local_demo_writes_enabled=writes_enabled,
                              ai_briefing_enabled=ai_briefing_enabled and writes_enabled)

    @router.post("/evaluations/{evaluation_id}/ai-briefing", response_model=AIBriefingResponse)
    def ai_briefing(evaluation_id: EvaluationId, request: EmptyRequest) -> AIBriefingResponse:
        return briefings.generate(managers().get_evaluation(evaluation_id))

    @router.get("/nws/alerts/active", response_model=NationalAlertsResponse)
    def national_nws_alerts() -> NationalAlertsResponse:
        return NationalAlertsResponse.model_validate(fetch_national_nws_alerts())

    @router.get("/facilities", response_model=list[FacilityResponse])
    def list_facilities() -> list[FacilityResponse]:
        return [_facility()]

    @router.get("/facilities/{facility_id}", response_model=FacilityResponse)
    def get_facility(facility_id: FacilityId, response: Response) -> FacilityResponse:
        if facility_id == LEGACY_FACILITY_ALIAS:
            response.headers["Deprecation"] = "true"
        elif facility_id != WORKFLOW_FACILITY:
            raise HTTPException(404, "Facility not found.")
        return _facility()

    @router.get("/demo/scenarios", response_model=list[ScenarioResponse])
    def scenarios() -> list[ScenarioResponse]:
        return [ScenarioResponse(
            scenario_id=name, source_timestamp=demo_input_for_facility(name, WORKFLOW_FACILITY).facility.source_timestamp,
            evaluation_clock=fixture.input.evaluated_at,
            expected_recommendation=fixture.expected_recommendation, expected_status=fixture.expected_status,
        ) for name, fixture in scenario_fixtures().items()]

    @router.post("/evaluations", response_model=TrustedEvaluation, status_code=201)
    def evaluate(request: CreateEvaluationRequest, response: Response) -> TrustedEvaluation:
        if request.facility_id != WORKFLOW_FACILITY or request.scenario_id not in scenario_fixtures():
            raise HTTPException(404, "Unknown demo facility or scenario binding.")
        evaluation = managers(request.scenario_id).evaluate_facility(request.facility_id)
        response.headers["Location"] = f"/api/evaluations/{evaluation.evaluation_id}"
        return evaluation

    @router.get("/evaluations/{evaluation_id}", response_model=TrustedEvaluation)
    def get_evaluation(evaluation_id: EvaluationId) -> TrustedEvaluation:
        return managers().get_evaluation(evaluation_id)

    @router.post("/evaluations/{evaluation_id}/decisions", response_model=DecisionRecord, status_code=201)
    def decide(evaluation_id: EvaluationId, request: DecisionActionRequest, response: Response) -> DecisionRecord:
        record = managers().record_decision(request.for_evaluation(evaluation_id))
        response.headers["Location"] = f"/api/decisions/{record.decision_id}"
        return record

    @router.get("/decisions/{decision_id}", response_model=DecisionRecord)
    def get_decision(decision_id: DecisionId) -> DecisionRecord:
        return managers().get_decision(decision_id)

    @router.post("/decisions/{decision_id}/notification-plans", response_model=NotificationPlan, status_code=201)
    def prepare(decision_id: DecisionId, response: Response,
                request: Annotated[EmptyRequest, Body()]) -> NotificationPlan:
        plan = notifications().prepare(NotificationPlanRequest(decision_id=decision_id))
        response.headers["Location"] = f"/api/decisions/{decision_id}/notification-plan"
        return plan

    @router.get("/decisions/{decision_id}/notification-plan", response_model=NotificationPlan)
    def get_plan(decision_id: DecisionId) -> NotificationPlan:
        # Distinguish a missing decision from a decision with no plan yet.
        managers().get_decision(decision_id)
        return notifications().get_plan_for_decision(decision_id)

    @router.get("/audit", response_model=list[DecisionRecord])
    def history(facility_id: FacilityId | None = None,
                limit: Annotated[int, Query(ge=1, le=100)] = 100) -> list[DecisionRecord]:
        if facility_id is not None and facility_id != WORKFLOW_FACILITY:
            raise HTTPException(404, "Unknown demo facility.")
        return list(managers().list_history(facility_id=facility_id, limit=limit))

    return router
