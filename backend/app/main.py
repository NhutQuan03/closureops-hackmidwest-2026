"""Local FastAPI composition; no inference or live acquisition at startup."""

from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

from backend.app.api import create_router
from backend.app.api_security import REACT_ORIGINS, LocalDemoGuard, LocalDemoSettings, error_response
from backend.app.employee_notifications import (
    DuplicateNotificationPlan, NotificationPlanError, NotificationPlanNotFound, NotificationPlanService,
)
from backend.app.manager_decisions import (
    AuditStorageError, DecisionNotFound, DuplicateDecision, EvaluationNotFound,
    ManagerDecisionError, ManagerDecisionService,
)


def create_app(settings: LocalDemoSettings | None = None) -> FastAPI:
    """Compose existing SQLite services with server-owned demo configuration."""
    settings = settings or LocalDemoSettings.from_environment()
    settings.validate_local()
    application = FastAPI(title="ClosureOps Local Demo API", version="0.9.0", debug=False)

    @lru_cache(maxsize=8)
    def managers(scenario_id: str = "normal") -> ManagerDecisionService:
        return ManagerDecisionService(
            Path(settings.database_path), data_mode="SIMULATED DEMO",
            demo_scenario=scenario_id, demo_facility_id="jefferson-research",
        )

    @lru_cache(maxsize=1)
    def notifications() -> NotificationPlanService:
        return NotificationPlanService(Path(settings.database_path))

    application.include_router(create_router(managers, notifications, writes_enabled=settings.writes_enabled,
                                            ai_briefing_enabled=settings.ai_briefing_enabled))

    async def validation_error(request: Request, error: Exception) -> JSONResponse:
        # Never echo rejected inputs, exception context, configuration or secrets.
        return error_response(422, "INVALID_REQUEST", "Request does not match the API schema.")

    async def service_error(request: Request, error: Exception) -> JSONResponse:
        if isinstance(error, (EvaluationNotFound, DecisionNotFound, NotificationPlanNotFound)):
            return error_response(404, "RECORD_NOT_FOUND", "Requested persisted record was not found.")
        if isinstance(error, (DuplicateDecision, DuplicateNotificationPlan)):
            return error_response(409, "ALREADY_FINALIZED", "A final decision or plan already exists.")
        if isinstance(error, AuditStorageError):
            return error_response(503, "AUDIT_UNAVAILABLE", "Local audit storage is unavailable; retrieve history before retrying.")
        return error_response(409, "ACTION_NOT_ALLOWED", str(error))

    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        return error_response(error.status_code, "REQUEST_FAILED", str(error.detail))

    async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
        return error_response(500, "INTERNAL_ERROR", "Request failed; retrieve persisted history before retrying.")

    for exception in (RequestValidationError, ValidationError):
        application.add_exception_handler(exception, validation_error)
    for exception in (ManagerDecisionError, NotificationPlanError, AuditStorageError):
        application.add_exception_handler(exception, service_error)
    application.add_exception_handler(HTTPException, http_error)
    application.add_exception_handler(Exception, unexpected_error)

    application.add_middleware(LocalDemoGuard, settings=settings)
    application.add_middleware(
        CORSMiddleware, allow_origins=list(REACT_ORIGINS), allow_credentials=False,
        allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
    )
    return application


app = create_app()
