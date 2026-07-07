from __future__ import annotations

from typing import Any, Protocol
from uuid import uuid4

from app.execution.contracts import ApprovedExecutionPlan
from app.execution.queueing import queue_for_execution_plan


class CeleryTaskLike(Protocol):
    def apply_async(self, *, args: list[Any], queue: str) -> Any:
        ...


class CeleryTaskExecutor:
    def __init__(self, *, celery_task: CeleryTaskLike | None = None) -> None:
        self._celery_task = celery_task

    @property
    def celery_task(self) -> CeleryTaskLike:
        if self._celery_task is not None:
            return self._celery_task
        from app.execution.celery_tasks import execute_execution_plan_task

        return execute_execution_plan_task

    def submit(self, plan: ApprovedExecutionPlan) -> dict[str, Any]:
        queue = queue_for_execution_plan(plan)
        result = self.celery_task.apply_async(args=[plan.to_task_payload()], queue=queue)
        return {
            "executor": "celery",
            "celery_task_id": result.id,
            "queue": queue,
            "task_id": plan.task_id,
        }


class LocalThreadTaskExecutor:
    """Diagnostic fallback for local tests/dev when Celery is not installed."""

    def submit(self, plan: ApprovedExecutionPlan) -> dict[str, Any]:
        from app.execution.worker import execute_plan_payload
        from app.services.background import submit_background

        queue = queue_for_execution_plan(plan)
        local_id = f"local-thread-{uuid4().hex}"
        submit_background(execute_plan_payload, plan.to_task_payload())
        return {
            "executor": "local_thread",
            "celery_task_id": local_id,
            "queue": queue,
            "task_id": plan.task_id,
        }
