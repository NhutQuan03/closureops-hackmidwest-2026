"""Deterministic national NWS reads; synthetic test fixtures are never live fallback."""
from datetime import datetime, timezone
from email.utils import format_datetime
import json
from unittest.mock import Mock

from fastapi.testclient import TestClient
import httpx
import pytest

from backend.app.api_security import LocalDemoSettings
from backend.app.main import create_app
from backend.app.national_nws import NationalAlertsResponse
from backend.app.services import nws

NOW = datetime(2026, 10, 11, 6, 0, tzinfo=timezone.utc)


def collection(count=1):
    return {"type": "FeatureCollection", "features": [{
        "type": "Feature", "id": f"https://api.weather.gov/alerts/urn:test:{number}",
        "properties": {
            "id": f"urn:test:{number}", "event": "Synthetic offline test warning",
            "status": "Actual", "messageType": "Alert", "severity": "Severe",
            "urgency": "Immediate", "certainty": "Observed", "areaDesc": "Synthetic test area",
            "sent": "2026-10-11T05:45:00Z", "effective": "2026-10-11T05:45:00Z",
            "expires": "2026-10-11T07:00:00Z",
        },
    } for number in range(count)]}


@pytest.fixture
def transport(monkeypatch):
    original_client = httpx.Client
    requests = []

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(nws, "datetime", Clock)
    monkeypatch.setattr(nws.time, "sleep", Mock())
    monkeypatch.delenv("NWS_USER_AGENT", raising=False)

    def install(handler):
        def capture(request):
            requests.append(request)
            return handler(request)

        monkeypatch.setattr(nws.httpx, "Client", lambda **kwargs: original_client(
            transport=httpx.MockTransport(capture), **kwargs))
        return requests
    return install


def success(data, **headers):
    return httpx.Response(200, json=data, headers={"Date": format_datetime(NOW), **headers})


def test_nationwide_selection_uses_actual_filter_and_official_feature_urls(transport):
    requests = transport(lambda request: success(collection(8)))
    result = NationalAlertsResponse.model_validate(nws.fetch_national_nws_alerts())
    assert result.status == "LIVE"
    assert len(result.alerts) == 5
    assert result.examined_count == 8 and result.collection_limited
    assert result.facility_applicability == "NOT_ASSESSED"
    assert str(requests[0].url) == "https://api.weather.gov/alerts/active?status=actual"
    assert requests[0].method == "GET"
    assert "point" not in requests[0].url.params
    assert result.alerts[0].source_url.startswith("https://api.weather.gov/alerts/urn:test:")
    assert result.alerts[0].retrieved_at == NOW
    assert "facility_id" not in result.model_dump()
    assert "recommendation" not in result.model_dump()


def test_empty_requires_complete_fresh_collection(transport):
    transport(lambda request: success(collection(0)))
    assert nws.fetch_national_nws_alerts()["status"] == "NO_ACTIVE_ALERTS"


@pytest.mark.parametrize("expired,missing_date,age", [(True, False, 0), (False, True, 0), (False, False, 301)])
def test_expiry_and_unknown_or_old_provider_freshness_are_stale(transport, expired, missing_date, age):
    data = collection()
    if expired:
        data["features"][0]["properties"]["expires"] = "2026-10-11T05:00:00Z"
    response = httpx.Response(200, json=data) if missing_date else success(data, Age=str(age))
    transport(lambda request: response)
    result = nws.fetch_national_nws_alerts()
    assert result["status"] == "STALE"
    assert result["alerts"][0]["status"] == "STALE"
    assert result["retrieved_at"]


def test_optional_fields_are_unavailable_not_invented(transport):
    data = collection()
    for key in ("severity", "urgency", "certainty", "areaDesc", "effective", "sent", "expires"):
        data["features"][0]["properties"].pop(key)
    transport(lambda request: success(data))
    result = nws.fetch_national_nws_alerts()
    assert result["status"] == "STALE"
    assert result["alerts"][0]["sent"] is None
    assert result["alerts"][0]["severity"] is None


def test_pagination_is_limited_never_followed_or_treated_as_empty(transport):
    data = collection()
    data["pagination"] = {"next": "https://untrusted.example/next"}
    requests = transport(lambda request: success(data))
    result = nws.fetch_national_nws_alerts()
    assert result["collection_limited"] is True
    assert len(requests) == 1
    data["features"] = []
    assert nws.fetch_national_nws_alerts()["status"] == "UNAVAILABLE"


def test_test_and_cancelled_messages_cannot_be_live(transport):
    data = collection(3)
    data["features"][0]["properties"]["status"] = "Test"
    data["features"][1]["properties"]["messageType"] = "Cancel"
    transport(lambda request: success(data))
    assert len(nws.fetch_national_nws_alerts()["alerts"]) == 1


@pytest.mark.parametrize("mutate", [
    lambda data: data.pop("features"),
    lambda data: data["features"][0].update(id="https://evil.example/alerts/1"),
    lambda data: data["features"][0]["properties"].update(sent="invalid"),
    lambda data: data["features"][0]["properties"].update(severity="Invented"),
    lambda data: data.update(features=data["features"] * (nws.NATIONAL_MAX_ALERTS + 1)),
])
def test_malformed_responses_never_become_live_or_empty(transport, mutate):
    data = collection()
    mutate(data)
    transport(lambda request: success(data))
    result = nws.fetch_national_nws_alerts()
    assert result["status"] == "UNAVAILABLE"
    assert result["error"] == "INVALID_RESPONSE"
    assert result["alerts"] == []


@pytest.mark.parametrize("failure", ["timeout", "http", "html", "size", "redirect"])
def test_bounded_failures_are_sanitized(transport, failure):
    def response(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("PRIVATE", request=request)
        if failure == "http":
            return httpx.Response(503, text="PRIVATE")
        if failure == "html":
            return httpx.Response(200, text="PRIVATE", headers={"Content-Type": "text/html"})
        if failure == "size":
            return httpx.Response(200, content=b" " * (nws.NATIONAL_MAX_BYTES + 1), headers={"Content-Type": "application/json"})
        return httpx.Response(301, headers={"Location": "https://evil.example/alerts"})
    requests = transport(response)
    result = nws.fetch_national_nws_alerts()
    assert result["status"] == "UNAVAILABLE"
    assert len(requests) <= nws.MAX_ATTEMPTS
    assert "PRIVATE" not in json.dumps(result)


def test_only_same_host_actual_active_redirect_allowed(transport):
    responses = iter([httpx.Response(301, headers={"Location": "/alerts?active=true&status=actual"}), success(collection())])
    requests = transport(lambda request: next(responses))
    assert nws.fetch_national_nws_alerts()["status"] == "LIVE"
    assert len(requests) == 2


def test_read_route_with_writes_disabled_does_not_touch_audit(transport, tmp_path):
    transport(lambda request: success(collection()))
    database = tmp_path / "untouched.sqlite3"
    with TestClient(create_app(LocalDemoSettings(database_path=database)),
                    base_url="http://127.0.0.1:8001", client=("127.0.0.1", 12345)) as client:
        response = client.get("/api/nws/alerts/active")
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        assert response.json()["status"] == "LIVE"
        assert response.json()["alerts"][0]["sent"] == "2026-10-11T05:45:00Z"
        assert client.post("/api/nws/alerts/active", json={}).status_code == 403
        assert not database.exists()
