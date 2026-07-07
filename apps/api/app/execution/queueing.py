from __future__ import annotations

from app.execution.contracts import ExecutionPlan, ExecutionResource


EXECUTION_QUEUES = {
    ExecutionResource.CPU: "image_agent_cpu",
    ExecutionResource.GPU: "image_agent_gpu",
    ExecutionResource.SANDBOX: "image_agent_sandbox",
    ExecutionResource.LONG: "image_agent_long",
}


def queue_for_execution_plan(plan: ExecutionPlan) -> str:
    return EXECUTION_QUEUES[plan.resource]


def resource_for_workflow(*, workflow_type: str, runtime_workflow_type: str) -> ExecutionResource:
    key = f"{workflow_type} {runtime_workflow_type}".lower()
    if "sandbox" in key or "incubat" in key:
        return ExecutionResource.SANDBOX
    if "gpu" in key or "dwi_fast_gpu_dti" in key:
        return ExecutionResource.GPU
    return ExecutionResource.LONG
