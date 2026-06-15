from __future__ import annotations

import os
import json
from pathlib import Path

from fastapi import HTTPException

from app.agent.backend_context import build_chat_backend_context, build_rag_backend_context
from app.agent.contracts import (
    AGENT_RUN_LOOKUP_CONTRACT_VERSION,
    agent_api_error_detail,
    build_agent_run_response_payload,
    build_chat_compatibility_response,
    build_project_agent_run_history_response,
    normalize_agent_run_result,
)
from app.agent.deepseek import DeepSeekUnavailable, complete_chat
from app.agent.deepseek import provider_status as legacy_chat_provider_status
from app.agent.graph import AgentRunner
from app.agent.model_gateway import ModelGateway, ModelGatewayError
from app.agent.rag_orchestration import build_rag_response
from app.agent.run_ledger import finish_agent_run, list_project_agent_runs, load_agent_run, start_agent_run
from app.agent.status import public_model_status, rag_status, rebuild_rag_index
from app.agent.tools import read_project_context
from app.core import config
from app.db.database import connect, now_iso
from app.db.queries import fetch_rows
from app.scripts.verify_scientific_reports import check_output as check_scientific_report_output
from app.scripts.verify_scientific_reports import resolve_task_output_dirs
from app.schemas import RunRequest
from app.services import task_service
from app.services.runtime_overrides import main_patch_attr, main_projects_root
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


WORKFLOWS = registry_list_workflows()
_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_PROJECTS_ROOT = Path(config.PROJECTS_ROOT)


def _repo_root() -> Path:
    return Path(main_patch_attr("REPO_ROOT", _DEFAULT_REPO_ROOT))


def _projects_root() -> Path:
    return main_projects_root(_DEFAULT_PROJECTS_ROOT, require_override=True)


def _chat_intent(message: str) -> str:
    lowered = message.lower()
    if any(token in lowered for token in ("task", "tasks", "status", "progress", "state", "任务", "状态", "进度", "查看")):
        return "status"
    if any(token in lowered for token in ("next", "下一步", "建议", "tool", "工具", "调用")):
        return "next_step"
    if any(token in lowered for token in ("series", "image", "影像", "序列")):
        return "series"
    return "general"


def _status_reply(tasks: list[dict], recommended_next_step: str) -> str:
    if not tasks:
        return f"Tasks: none. Recommended next step: {recommended_next_step}"
    parts = []
    for task in tasks:
        error = f", error={task['error_message']}" if task.get("error_message") else ""
        parts.append(f"#{task['id']} {task['workflow_type']} {task['status']} {task['progress']}%{error}")
    return "Tasks: " + "; ".join(parts) + f". Recommended next step: {recommended_next_step}"


def health():
    return {"status": "ok", "app": "image_agent", "version": "0.2.0"}


def list_workflows():
    return {"workflows": main_patch_attr("WORKFLOWS", WORKFLOWS)}


def get_result_contract():
    return result_contract_spec()


