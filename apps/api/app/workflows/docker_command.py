from __future__ import annotations

import os
import shlex

DOCKER_COMMAND_ENV = "IMAGE_AGENT_DOCKER_COMMAND"
SUDO_PASSWORD_ENV = "IMAGE_AGENT_SUDO_PASSWORD"


def docker_command_prefix(*, default: list[str] | None = None) -> list[str]:
    configured = os.environ.get(DOCKER_COMMAND_ENV, "").strip()
    if configured:
        parts = shlex.split(configured)
        if not parts or parts[-1] != "docker":
            raise RuntimeError(f"{DOCKER_COMMAND_ENV} must end with docker")
        return parts
    return list(default or ["docker"])


def docker_stdin_for_prefix(prefix: list[str], *, purpose: str) -> str | None:
    if "-S" not in prefix:
        return None
    password = os.environ.get(SUDO_PASSWORD_ENV)
    if not password:
        raise RuntimeError(f"{SUDO_PASSWORD_ENV} is required for {purpose}")
    return password + "\n"


def docker_uses_password(prefix: list[str]) -> bool:
    return "-S" in prefix
