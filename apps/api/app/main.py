from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import (
    request_validation_exception_handler as fastapi_request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agent.deepseek import DeepSeekUnavailable, complete_chat
from app.agent.graph import AgentRunner
from app.agent.model_gateway import ModelGateway, ModelGatewayError
from app.agent.rag_index import build_local_rag_index, local_rag_index_status
from app.agent.rag_orchestration import build_rag_response
from app.agent.tools import read_project_context
from app.agent.contracts import agent_api_error_detail
from app.core.config import PROJECTS_ROOT
from app.db.database import init_db
from app.db.queries import fetch_rows
from app.routes import agent, auth, chat, projects, reports, results, series, system, tasks, uploads
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
from app.workflows.registry import allowed_runtime_workflows
from app.workflows.pipeline import run_pipeline_task

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

app = FastAPI(title="Brain Image Agent API", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

for router in (
    system.router,
    agent.router,
    auth.router,
    projects.router,
    uploads.router,
    series.router,
    tasks.router,
    results.router,
    reports.router,
    chat.router,
):
    app.include_router(router)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/agent/runs"):
        return JSONResponse(
            status_code=422,
            content={
                "detail": agent_api_error_detail(
                    "request_contract_violation",
                    "Request does not match the Agent API contract.",
                )
            },
        )
    return await fastapi_request_validation_exception_handler(request, exc)


# Compatibility exports for existing tests and scripts that monkeypatch app.main.
REPO_ROOT = Path(__file__).resolve().parents[3]
ALLOWED_WORKFLOWS = allowed_runtime_workflows()

rows = fetch_rows
parse_series_row = task_service._parse_series_row
save_upload = upload_service._save_upload
validate_run_request = task_service.validate_run_request
create_series_task = task_service.create_series_task
get_task = task_service.get_task
get_outputs = result_service.get_outputs
get_result_summary = result_service.get_result_summary
