from __future__ import annotations

import json
import mimetypes
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException

from app.core import config
from app.db.database import connect
from app.db.queries import fetch_rows
from app.services.project_service import require_project
from app.services import task_service
from app.services.runtime_overrides import main_patch_attr_if_changed, main_projects_root
from app.workflows.artifact_manifest import build_artifact_manifest
from app.workflows.result_contract import load_result_summary
from app.workflows.task_logs import collect_remote_task_logs

try:
    from app.workflows.bold_group_analysis import run_group_analysis
except ImportError:

    def run_group_analysis(*args, **kwargs):
        raise RuntimeError("bold group analysis unavailable")

try:
    from app.workflows.bold_descriptive_review import run_descriptive_review
except ImportError:

    def run_descriptive_review(*args, **kwargs):
        raise RuntimeError("bold descriptive review unavailable")


_DEFAULT_PROJECTS_ROOT = Path(config.PROJECTS_ROOT)
_INITIAL_RUN_GROUP_ANALYSIS = run_group_analysis
_INITIAL_RUN_DESCRIPTIVE_REVIEW = run_descriptive_review


def _projects_root() -> Path:
    return main_projects_root(_DEFAULT_PROJECTS_ROOT, require_override=True)


def _redact_log_text(value: str) -> str:
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


def _safe_remote_logs(remote_logs: list[dict]) -> list[dict]:
    safe_logs = []
    for item in remote_logs:
        safe_logs.append(
            {
                "name": item.get("name"),
                "source_stage": item.get("source_stage"),
                "size_bytes": item.get("size_bytes"),
                "tail": _redact_log_text(str(item.get("tail") or "")),
            }
        )
    return safe_logs


def get_logs(task_id):
    task = task_service.get_task(task_id)
    path = Path(task["log_path"])
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    output_dir = _projects_root() / str(task["project_id"]) / "derivatives" / str(task_id) / "output"
    remote_logs = collect_remote_task_logs(output_dir)
    return {
        "task_id": task_id,
        "text": _redact_log_text(text),
        "remote_logs": _safe_remote_logs(remote_logs),
    }


_HOST_PATH_METADATA_KEYS = {
    "path",
    "preview_path",
    "storage_path",
    "log_path",
    "summary_path",
    "absolute_path",
    "host_path",
}


def _get_output_rows(task_id):
    result = []
    for row in fetch_rows("SELECT * FROM outputs WHERE task_id=? ORDER BY id", (task_id,)):
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json"))
        result.append(item)
    return result


def _task_output_dir(task) -> Path:
    return _task_project_root(task) / "derivatives" / str(task["id"]) / "output"


def _task_project_root(task) -> Path:
    log_path = Path(str(task.get("log_path") or ""))
    if log_path.parent.name == "logs":
        return log_path.parent.parent
    return _projects_root() / str(task["project_id"])


def _safe_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _safe_metadata(item)
            for key, item in value.items()
            if key not in _HOST_PATH_METADATA_KEYS
        }
    if isinstance(value, list):
        return [_safe_metadata(item) for item in value]
    if isinstance(value, str):
        return _redact_log_text(value)
    return value


def _is_safe_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    normalized = value.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    return (
        "\\" not in value
        and not normalized.startswith("/")
        and not (len(normalized) >= 2 and normalized[1] == ":" and normalized[0].isalpha())
        and ".." not in parts
    )


def _output_relative_path(output_dir: Path, output) -> str | None:
    metadata = output.get("metadata") or {}
    declared = metadata.get("relative_path")
    if _is_safe_relative_path(declared):
        return str(declared).replace("\\", "/")
    output_path = output.get("path")
    if not output_path:
        return None
    try:
        path = Path(str(output_path)).resolve()
        return path.relative_to(output_dir).as_posix()
    except (OSError, ValueError):
        return None


