"""Read-only public alert response models; no facility or decision authority."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from backend.app.services.nws import NATIONAL_SELECTION_LIMIT


class NationalAlert(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alert_id: str = Field(min_length=1, max_length=2048)
    source_url: str = Field(min_length=1, max_length=2048)
    event: str = Field(min_length=1, max_length=500)
    severity: str | None
    urgency: str | None
    certainty: str | None
    affected_area: str | None = Field(max_length=100_000)
    sent: AwareDatetime | None
    effective: AwareDatetime | None
    expires: AwareDatetime | None
    status: Literal["LIVE", "STALE"]
    source: Literal["NWS"]
    retrieved_at: AwareDatetime


class NationalAlertsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool
    status: Literal["LIVE", "STALE", "NO_ACTIVE_ALERTS", "UNAVAILABLE"]
    source: Literal["NWS"]
    scope: Literal["NATIONWIDE"]
    source_url: Literal["https://api.weather.gov/alerts/active"]
    facility_applicability: Literal["NOT_ASSESSED"]
    retrieved_at: AwareDatetime | None
    checked_at: AwareDatetime
    fresh_until: AwareDatetime | None
    alerts: list[NationalAlert] = Field(max_length=NATIONAL_SELECTION_LIMIT)
    selection_limit: Literal[5]
    collection_limited: bool
    examined_count: int = Field(ge=0, le=5000)
    error: str | None = None
