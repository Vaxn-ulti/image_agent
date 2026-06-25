from __future__ import annotations

import hashlib
import os
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse

AUTH_EXEMPT_PATHS = {"/auth/login", "/health"}


def auth_required() -> bool:
    return os.environ.get("IMAGE_AGENT_REQUIRE_AUTH", "").strip().lower() in {"1", "true", "yes", "on"}


def console_username() -> str:
    return os.environ.get("IMAGE_AGENT_CONSOLE_USERNAME", "demo").strip() or "demo"


def _console_password() -> str:
    return os.environ.get("IMAGE_AGENT_CONSOLE_PASSWORD", "demo")


def auth_token() -> str:
    configured = os.environ.get("IMAGE_AGENT_CONSOLE_TOKEN", "").strip()
    if configured:
        return configured
    seed = f"image-agent-console:{console_username()}:{_console_password()}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()


def validate_console_credentials(username: str, password: str) -> bool:
    if not auth_required():
        return True
    return secrets.compare_digest(username, console_username()) and secrets.compare_digest(password, _console_password())


async def bearer_auth_middleware(request: Request, call_next):
    if not auth_required() or request.method == "OPTIONS" or request.url.path in AUTH_EXEMPT_PATHS:
        return await call_next(request)
    if _is_export_download_request(request):
        return await call_next(request)

    authorization = request.headers.get("authorization", "")
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(value.strip(), auth_token()):
        return JSONResponse(
            {"detail": "Authentication required"},
            headers={"WWW-Authenticate": "Bearer"},
            status_code=401,
        )
    return await call_next(request)


def _is_export_download_request(request: Request) -> bool:
    marker = "/tasks/"
    suffix = "/export-bundle-download"
    path = request.url.path
    if marker not in path or not path.endswith(suffix):
        return False
    task_part = path.removeprefix(marker).removesuffix(suffix)
    return task_part.isdigit()
