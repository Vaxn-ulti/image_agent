from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ExecutionResource(StrEnum):
    CPU = "cpu"
    GPU = "gpu"
    SANDBOX = "sandbox"
    LONG = "long"


class ExecutionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_version: Literal["execution_plan.v1"] = "execution_plan.v1"
    execution_kind: Literal["fixed_workflow", "exploratory_toolchain"] = "fixed_workflow"
    project_id: int
    series_id: int
    task_id: int
    workflow_type: str
    runtime_workflow_type: str
    resource: ExecutionResource = ExecutionResource.LONG
    qsiprep_task_id: int | None = None
    timeout_seconds: int | None = Field(default=None, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_task_payload(self) -> dict[str, Any]:
        return {
            "plan_version": self.plan_version,
            "execution_kind": self.execution_kind,
            "project_id": self.project_id,
            "series_id": self.series_id,
            "task_id": self.task_id,
            "workflow_type": self.workflow_type,
            "runtime_workflow_type": self.runtime_workflow_type,
            "resource": self.resource.value,
            "qsiprep_task_id": self.qsiprep_task_id,
            "timeout_seconds": self.timeout_seconds,
            "metadata": self.metadata,
        }


class ValidatedExecutionPlan(ExecutionPlan):
    validation_status: Literal["validated"] = "validated"
    validation_checks: list[dict[str, Any]] = Field(default_factory=list)


class ApprovedExecutionPlan(ValidatedExecutionPlan):
    approval_status: Literal["approved"] = "approved"
    approved_by: Literal["human"] = "human"
    confirmation_id: str
    confirmation_fingerprint: str = Field(min_length=16)

    def to_task_payload(self) -> dict[str, Any]:
        payload = super().to_task_payload()
        payload["validation"] = {
            "status": self.validation_status,
            "checks": self.validation_checks,
        }
        payload["authorization"] = {
            "status": self.approval_status,
            "approved_by": self.approved_by,
            "confirmation_id": self.confirmation_id,
            "confirmation_fingerprint": self.confirmation_fingerprint,
        }
        return payload
