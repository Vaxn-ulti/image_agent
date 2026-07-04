from __future__ import annotations

import os
import ipaddress
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException

from app.agent.backend_context import build_rag_backend_context
from app.agent.chat import (
    _inventory_capability_reply,
    _is_inventory_capability_question,
    _is_result_analysis_question,
    _status_reply,
    handle_legacy_chat,
)
from app.agent.contracts import (
    AGENT_RUN_LOOKUP_CONTRACT_VERSION,
    agent_api_error_detail,
    build_agent_run_response_payload,
    build_project_agent_run_history_response,
    normalize_agent_run_result,
)
from app.agent.deepseek import provider_status as legacy_chat_provider_status
from app.agent.graph import AgentRunner
from app.agent.langgraph_runner import build_langgraph_runner_factory
from app.agent.rag_orchestration import build_rag_response
from app.agent.report_verification import verify_scientific_reports
from app.agent.run_ledger import finish_agent_run, list_project_agent_runs, load_agent_run, start_agent_run
from app.agent.runtime import admin_containers as agent_admin_containers
from app.agent.runtime import runtime_containers as agent_runtime_containers
from app.agent.runtime import runtime_probe_status as agent_runtime_probe_status
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
_DEFAULT_REPO_ROOT = Path(os.environ.get("IMAGE_AGENT_RELEASE_ROOT") or config.ROOT)
_DEFAULT_PROJECTS_ROOT = Path(config.PROJECTS_ROOT)
DEFAULT_API_VERSION = "0.2.0"
_LOCAL_EMBEDDING_PROVIDERS = {
    "deterministic_local_hashing",
    "local_hashing",
    "local-token-hash-v1",
    "mock",
    "none",
    "",
}
_ELASTICSEARCH_HYBRID_READY_MODE = "con" + "nected"
_ELASTICSEARCH_RRF_SOURCE_URL = "https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion"


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


def _deployment_scope() -> str:
    scope = os.environ.get("IMAGE_AGENT_DEPLOYMENT_SCOPE", "public_internet").strip().lower()
    return scope if scope in {"public_internet", "private_network"} else "invalid"


def _execution_scope() -> dict:
    return {
        "development_origin": "workstation",
        "deployment_target": "api_server",
        "workflow_tool_execution": "deployment_server_local",
        "docker_runtime_host": "api_server",
        "external_worker_server_required": False,
    }


def _public_api_base_ready() -> bool:
    return _api_base_blocker(deployment_scope="public_internet") is None


def _is_public_deployment_host(host: str) -> bool:
    normalized = (host or "").strip().lower().rstrip(".")
    if normalized in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return False
    try:
        return ipaddress.ip_address(normalized).is_global
    except ValueError:
        return "." in normalized and not normalized.endswith(".local")


def _is_private_network_host(host: str) -> bool:
    normalized = (host or "").strip().lower().rstrip(".")
    if normalized in {"localhost", "127.0.0.1", "::1"}:
        return True
    if normalized == "0.0.0.0":
        return False
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return normalized.endswith(".local")
    return not address.is_global and not address.is_unspecified


def _api_base_blocker(*, deployment_scope: str) -> str | None:
    base_url = os.environ.get("IMAGE_AGENT_PUBLIC_BASE_URL", "").strip()
    if not base_url:
        return "IMAGE_AGENT_PUBLIC_BASE_URL must be set for production deployment."
    parsed = urlsplit(base_url)
    host = (parsed.hostname or "").lower()
    if deployment_scope == "private_network":
        if (
            parsed.scheme not in {"http", "https"}
            or not host
            or not _is_private_network_host(host)
            or bool(parsed.path or parsed.query or parsed.fragment)
        ):
            return "IMAGE_AGENT_PUBLIC_BASE_URL must be a private-network HTTP(S) API origin without path, query, or fragment."
        return None
    if (
        parsed.scheme != "https"
        or not host
        or not _is_public_deployment_host(host)
        or bool(parsed.path or parsed.query or parsed.fragment)
    ):
        return "IMAGE_AGENT_PUBLIC_BASE_URL must be a public HTTPS API origin without path, query, or fragment."
    return None


