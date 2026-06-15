from __future__ import annotations

import json
from pathlib import Path

from app.agent.backend_context import build_chat_backend_context
from app.agent.contracts import build_chat_compatibility_response
from app.agent.deepseek import DeepSeekUnavailable, complete_chat
from app.agent.model_gateway import ModelGateway, ModelGatewayError
from app.agent.rag_orchestration import build_rag_response
from app.db.database import connect, now_iso
from app.services.runtime_overrides import main_patch_attr


def _chat_intent(message: str) -> str:
    lowered = message.lower()
    if any(token in lowered for token in ("task", "tasks", "status", "progress", "state", "浠诲姟", "鐘舵€?", "杩涘害", "鏌ョ湅")):
        return "status"
    if any(token in lowered for token in ("next", "涓嬩竴姝?", "寤鸿", "tool", "宸ュ叿", "璋冪敤")):
        return "next_step"
    if any(token in lowered for token in ("series", "image", "褰卞儚", "搴忓垪")):
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


def handle_legacy_chat(req, *, repo_root: Path, projects_root: Path, workflows: dict) -> dict:
    message = req.message.lower()
    reply = "I can list series, check task status, and explain DICOM, DeepPrep, QSIPrep, QSIRecon, and BOLD workflow results."
    refs = []
    project_context = build_chat_backend_context(
        req.project_id,
        req.message,
        projects_root=projects_root,
        workflows=workflows,
    )
    rag_builder = main_patch_attr("build_rag_response", build_rag_response)
    rag_response = rag_builder(req.message, root=repo_root, backend_context=project_context)
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
