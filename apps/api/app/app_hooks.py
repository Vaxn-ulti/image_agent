from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exception_handlers import (
    request_validation_exception_handler as fastapi_request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.agent.contracts import agent_api_error_detail
from app.db.database import init_db


def register_app_hooks(app: FastAPI) -> None:
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
