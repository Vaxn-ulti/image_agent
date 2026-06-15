from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from app.agent.rag_index import (
    build_local_rag_index,
    local_rag_index_status,
    rag_vendor_coverage_catalog,
    rag_vendor_pointer_integrity,
    vendor_raw_source_status,
)
from app.agent.rag_orchestration import build_rag_response
from app.agent.rag_orchestration import dependency_status as rag_dependency_status
from app.agent.rag_orchestration import grounding_policy as rag_grounding_policy
from app.agent.deepseek import provider_status as legacy_chat_provider_status
from app.agent.model_gateway import provider_status as model_provider_status
from app.core import config
from app.db.database import connect
from app.scripts.verify_scientific_reports import check_output as check_scientific_report_output
from app.scripts.verify_scientific_reports import resolve_task_output_dirs
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
_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_PROJECTS_ROOT = Path(config.PROJECTS_ROOT)


def _repo_root() -> Path:
    return Path(_main_attr("REPO_ROOT", _DEFAULT_REPO_ROOT))


def _projects_root() -> Path:
    main = sys.modules.get("app.main")
    if main is not None and hasattr(main, "PROJECTS_ROOT"):
        main_root = Path(getattr(main, "PROJECTS_ROOT"))
        if main_root != _DEFAULT_PROJECTS_ROOT:
            return main_root
    return Path(config.PROJECTS_ROOT)


def _rows(sql: str, params=()):
    with connect() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


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
    root = _repo_root()
    index_status = local_rag_index_status(root=root, persist_dir=root / ".rag_index")
    indexed_sources = index_status.get("indexed_sources") or []
    return {
        "dependencies": rag_dependency_status(),
        "grounding_policy": rag_grounding_policy(),
        "index": index_status,
        "vendor_raw_sources": vendor_raw_source_status(
            root=root,
            indexed_sources=indexed_sources,
        ),
        "vendor_pointer_integrity": rag_vendor_pointer_integrity(root=root),
        "vendor_coverage_catalog": rag_vendor_coverage_catalog(
            root=root,
            indexed_sources=indexed_sources,
        ),
    }


def agent_rag_rebuild():
    root = _repo_root()
    return build_local_rag_index(root=root, persist_dir=root / ".rag_index")


def agent_model_status():
    return _public_model_status()


def agent_run(req):
    return legacy().agent_run(req)


def agent_run_lookup(agent_run_id):
    return legacy().agent_run_lookup(agent_run_id)


def agent_resume(thread_id, req):
    return legacy().agent_resume(thread_id, req)


def agent_rag_query(req):
    backend_context = {
        "project_id": req.project_id,
        "tasks": _rows(
            "SELECT id, workflow_type, status, progress, error_message FROM tasks WHERE project_id=? ORDER BY id DESC LIMIT 20",
            (req.project_id,),
        )
        if req.project_id
        else [],
        "outputs": _rows(
            "SELECT outputs.task_id, outputs.output_type, outputs.path, outputs.metadata_json FROM outputs JOIN tasks ON tasks.id=outputs.task_id WHERE tasks.project_id=? ORDER BY outputs.id DESC LIMIT 20",
            (req.project_id,),
        )
        if req.project_id
        else [],
    }
    builder = _main_attr("build_rag_response", build_rag_response)
    return builder(req.query, root=_repo_root(), backend_context=backend_context)


def agent_verify_scientific_reports(req):
    projects_root = Path(req.projects_root) if req.projects_root else _projects_root()
    resolver = _main_attr("resolve_task_output_dirs", resolve_task_output_dirs)
    checker = _main_attr("check_scientific_report_output", check_scientific_report_output)
    task_output_dirs, resolution_errors = resolver(projects_root, req.task_ids)
    explicit_output_dirs = [Path(path) for path in req.output_dirs]
    output_paths = [*explicit_output_dirs, *task_output_dirs]
    results = [
        checker(
            path,
            require_container_native_qc=req.require_container_native_qc,
            min_native_qc_images=max(req.min_native_qc_images, 0),
        )
        for path in output_paths
    ]
    required_modalities = {modality.upper() for modality in req.require_modalities}
    present_modalities = {result.modality for result in results}
    missing_modalities = sorted(required_modalities - present_modalities)
    ok = all(result.ok for result in results) and not resolution_errors and not missing_modalities
    return {
        "ok": ok,
        "read_only": True,
        "projects_root": str(projects_root),
        "task_ids": req.task_ids,
        "require_container_native_qc": req.require_container_native_qc,
        "min_native_qc_images": max(req.min_native_qc_images, 0),
        "resolution_errors": resolution_errors,
        "missing_modalities": missing_modalities,
        "results": [
            {
                "output_dir": str(result.output_dir),
                "modality": result.modality,
                "ok": result.ok,
                "errors": result.errors,
                "warnings": result.warnings,
            }
            for result in results
        ],
    }


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
