from __future__ import annotations

from typing import Any

from app.execution.celery_app import celery_app


@celery_app.task(name="image_agent.execution.execute_plan")
def execute_execution_plan_task(payload: dict[str, Any]) -> dict[str, Any]:
    from app.execution.worker import execute_plan_payload

    return execute_plan_payload(payload)
