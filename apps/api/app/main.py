from fastapi import FastAPI, Request
from fastapi.exception_handlers import (
    request_validation_exception_handler as fastapi_request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agent.contracts import agent_api_error_detail
from app.db.database import init_db
from app.routes import agent, auth, chat, projects, reports, results, series, system, tasks, uploads
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
from app.services import legacy_service as _legacy

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
PROJECTS_ROOT = _legacy.PROJECTS_ROOT
REPO_ROOT = _legacy.REPO_ROOT
WORKFLOWS = _legacy.WORKFLOWS
ALLOWED_WORKFLOWS = _legacy.ALLOWED_WORKFLOWS
AgentRunner = _legacy.AgentRunner
ModelGateway = _legacy.ModelGateway
ModelGatewayError = _legacy.ModelGatewayError
DeepSeekUnavailable = _legacy.DeepSeekUnavailable
complete_chat = _legacy.complete_chat
build_rag_response = _legacy.build_rag_response
local_rag_index_status = _legacy.local_rag_index_status
build_local_rag_index = _legacy.build_local_rag_index
resolve_task_output_dirs = _legacy.resolve_task_output_dirs
check_scientific_report_output = _legacy.check_scientific_report_output
run_pipeline_task = _legacy.run_pipeline_task
run_mock_deepprep = _legacy.run_mock_deepprep
run_group_analysis = _legacy.run_group_analysis
run_descriptive_review = _legacy.run_descriptive_review
read_project_context = _legacy.read_project_context

rows = _legacy.rows
parse_series_row = _legacy.parse_series_row
save_upload = _legacy.save_upload
validate_run_request = _legacy.validate_run_request
create_series_task = _legacy.create_series_task
get_task = _legacy.get_task
get_outputs = _legacy.get_outputs
get_result_summary = _legacy.get_result_summary
