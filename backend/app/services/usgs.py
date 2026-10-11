"""Read-only USGS observations; freshness and trends are evidence, not policy.

Query names and upstream fields: https://api.waterdata.usgs.gov/ogcapi/v1/openapi
and collections/{latest-continuous,continuous}/queryables?f=json.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import math
import os
import re
import ssl
import time
from typing import Annotated, Literal

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictStr, ValidationError, field_validator

BASE_URL = "https://api.waterdata.usgs.gov/ogcapi/v1/"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
MAX_ATTEMPTS = 2
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_FEATURES = 1000
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
DEFAULT_FRESHNESS_MINUTES = 120
TREND_WINDOW_HOURS = 3
MIN_TREND_SPAN_SECONDS = 3600
PARAMETERS = ("00065", "00060")
UNITS = {"00065": "ft", "00060": "ft^3/s"}
Text = Annotated[StrictStr, Field(min_length=1, max_length=500)]


class Station(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    monitoring_location_id: Annotated[StrictStr, Field(pattern=r"^USGS-[0-9]{8,15}$")]
    station_name: Text
    facility_relevance_note: Text


class Observation(BaseModel):
    # Extra GeoJSON properties are upstream data, never tool permissions.
    model_config = ConfigDict(extra="ignore")
    monitoring_location_id: Annotated[StrictStr, Field(pattern=r"^USGS-[0-9]{8,15}$")]
    time_series_id: Annotated[StrictStr, Field(pattern=r"^[a-zA-Z0-9-]{1,64}$")]
    parameter_code: Literal["00065", "00060"]
    value: Annotated[StrictStr, Field(min_length=1, max_length=100)]
    unit_of_measure: Text
    time: AwareDatetime
    approval_status: Literal["Approved", "Provisional"]
    qualifier: Annotated[StrictStr, Field(max_length=500)] | None

    @field_validator("time", mode="before")
    @classmethod
    def timestamp_text(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("Expected timestamp text")
        return value

    @field_validator("value")
    @classmethod
    def numeric_value(cls, value: str) -> str:
        if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", value):
            raise ValueError("Expected numeric observation")
        if not math.isfinite(float(value)):
            raise ValueError("Expected finite observation")
        return value


class Feature(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["Feature"]
    properties: dict[str, object]


class Link(BaseModel):
    model_config = ConfigDict(extra="ignore")
    rel: StrictStr


class Collection(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["FeatureCollection"]
    features: list[Feature] = Field(max_length=MAX_FEATURES)
    links: list[Link] = Field(default_factory=list, max_length=100)
    numberMatched: int | None = Field(default=None, ge=0, strict=True)
    numberReturned: int | None = Field(default=None, ge=0, strict=True)


class FetchFailure(Exception):
    """Controlled failure category, with no upstream response/exception text."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _url(collection: str, station: Station, **filters: str) -> httpx.URL:
    # Callers are internal; collections and all query fields are server-selected.
    return httpx.URL(BASE_URL + f"collections/{collection}/items", params={
        "f": "json", "monitoring_location_id": station.monitoring_location_id,
        "parameter_code": ",".join(PARAMETERS), "limit": str(MAX_FEATURES), **filters,
    })


def _read_collection(client: httpx.Client, url: httpx.URL) -> Collection:
    for attempt in range(MAX_ATTEMPTS):
        try:
            with client.stream("GET", url, timeout=TIMEOUT, follow_redirects=False) as response:
                if response.is_redirect:
                    raise FetchFailure("UNEXPECTED_REDIRECT")
                response.raise_for_status()
                if response.status_code != 200:
                    raise FetchFailure("INVALID_RESPONSE")
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if content_type not in {"application/json", "application/geo+json"}:
                    raise FetchFailure("INVALID_RESPONSE")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise FetchFailure("RESPONSE_TOO_LARGE")
                collection = Collection.model_validate(json.loads(body))
                if (
                    any(link.rel == "next" for link in collection.links)
                    or (collection.numberMatched is not None and collection.numberMatched > len(collection.features))
                    or (collection.numberReturned is not None and collection.numberReturned != len(collection.features))
                ):
                    # Never follow upstream links or silently use a partial page.
                    raise FetchFailure("INCOMPLETE_RESPONSE")
                return collection
        except httpx.HTTPStatusError as error:
            category = "HTTP_ERROR"
            if error.response.status_code not in RETRYABLE_STATUS_CODES:
                raise FetchFailure(category) from None
        except httpx.TimeoutException:
            category = "TIMEOUT"
        except httpx.TransportError:
            category = "NETWORK_ERROR"
        except (ValueError, ValidationError, UnicodeError):
            raise FetchFailure("INVALID_RESPONSE") from None
        if attempt == MAX_ATTEMPTS - 1:
            raise FetchFailure(category) from None
        time.sleep(0.5 * 2 ** attempt)
    raise FetchFailure("NETWORK_ERROR")


