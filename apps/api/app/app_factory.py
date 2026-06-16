from __future__ import annotations

import os
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.app_hooks import register_app_hooks
from app.routes import agent, auth, chat, projects, reports, results, series, system, tasks, uploads

DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def is_production_mode() -> bool:
    return os.environ.get("IMAGE_AGENT_ENV", "").strip().lower() in {"prod", "production"}


def _origin_host(origin: str) -> str:
    return (urlsplit(origin).hostname or "").lower()


def _origin_has_path_or_query(origin: str) -> bool:
    parsed = urlsplit(origin)
    return bool(parsed.path or parsed.query or parsed.fragment)


def _is_local_origin(origin: str) -> bool:
    return _origin_host(origin) in {"localhost", "127.0.0.1", "::1"}


def _is_public_origin(origin: str) -> bool:
    return bool(_origin_host(origin)) and not _is_local_origin(origin)


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


def production_cors_has_public_origin() -> bool:
    if not is_production_mode():
        return True
    return any(
        urlsplit(origin).scheme == "https" and _is_public_origin(origin)
        for origin in cors_origins()
    )


def production_cors_has_insecure_public_origin() -> bool:
    if not is_production_mode():
        return False
    return any(
        _is_public_origin(origin) and urlsplit(origin).scheme != "https"
        for origin in cors_origins()
    )


def create_app() -> FastAPI:
    app = FastAPI(title="Brain Image Agent API", version="0.2.0")
    app.add_middleware(CORSMiddleware, allow_origins=cors_origins(), allow_methods=["*"], allow_headers=["*"])

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
