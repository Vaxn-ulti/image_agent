import sys

from fastapi import FastAPI, Request
from fastapi.exception_handlers import (
    request_validation_exception_handler as fastapi_request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agent.contracts import agent_api_error_detail
from app.db.database import init_db
from app.main_compat import install_main_compat_exports
from app.routes import agent, auth, chat, projects, reports, results, series, system, tasks, uploads

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


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/agent/runs"):
        return JSONResponse(
            status_code=422,
            content={
                "detail": agent_api_error_detail(
                    "request_contract_violation",
                    "Request does not match the Agent API contract.",
                )
            },
        )
    return await fastapi_request_validation_exception_handler(request, exc)


# Compatibility exports for existing tests and scripts that monkeypatch app.main.
install_main_compat_exports(sys.modules[__name__])
