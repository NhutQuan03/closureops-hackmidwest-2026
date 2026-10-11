from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))


def test_health_endpoint() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "closureops-api",
        "data_mode": "synthetic_demo",
        "local_demo_writes_enabled": False,
        "ai_briefing_enabled": False,
    }


def test_list_facilities_endpoint() -> None:
    response = client.get("/api/facilities")

    assert response.status_code == 200
    facilities = response.json()
    assert len(facilities) == 1
    assert facilities[0]["id"] == "jefferson-research"
    assert facilities[0]["name"] == "Jefferson Research Facility"
    assert facilities[0]["data_mode"] == "synthetic_demo"


def test_get_facility_endpoint() -> None:
    response = client.get("/api/facilities/jefferson-research-facility")

    assert response.status_code == 200
    facility = response.json()
    assert facility["city"] == "Columbia"
    assert facility["state"] == "MO"
    assert facility["operating_status"] == "open"
    assert facility["id"] == "jefferson-research"
    assert response.headers["Deprecation"] == "true"


def test_get_unknown_facility_endpoint() -> None:
    response = client.get("/api/facilities/not-real")

    assert response.status_code == 404
