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
