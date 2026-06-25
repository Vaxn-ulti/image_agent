from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.db.queries import fetch_rows
from app.workflows.registry import list_workflows, workflow_public_metadata, workflow_public_metadata_for_record
from app.workflows.result_contract import load_result_summary


def build_rag_backend_context(project_id: int | None) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "tasks": fetch_rows(
            "SELECT id, workflow_type, runtime_workflow_type, status, progress, error_message FROM tasks WHERE project_id=? ORDER BY id DESC LIMIT 20",
            (project_id,),
        )
        if project_id
        else [],
        "outputs": fetch_rows(
            "SELECT outputs.task_id, outputs.output_type, outputs.path, outputs.metadata_json FROM outputs JOIN tasks ON tasks.id=outputs.task_id WHERE tasks.project_id=? ORDER BY outputs.id DESC LIMIT 20",
            (project_id,),
        )
        if project_id
        else [],
        "supported_workflows": [
            workflow_public_metadata(workflow)
            for workflow in list_workflows()
        ],
    }


def build_chat_backend_context(
    project_id: int | None,
    message: str,
    *,
    projects_root: Path,
    workflows: list[dict[str, Any]],
) -> dict[str, Any]:
    tasks = _task_context(project_id, message)
    task_ids = [task["id"] for task in tasks if task.get("status") != "not_found_in_project"]
    return {
        "project_id": project_id,
        "series": fetch_rows(
            "SELECT id, modality, sequence_label, supported_for_processing, status, confidence FROM imaging_series WHERE project_id=? ORDER BY id DESC LIMIT 20",
            (project_id,),
        )
        if project_id
        else [],
        "tasks": tasks,
        "outputs": _output_context(project_id, task_ids=task_ids),
        "result_summaries": _result_summary_context(tasks, projects_root=projects_root),
        "supported_workflows": workflows,
    }


def _requested_task_ids(message: str) -> list[int]:
    anchored = [
        int(match.group(1))
        for match in re.finditer(r"(?:#|浠诲姟|task\s*)(\d+)", message, flags=re.IGNORECASE)
    ]
    lowered = message.lower()
    if any(token in lowered for token in ("task", "tasks", "status", "progress", "state", "任务", "状态", "进度", "查看")):
        tail = message
        first_anchor = re.search(r"(?:#|任务|task\s*)\s*\d+", message, flags=re.IGNORECASE)
        if first_anchor:
            tail = message[first_anchor.start() :]
        nearby = [
            int(match)
            for match in re.findall(r"\d+", tail)
            if int(match) >= 20
        ]
        return list(dict.fromkeys([*anchored, *nearby]))
    return []


def _task_context(project_id: int | None, message: str) -> list[dict]:
    requested_ids = _requested_task_ids(message)
    if project_id and requested_ids:
        placeholders = ",".join("?" for _ in requested_ids)
        query = (
            "SELECT id, project_id, workflow_type, runtime_workflow_type, status, progress, error_message "
            f"FROM tasks WHERE project_id=? AND id IN ({placeholders}) ORDER BY id DESC"
        )
        explicit = fetch_rows(query, (project_id, *requested_ids))
        found_ids = {task["id"] for task in explicit}
        missing = [
            {
                "id": task_id,
                "workflow_type": "unknown",
                "runtime_workflow_type": None,
                "status": "not_found_in_project",
                "progress": 0,
                "error_message": None,
            }
            for task_id in requested_ids
            if task_id not in found_ids
        ]
        return sorted([*explicit, *missing], key=lambda task: int(task["id"]), reverse=True)
    if project_id:
        return fetch_rows(
            "SELECT id, project_id, workflow_type, runtime_workflow_type, status, progress, error_message FROM tasks WHERE project_id=? ORDER BY id DESC LIMIT 50",
            (project_id,),
        )
    if requested_ids:
        placeholders = ",".join("?" for _ in requested_ids)
        return fetch_rows(
            f"SELECT id, project_id, workflow_type, runtime_workflow_type, status, progress, error_message FROM tasks WHERE id IN ({placeholders}) ORDER BY id DESC",
            tuple(requested_ids),
        )
    return fetch_rows("SELECT id, project_id, workflow_type, runtime_workflow_type, status, progress, error_message FROM tasks ORDER BY id DESC LIMIT 10")


def _output_context(project_id: int | None, task_ids: list[int] | None = None) -> list[dict]:
    if task_ids:
        placeholders = ",".join("?" for _ in task_ids)
        return fetch_rows(
            "SELECT outputs.task_id, outputs.output_type, outputs.path, outputs.metadata_json "
            f"FROM outputs JOIN tasks ON tasks.id=outputs.task_id WHERE outputs.task_id IN ({placeholders}) ORDER BY outputs.id DESC",
            tuple(task_ids),
        )
    if project_id:
        return fetch_rows(
            "SELECT outputs.task_id, outputs.output_type, outputs.path, outputs.metadata_json FROM outputs JOIN tasks ON tasks.id=outputs.task_id WHERE tasks.project_id=? ORDER BY outputs.id DESC LIMIT 100",
            (project_id,),
        )
    return []


def _result_summary_context(tasks: list[dict], *, projects_root: Path) -> list[dict]:
    summaries = []
    for task in tasks:
        if task.get("status") == "not_found_in_project":
            continue
        output_dir = projects_root / str(task["project_id"]) / "derivatives" / str(task["id"]) / "output"
        try:
            summary = load_result_summary(output_dir)
        except FileNotFoundError:
            continue
        if summary:
            public_summary = dict(summary)
            public_summary.pop("summary_path", None)
            public_summary.setdefault(
                "workflow_metadata",
                workflow_public_metadata_for_record(
                    public_summary.get("workflow_type") or task.get("workflow_type"),
                    task.get("runtime_workflow_type"),
                ),
            )
            summaries.append(public_summary)
    return summaries
