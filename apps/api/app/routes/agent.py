from fastapi import APIRouter

from app.agent.contracts import (
    AgentApiErrorResponse,
    AgentRunLookupResponse,
    AgentRunResponse,
    ProjectAgentRunHistoryResponse,
)
from app.schemas import AgentResumeRequest, AgentRunRequest, RagQueryRequest
from app.services import agent_service

router = APIRouter()

AGENT_RUN_ERROR_RESPONSES = {
    404: {"model": AgentApiErrorResponse},
    422: {"model": AgentApiErrorResponse},
    502: {"model": AgentApiErrorResponse},
}


@router.get("/agent/rag/status")
def agent_rag_status():
    return agent_service.agent_rag_status()


@router.post("/agent/rag/rebuild")
def agent_rag_rebuild():
    return agent_service.agent_rag_rebuild()


@router.get("/agent/model/status")
def agent_model_status():
    return agent_service.agent_model_status()


@router.post("/agent/runs", response_model=AgentRunResponse, responses=AGENT_RUN_ERROR_RESPONSES)
def agent_run(req: AgentRunRequest):
    return agent_service.agent_run(req)


@router.get("/agent/runs/{agent_run_id}", response_model=AgentRunLookupResponse, responses=AGENT_RUN_ERROR_RESPONSES)
def agent_run_lookup(agent_run_id: str):
    return agent_service.agent_run_lookup(agent_run_id)


@router.post("/agent/runs/{thread_id}/resume", response_model=AgentRunResponse, responses=AGENT_RUN_ERROR_RESPONSES)
def agent_resume(thread_id: str, req: AgentResumeRequest):
    return agent_service.agent_resume(thread_id, req)


@router.post("/agent/rag/query")
def agent_rag_query(req: RagQueryRequest):
    return agent_service.agent_rag_query(req)


@router.get("/projects/{project_id}/agent-runs", response_model=ProjectAgentRunHistoryResponse)
def list_project_agent_run_history(project_id: int):
    return agent_service.list_project_agent_run_history(project_id)
