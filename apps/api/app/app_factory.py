from __future__ import annotations

import os

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


def cors_origins() -> list[str]:
    raw = os.environ.get("IMAGE_AGENT_CORS_ORIGINS", "")
    if not raw.strip():
        if is_production_mode():
            raise RuntimeError("IMAGE_AGENT_CORS_ORIGINS must be set explicitly when IMAGE_AGENT_ENV=production")
        return list(DEFAULT_CORS_ORIGINS)
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if is_production_mode() and "*" in origins:
        raise RuntimeError("CORS wildcard origin is not allowed when IMAGE_AGENT_ENV=production")
    return origins


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