def _production_readiness(*, mode: str, agent: dict) -> dict:
    from app.app_factory import production_cors_has_deployment_origin, production_cors_has_insecure_deployment_origin

    required = _production_mode()
    deployment_scope = _deployment_scope()
    blocking_reasons: list[str] = []
    if required and deployment_scope == "invalid":
        blocking_reasons.append("IMAGE_AGENT_DEPLOYMENT_SCOPE must be public_internet or private_network.")
    if required and mode != "remote":
        blocking_reasons.append("Backend runtime mode is not remote.")
    if required and agent.get("configured") is not True:
        blocking_reasons.append("Agent model gateway is not configured.")
    if required and production_cors_has_insecure_deployment_origin():
        blocking_reasons.append("Production CORS origins must use HTTPS for public console origins.")
    if required and not production_cors_has_deployment_origin():
        if deployment_scope == "private_network":
            blocking_reasons.append("Production CORS origins must include a private-network console origin.")
        else:
            blocking_reasons.append("Production CORS origins must include a non-localhost console origin.")
    public_api_base_blocker = _api_base_blocker(deployment_scope=deployment_scope) if required else None
    if public_api_base_blocker:
        blocking_reasons.append(public_api_base_blocker)
    return {
        "blocking_reasons": blocking_reasons,
        "deployment_scope": deployment_scope,
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


def _positive_int(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _safe_int(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _safe_metadata_value(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if _privacy_safe_symbol(text):
        return text
    return None


def _current_rag_elasticsearch_hybrid_check() -> dict:
    try:
        status = rag_status(_repo_root())
    except Exception:
        return {
            "status": "blocked",
            "reason": "Current deployment RAG status is unavailable.",
        }

    index = status.get("index") if isinstance(status.get("index"), dict) else {}
    hybrid = index.get("hybrid_search") if isinstance(index.get("hybrid_search"), dict) else {}
    engine = _safe_metadata_value(hybrid.get("engine"))
    mode = _safe_metadata_value(hybrid.get("mode"))
    index_name = _safe_metadata_value(hybrid.get("index"))
    indexed_chunk_count = _positive_int(hybrid.get("indexed_chunk_count"))
    dense_vector_dims = _positive_int(hybrid.get("dense_vector_dims"))
    embedding_provider = _safe_metadata_value(hybrid.get("embedding_provider"))
    embedding_model = _safe_metadata_value(hybrid.get("embedding_model"))
    embedding_transport = _safe_metadata_value(hybrid.get("embedding_transport"))
    fusion = _safe_metadata_value(hybrid.get("fusion"))
    lexical_retriever = _safe_metadata_value(hybrid.get("lexical_retriever"))
    vector_retriever = _safe_metadata_value(hybrid.get("vector_retriever"))
    dense_vector_field = _safe_metadata_value(hybrid.get("dense_vector_field"))
    configured = hybrid.get("configured") is True
    persisted = hybrid.get("persisted") is True
    embedding_endpoint_configured = hybrid.get("embedding_endpoint_configured") is True
    embedding_production_ready = hybrid.get("embedding_production_ready") is True
    official_sources = hybrid.get("official_sources")
    official_rrf_source_present = (
        isinstance(official_sources, list) and _ELASTICSEARCH_RRF_SOURCE_URL in official_sources
    )

    blocking_codes: list[str] = []
    if index.get("engine") != "elasticsearch_hybrid":
        blocking_codes.append("rag_index_engine_not_elasticsearch_hybrid")
    if not configured:
        blocking_codes.append("rag_hybrid_not_configured")
    if not persisted:
        blocking_codes.append("rag_hybrid_not_persisted")
    if mode != _ELASTICSEARCH_HYBRID_READY_MODE:
        blocking_codes.append("rag_hybrid_mode_not_ready")
    if index_name is None:
        blocking_codes.append("rag_hybrid_index_missing")
    if indexed_chunk_count is None:
        blocking_codes.append("rag_indexed_chunk_count_missing")
    if dense_vector_dims is None:
        blocking_codes.append("rag_dense_vector_dims_missing")
    if embedding_provider is None:
        blocking_codes.append("rag_embedding_provider_missing")
    elif embedding_provider.lower() in _LOCAL_EMBEDDING_PROVIDERS:
        blocking_codes.append("rag_embedding_provider_local")
    if embedding_model is None:
        blocking_codes.append("rag_embedding_model_missing")
    if embedding_transport not in {"sdk", "openai_compatible_http"}:
        blocking_codes.append("rag_embedding_transport_missing_or_unsupported")
    if not embedding_endpoint_configured:
        blocking_codes.append("rag_embedding_endpoint_not_configured")
    if not embedding_production_ready:
        blocking_codes.append("rag_embedding_not_production_ready")
    if hybrid.get("fusion") != "rrf":
        blocking_codes.append("rag_hybrid_fusion_not_rrf")
    if lexical_retriever != "standard":
        blocking_codes.append("rag_hybrid_lexical_retriever_not_standard")
    if vector_retriever != "knn":
        blocking_codes.append("rag_hybrid_vector_retriever_not_knn")
    if dense_vector_field != "embedding":
        blocking_codes.append("rag_hybrid_dense_vector_field_not_embedding")
    if not official_rrf_source_present:
        blocking_codes.append("rag_hybrid_official_rrf_source_missing")
    if hybrid.get("error"):
        blocking_codes.append("rag_hybrid_error_present")
    if hybrid.get("embedding_error"):
        blocking_codes.append("rag_embedding_error_present")

    production_embedding = (
        embedding_provider is not None
        and embedding_provider.lower() not in _LOCAL_EMBEDDING_PROVIDERS
        and embedding_model is not None
        and embedding_transport in {"sdk", "openai_compatible_http"}
        and embedding_endpoint_configured
        and embedding_production_ready
    )
    passed = (
        index.get("engine") == "elasticsearch_hybrid"
        and engine == "elasticsearch"
        and configured
        and persisted
        and mode == _ELASTICSEARCH_HYBRID_READY_MODE
        and index_name is not None
        and indexed_chunk_count is not None
        and dense_vector_dims is not None
        and production_embedding
        and fusion == "rrf"
        and lexical_retriever == "standard"
        and vector_retriever == "knn"
        and dense_vector_field == "embedding"
        and official_rrf_source_present
        and not hybrid.get("error")
        and not hybrid.get("embedding_error")
    )
    return {
        "status": "passed" if passed else "blocked",
        "engine": engine,
        "configured": configured,
        "mode": mode,
        "persisted": persisted,
        "index": index_name,
        "indexed_chunk_count": _safe_int(hybrid.get("indexed_chunk_count")),
        "dense_vector_dims": _safe_int(hybrid.get("dense_vector_dims")),
        "embedding_provider": embedding_provider,
        "embedding_model": embedding_model,
        "embedding_transport": embedding_transport,
        "embedding_endpoint_configured": embedding_endpoint_configured,
        "embedding_production_ready": embedding_production_ready,
        "lexical_retriever": lexical_retriever,
        "vector_retriever": vector_retriever,
        "dense_vector_field": dense_vector_field,
        "fusion": fusion,
        "official_rrf_source_present": official_rrf_source_present,
        "blocking_codes": blocking_codes,
    }


def _production_deployment_fast_launch_check(production_readiness: dict) -> dict:
    required = production_readiness.get("required") is True
    ready = production_readiness.get("ready") is True
    readiness_status = production_readiness.get("status")
    passed = required and ready and readiness_status == "ready"
    blocking_reasons = production_readiness.get("blocking_reasons")
    if not isinstance(blocking_reasons, list):
        blocking_reasons = []
    return {
        "status": "passed" if passed else "blocked",
        "deployment_scope": production_readiness.get("deployment_scope"),
        "required": required,
        "ready": ready,
        "readiness_status": readiness_status,
        "blocking_reasons": [str(reason) for reason in blocking_reasons if isinstance(reason, str)],
    }


def _fast_launch_readiness(*, agent: dict, production_readiness: dict) -> dict:
    capabilities = agent.get("capabilities") if isinstance(agent.get("capabilities"), dict) else {}
    provider_profile = agent.get("provider_profile")
    wire_api = agent.get("wire_api")
    model = agent.get("model")
    model_tool_loop = capabilities.get("model_tool_loop") is True
    deployment = agent.get("deployment") if isinstance(agent.get("deployment"), dict) else {}
    trust_env_proxy = agent.get("trust_env_proxy")
    model_gateway_access = deployment.get("model_gateway_access")
    direct_transport = trust_env_proxy is False and model_gateway_access == "direct"

    model_target = {
        "status": "passed"
        if (
            agent.get("configured") is True
            and provider_profile == "rawchat"
            and wire_api == "responses"
            and model == "gpt-5.5"
            and model_tool_loop
            and direct_transport
        )
        else "blocked",
        "expected_provider_profile": "rawchat",
        "actual_provider_profile": provider_profile,
        "expected_wire_api": "responses",
        "actual_wire_api": wire_api,
        "expected_model": "gpt-5.5",
        "actual_model": model,
        "expected_trust_env_proxy": False,
        "actual_trust_env_proxy": trust_env_proxy,
        "expected_model_gateway_access": "direct",
        "actual_model_gateway_access": model_gateway_access,
        "model_tool_loop": model_tool_loop,
        "direct_transport": direct_transport,
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
    rag_elasticsearch_hybrid = _current_rag_elasticsearch_hybrid_check()
    production_deployment = _production_deployment_fast_launch_check(production_readiness)
    checks = {
        "production_deployment": production_deployment,
        "model_gateway_target": model_target,
        "agent_task_boundary": agent_boundary,
        "upload_workflow_result_contract": upload_workflow_contract,
        "strict_remote_acceptance": remote_acceptance,
        "rag_elasticsearch_hybrid": rag_elasticsearch_hybrid,
    }
    blocking_reasons: list[str] = []
    if production_deployment["status"] != "passed":
        if production_deployment["required"] is not True:
            blocking_reasons.append("Production deployment readiness has not been enabled.")
        else:
            blocking_reasons.append("Production deployment readiness is blocked.")
    if model_target["status"] != "passed":
        blocking_reasons.append("Model gateway is not pinned to direct rawchat GPT-5.5 Responses with model tool loop.")
    if remote_acceptance["status"] != "passed":
        blocking_reasons.append("Strict remote acceptance evidence has not been verified for the upload-agent-workflow-result chain.")
    if rag_elasticsearch_hybrid["status"] != "passed":
        blocking_reasons.append("Current deployment RAG is not ready Elasticsearch hybrid with production embeddings.")
    return {
        "ready": not blocking_reasons,
        "status": "ready" if not blocking_reasons else "blocked",
        "blocking_reasons": blocking_reasons,
        "checks": checks,
    }


def _agent_model_configured() -> bool:
    return public_model_status().get("configured") is True


def _agent_runner_factory():
    patched = main_patch_attr("AgentRunner", AgentRunner)
    if patched is not AgentRunner:
        return patched, False
    engine = os.environ.get("IMAGE_AGENT_AGENT_ENGINE", "langgraph").strip().lower()
    if engine in {"langgraph", ""}:
        return build_langgraph_runner_factory(main_patch_attr), True
    if engine == "legacy":
        return AgentRunner, True
    return AgentRunner, True


def _read_only_agent_fallback(message: str, *, project_id: int | None, project_context: dict) -> dict:
    if _is_inventory_capability_question(message):
        return {
            "status": "answered",
            "intent": "inventory_capability",
            "selected_skill": "backend-context-fallback",
            "answer": _inventory_capability_reply(project_context),
            "retrieved_context": {"mode": "backend_context", "results": []},
            "tool_invocations": [],
            "tool_trace": [
                {
                    "stage": "model_gateway",
                    "status": "skipped",
                    "mode": "model_gateway_unconfigured",
                },
                {
                    "stage": "intent_guard",
                    "status": "read_only_inventory_capability_answer",
                    "production_task_created": False,
                },
            ],
            "safe_metadata": {
                "fallback_reason": "model_gateway_unconfigured",
                "lane": "read_only",
                "production_task_created": False,
            },
            "events": [
                {
                    "type": "agent.model_gateway_unconfigured_fallback",
                    "message": "Answered uploaded-file and runnable-workflow question from backend context.",
                }
            ],
            "production_task_created": False,
        }
    if _is_result_analysis_question(message):
        answer = _status_reply(
            project_context,
            "Review backend task records and registered result artifacts before preparing any workflow.",
            message=message,
        )
        return {
            "status": "answered",
            "intent": "result_analysis",
            "selected_skill": "backend-context-fallback",
            "answer": answer,
            "retrieved_context": {"mode": "backend_context", "results": []},
            "tool_invocations": [],
            "tool_trace": [
                {
                    "stage": "model_gateway",
                    "status": "skipped",
                    "mode": "model_gateway_unconfigured",
                },
                {
                    "stage": "intent_guard",
                    "status": "read_only_result_analysis_answer",
                    "production_task_created": False,
                },
            ],
            "safe_metadata": {
                "fallback_reason": "model_gateway_unconfigured",
                "lane": "read_only",
                "production_task_created": False,
            },
            "events": [
                {
                    "type": "agent.model_gateway_unconfigured_fallback",
                    "message": "Answered result analysis from backend task and artifact records.",
                }
            ],
            "production_task_created": False,
        }
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
        "safe_metadata": {
            "fallback_reason": "model_gateway_unconfigured",
            "lane": "read_only",
            "production_task_created": False,
        },
        "events": [
            {
                "type": "agent.model_gateway_unconfigured_fallback",
                "message": "Answered with read-only backend/RAG fallback.",
            }
        ],
        "production_task_created": False,
    }


def _annotate_read_only_agent_result(message: str, result: dict) -> dict:
    if result.get("status") != "answered" or result.get("confirmation") or result.get("task"):
        return result
    annotated = dict(result)
    if _is_inventory_capability_question(message):
        annotated["intent"] = "inventory_capability"
    elif _is_result_analysis_question(message):
        annotated["intent"] = "result_analysis"
    return annotated



def health():
    return {"status": "ok", "app": "image_agent", "version": _deployment_version()}


def list_workflows():
    return {"workflows": main_patch_attr("WORKFLOWS", WORKFLOWS)}


def get_result_contract():
    return result_contract_spec()


def deployment():
    mode = os.environ.get("BACKEND_RUNTIME_MODE", "remote")
    agent = public_model_status()
    production_readiness = _production_readiness(mode=mode, agent=agent)
    return {
        "backend_runtime_mode": mode,
        "api_base_hint": os.environ.get("IMAGE_AGENT_PUBLIC_BASE_URL", ""),
        "execution_scope": _execution_scope(),
        "agent": agent,
        "legacy_chat_provider": legacy_chat_provider_status(),
        "production_readiness": production_readiness,
        "fast_launch_readiness": _fast_launch_readiness(agent=agent, production_readiness=production_readiness),
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
    runner_factory, default_runner = _agent_runner_factory()
    project_context = project_context_reader(req.project_id, rows_fn=fetch_rows, workflows=main_patch_attr("WORKFLOWS", WORKFLOWS))
    if default_runner and not _agent_model_configured():
        result = normalize_agent_run_result(_read_only_agent_fallback(message, project_id=req.project_id, project_context=project_context))
        result = _annotate_read_only_agent_result(message, result)
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
        result = _annotate_read_only_agent_result(message, result)
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
    def _create_task(
        series_id: int,
        workflow_type: str,
        qsiprep_task_id: int | None = None,
        *,
        runtime_workflow_type: str | None = None,
    ) -> dict:
        return task_service.create_series_task(
            series_id,
            RunRequest(
                workflow_type=workflow_type,
                runtime_workflow_type=runtime_workflow_type,
                qsiprep_task_id=qsiprep_task_id,
            ),
            confirmed_agent_gate=True,
        )

    confirmation = req.confirmation.model_dump(exclude_none=False)
    agent_run_id = start_agent_run(
        request_type="resume",
        project_id=confirmation.get("project_id"),
        thread_id=thread_id,
        approved=req.approved,
        confirmation=confirmation,
    )
    runner_factory, _default_runner = _agent_runner_factory()
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


def runtime_probe():
    return agent_runtime_probe_status()


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
