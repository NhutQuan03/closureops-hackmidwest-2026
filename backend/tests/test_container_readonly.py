"""Container read transport must never extend local write or inference access."""

from dataclasses import replace
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from backend.app.api_security import LocalDemoSettings
from backend.app.main import create_app
from scripts.init_docker_demo import initialize_synthetic_fixture


@pytest.fixture
def settings(tmp_path):
    return LocalDemoSettings(environment="container_readonly", bind_host="0.0.0.0", database_path=tmp_path / "docker.sqlite3")


def test_private_container_reads_without_any_write_capability(settings):
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8001", client=("172.30.11.2", 12345)) as client:
        health = client.get("/api/health").json()
        assert health["status"] == "ok"
        assert health["local_demo_writes_enabled"] is health["ai_briefing_enabled"] is False
        assert len(client.get("/api/facilities").json()) == 1
        assert len(client.get("/api/demo/scenarios").json()) == 7
        assert client.get("/api/audit").json() == []
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            for path in ("/api/evaluations", f"/api/evaluations/eval_{'0' * 32}/decisions",
                         f"/api/evaluations/eval_{'0' * 32}/ai-briefing"):
                assert client.request(method, path, json={}).status_code == 403


@pytest.mark.parametrize("changes", [
    {"writes_enabled": True}, {"ai_briefing_enabled": True}, {"bind_host": "127.0.0.1"},
    {"container_network": "0.0.0.0/0"}, {"container_network": "172.30.0.0/16"},
    {"container_network": "203.0.113.0/24"}, {"container_network": "::/0"},
])
def test_container_mode_fails_closed_on_unsafe_settings(settings, changes):
    with pytest.raises(ValueError):
        create_app(replace(settings, **changes))


@pytest.mark.parametrize("peer,headers", [
    ("203.0.113.1", {}), ("172.30.12.2", {}), ("172.30.11.2", {"X-Forwarded-For": "127.0.0.1"}),
    ("172.30.11.2", {"Host": "evil.example"}),
])
def test_untrusted_peers_hosts_and_forwarding_headers_remain_rejected(settings, peer, headers):
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8001", client=(peer, 12345)) as client:
        assert client.get("/api/health", headers=headers).status_code == 403


def test_local_demo_does_not_accept_container_peers_or_non_loopback_bind(tmp_path):
    settings = LocalDemoSettings(writes_enabled=True, database_path=tmp_path / "local.sqlite3")
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8001", client=("172.30.11.2", 12345)) as client:
        assert client.get("/api/health").status_code == 403
        assert client.post("/api/evaluations", json={}).status_code == 403
    with pytest.raises(ValueError):
        create_app(replace(settings, bind_host="0.0.0.0"))


def test_explicit_isolated_fixture_preserves_records_and_never_runs_inference(tmp_path, monkeypatch):
    from backend.app import ai_briefing
    monkeypatch.setattr(ai_briefing, "run_agent", Mock(side_effect=AssertionError("No inference")))
    database = tmp_path / "isolated.sqlite3"
    ids = initialize_synthetic_fixture(database)
    assert ids["data_mode"] == "SIMULATED DEMO"
    assert ids["notification_status"] == "GENERATED_SIMULATED"
    before = database.read_bytes()
    with pytest.raises(ValueError, match="existing records are preserved"):
        initialize_synthetic_fixture(database)
    assert database.read_bytes() == before
