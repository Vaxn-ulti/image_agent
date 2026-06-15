from __future__ import annotations

import os
from pathlib import Path

from fastapi import HTTPException

from app.agent.backend_context import build_rag_backend_context
from app.agent.chat import handle_legacy_chat
from app.agent.contracts import (
    AGENT_RUN_LOOKUP_CONTRACT_VERSION,
    agent_api_error_detail,
    build_agent_run_response_payload,
    build_project_agent_run_history_response,
    normalize_agent_run_result,
)
from app.agent.deepseek import provider_status as legacy_chat_provider_status
from app.agent.graph import AgentRunner
from app.agent.rag_orchestration import build_rag_response
from app.agent.report_verification import verify_scientific_reports
from app.agent.run_ledger import finish_agent_run, list_project_agent_runs, load_agent_run, start_agent_run
from app.agent.runtime import admin_containers as agent_admin_containers
from app.agent.runtime import runtime_containers as agent_runtime_containers
from app.agent.status import public_model_status, rag_status, rebuild_rag_index
from app.agent.tools import read_project_context
from app.core import config
from app.db.queries import fetch_rows
from app.schemas import RunRequest
from app.services import task_service
from app.services.runtime_overrides import main_patch_attr, main_projects_root
from app.workflows.registry import list_workflows as registry_list_workflows
from app.workflows.result_contract import result_contract_spec

WORKFLOWS = registry_list_workflows()
_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_PROJECTS_ROOT = Path(config.PROJECTS_ROOT)
DEFAULT_API_VERSION = "0.2.0"


def _repo_root() -> Path:
    return Path(main_patch_attr("REPO_ROOT", _DEFAULT_REPO_ROOT))


def _projects_root() -> Path:
    return main_projects_root(_DEFAULT_PROJECTS_ROOT, require_override=True)


def _privacy_safe_symbol(value: str) -> bool:
    return bool(value) and len(value) <= 140 and all(char.isalnum() or char in "_.-" for char in value)


def _deployment_version() -> str:
    version = os.environ.get("IMAGE_AGENT_DEPLOYMENT_VERSION", "").strip()
    if version and _privacy_safe_symbol(version):
        return version
    return DEFAULT_API_VERSION


def _production_mode() -> bool:
    return os.environ.get("IMAGE_AGENT_ENV", "").strip().lower() in {"prod", "production"}


def _production_readiness(*, mode: str, agent: dict) -> dict:
    required = _production_mode()
    blocking_reasons: list[str] = []
    if required and mode != "remote":
        blocking_reasons.append("Backend runtime mode is not remote.")
    if required and agent.get("configured") is not True:
        blocking_reasons.append("Agent model gateway is not configured.")
    return {
        "blocking_reasons": blocking_reasons,
        "ready": not blocking_reasons,
        "required": required,
        "status": "ready" if not blocking_reasons else "blocked",
    }



def health():
    return {"status": "ok", "app": "image_agent", "version": _deployment_version()}


def list_workflows():
    return {"workflows": main_patch_attr("WORKFLOWS", WORKFLOWS)}


def get_result_contract():
    return result_contract_spec()


def deployment():
    mode = os.environ.get("BACKEND_RUNTIME_MODE", "remote")
    agent = public_model_status()
    return {
        "backend_runtime_mode": mode,
        "api_base_hint": os.environ.get("IMAGE_AGENT_PUBLIC_BASE_URL", ""),
        "agent": agent,
        "legacy_chat_provider": legacy_chat_provider_status(),
        "production_readiness": _production_readiness(mode=mode, agent=agent),
    }


def agent_rag_status():
    return rag_status(_repo_root())


def agent_rag_rebuild():
    return rebuild_rag_index(_repo_root())


def agent_model_status():
    return public_model_status()


