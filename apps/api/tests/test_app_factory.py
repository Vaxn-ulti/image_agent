import pytest
from fastapi.testclient import TestClient

from app.app_factory import create_app


def test_cors_origins_are_configured_from_environment(monkeypatch):
    monkeypatch.setenv("IMAGE_AGENT_CORS_ORIGINS", "https://console.example.com,http://localhost:5173")
    client = TestClient(create_app())

    allowed = client.options(
        "/health",
        headers={
            "Origin": "https://console.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    denied = client.options(
        "/health",
        headers={
            "Origin": "https://untrusted.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.headers["access-control-allow-origin"] == "https://console.example.com"
    assert "access-control-allow-origin" not in denied.headers


def test_auth_rejection_keeps_cors_headers_for_console_origin(monkeypatch):
    monkeypatch.setenv("IMAGE_AGENT_REQUIRE_AUTH", "true")
    monkeypatch.setenv("IMAGE_AGENT_CONSOLE_USERNAME", "fjx")
    monkeypatch.setenv("IMAGE_AGENT_CONSOLE_PASSWORD", "fjx123")
    monkeypatch.setenv("IMAGE_AGENT_CORS_ORIGINS", "http://10.2.32.14:5180")
    client = TestClient(create_app())

    result = client.get(
        "/projects",
        headers={
            "Authorization": "Bearer stale-token",
            "Origin": "http://10.2.32.14:5180",
        },
    )

    assert result.status_code == 401
    assert result.headers["access-control-allow-origin"] == "http://10.2.32.14:5180"


def test_production_cors_requires_explicit_origins(monkeypatch):
    monkeypatch.setenv("IMAGE_AGENT_ENV", "production")
    monkeypatch.delenv("IMAGE_AGENT_CORS_ORIGINS", raising=False)

    with pytest.raises(RuntimeError, match="IMAGE_AGENT_CORS_ORIGINS"):
        create_app()


def test_production_cors_rejects_wildcard_origin(monkeypatch):
    monkeypatch.setenv("IMAGE_AGENT_ENV", "production")
    monkeypatch.setenv("IMAGE_AGENT_CORS_ORIGINS", "https://console.example.com,*")

    with pytest.raises(RuntimeError, match="wildcard"):
        create_app()


def test_production_cors_rejects_origins_with_paths(monkeypatch):
    monkeypatch.setenv("IMAGE_AGENT_ENV", "production")
    monkeypatch.setenv("IMAGE_AGENT_CORS_ORIGINS", "https://console.example.com/")

    with pytest.raises(RuntimeError, match="must not include paths"):
        create_app()


def test_deployment_readiness_blocks_localhost_only_production_cors(monkeypatch):
    monkeypatch.setenv("IMAGE_AGENT_ENV", "production")
    monkeypatch.setenv("IMAGE_AGENT_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    monkeypatch.setenv("BACKEND_RUNTIME_MODE", "remote")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    result = TestClient(create_app()).get("/deployment")

    assert result.status_code == 200
    readiness = result.json()["production_readiness"]
    assert readiness["required"] is True
    assert readiness["ready"] is False
    assert readiness["status"] == "blocked"
    assert "Production CORS origins must include a non-localhost console origin." in readiness["blocking_reasons"]


def test_deployment_readiness_blocks_insecure_public_production_cors(monkeypatch):
    monkeypatch.setenv("IMAGE_AGENT_ENV", "production")
    monkeypatch.setenv("IMAGE_AGENT_CORS_ORIGINS", "http://console.example.com")
    monkeypatch.setenv("IMAGE_AGENT_PUBLIC_BASE_URL", "https://api.example.com")
    monkeypatch.setenv("BACKEND_RUNTIME_MODE", "remote")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    result = TestClient(create_app()).get("/deployment")

    assert result.status_code == 200
    readiness = result.json()["production_readiness"]
    assert readiness["required"] is True
    assert readiness["ready"] is False
    assert readiness["status"] == "blocked"
    assert "Production CORS origins must use HTTPS for public console origins." in readiness["blocking_reasons"]
