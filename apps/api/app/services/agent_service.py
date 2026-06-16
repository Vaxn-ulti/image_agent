from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

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
from app.services.project_service import require_project
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


def _execution_scope() -> dict:
    return {
        "development_origin": "workstation",
        "deployment_target": "api_server",
        "workflow_tool_execution": "deployment_server_local",
        "docker_runtime_host": "api_server",
        "external_worker_server_required": False,
    }


def _public_api_base_ready() -> bool:
    return _public_api_base_blocker() is None


def _public_api_base_blocker() -> str | None:
    base_url = os.environ.get("IMAGE_AGENT_PUBLIC_BASE_URL", "").strip()
    if not base_url:
        return "IMAGE_AGENT_PUBLIC_BASE_URL must be set for production deployment."
    parsed = urlsplit(base_url)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not host
        or host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
        or bool(parsed.path or parsed.query or parsed.fragment)
    ):
        return "IMAGE_AGENT_PUBLIC_BASE_URL must be a public HTTPS API origin without path, query, or fragment."
    return None


def _production_readiness(*, mode: str, agent: dict) -> dict:
    from app.app_factory import production_cors_has_insecure_public_origin, production_cors_has_public_origin

    required = _production_mode()
    blocking_reasons: list[str] = []
    if required and mode != "remote":
        blocking_reasons.append("Backend runtime mode is not remote.")
    if required and agent.get("configured") is not True:
        blocking_reasons.append("Agent model gateway is not configured.")
    if required and production_cors_has_insecure_public_origin():
        blocking_reasons.append("Production CORS origins must use HTTPS for public console origins.")
    if required and not production_cors_has_public_origin():
        blocking_reasons.append("Production CORS origins must include a non-localhost console origin.")
    public_api_base_blocker = _public_api_base_blocker() if required else None
    if public_api_base_blocker:
        blocking_reasons.append(public_api_base_blocker)
    return {
        "blocking_reasons": blocking_reasons,
        "ready": not blocking_reasons,
        "required": required,
        "status": "ready" if not blocking_reasons else "blocked",
    }


def _env_flag(name: str) -> str:
    return os.environ.get(name, "").strip().lower()


def _remote_acceptance_evidence() -> dict:
    status = _env_flag("IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_STATUS")
    evidence_id = os.environ.get("IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID", "").strip()
    if status == "passed" and _privacy_safe_symbol(evidence_id):
        return {
            "status": "passed",
            "evidence_id": evidence_id,
            "required_evidence": "strict remote smoke JSON verified within freshness window",
        }
    if status == "passed":
        return {
            "status": "blocked",
            "required_evidence": "strict remote smoke JSON verified within freshness window",
            "reason": "Strict remote acceptance evidence id is missing or not privacy-safe.",
        }
    return {
        "status": "missing",
        "required_evidence": "strict remote smoke JSON verified within freshness window",
    }


def _fast_launch_readiness(*, agent: dict) -> dict:
    capabilities = agent.get("capabilities") if isinstance(agent.get("capabilities"), dict) else {}
    provider_profile = agent.get("provider_profile")
    wire_api = agent.get("wire_api")
    model = agent.get("model")
    model_tool_loop = capabilities.get("model_tool_loop") is True

    model_target = {
        "status": "passed"
        if (
            agent.get("configured") is True
            and provider_profile == "rawchat"
            and wire_api == "responses"
            and model == "gpt-5.5"
            and model_tool_loop
        )
        else "blocked",
        "expected_provider_profile": "rawchat",
        "actual_provider_profile": provider_profile,
        "expected_wire_api": "responses",
        "actual_wire_api": wire_api,
        "expected_model": "gpt-5.5",
        "actual_model": model,
        "model_tool_loop": model_tool_loop,
    }
    agent_boundary = {
        "status": "passed",
        "task_creation": "server_side_resume_confirmation_only",
        "chat_authority": "read_explain_recommend",
        "deterministic_launch_endpoint": "/series/{series_id}/run",
    }
    upload_workflow_contract = {
        "status": "passed",
        "upload_endpoint": "/projects/{project_id}/upload",
        "series_endpoint": "/projects/{project_id}/series",
        "workflow_launch_endpoint": "/series/{series_id}/run",
        "result_endpoints": [
            "/tasks/{task_id}/outputs",
            "/tasks/{task_id}/result-summary",
            "/tasks/{task_id}/artifact-manifest",
        ],
    }
    remote_acceptance = _remote_acceptance_evidence()
    checks = {
        "model_gateway_target": model_target,
        "agent_task_boundary": agent_boundary,
        "upload_workflow_result_contract": upload_workflow_contract,
        "strict_remote_acceptance": remote_acceptance,
    }
    blocking_reasons: list[str] = []
    if model_target["status"] != "passed":
        blocking_reasons.append("Model gateway is not pinned to rawchat GPT-5.5 Responses with model tool loop.")
    if remote_acceptance["status"] != "passed":
        blocking_reasons.append("Strict remote acceptance evidence has not been verified for the upload-agent-workflow-result chain.")
    return {
        "ready": not blocking_reasons,
        "status": "ready" if not blocking_reasons else "blocked",
        "blocking_reasons": blocking_reasons,
        "checks": checks,
    }


