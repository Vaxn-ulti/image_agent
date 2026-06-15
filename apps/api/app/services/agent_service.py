from __future__ import annotations

import os
import sys
from typing import Any

from app.agent.deepseek import provider_status as legacy_chat_provider_status
from app.agent.model_gateway import provider_status as model_provider_status
from app.services.compat import legacy
from app.workflows.registry import list_workflows as registry_list_workflows
from app.workflows.result_contract import result_contract_spec

try:
    from app.workflows.pipeline import inspect_runtime
    from app.workflows.recovery import list_image_agent_containers as _list_agent_containers
except ImportError:
    def inspect_runtime() -> dict:
        return {"error": "pipeline runner missing", "workflows": {}}

    def _list_agent_containers():
        return []


def _main_attr(name: str, default: Any) -> Any:
    main = sys.modules.get("app.main")
    if main is not None and hasattr(main, name):
        return getattr(main, name)
    return default


WORKFLOWS = registry_list_workflows()


def health():
    return {"status": "ok", "app": "image_agent", "version": "0.2.0"}


def list_workflows():
    return {"workflows": _main_attr("WORKFLOWS", WORKFLOWS)}


def get_result_contract():
    return result_contract_spec()


def deployment():
    mode = os.environ.get("BACKEND_RUNTIME_MODE", "remote")
    return {
        "backend_runtime_mode": mode,
        "api_base_hint": os.environ.get("IMAGE_AGENT_PUBLIC_BASE_URL", ""),
        "agent": _public_model_status(),
        "legacy_chat_provider": legacy_chat_provider_status(),
    }


def _public_model_status() -> dict[str, Any]:
    status = model_provider_status()
    safe: dict[str, Any] = {
        key: value
        for key, value in status.items()
        if key
        in {
            "provider",
            "configured",
            "base_url",
            "model",
            "review_model",
            "wire_api",
            "reasoning_effort",
            "store",
            "metadata_enabled",
            "context_window",
            "auto_compact_token_limit",
        }
    }
    deployment_status = status.get("deployment") if isinstance(status.get("deployment"), dict) else {}
    safe_deployment = {
        key: deployment_status[key]
        for key in ("backend_runtime_mode", "model_gateway_access")
        if key in deployment_status
    }
    if safe_deployment:
        safe["deployment"] = safe_deployment
    return safe


def agent_rag_status():
    return legacy().agent_rag_status()


def agent_rag_rebuild():
    return legacy().agent_rag_rebuild()


def agent_model_status():
    return _public_model_status()


def agent_run(req):
    return legacy().agent_run(req)


def agent_run_lookup(agent_run_id):
    return legacy().agent_run_lookup(agent_run_id)


def agent_resume(thread_id, req):
    return legacy().agent_resume(thread_id, req)


def agent_rag_query(req):
    return legacy().agent_rag_query(req)


def agent_verify_scientific_reports(req):
    return legacy().agent_verify_scientific_reports(req)


def runtime_containers():
    runtime_inspector = _main_attr("inspect_runtime", inspect_runtime)
    return runtime_inspector()


def admin_containers():
    container_lister = _main_attr("_list_agent_containers", _list_agent_containers)
    containers = container_lister()
    return {"containers": containers, "count": len(containers)}


def list_project_agent_run_history(project_id):
    return legacy().list_project_agent_run_history(project_id)


def chat(req):
    return legacy().chat(req)
