from __future__ import annotations

import os
import ipaddress
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.app_hooks import register_app_hooks
from app.routes import agent, auth, chat, projects, reports, results, series, system, tasks, uploads
from app.security import bearer_auth_middleware

DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def is_production_mode() -> bool:
    return os.environ.get("IMAGE_AGENT_ENV", "").strip().lower() in {"prod", "production"}


def deployment_scope() -> str:
    scope = os.environ.get("IMAGE_AGENT_DEPLOYMENT_SCOPE", "public_internet").strip().lower()
    return scope if scope in {"public_internet", "private_network"} else "public_internet"


def _origin_host(origin: str) -> str:
    return (urlsplit(origin).hostname or "").lower()


def _origin_has_path_or_query(origin: str) -> bool:
    parsed = urlsplit(origin)
    return bool(parsed.path or parsed.query or parsed.fragment)


def _is_local_origin(origin: str) -> bool:
    return _origin_host(origin) in {"localhost", "127.0.0.1", "::1"}


def _is_public_deployment_host(host: str) -> bool:
    normalized = (host or "").strip().lower().rstrip(".")
    if normalized in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return False
    try:
        return ipaddress.ip_address(normalized).is_global
    except ValueError:
        return "." in normalized and not normalized.endswith(".local")


def _is_public_origin(origin: str) -> bool:
    return _is_public_deployment_host(_origin_host(origin))


def _is_private_network_host(host: str) -> bool:
    normalized = (host or "").strip().lower().rstrip(".")
    if normalized in {"localhost", "127.0.0.1", "::1"}:
        return True
    if normalized == "0.0.0.0":
        return False
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return normalized.endswith(".local")
    return not address.is_global and not address.is_unspecified


def _is_private_network_origin(origin: str) -> bool:
    parsed = urlsplit(origin)
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and _is_private_network_host(parsed.hostname)
        and not _origin_has_path_or_query(origin)
    )


def cors_origins() -> list[str]:
    raw = os.environ.get("IMAGE_AGENT_CORS_ORIGINS", "")
    if not raw.strip():
        if is_production_mode():
            raise RuntimeError("IMAGE_AGENT_CORS_ORIGINS must be set explicitly when IMAGE_AGENT_ENV=production")
        return list(DEFAULT_CORS_ORIGINS)
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if is_production_mode():
        if "*" in origins:
            raise RuntimeError("CORS wildcard origin is not allowed when IMAGE_AGENT_ENV=production")
        if any(_origin_has_path_or_query(origin) for origin in origins):
            raise RuntimeError("Production CORS origins must not include paths, query strings, fragments, or trailing slashes")
    return origins


def production_cors_has_deployment_origin() -> bool:
    if not is_production_mode():
        return True
    if deployment_scope() == "private_network":
        return any(_is_private_network_origin(origin) for origin in cors_origins())
    return any(
        urlsplit(origin).scheme == "https" and _is_public_origin(origin)
        for origin in cors_origins()
    )


def production_cors_has_insecure_deployment_origin() -> bool:
    if not is_production_mode():
        return False
    if deployment_scope() == "private_network":
        return False
    return any(
        _is_public_origin(origin) and urlsplit(origin).scheme != "https"
        for origin in cors_origins()
    )


def create_app() -> FastAPI:
    app = FastAPI(title="Brain Image Agent API", version="0.2.0")
    app.add_middleware(CORSMiddleware, allow_origins=cors_origins(), allow_methods=["*"], allow_headers=["*"])
    app.middleware("http")(bearer_auth_middleware)

    for router in (
        system.router,
        agent.router,
        auth.router,
        projects.router,
        uploads.router,
        series.router,
        tasks.router,
        results.router,
        reports.router,
        chat.router,
    ):
        app.include_router(router)

    register_app_hooks(app)
    return app
