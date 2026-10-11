"""Bounded, read-only NWS retrieval. Alert text is untrusted evidence only."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
import os
import ssl
import time
from typing import Annotated, Literal

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, PrivateAttr, StrictStr, ValidationError, field_validator

ALERTS_URL = "https://api.weather.gov/alerts/active"
DEFAULT_USER_AGENT = "ClosureOps/0.1 (local hackathon development)"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
MAX_ATTEMPTS = 3
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_ALERTS = 100
NATIONAL_MAX_BYTES = 10 * 1024 * 1024
NATIONAL_MAX_ALERTS = 5000
NATIONAL_SELECTION_LIMIT = 5
NATIONAL_FRESH_SECONDS = 300
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

Text = Annotated[StrictStr, Field(max_length=100_000)]
Identifier = Annotated[StrictStr, Field(min_length=1, max_length=2048)]


class ReferencePoint(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class AlertProperties(BaseModel):
    # Ignore unrelated upstream GeoJSON fields; require the evidence we consume.
    model_config = ConfigDict(extra="ignore")
    id: Identifier
    event: Annotated[StrictStr, Field(min_length=1, max_length=500)]
    headline: Text | None
    severity: Literal["Extreme", "Severe", "Moderate", "Minor", "Unknown"]
    urgency: Literal["Immediate", "Expected", "Future", "Past", "Unknown"]
    certainty: Literal["Observed", "Likely", "Possible", "Unlikely", "Unknown"]
    effective: AwareDatetime
    expires: AwareDatetime
    areaDesc: Text
    description: Text
    instruction: Text | None

    @field_validator("effective", "expires", mode="before")
    @classmethod
    def require_timestamp_text(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("Expected timestamp text")
        return value


class AlertFeature(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["Feature"]
    properties: AlertProperties


class AlertCollection(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["FeatureCollection"]
    features: list[AlertFeature] = Field(max_length=MAX_ALERTS)
    # Refuse incomplete pages rather than silently reporting a partial collection.
    pagination: dict[str, object] | None = None


class NationalAlertProperties(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: Identifier
    event: Annotated[StrictStr, Field(min_length=1, max_length=500)]
    status: Literal["Actual", "Exercise", "System", "Test", "Draft"]
    messageType: Literal["Alert", "Update", "Cancel"]
    severity: Literal["Extreme", "Severe", "Moderate", "Minor", "Unknown"] | None = None
    urgency: Literal["Immediate", "Expected", "Future", "Past", "Unknown"] | None = None
    certainty: Literal["Observed", "Likely", "Possible", "Unlikely", "Unknown"] | None = None
    areaDesc: Text | None = None
    sent: AwareDatetime | None = None
    effective: AwareDatetime | None = None
    expires: AwareDatetime | None = None

    @field_validator("sent", "effective", "expires", mode="before")
    @classmethod
    def timestamp_text(cls, value: object) -> object:
        if value is not None and not isinstance(value, str):
            raise ValueError("Expected timestamp text")
        return value


class NationalAlertFeature(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["Feature"]
    id: Identifier
    properties: NationalAlertProperties

    @field_validator("id")
    @classmethod
    def official_alert_url(cls, value: str) -> str:
        url = httpx.URL(value)
        if (url.scheme != "https" or url.host != "api.weather.gov"
                or url.port not in {None, 443} or url.userinfo or url.query or url.fragment
                or not url.path.startswith("/alerts/") or len(url.path) <= len("/alerts/")):
            raise ValueError("Expected official NWS alert URL")
        return value


class NationalAlertCollection(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["FeatureCollection"]
    features: list[NationalAlertFeature] = Field(max_length=NATIONAL_MAX_ALERTS)
    pagination: dict[str, object] | None = None
    _response_at: datetime | None = PrivateAttr(default=None)
    _age: int = PrivateAttr(default=0)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _unavailable(error: str) -> dict[str, object]:
    return {
        "ok": False, "status": "UNAVAILABLE", "source": "NWS",
        "retrieved_at": None, "checked_at": _now(), "alerts": [], "error": error,
    }


def _read_collection(client: httpx.Client, point: str | None) -> AlertCollection | NationalAlertCollection:
    parameters = {"point": point} if point is not None else {"status": "actual"}
    url = httpx.URL(ALERTS_URL, params=parameters)
    # NWS documents an internal redirect to /alerts?active=true. Permit only
    # that fixed HTTPS host/path and original filters, never arbitrary URLs.
    for redirect_count in range(3):
        with client.stream("GET", url, timeout=TIMEOUT, follow_redirects=False) as response:
            if response.is_redirect:
                target = url.join(response.headers.get("location", ""))
                if (
                    redirect_count == 2 or target.scheme != "https"
                    or target.host != "api.weather.gov" or target.port not in {None, 443}
                    or target.userinfo or target.path not in {"/alerts", "/alerts/active"}
                    or any(target.params.get_list(key) != [value] for key, value in parameters.items())
                    or (target.path == "/alerts" and target.params.get_list("active") != ["true"])
                    or set(target.params) - {*parameters, "active"}
                ):
                    raise ValueError("Unexpected redirect")
                url = target
                continue
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError("Unexpected status")
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if content_type not in {"application/geo+json", "application/json"}:
                raise ValueError("Unexpected content type")
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > (MAX_RESPONSE_BYTES if point is not None else NATIONAL_MAX_BYTES):
                    raise ValueError("Response too large")
            model = AlertCollection if point is not None else NationalAlertCollection
            collection = model.model_validate(json.loads(body))
            if point is not None and collection.pagination and collection.pagination.get("next"):
                raise ValueError("Incomplete response")
            if isinstance(collection, NationalAlertCollection):
                if response.headers.get("date"):
                    collection._response_at = parsedate_to_datetime(response.headers["date"])
                    if collection._response_at.tzinfo is None:
                        raise ValueError("Invalid response timestamp")
                collection._age = int(response.headers.get("age", "0"))
                if collection._age < 0:
                    raise ValueError("Invalid response age")
            return collection
    raise ValueError("Redirect budget exceeded")


def _fetch_collection(point: str | None) -> AlertCollection | NationalAlertCollection | dict[str, object]:
    user_agent = os.environ.get("NWS_USER_AGENT", DEFAULT_USER_AGENT)
    if not user_agent.strip() or len(user_agent) > 256 or any(
        ord(character) < 32 or ord(character) > 126 for character in user_agent
    ):
        return _unavailable("INVALID_USER_AGENT")
    user_agent = user_agent.strip()
    try:
        # Use standard platform CA trust with certificate verification enabled.
        # SSL_CERT_FILE/SSL_CERT_DIR can configure a trusted local CA bundle.
        with httpx.Client(
            headers={"User-Agent": user_agent, "Accept": "application/geo+json"},
            timeout=TIMEOUT, follow_redirects=False, verify=ssl.create_default_context(),
        ) as client:
            for attempt in range(MAX_ATTEMPTS):
                try:
                    collection = _read_collection(client, point)
                    break
                except httpx.HTTPStatusError as error:
                    if error.response.status_code not in RETRYABLE_STATUS_CODES or attempt == MAX_ATTEMPTS - 1:
                        return _unavailable("HTTP_ERROR")
                except httpx.TimeoutException:
                    if attempt == MAX_ATTEMPTS - 1:
                        return _unavailable("TIMEOUT")
                except httpx.TransportError:
                    if attempt == MAX_ATTEMPTS - 1:
                        return _unavailable("NETWORK_ERROR")
                time.sleep(0.5 * 2 ** attempt)
    except (ValueError, ValidationError, UnicodeError):
        return _unavailable("INVALID_RESPONSE")
    except (OSError, ssl.SSLError):
        return _unavailable("TLS_CONFIGURATION_ERROR")
    except httpx.HTTPError:
        return _unavailable("NETWORK_ERROR")

    return collection


def fetch_nws_alerts(latitude: float, longitude: float) -> dict[str, object]:
    """Read point-filtered evidence; no recommendations or writes occur."""
    try:
        location = ReferencePoint(latitude=latitude, longitude=longitude)
    except ValidationError:
        return _unavailable("INVALID_COORDINATES")
    collection = _fetch_collection(f"{location.latitude},{location.longitude}")
    if isinstance(collection, dict):
        return collection

    retrieved_at = _now()
    alerts = []
    for feature in collection.features:
        properties = feature.properties.model_dump(mode="json")
        properties["alert_id"] = properties.pop("id")
        properties["affected_area"] = properties.pop("areaDesc")
        properties.update(source="NWS", retrieved_at=retrieved_at)
        alerts.append(properties)
    return {
        "ok": True, "status": "LIVE" if alerts else "NO_ACTIVE_ALERTS",
        "source": "NWS", "retrieved_at": retrieved_at, "checked_at": retrieved_at,
        "alerts": alerts,
    }


def fetch_national_nws_alerts() -> dict[str, object]:
    """Small read-only selection of actual national alerts, never facility evidence.

    Do not follow upstream pagination links. An incomplete collection is explicitly
    identified and never used to claim that no nationwide alerts exist.
    """
    collection = _fetch_collection(None)
    context = {
        "scope": "NATIONWIDE", "source_url": ALERTS_URL,
        "selection_limit": NATIONAL_SELECTION_LIMIT,
        "facility_applicability": "NOT_ASSESSED",
        "collection_limited": False, "examined_count": 0,
        "fresh_until": None,
    }
    if isinstance(collection, dict):
        return {**collection, **context}
    assert isinstance(collection, NationalAlertCollection)
    now = datetime.now(timezone.utc)
    response_at = collection._response_at
    fresh_until = min(
        now + timedelta(seconds=max(0, NATIONAL_FRESH_SECONDS - collection._age)),
        response_at + timedelta(seconds=NATIONAL_FRESH_SECONDS) if response_at else now,
    )
    fresh = response_at is not None and response_at <= now + timedelta(seconds=60) and fresh_until > now
    partial = bool(collection.pagination and collection.pagination.get("next"))
    actual = [feature for feature in collection.features
              if feature.properties.status == "Actual" and feature.properties.messageType != "Cancel"]
    # Expired and unknown-validity evidence is never presented as current.
    current = [feature for feature in actual if feature.properties.expires and feature.properties.expires > now
               and (feature.properties.sent is None or feature.properties.sent <= now + timedelta(seconds=60))]
    candidates = current or actual
    candidates.sort(key=lambda feature: (feature.properties.sent or datetime.min.replace(tzinfo=timezone.utc), feature.id), reverse=True)
    retrieved_at = now.isoformat().replace("+00:00", "Z")
    alerts = []
    for feature in candidates[:NATIONAL_SELECTION_LIMIT]:
        alert = feature.properties
        alerts.append({
            "alert_id": alert.id, "source_url": feature.id, "event": alert.event,
            "severity": alert.severity, "urgency": alert.urgency, "certainty": alert.certainty,
            "affected_area": alert.areaDesc, "sent": alert.sent, "effective": alert.effective,
            "expires": alert.expires,
            "status": "LIVE" if fresh and feature in current else "STALE",
            "retrieved_at": retrieved_at, "source": "NWS",
        })
    if not actual and (partial or collection.features):
        status, error = "UNAVAILABLE", "INCOMPLETE_ACTUAL_ALERTS"
    else:
        status = ("LIVE" if current else "STALE") if alerts else "NO_ACTIVE_ALERTS"
        if not fresh:
            status = "STALE"
        error = None
    return {
        **context, "ok": status != "UNAVAILABLE", "status": status, "source": "NWS",
        "retrieved_at": retrieved_at, "checked_at": retrieved_at, "alerts": alerts,
        "error": error, "collection_limited": partial or len(candidates) > NATIONAL_SELECTION_LIMIT,
        "examined_count": len(collection.features), "fresh_until": fresh_until,
    }