def deployment():
    mode = os.environ.get("BACKEND_RUNTIME_MODE", "remote")
    return {
        "backend_runtime_mode": mode,
        "api_base_hint": os.environ.get("IMAGE_AGENT_PUBLIC_BASE_URL", ""),
        "agent": public_model_status(),
        "legacy_chat_provider": legacy_chat_provider_status(),
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
    resolver = main_patch_attr("resolve_task_output_dirs", resolve_task_output_dirs)
    checker = main_patch_attr("check_scientific_report_output", check_scientific_report_output)
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
    runtime_inspector = main_patch_attr("inspect_runtime", inspect_runtime)
    return runtime_inspector()


def admin_containers():
    container_lister = main_patch_attr("_list_agent_containers", _list_agent_containers)
    containers = container_lister()
    return {"containers": containers, "count": len(containers)}


def list_project_agent_run_history(project_id):
    return build_project_agent_run_history_response(project_id, list_project_agent_runs(project_id))


def chat(req):
    message = req.message.lower()
    reply = "I can list series, check task status, and explain DICOM, DeepPrep, QSIPrep, QSIRecon, and BOLD workflow results."
    refs = []
    project_context = build_chat_backend_context(
        req.project_id,
        req.message,
        projects_root=_projects_root(),
        workflows=main_patch_attr("WORKFLOWS", WORKFLOWS),
    )
    rag_builder = main_patch_attr("build_rag_response", build_rag_response)
    rag_response = rag_builder(req.message, root=_repo_root(), backend_context=project_context)
    intent = rag_response.get("intent") or _chat_intent(req.message)
    tool_recommendation = next(
        (
            invocation.get("result", {}).get("recommended_action")
            for invocation in rag_response.get("tool_invocations", [])
            if invocation.get("tool") == "recommend_next_action"
        ),
        None,
    )
    recommended_next_step = tool_recommendation or rag_response.get("recommended_next_step") or rag_response.get("tool_chain_hint") or "Inspect backend task state before launching a new workflow."
    used_provider = "rules"
    provider_error = ""
    if intent not in {"status", "next_step", "launchability"}:
        try:
            gateway_factory = main_patch_attr("ModelGateway", ModelGateway)
            reply = gateway_factory().complete_text(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are the built-in chat for image_agent. Answer from backend records first, "
                            "use retrieved RAG only as supporting context, and stay non-diagnostic."
                        ),
                    },
                    {
                        "role": "user",
                        "content": "User message:\n"
                        + req.message
                        + "\n\nBackend project context JSON:\n"
                        + json.dumps(project_context, ensure_ascii=False)[:20000]
                        + "\n\nRetrieved RAG response JSON:\n"
                        + json.dumps(rag_response, ensure_ascii=False)[:12000],
                    },
                ],
                purpose="chat_answer",
            )
            used_provider = "OpenAI"
        except ModelGatewayError as exc:
            provider_error = str(exc)
            try:
                chat_fallback = main_patch_attr("complete_chat", complete_chat)
                reply = chat_fallback(req.message, project_context)
                used_provider = "deepseek"
                provider_error = ""
            except DeepSeekUnavailable as fallback_exc:
                provider_error = f"OpenAI gateway: {provider_error}; DeepSeek fallback: {fallback_exc}"
    message = req.message.lower()
    if intent == "launchability":
        reply = rag_response.get("answer") or "Use workflow_eligibility and backend task records to decide workflow launchability."
        refs = [
            {"type": "rag_source", "source": citation.get("path") or citation.get("source"), "title": citation.get("title")}
            for citation in rag_response.get("citations", [])
            if citation.get("path") or citation.get("source")
        ]
        used_provider = "rules"
    elif "series" in message or "image" in message:
        data = project_context["series"] if req.project_id else []
        reply = "Series: " + (", ".join([f"#{item['id']} {item['modality']} ({item['confidence']:.2f})" for item in data]) or "none")
        used_provider = "rules"
    elif intent in {"status", "next_step"} or "task" in message or "status" in message:
        data = project_context["tasks"]
        reply = _status_reply(data, recommended_next_step)
        refs = [{"type": "task", "id": item["id"]} for item in data if item.get("status") != "not_found_in_project"]
        used_provider = "rules"
    elif "qsiprep" in message:
        if used_provider not in {"OpenAI", "deepseek"}:
            reply = "QSIPrep preprocesses DWI data and requires a DWI NIfTI plus bval/bvec sidecars."
    elif "qsirecon" in message:
        if used_provider not in {"OpenAI", "deepseek"}:
            reply = "QSIRecon reconstructs diffusion models from a completed QSIPrep output."
    elif "dicom" in message:
        if used_provider not in {"OpenAI", "deepseek"}:
            reply = "Upload DICOM studies as a zip archive. Dataset ingest attempts dcm2niix conversion and reports conversion status in inventory."
    elif "alff" in message or "falff" in message or "bold" in message:
        bold_scope = (
            "BOLD/fMRI preprocessing is handled by DeepPrep in this project. "
            "Downstream BOLD structured outputs include ALFF, fALFF, ReHo, DMN, "
            "seed-to-ROI summaries, and fixed-coordinate spherical seed runs."
        )
        reply = bold_scope if used_provider not in {"OpenAI", "deepseek"} else f"{reply}\n\n{bold_scope}"
    elif "deepprep" in message or "t1" in message:
        if used_provider not in {"OpenAI", "deepseek"}:
            reply = "DeepPrep runs anatomical processing for T1 images. Use validate mode to check the command before launching a long job."
    with connect() as conn:
        conn.execute(
            "INSERT INTO chat_messages(project_id, role, content, created_at) VALUES(?,?,?,?)",
            (req.project_id, "user", req.message, now_iso()),
        )
        conn.execute(
            "INSERT INTO chat_messages(project_id, role, content, created_at) VALUES(?,?,?,?)",
            (req.project_id, "assistant", reply, now_iso()),
        )
    return build_chat_compatibility_response(
        {
            "reply": reply,
            "references": refs,
            "provider": used_provider,
            "provider_error": provider_error,
            "intent": intent,
            "recommended_next_step": recommended_next_step,
            "tool_chain_hint": rag_response.get("tool_chain_hint"),
            "tool_invocations": rag_response.get("tool_invocations", []),
            "rag_mode": rag_response.get("mode"),
        }
    )