def _observations(collection: Collection, station: Station, checked_at: datetime) -> tuple[list[Observation], int]:
    observations = []
    rejected = 0
    for feature in collection.features:
        # A mismatched location indicates an unreliable filter/response, not no data.
        if feature.properties.get("monitoring_location_id") != station.monitoring_location_id:
            raise FetchFailure("INVALID_RESPONSE")
        try:
            observation = Observation.model_validate(feature.properties)
            if observation.unit_of_measure != UNITS[observation.parameter_code] or observation.time > checked_at:
                raise ValueError("Unusable observation")
        except (ValueError, ValidationError):
            rejected += 1
            continue
        observations.append(observation)
    return observations, rejected


def _empty_trend(reason: str) -> dict[str, object]:
    return {"status": "UNAVAILABLE", "reason": reason, "change_feet": None,
            "start_timestamp": None, "end_timestamp": None, "elapsed_seconds": None,
            "source": "USGS", "source_url": None, "retrieved_at": None}


def _reading(station: Station, parameter: str, url: httpx.URL, retrieved_at: datetime | None,
             observation: Observation | None, freshness: int, checked_at: datetime) -> dict[str, object]:
    status = "UNAVAILABLE" if retrieved_at is None else "NO_DATA"
    if observation is not None:
        status = "LIVE" if checked_at - observation.time <= timedelta(minutes=freshness) else "STALE"
    return {
        **station.model_dump(), "parameter_code": parameter,
        "value": float(observation.value) if observation else None,
        "unit": observation.unit_of_measure if observation else None,
        "observation_timestamp": _iso(observation.time) if observation else None,
        "retrieved_at": _iso(retrieved_at) if retrieved_at else None,
        "approval_status": observation.approval_status if observation else None,
        "qualifier": observation.qualifier if observation else None,
        "time_series_id": observation.time_series_id if observation else None,
        "source": "USGS", "source_url": str(url), "evidence_status": status,
    }


def calculate_trend(observations: list[Observation], latest: Observation, station: Station,
                    checked_at: datetime, url: httpx.URL, freshness: int) -> dict[str, object]:
    """Observed endpoint change over >=1 hour inside a 3-hour window; no rate inference."""
    window_start = latest.time - timedelta(hours=TREND_WINDOW_HOURS)
    points: dict[datetime, Observation] = {}
    for observation in observations:
        if (observation.monitoring_location_id != station.monitoring_location_id
                or observation.parameter_code != "00065" or observation.unit_of_measure != "ft"
                or observation.time_series_id != latest.time_series_id
                or not window_start <= observation.time <= latest.time):
            return _empty_trend("INCONSISTENT_HISTORY")
        previous = points.get(observation.time)
        if previous and Decimal(previous.value) != Decimal(observation.value):
            return _empty_trend("CONFLICTING_HISTORY")
        points[observation.time] = observation
    if len(points) < 2:
        return _empty_trend("INSUFFICIENT_HISTORY")
    start, end = points[min(points)], points[max(points)]
    elapsed = (end.time - start.time).total_seconds()
    if end.time != latest.time or Decimal(end.value) != Decimal(latest.value):
        return _empty_trend("LATEST_HISTORY_MISMATCH")
    if elapsed < MIN_TREND_SPAN_SECONDS:
        return _empty_trend("INSUFFICIENT_HISTORY_SPAN")
    change_feet = float(Decimal(end.value) - Decimal(start.value))
    if not math.isfinite(change_feet):
        return _empty_trend("INVALID_CHANGE")
    return {
        "status": "AVAILABLE", "change_feet": change_feet,
        "start_timestamp": _iso(start.time), "end_timestamp": _iso(end.time),
        "start_value_feet": float(start.value), "end_value_feet": float(end.value),
        "elapsed_seconds": elapsed, "observation_count": len(points),
        "requested_window_start": _iso(window_start), "requested_window_end": _iso(latest.time),
        "evidence_status": "LIVE" if checked_at - end.time <= timedelta(minutes=freshness) else "STALE",
        "source": "USGS", "source_url": str(url), "retrieved_at": _iso(checked_at),
        "facility_relevance_note": station.facility_relevance_note,
        "description": "Observed endpoint change only; not a flood threshold or facility impact assessment.",
    }


