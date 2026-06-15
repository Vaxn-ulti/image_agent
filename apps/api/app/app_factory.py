from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.app_hooks import register_app_hooks
from app.routes import agent, auth, chat, projects, reports, results, series, system, tasks, uploads


def create_app() -> FastAPI:
    app = FastAPI(title="Brain Image Agent API", version="0.2.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

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
