from __future__ import annotations

import os
from pathlib import Path
from types import ModuleType

from app.agent.deepseek import DeepSeekUnavailable, complete_chat
from app.agent.graph import AgentRunner
from app.agent.model_gateway import ModelGateway, ModelGatewayError
from app.agent.rag_index import build_local_rag_index, local_rag_index_status
from app.agent.rag_orchestration import build_rag_response
from app.agent.tools import read_project_context
from app.core.config import PROJECTS_ROOT, ROOT
from app.db.queries import fetch_rows
from app.imaging.series_records import parse_series_row
from app.scripts.verify_scientific_reports import check_output as check_scientific_report_output
from app.scripts.verify_scientific_reports import resolve_task_output_dirs
from app.schemas import (
    AgentResumeConfirmation,
    AgentResumeRequest,
    AgentRunRequest,
    BoldDescriptiveReviewRequest,
    BoldGroupAnalysisRequest,
    ChatRequest,
    LoginRequest,
    ProjectCreate,
    RagQueryRequest,
    RunRequest,
    ScientificReportVerifyRequest,
    UploadSessionCreate,
)
from app.services import result_service, task_service, upload_service
from app.services.agent_service import WORKFLOWS
from app.workflows.deepprep import run_mock_deepprep
from app.workflows.pipeline import run_pipeline_task
from app.workflows.registry import allowed_runtime_workflows

try:
    from app.workflows.bold_group_analysis import run_group_analysis
except ImportError:

    def run_group_analysis(*args, **kwargs):
        raise RuntimeError("bold group analysis unavailable")

try:
    from app.workflows.bold_descriptive_review import run_descriptive_review
except ImportError:

    def run_descriptive_review(*args, **kwargs):
        raise RuntimeError("bold descriptive review unavailable")


def install_main_compat_exports(module: ModuleType) -> None:
    repo_root = Path(os.environ.get("IMAGE_AGENT_RELEASE_ROOT") or ROOT)
    exports = {
        "AgentResumeConfirmation": AgentResumeConfirmation,
        "AgentResumeRequest": AgentResumeRequest,
        "AgentRunRequest": AgentRunRequest,
        "AgentRunner": AgentRunner,
        "ALLOWED_WORKFLOWS": allowed_runtime_workflows(),
        "BoldDescriptiveReviewRequest": BoldDescriptiveReviewRequest,
        "BoldGroupAnalysisRequest": BoldGroupAnalysisRequest,
        "ChatRequest": ChatRequest,
        "DeepSeekUnavailable": DeepSeekUnavailable,
        "LoginRequest": LoginRequest,
        "ModelGateway": ModelGateway,
        "ModelGatewayError": ModelGatewayError,
        "PROJECTS_ROOT": PROJECTS_ROOT,
        "ProjectCreate": ProjectCreate,
        "REPO_ROOT": repo_root,
        "RagQueryRequest": RagQueryRequest,
        "RunRequest": RunRequest,
        "ScientificReportVerifyRequest": ScientificReportVerifyRequest,
        "UploadSessionCreate": UploadSessionCreate,
        "WORKFLOWS": WORKFLOWS,
        "build_local_rag_index": build_local_rag_index,
        "build_rag_response": build_rag_response,
        "check_scientific_report_output": check_scientific_report_output,
        "complete_chat": complete_chat,
        "create_series_task": task_service.create_series_task,
        "get_outputs": result_service.get_outputs,
        "get_result_summary": result_service.get_result_summary,
        "get_task": task_service.get_task,
        "local_rag_index_status": local_rag_index_status,
        "parse_series_row": parse_series_row,
        "read_project_context": read_project_context,
        "resolve_task_output_dirs": resolve_task_output_dirs,
        "rows": fetch_rows,
        "run_descriptive_review": run_descriptive_review,
        "run_group_analysis": run_group_analysis,
        "run_mock_deepprep": run_mock_deepprep,
        "run_pipeline_task": run_pipeline_task,
        "save_upload": upload_service._save_upload,
        "validate_run_request": task_service.validate_run_request,
    }
    for name, value in exports.items():
        setattr(module, name, value)
