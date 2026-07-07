from __future__ import annotations

import json
from typing import Any

from app.db.database import connect, now_iso
from app.execution.contracts import ApprovedExecutionPlan


def record_plan_approved(plan: ApprovedExecutionPlan) -> int:
    now = now_iso()
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO execution_runs("
            "task_id, project_id, series_id, workflow_type, runtime_workflow_type, status, approved_plan_json, created_at, updated_at"
            ") VALUES(?,?,?,?,?,?,?,?,?)",
            (
                plan.task_id,
                plan.project_id,
                plan.series_id,
                plan.workflow_type,
                plan.runtime_workflow_type,
                "approved",
                json.dumps(plan.to_task_payload(), sort_keys=True),
                now,
                now,
            ),
        )
        run_id = int(cursor.lastrowid)
        conn.execute(
            "INSERT INTO execution_events(run_id, task_id, event_type, status, metadata_json, created_at) VALUES(?,?,?,?,?,?)",
            (
                run_id,
                plan.task_id,
                "execution.plan_approved",
                "approved",
                json.dumps({"resource": plan.resource.value}, sort_keys=True),
                now,
            ),
        )
    return run_id


def record_execution_queued(plan: ApprovedExecutionPlan, *, handle: dict[str, Any]) -> None:
    now = now_iso()
    queue = str(handle.get("queue") or "")
    celery_task_id = str(handle.get("celery_task_id") or "")
    with connect() as conn:
        run = conn.execute("SELECT id FROM execution_runs WHERE task_id=?", (plan.task_id,)).fetchone()
        if run is None:
            run_id = record_plan_approved(plan)
        else:
            run_id = int(run["id"])
        cursor = conn.execute(
            "INSERT INTO execution_attempts(run_id, task_id, attempt_no, status, queue, celery_task_id, created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (run_id, plan.task_id, 1, "queued", queue, celery_task_id, now),
        )
        attempt_id = int(cursor.lastrowid)
        conn.execute(
            "UPDATE execution_runs SET status=?, queue=?, celery_task_id=?, updated_at=? WHERE id=?",
            ("queued", queue, celery_task_id, now, run_id),
        )
        conn.execute(
            "INSERT INTO execution_events(run_id, task_id, attempt_id, event_type, status, metadata_json, created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                run_id,
                plan.task_id,
                attempt_id,
                "execution.queued",
                "queued",
                json.dumps({"queue": queue, "executor": handle.get("executor")}, sort_keys=True),
                now,
            ),
        )
