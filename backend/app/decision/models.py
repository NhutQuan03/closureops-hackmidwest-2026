"""Strict normalized evidence and server-owned prototype configuration.

These models deliberately do not import retrieval services or Strands. Raw tool
responses need explicit normalization; regional relevance is never promoted to
facility exposure here. Unknown evidence is represented, not filled in.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
import math
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, StrictStr,
    field_validator, model_validator,
)

Text = Annotated[StrictStr, Field(min_length=1, max_length=500)]
Reference = Annotated[StrictStr, Field(min_length=1, max_length=2048)]
FacilityId = Annotated[StrictStr, Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")]
StationId = Annotated[StrictStr, Field(pattern=r"^USGS-[0-9]{8,15}$")]
SeriesId = Annotated[StrictStr, Field(pattern=r"^[a-zA-Z0-9-]{1,64}$")]
Number = Annotated[float, Field(strict=True)]
Timestamp = Annotated[AwareDatetime, Field()]
ConfigurationLabel = Literal["CONFIGURED", "SIMULATED DEMO"]


class Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, allow_inf_nan=False, str_strip_whitespace=True,
    )

    @field_validator("*", mode="before")
    @classmethod
    def reject_control_characters(cls, value: object) -> object:
        if isinstance(value, str) and any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value):
            raise ValueError("Control characters are not accepted")
        return value


class TimedModel(Model):
    @field_validator(
        "source_timestamp", "retrieved_at", "effective", "expires",
        "observation_timestamp", "start_timestamp", "end_timestamp", "evaluated_at",
        "observed_at", "valid_from", "valid_until", check_fields=False, mode="before",
    )
    @classmethod
    def timestamp_type(cls, value: object) -> object:
        if value is not None and not isinstance(value, (str, datetime)):
            raise ValueError("Expected an aware datetime or ISO timestamp")
        return value


class OperatingPosture(StrEnum):
    OPEN = "OPEN"
    DELAYED_ARRIVAL = "DELAYED_ARRIVAL"
    UNSCHEDULED_TELEWORK = "UNSCHEDULED_TELEWORK"
    FACILITY_CLOSURE = "FACILITY_CLOSURE"


class EvaluationStatus(StrEnum):
    RECOMMENDATION_READY = "RECOMMENDATION_READY"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class EvidenceSufficiency(StrEnum):
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"
    CONFLICTING = "CONFLICTING"


class SourceState(StrEnum):
    LIVE = "LIVE"
    STALE = "STALE"
    SIMULATED_DEMO = "SIMULATED DEMO"
    UNAVAILABLE = "UNAVAILABLE"
    NO_DATA = "NO_DATA"


class Facility(TimedModel):
    id: FacilityId
    name: Text
    latitude: Number = Field(ge=-90, le=90)
    longitude: Number = Field(ge=-180, le=180)
    data_source: ConfigurationLabel
    source_timestamp: Timestamp
    source_reference: Reference


class GaugeThresholds(Model):
    """Site-specific prototype triggers in feet; never official flood stages."""

    delayed_arrival_feet: Number = Field(ge=0, le=1000)
    telework_feet: Number = Field(ge=0, le=1000)
    closure_feet: Number = Field(ge=0, le=1000)

    @model_validator(mode="after")
    def ordered_thresholds(self) -> GaugeThresholds:
        if not self.delayed_arrival_feet < self.telework_feet < self.closure_feet:
            raise ValueError("Prototype gauge thresholds must be strictly increasing")
        return self


class FacilityExposure(TimedModel):
    facility_id: FacilityId
    monitoring_location_id: StationId
    relationship: Literal["REGIONAL_ONLY", "ACCESS_ROUTE", "FACILITY"]
    basis: Text
    source_reference: Reference
    source_timestamp: Timestamp
    data_source: ConfigurationLabel
    thresholds: GaugeThresholds | None = None


class PrototypeRules(Model):
    """Trusted application configuration, never provided by an LLM."""

    version: Literal["prototype-flood-v1"] = "prototype-flood-v1"
    policy_label: Literal["PROTOTYPE - NOT OFFICIAL USDA POLICY"] = "PROTOTYPE - NOT OFFICIAL USDA POLICY"
    nws_max_age_minutes: StrictInt = Field(default=15, ge=1, le=1440)
    usgs_max_age_minutes: StrictInt = Field(default=120, ge=1, le=1440)
    rising_change_feet: Number = Field(default=1.0, gt=0, le=1000)


class NWSAlert(TimedModel):
    alert_id: Reference
    event: Text
    severity: Literal["Extreme", "Severe", "Moderate", "Minor", "Unknown"]
    urgency: Literal["Immediate", "Expected", "Future", "Past", "Unknown"]
    certainty: Literal["Observed", "Likely", "Possible", "Unlikely", "Unknown"]
    effective: Timestamp
    expires: Timestamp

    @model_validator(mode="after")
    def valid_interval(self) -> NWSAlert:
        if self.expires <= self.effective:
            raise ValueError("Alert expiry must follow its effective time")
        return self


class NWSEvidence(TimedModel):
    facility_id: FacilityId
    source: Literal["NWS"] = "NWS"
    source_reference: Reference
    evidence_status: SourceState
    collection_status: Literal["ACTIVE_ALERTS", "NO_ACTIVE_ALERTS", "UNAVAILABLE"]
    retrieved_at: Timestamp | None
    geographic_scope: Literal["FACILITY_POINT_FILTERED", "REGIONAL", "UNKNOWN"]
    query_latitude: Number = Field(ge=-90, le=90)
    query_longitude: Number = Field(ge=-180, le=180)
    alerts: tuple[NWSAlert, ...] = Field(default=(), max_length=100)

    @model_validator(mode="after")
    def collection_consistency(self) -> NWSEvidence:
        if self.collection_status == "NO_ACTIVE_ALERTS" and self.alerts:
            raise ValueError("NO_ACTIVE_ALERTS cannot contain alerts")
        if self.collection_status == "ACTIVE_ALERTS" and not self.alerts:
            raise ValueError("ACTIVE_ALERTS requires alerts")
        if len({alert.alert_id for alert in self.alerts}) != len(self.alerts):
            raise ValueError("Duplicate alert identifiers")
        return self


class USGSObservation(TimedModel):
    monitoring_location_id: StationId
    time_series_id: SeriesId
    parameter_code: Literal["00065", "00060"]
    value: Number
    unit: Literal["ft", "ft^3/s"]
    observation_timestamp: Timestamp
    retrieved_at: Timestamp
    evidence_status: SourceState
    source_reference: Reference
    approval_status: Literal["Approved", "Provisional"]

    @model_validator(mode="after")
    def correct_units(self) -> USGSObservation:
        if self.unit != {"00065": "ft", "00060": "ft^3/s"}[self.parameter_code]:
            raise ValueError("Parameter and unit mismatch")
        if self.observation_timestamp > self.retrieved_at:
            raise ValueError("Observation cannot follow retrieval")
        return self


class USGSTrend(TimedModel):
    monitoring_location_id: StationId
    time_series_id: SeriesId
    start_value_feet: Number
    end_value_feet: Number
    start_timestamp: Timestamp
    end_timestamp: Timestamp
    retrieved_at: Timestamp
    evidence_status: SourceState
    source_reference: Reference

    @model_validator(mode="after")
    def bounded_interval(self) -> USGSTrend:
        elapsed = (self.end_timestamp - self.start_timestamp).total_seconds()
        if not 3600 <= elapsed <= 10800:
            raise ValueError("Trend must span one to three hours")
        if self.end_timestamp > self.retrieved_at:
            raise ValueError("Trend cannot end after retrieval")
        if not math.isfinite(self.change_feet):
            raise ValueError("Trend endpoint difference must be finite")
        return self

    @property
    def change_feet(self) -> float:
        return self.end_value_feet - self.start_value_feet


class USGSEvidence(Model):
    facility_id: FacilityId
    source: Literal["USGS"] = "USGS"
    observations: tuple[USGSObservation, ...] = Field(default=(), max_length=20)
    trend: USGSTrend | None = None


class DecisionInput(TimedModel):
    facility: Facility
    nws: NWSEvidence | None
    usgs: USGSEvidence | None
    exposure: FacilityExposure | None
    rules: PrototypeRules
    evaluated_at: Timestamp


class EvidenceReference(TimedModel):
    reference_id: Reference
    source: Literal["FACILITY", "EXPOSURE", "NWS", "USGS"]
    source_reference: Reference
    state: SourceState | Literal["CONFIGURED"]
    observed_at: Timestamp | None = None
    retrieved_at: Timestamp | None = None
    valid_from: Timestamp | None = None
    valid_until: Timestamp | None = None


class TriggeredRule(Model):
    rule_id: Text
    reason: Text
    evidence_reference_ids: tuple[Reference, ...] = Field(max_length=125)


class DecisionResult(TimedModel):
    facility_id: FacilityId
    recommendation: OperatingPosture | None
    evaluation_status: EvaluationStatus
    evidence_sufficiency: EvidenceSufficiency
    data_label: Literal["LIVE", "STALE", "UNAVAILABLE", "SIMULATED DEMO"]
    evaluated_at: Timestamp
    rules: PrototypeRules
    thresholds: GaugeThresholds | None
    triggered_rules: tuple[TriggeredRule, ...]
    evidence_references: tuple[EvidenceReference, ...]
    reasons: tuple[Text, ...]
    limitations: tuple[Text, ...]
    human_approval_required: Literal[True] = True

    @field_validator("human_approval_required", mode="before")
    @classmethod
    def require_human_approval(cls, value: object) -> bool:
        if value is not True:
            raise ValueError("Human approval must be required")
        return True

    @model_validator(mode="after")
    def recommendation_consistency(self) -> DecisionResult:
        ready = self.evaluation_status == EvaluationStatus.RECOMMENDATION_READY
        if ready != (self.recommendation is not None):
            raise ValueError("Review is a status, not an operating posture")
        if ready != (self.evidence_sufficiency == EvidenceSufficiency.SUFFICIENT):
            raise ValueError("Recommendation requires sufficient evidence")
        return self
