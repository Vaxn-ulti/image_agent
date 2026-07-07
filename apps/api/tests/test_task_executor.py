from app.execution.contracts import ApprovedExecutionPlan, ExecutionResource
from app.execution.task_executor import CeleryTaskExecutor


class FakeCeleryTask:
    def __init__(self):
        self.calls = []

    def apply_async(self, *, args, queue):
        self.calls.append({"args": args, "queue": queue})
        return type("AsyncResult", (), {"id": "celery-task-1"})()


def test_celery_task_executor_submits_payload_to_resource_queue():
    celery_task = FakeCeleryTask()
    executor = CeleryTaskExecutor(celery_task=celery_task)
    plan = ApprovedExecutionPlan(
        project_id=7,
        series_id=24,
        task_id=102,
        workflow_type="dwi_fast_gpu_dti",
        runtime_workflow_type="dwi_fast_gpu_dti",
        resource=ExecutionResource.GPU,
        approved_by="human",
        confirmation_id="agent_abc123",
        confirmation_fingerprint="f" * 64,
    )

    handle = executor.submit(plan)

    assert handle["executor"] == "celery"
    assert handle["celery_task_id"] == "celery-task-1"
    assert handle["queue"] == "image_agent_gpu"
    assert celery_task.calls == [
        {
            "args": [plan.to_task_payload()],
            "queue": "image_agent_gpu",
        }
    ]