def fetch_usgs_conditions(monitoring_location_id: str, station_name: str,
                          facility_relevance_note: str) -> dict[str, object]:
    """Fetch latest observations and, only for one usable gage series, bounded history.

    The configurable 120-minute default is a prototype freshness window, not an
    official flood threshold. Partial/missing measurements remain explicit.
    """
    try:
        station = Station(monitoring_location_id=monitoring_location_id, station_name=station_name,
                          facility_relevance_note=facility_relevance_note)
    except ValidationError:
        return {"ok": False, "status": "UNAVAILABLE", "source": "USGS", "error": "INVALID_STATION"}
    latest_url = _url("latest-continuous", station)
    checked_at = _now()
    result = {
        **station.model_dump(), "ok": False, "status": "UNAVAILABLE", "source": "USGS",
        "source_url": str(latest_url), "checked_at": _iso(checked_at), "retrieved_at": None,
        "observations": [_reading(station, code, latest_url, None, None, 0, checked_at) for code in PARAMETERS],
        "trend": _empty_trend("NO_USABLE_GAGE_HEIGHT"),
    }
    raw_freshness = os.environ.get("USGS_FRESHNESS_MINUTES", str(DEFAULT_FRESHNESS_MINUTES))
    if not re.fullmatch(r"[0-9]{1,4}", raw_freshness) or not 1 <= int(raw_freshness) <= 1440:
        return {**result, "error": "INVALID_FRESHNESS_CONFIGURATION"}
    freshness = int(raw_freshness)
    result["freshness_threshold_minutes"] = freshness
    try:
        with httpx.Client(
            headers={"User-Agent": "ClosureOps/0.1 (local hackathon development)", "Accept": "application/geo+json"},
            timeout=TIMEOUT, follow_redirects=False, verify=ssl.create_default_context(),
        ) as client:
            collection = _read_collection(client, latest_url)
            checked_at = _now()
            observations, rejected = _observations(collection, station, checked_at)
            readings = []
            for code in PARAMETERS:
                matches = [observation for observation in observations if observation.parameter_code == code]
                readings.extend(
                    _reading(station, code, latest_url, checked_at, observation, freshness, checked_at)
                    for observation in matches or [None]
                )
            states = {reading["evidence_status"] for reading in readings}
            result.update(
                ok=True, status="NO_DATA" if "NO_DATA" in states else "STALE" if "STALE" in states else "LIVE",
                checked_at=_iso(checked_at), retrieved_at=_iso(checked_at), observations=readings,
                rejected_observation_count=rejected,
            )
            gages = [observation for observation in observations if observation.parameter_code == "00065"]
            if len(gages) == 1:
                latest = gages[0]
                history_url = _url(
                    "continuous", station, parameter_code="00065", time_series_id=latest.time_series_id,
                    time=f"{_iso(latest.time - timedelta(hours=TREND_WINDOW_HOURS))}/{_iso(latest.time)}",
                )
                try:
                    history = _read_collection(client, history_url)
                    history_checked_at = _now()
                    points, rejected_history = _observations(history, station, history_checked_at)
                    trend = calculate_trend(points, latest, station, history_checked_at, history_url, freshness)
                    trend.update(source_url=str(history_url), retrieved_at=_iso(history_checked_at),
                                 rejected_observation_count=rejected_history)
                    result["trend"] = trend
                except FetchFailure as error:
                    result["trend"] = {**_empty_trend(str(error)), "source_url": str(history_url)}
            elif len(gages) > 1:
                result["trend"] = _empty_trend("AMBIGUOUS_GAGE_SERIES")
    except FetchFailure as error:
        return {**result, "error": str(error)}
    except (OSError, ssl.SSLError):
        return {**result, "error": "TLS_CONFIGURATION_ERROR"}
    except httpx.HTTPError:
        return {**result, "error": "NETWORK_ERROR"}
    return result
