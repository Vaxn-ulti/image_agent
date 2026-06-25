import re
from typing import Any

from fastapi import APIRouter

from app.agent.tools import observe_repair_task
from app.db.queries import fetch_rows
from app.services import result_service, task_service

router = APIRouter()


_SENSITIVE_KEYS = {
    "log_path",
    "path",
    "preview_path",
    "storage_path",
    "summary_path",
    "absolute_path",
    "host_path",
}


def _redact_observe_repair_text(value: str) -> str:
    text = str(value)
    text = re.sub(
        r"(?i)\b([A-Z0-9_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|LICENSE)[A-Z0-9_]*)\s*=\s*[^\s\"']+",
        r"\1=[redacted-secret]",
        text,
    )
    text = re.sub(r"sk-[A-Za-z0-9._-]+", "[redacted-secret]", text)
    text = re.sub(r"[A-Za-z]:[\\/][^\s\"']+", "[redacted-host-path]", text)
    text = re.sub(r"/(?:home|Users|mnt|data|tmp|var)/[^\s\"']+", "[redacted-host-path]", text)
    text = re.sub(r"(?i)\bpatient[-_\s]*[A-Za-z0-9_.-]+", "patient-[redacted]", text)
    return text


def _safe_observe_repair_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _safe_observe_repair_payload(item)
            for key, item in value.items()
            if key not in _SENSITIVE_KEYS
        }
    if isinstance(value, list):
        return [_safe_observe_repair_payload(item) for item in value]
    if isinstance(value, str):
        return _redact_observe_repair_text(value)
    return value


@router.get("/projects/{project_id}/tasks")
def list_project_tasks(project_id: int):
    return task_service.list_project_tasks(project_id)


@router.get("/tasks/{task_id}")
def get_task(task_id: int):
    return task_service.get_public_task(task_id)


@router.get("/tasks/{task_id}/logs")
def get_logs(task_id: int):
    return result_service.get_logs(task_id)


@router.get("/tasks/{task_id}/events")
def get_task_events(task_id: int):
    return result_service.get_task_events(task_id)


@router.get("/tasks/{task_id}/outputs")
def get_outputs(task_id: int):
    return result_service.get_outputs(task_id)


@router.get("/tasks/{task_id}/observe-repair")
def observe_repair(task_id: int):
    payload = observe_repair_task(task_id, rows_fn=fetch_rows, projects_root=result_service._projects_root())
    return _safe_observe_repair_payload(payload)
