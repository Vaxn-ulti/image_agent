import pytest
from pydantic import ValidationError

from app.execution.contracts import ApprovedExecutionPlan, ExecutionPlan, ExecutionResource
from app.execution.queueing import queue_for_execution_plan


def test_fixed_workflow_execution_plan_defaults_to_long_queue():
    plan = ExecutionPlan(
        project_id=7,
        series_id=11,
        task_id=101,
        workflow_type="t1_deepprep_anat_report",
        runtime_workflow_type="t1_deepprep",
        resource=ExecutionResource.LONG,
    )

    assert plan.plan_version == "execution_plan.v1"
    assert plan.execution_kind == "fixed_workflow"
    assert queue_for_execution_plan(plan) == "image_agent_long"


def test_gpu_execution_plan_routes_to_gpu_queue():
    plan = ExecutionPlan(
        project_id=7,
        series_id=24,
        task_id=102,
        workflow_type="dwi_fast_gpu_dti",
        runtime_workflow_type="dwi_fast_gpu_dti",
        resource=ExecutionResource.GPU,
    )

    assert queue_for_execution_plan(plan) == "image_agent_gpu"


def test_approved_execution_plan_requires_human_confirmation():
    with pytest.raises(ValidationError):
        ApprovedExecutionPlan(
            project_id=7,
            series_id=11,
            task_id=101,
            workflow_type="t1_deepprep_anat_report",
            runtime_workflow_type="t1_deepprep",
            resource=ExecutionResource.LONG,
        )


def test_approved_execution_plan_keeps_authorization_metadata():
    plan = ApprovedExecutionPlan(
        project_id=7,
        series_id=11,
        task_id=101,
        workflow_type="t1_deepprep_anat_report",
        runtime_workflow_type="t1_deepprep",
        resource=ExecutionResource.LONG,
        approved_by="human",
        confirmation_id="agent_abc123",
        confirmation_fingerprint="f" * 64,
    )

    payload = plan.to_task_payload()

    assert payload["task_id"] == 101
    assert payload["workflow_type"] == "t1_deepprep_anat_report"
    assert payload["runtime_workflow_type"] == "t1_deepprep"
    assert payload["authorization"]["confirmation_id"] == "agent_abc123"