def get_outputs(task_id):
    task = task_service.get_task(task_id)
    output_dir = _task_output_dir(task).resolve()
    result = []
    for output in _get_output_rows(task_id):
        metadata = output.get("metadata") or {}
        relative_path = _output_relative_path(output_dir, output)
        public = {
            "id": output.get("id"),
            "task_id": output.get("task_id"),
            "output_type": output.get("output_type"),
            "created_at": output.get("created_at"),
            "metadata": _safe_metadata(metadata),
        }
        if relative_path:
            target = (output_dir / relative_path).resolve()
            public["relative_path"] = relative_path
            public["download_url"] = f"/tasks/{task_id}/artifacts/{quote(relative_path)}"
            public["content_type"] = (
                metadata.get("content_type")
                or ("application/gzip" if target.name.endswith(".nii.gz") else mimetypes.guess_type(target.name)[0])
                or "application/octet-stream"
            )
            if output_dir in [target, *target.parents] and target.exists() and target.is_file():
                public["size_bytes"] = target.stat().st_size
        result.append(public)
    return result


def _public_result_summary(task, payload):
    public = dict(payload)
    public["task_id"] = task["id"]
    public["project_id"] = task["project_id"]
    public.pop("summary_path", None)
    return public


def _load_raw_result_summary(task, task_outputs):
    task_id = task["id"]
    for output in task_outputs:
        metadata = output["metadata"]
        output_path = output.get("path") or ""
        if metadata.get("kind") == "result_summary" or output_path.endswith("_result_summary.json"):
            path = Path(output["path"])
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload.setdefault("summary_path", str(path))
                return payload
    for output in task_outputs:
        metadata = output["metadata"]
        output_path = output.get("path") or ""
        if metadata.get("kind") == "bold_metrics_summary" and output_path:
            path = Path(output["path"])
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
                return {
                    "contract_version": payload.get("contract_version", "legacy-bold-metrics"),
                    "task_id": task_id,
                    "workflow_type": task["workflow_type"],
                    "modality": "BOLD",
                    "spaces": payload.get("spaces", ["MNI152"]),
                    "feature_groups": ["legacy_bold_metrics"],
                    "outputs": {},
                    "provenance": {
                        "legacy_fallback": True,
                        "legacy_summary_path": str(path),
                        "note": "Legacy BOLD metrics summary returned because no unified result_summary was registered.",
                    },
                    "legacy_summary": payload,
                }
    output_dir = _task_output_dir(task)
    return load_result_summary(output_dir)


def get_result_summary(task_id):
    task = task_service.get_task(task_id)
    summary = _load_raw_result_summary(task, _get_output_rows(task_id))
    if summary is None:
        raise HTTPException(404, "Result summary not found")
    return _public_result_summary(task, summary)


def get_task_artifact_manifest(task_id):
    task = task_service.get_task(task_id)
    output_dir = _task_output_dir(task)
    output_rows = _get_output_rows(task_id)
    summary = _load_raw_result_summary(task, output_rows)
    return build_artifact_manifest(task, output_dir, summary, output_rows)


def resolve_task_artifact(task_id, relative_path):
    if "\\" in relative_path:
        raise HTTPException(400, "Artifact path is outside the task output directory")
    task = task_service.get_task(task_id)
    output_dir = _task_output_dir(task).resolve()
    target = (output_dir / relative_path).resolve()
    if output_dir not in [target, *target.parents]:
        raise HTTPException(400, "Artifact path is outside the task output directory")
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "Artifact not found")
    media_type = "application/gzip" if target.name.endswith(".nii.gz") else mimetypes.guess_type(target.name)[0]
    return {"path": target, "media_type": media_type}


def get_task_artifact(task_id, relative_path):
    return resolve_task_artifact(task_id, relative_path)


def bold_group_analysis(project_id, req):
    require_project(project_id)
    try:
        runner = main_patch_attr_if_changed("run_group_analysis", _INITIAL_RUN_GROUP_ANALYSIS, run_group_analysis)
        return runner(
            project_id=project_id,
            group_a_tasks=req.group_a_task_ids,
            group_b_tasks=req.group_b_task_ids,
            seed_query=req.seed_query,
            label_a=req.label_a,
            label_b=req.label_b,
        )
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc


def bold_descriptive_review(project_id, req):
    require_project(project_id)
    try:
        runner = main_patch_attr_if_changed("run_descriptive_review", _INITIAL_RUN_DESCRIPTIVE_REVIEW, run_descriptive_review)
        return runner(
            project_id=project_id,
            deepprep_task_ids=req.deepprep_task_ids,
            seed_preset=req.seed_preset,
        )
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