def agent_run(req):
    message = req.message.strip()
    if not message:
        raise HTTPException(
            422,
            agent_api_error_detail("message_required", "message is required"),
        )
    agent_run_id = start_agent_run(request_type="run", project_id=req.project_id, message=message)
    project_context_reader = main_patch_attr("read_project_context", read_project_context)
    runner_factory = main_patch_attr("AgentRunner", AgentRunner)
    project_context = project_context_reader(req.project_id, rows_fn=fetch_rows, workflows=main_patch_attr("WORKFLOWS", WORKFLOWS))
    try:
        result = normalize_agent_run_result(dict(runner_factory().run(message=message, project_context=project_context)))
        result["agent_run_id"] = agent_run_id
        finish_agent_run(agent_run_id, result=result)
        ledger = load_agent_run(agent_run_id) or {}
        return build_agent_run_response_payload(
            result,
            ledger=ledger,
            request_type="run",
            project_id=req.project_id,
        )
    except HTTPException as exc:
        finish_agent_run(agent_run_id, error=exc)
        raise
    except Exception as exc:
        finish_agent_run(agent_run_id, error=exc)
        raise HTTPException(
            502,
            agent_api_error_detail(
                "agent_model_call_failed",
                "Agent model call failed.",
                agent_run_id=agent_run_id,
            ),
        ) from exc


def agent_run_lookup(agent_run_id):
    run = load_agent_run(agent_run_id)
    if run is None:
        raise HTTPException(
            404,
            agent_api_error_detail("agent_run_not_found", "Agent run not found"),
        )
    return build_agent_run_response_payload(
        run,
        ledger=run,
        contract_version=AGENT_RUN_LOOKUP_CONTRACT_VERSION,
    )


def agent_resume(thread_id, req):
    def _create_task(series_id: int, workflow_type: str, qsiprep_task_id: int | None = None) -> dict:
        return task_service.create_series_task(
            series_id,
            RunRequest(workflow_type=workflow_type, qsiprep_task_id=qsiprep_task_id),
        )

    confirmation = req.confirmation.model_dump(exclude_none=True)
    agent_run_id = start_agent_run(
        request_type="resume",
        project_id=confirmation.get("project_id"),
        thread_id=thread_id,
        approved=req.approved,
        confirmation=confirmation,
    )
    runner_factory = main_patch_attr("AgentRunner", AgentRunner)
    try:
        result = normalize_agent_run_result(dict(runner_factory().resume(
            thread_id=thread_id,
            approved=req.approved,
            confirmation=confirmation,
            create_task_fn=_create_task,
        )))
        result["agent_run_id"] = agent_run_id
        finish_agent_run(agent_run_id, result=result)
        ledger = load_agent_run(agent_run_id) or {}
        return build_agent_run_response_payload(
            result,
            ledger=ledger,
            request_type="resume",
        )
    except HTTPException as exc:
        finish_agent_run(agent_run_id, error=exc)
        raise
    except Exception as exc:
        finish_agent_run(agent_run_id, error=exc)
        raise HTTPException(
            502,
            agent_api_error_detail(
                "agent_resume_failed",
                "Agent resume failed.",
                agent_run_id=agent_run_id,
            ),
        ) from exc


def agent_rag_query(req):
    backend_context = build_rag_backend_context(req.project_id)
    builder = main_patch_attr("build_rag_response", build_rag_response)
    return builder(req.query, root=_repo_root(), backend_context=backend_context)


def agent_verify_scientific_reports(req):
    projects_root = Path(req.projects_root) if req.projects_root else _projects_root()
    verifier = main_patch_attr("verify_scientific_reports", verify_scientific_reports)
    return verifier(req, projects_root=projects_root)


def runtime_containers():
    return agent_runtime_containers()


def admin_containers():
    return agent_admin_containers()


def list_project_agent_run_history(project_id):
    return build_project_agent_run_history_response(project_id, list_project_agent_runs(project_id))


def chat(req):
    return handle_legacy_chat(
        req,
        repo_root=_repo_root(),
        projects_root=_projects_root(),
        workflows=main_patch_attr("WORKFLOWS", WORKFLOWS),
    )