def _agent_model_configured() -> bool:
    return public_model_status().get("configured") is True


def _read_only_agent_fallback(message: str, *, project_id: int | None, project_context: dict) -> dict:
    backend_context = {
        "project_id": project_id,
        "tasks": project_context.get("tasks") or [],
        "outputs": [],
    }
    rag_builder = main_patch_attr("build_rag_response", build_rag_response)
    rag_response = rag_builder(message, root=_repo_root(), backend_context=backend_context)
    answer = (
        "Model gateway is not configured; using read-only backend/RAG fallback. "
        + str(rag_response.get("answer") or "No backend records or local documents matched the query.")
    )
    citations = [
        item
        for item in rag_response.get("citations", [])
        if isinstance(item, dict)
    ]
    return {
        "status": "answered",
        "intent": rag_response.get("intent") or "general",
        "selected_skill": "backend-status-fallback",
        "answer": answer,
        "retrieved_context": {
            "mode": rag_response.get("mode") or "fallback",
            "results": citations,
        },
        "tool_invocations": rag_response.get("tool_invocations", []),
        "tool_trace": [
            {
                "stage": "model_gateway",
                "status": "skipped",
                "mode": "model_gateway_unconfigured",
            }
        ],
        "safe_metadata": {"fallback_reason": "model_gateway_unconfigured"},
        "events": [
            {
                "type": "agent.model_gateway_unconfigured_fallback",
                "message": "Answered with read-only backend/RAG fallback.",
            }
        ],
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
        "execution_scope": _execution_scope(),
        "agent": agent,
        "legacy_chat_provider": legacy_chat_provider_status(),
        "production_readiness": _production_readiness(mode=mode, agent=agent),
        "fast_launch_readiness": _fast_launch_readiness(agent=agent),
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
    if req.project_id is not None:
        require_project(req.project_id)
    agent_run_id = start_agent_run(request_type="run", project_id=req.project_id, message=message)
    project_context_reader = main_patch_attr("read_project_context", read_project_context)
    runner_factory = main_patch_attr("AgentRunner", AgentRunner)
    project_context = project_context_reader(req.project_id, rows_fn=fetch_rows, workflows=main_patch_attr("WORKFLOWS", WORKFLOWS))
    if runner_factory is AgentRunner and not _agent_model_configured():
        result = normalize_agent_run_result(_read_only_agent_fallback(message, project_id=req.project_id, project_context=project_context))
        result["agent_run_id"] = agent_run_id
        finish_agent_run(agent_run_id, result=result)
        ledger = load_agent_run(agent_run_id) or {}
        return build_agent_run_response_payload(
            result,
            ledger=ledger,
            request_type="run",
            project_id=req.project_id,
        )
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
    if req.project_id is not None:
        require_project(req.project_id)
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
    require_project(project_id)
    return build_project_agent_run_history_response(project_id, list_project_agent_runs(project_id))


def chat(req):
    return handle_legacy_chat(
        req,
        repo_root=_repo_root(),
        projects_root=_projects_root(),
        workflows=main_patch_attr("WORKFLOWS", WORKFLOWS),
    )
