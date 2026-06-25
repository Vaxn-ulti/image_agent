from __future__ import annotations

import json
import subprocess
from typing import Any, Callable


Runner = Callable[[list[str]], tuple[int, str, str]]


def inspect_container_primitives(
    primitive_chain: list[dict[str, Any]],
    *,
    runner: Runner | None = None,
) -> list[dict[str, Any]]:
    """Inspect container image metadata through backend-owned runtime tools."""

    inspections = []
    for primitive in primitive_chain:
        if primitive.get("kind") != "container":
            continue
        inspections.append(inspect_container_primitive(primitive, runner=runner))
    return inspections


def inspect_container_primitive(
    primitive: dict[str, Any],
    *,
    runner: Runner | None = None,
) -> dict[str, Any]:
    runtime = str(primitive.get("runtime") or "docker")
    image = str(primitive.get("image") or "")
    if runtime in {"singularity", "apptainer"}:
        command = [runtime, "inspect", "--json", image]
    else:
        command = [runtime, "image", "inspect", image]
    code, stdout, stderr = (runner or _run_command)(command)
    result: dict[str, Any] = {
        "step_order": primitive.get("order"),
        "stage": (primitive.get("contract") or {}).get("stage"),
        "runtime": runtime,
        "image": image,
        "command": _redacted_command(command),
        "exit_code": code,
        "status": "passed" if code == 0 else "failed",
        "metadata": {},
        "errors": [],
        "production_enabled": False,
        "production_task_created": False,
    }
    if code != 0:
        result["errors"].append(_redact_secret_text(stderr or stdout or "container inspection failed"))
        return result
    try:
        payload = json.loads(stdout or "null")
    except json.JSONDecodeError as exc:
        result["status"] = "failed"
        result["errors"].append(f"container inspection returned invalid JSON: {exc}")
        return result
    result["metadata"] = _normalize_inspection_metadata(payload)
    return result


def summarize_container_inspections(inspections: list[dict[str, Any]]) -> dict[str, Any]:
    passed = [item for item in inspections if item.get("status") == "passed"]
    failed = [item for item in inspections if item.get("status") != "passed"]
    return {
        "status": "passed" if inspections and not failed else "failed" if failed else "not_required",
        "container_count": len(inspections),
        "passed_count": len(passed),
        "failed_count": len(failed),
        "checks": [
            {"name": "container_image_inspected", "status": "pass" if item.get("status") == "passed" else "fail"}
            for item in inspections
        ],
        "inspections": inspections,
        "production_enabled": False,
        "production_task_created": False,
    }


def _run_command(command: list[str]) -> tuple[int, str, str]:
    completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
    return completed.returncode, completed.stdout, completed.stderr


def _normalize_inspection_metadata(payload: Any) -> dict[str, Any]:
    item = payload[0] if isinstance(payload, list) and payload else payload
    if not isinstance(item, dict):
        return {"raw_type": type(payload).__name__}
    config = item.get("Config") if isinstance(item.get("Config"), dict) else {}
    env = config.get("Env") if isinstance(config.get("Env"), list) else []
    labels = config.get("Labels") if isinstance(config.get("Labels"), dict) else {}
    return {
        "image_id": item.get("Id") or item.get("id") or item.get("image_id"),
        "repo_digests": item.get("RepoDigests") or item.get("repo_digests") or [],
        "created": item.get("Created") or item.get("created"),
        "entrypoint": config.get("Entrypoint") or config.get("entrypoint") or [],
        "cmd": config.get("Cmd") or config.get("cmd") or [],
        "env_keys": sorted(_env_key(value) for value in env if _env_key(value)),
        "labels": {str(key): _redact_secret_text(str(value)) for key, value in labels.items()},
        "working_dir": config.get("WorkingDir") or config.get("working_dir") or "",
        "user": config.get("User") or config.get("user") or "",
    }


def _env_key(value: str) -> str:
    return value.split("=", 1)[0] if "=" in value else value


def _redacted_command(command: list[str]) -> list[str]:
    return [_redact_secret_text(part) for part in command]


def _redact_secret_text(text: str) -> str:
    lowered = text.lower()
    if any(marker in lowered for marker in ["password", "passwd", "secret", "token", "api_key", "apikey"]):
        return "<redacted>"
    return text
