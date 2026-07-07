from __future__ import annotations

from typing import Any


def execute_plan_payload(payload: dict[str, Any]) -> dict[str, Any]:
    task_id = int(payload["task_id"])
    runtime_workflow_type = str(payload.get("runtime_workflow_type") or "")
    qsiprep_task_id = payload.get("qsiprep_task_id")

    if runtime_workflow_type == "t1_deepprep_mock":
        from app.workflows.deepprep import run_mock_deepprep

        run_mock_deepprep(task_id)
    else:
        from app.workflows.pipeline import run_pipeline_task

        run_pipeline_task(task_id, qsiprep_task_id)
    return {"status": "completed", "task_id": task_id}
