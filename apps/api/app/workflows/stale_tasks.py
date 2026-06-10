"""Auditable reconciliation for stale queued/running workflow tasks.

This module is intentionally conservative: dry-run is the default caller mode,
and apply mode must be given an explicit set of currently running Image Agent
container task ids. That keeps database state changes separate from ambiguous
Docker access failures.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from app.db.database import connect, now_iso


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _task_reference_time(task: dict) -> datetime | None:
    return _parse_iso(task.get("started_at")) or _parse_iso(task.get("created_at"))


def _active_tasks() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, project_id, series_id, workflow_type, status, progress,
                   log_path, error_message, created_at, started_at, finished_at
            FROM tasks
            WHERE status IN ('queued', 'running')
            ORDER BY id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def _append_audit_log(log_path: str | None, message: str) -> None:
    if not log_path:
        return
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(message.rstrip() + "\n")


def _candidate_summary(task: dict, *, now: datetime, max_age_hours: float) -> dict:
    reference_time = _task_reference_time(task)
    if reference_time is None:
        age_hours = None
        is_stale = False
    else:
        age_hours = max(0.0, (now - reference_time).total_seconds() / 3600)
        is_stale = age_hours >= max_age_hours
    return {
        "id": task["id"],
        "project_id": task["project_id"],
        "series_id": task["series_id"],
        "workflow_type": task["workflow_type"],
        "status": task["status"],
        "progress": task["progress"],
        "started_at": task.get("started_at"),
        "created_at": task.get("created_at"),
        "age_hours": age_hours,
        "is_stale": is_stale,
    }


def reconcile_stale_active_tasks(
    *,
    max_age_hours: float = 24,
    apply: bool = False,
    now: datetime | None = None,
    running_container_task_ids: Iterable[int] | None = None,
    reason: str = "operator confirmed no matching running Image Agent container",
) -> dict:
    """Report or fail stale active task rows.

    ``running_container_task_ids`` is mandatory for apply mode. Callers should
    derive it from a trusted Docker/Podman label check before mutating task rows.
    """

    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    running_ids = None if running_container_task_ids is None else {int(task_id) for task_id in running_container_task_ids}
    if apply and running_ids is None:
        raise ValueError("running_container_task_ids is required when apply=True")

    active = _active_tasks()
    summaries = [_candidate_summary(task, now=now, max_age_hours=max_age_hours) for task in active]
    by_id = {task["id"]: task for task in active}
    stale = [summary for summary in summaries if summary["is_stale"]]
    blocked = [summary for summary in stale if running_ids is not None and summary["id"] in running_ids]
    candidates = [summary for summary in stale if running_ids is None or summary["id"] not in running_ids]

    updated_task_ids: list[int] = []
    if apply:
        finished_at = now.isoformat()
        error_message = f"stale task reconciliation: {reason}"
        with connect() as conn:
            for summary in candidates:
                task_id = int(summary["id"])
                conn.execute(
                    "UPDATE tasks SET status='failed', error_message=?, finished_at=? WHERE id=?",
                    (error_message, finished_at, task_id),
                )
                updated_task_ids.append(task_id)
        for task_id in updated_task_ids:
            task = by_id[task_id]
            _append_audit_log(
                task.get("log_path"),
                f"{finished_at} stale task reconciliation: marked failed after {summary_age(task, now):.2f}h active; {reason}",
            )

    return {
        "mode": "apply" if apply else "dry_run",
        "max_age_hours": max_age_hours,
        "generated_at": now.isoformat(),
        "active_task_count": len(active),
        "active_tasks": summaries,
        "stale_candidates": candidates,
        "blocked_task_ids": [int(task["id"]) for task in blocked],
        "updated_task_ids": updated_task_ids,
    }


def summary_age(task: dict, now: datetime) -> float:
    reference_time = _task_reference_time(task)
    if reference_time is None:
        return 0.0
    return max(0.0, (now - reference_time).total_seconds() / 3600)


def running_container_task_ids_from_docker() -> set[int]:
    """Return running Image Agent task ids from labelled Docker containers."""

    from app.workflows.recovery import APP_LABEL_FILTER, _docker

    task_ids: set[int] = set()
    proc = _docker(
        [
            "ps",
            "--filter",
            f"label={APP_LABEL_FILTER}",
            "--filter",
            "status=running",
            "--format",
            "{{.Label \"image_agent.task_id\"}}",
        ]
    )
    if proc.returncode != 0:
        raise RuntimeError("Docker label check failed; refusing stale task reconciliation")
    for raw_task_id in proc.stdout.splitlines():
        raw_task_id = raw_task_id.strip()
        if not raw_task_id:
            continue
        try:
            task_ids.add(int(raw_task_id))
        except (TypeError, ValueError):
            continue
    return task_ids
