from typing import Any

from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    username: str
    password: str


class ProjectCreate(BaseModel):
    name: str
    description: str = ""


class UploadSessionCreate(BaseModel):
    source_type: str = "folder_or_archive"
    label: str = "dataset"


class RunRequest(BaseModel):
    workflow_type: str = "t1_deepprep_mock"
    runtime_workflow_type: str | None = None
    qsiprep_task_id: int | None = None


class ChatRequest(BaseModel):
    project_id: int | None = None
    message: str


class AgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: int | None = None
    message: str


class AgentResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool
    confirmation: "AgentResumeConfirmation"


class AgentResumeConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    action_lane: str | None = None
    title: str | None = None
    project_id: int | None = None
    series_id: int | None = None
    workflow_type: str | None = None
    runtime_workflow_type: str | None = None
    fingerprint: str | None = None
    confirmation_fingerprint: str | None = None
    workflow_metadata: dict[str, Any] | None = None
    qsiprep_task_id: int | None = None
    summary: str | None = None
    risks: list[str] | None = None
    preflight: dict[str, Any] | None = None
    data_candidate_selection: dict[str, Any] | None = None


class RagQueryRequest(BaseModel):
    project_id: int | None = None
    query: str


class ScientificReportVerifyRequest(BaseModel):
    task_ids: list[int] = []
    output_dirs: list[str] = []
    projects_root: str | None = None
    require_modalities: list[str] = []
    require_container_native_qc: bool = False
    min_native_qc_images: int = 0


class BoldGroupAnalysisRequest(BaseModel):
    group_a_task_ids: list[int]
    group_b_task_ids: list[int]
    seed_query: str = "PCC_DMN"
    label_a: str = "group_a"
    label_b: str = "group_b"


class BoldDescriptiveReviewRequest(BaseModel):
    deepprep_task_ids: list[int]
    seed_preset: str = "PCC_DMN"
