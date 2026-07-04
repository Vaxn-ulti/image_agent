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
    if _is_inventory_capability_question(message):
        return "inventory_capability"
    lowered = message.lower()
    if any(token in lowered for token in ("task", "tasks", "status", "progress", "state", "浠诲姟", "鐘舵€?", "杩涘害", "鏌ョ湅")):
        return "status"
    if any(token in lowered for token in ("next", "涓嬩竴姝?", "寤鸿", "tool", "宸ュ叿", "璋冪敤")):
        return "next_step"
    if any(token in lowered for token in ("series", "image", "褰卞儚", "搴忓垪")):
        return "series"
    return "general"


def _is_inventory_capability_question(message: str) -> bool:
    text = " ".join(str(message or "").lower().split())
    if not text:
        return False
    negated_launch_tokens = (
        "do not run",
        "don't run",
        "do not start",
        "don't start",
        "do not launch",
        "without launching",
        "no approval",
        "\u4e0d\u8981\u542f\u52a8",
        "\u522b\u542f\u52a8",
        "\u4e0d\u8981\u8dd1",
        "\u522b\u8dd1",
        "\u4e0d\u8981\u7533\u8bf7",
        "\u5148\u89e3\u91ca",
        "\u5148\u56de\u7b54",
    )
    explicit_launch_tokens = (
        "run now",
        "start now",
        "launch now",
        "create task",
        "submit task",
        "approve",
        "\u542f\u52a8",
        "\u5f00\u59cb\u8dd1",
        "\u76f4\u63a5\u8dd1",
        "\u7acb\u5373\u8dd1",
        "\u521b\u5efa\u4efb\u52a1",
        "\u7533\u8bf7\u8dd1",
    )
    if any(token in text for token in explicit_launch_tokens) and not any(token in text for token in negated_launch_tokens):
        return False
    inventory_tokens = (
        "what did i upload",
        "what have i uploaded",
        "uploaded files",
        "current uploads",
        "uploaded data",
        "uploaded dataset",
        "\u4e0a\u4f20\u4e86\u4ec0\u4e48",
        "\u4e0a\u4f20\u4e86\u54ea\u4e9b",
        "\u4e0a\u4f20\u7684\u6587\u4ef6",
        "\u4e0a\u4f20\u7684\u6570\u636e",
        "\u5df2\u4e0a\u4f20",
        "\u4ec0\u4e48\u6587\u4ef6",
        "\u54ea\u4e9b\u6587\u4ef6",
        "\u54ea\u4e9b\u6570\u636e",
    )
    capability_tokens = (
        "what workflow",
        "what task",
        "what can run",
        "which workflow",
        "which task",
        "can run",
        "can process",
        "can do",
        "runnable",
        "possible workflow",
        "available workflow",
        "\u53ef\u4ee5\u8dd1\u4ec0\u4e48",
        "\u80fd\u8dd1\u4ec0\u4e48",
        "\u53ef\u8dd1",
        "\u80fd\u505a\u54ea\u4e9b",
        "\u53ef\u4ee5\u505a\u54ea\u4e9b",
        "\u80fd\u5904\u7406\u4ec0\u4e48",
        "\u80fd\u505a\u4ec0\u4e48",
        "\u9002\u5408\u505a\u4ec0\u4e48",
        "\u4ec0\u4e48\u4efb\u52a1",
        "\u4ec0\u4e48\u5de5\u4f5c\u6d41",
        "\u54ea\u4e9b\u5de5\u4f5c\u6d41",
        "\u4f1a\u505a\u4ec0\u4e48",
        "\u5904\u7406\u6d41\u7a0b",
    )
    return any(token in text for token in inventory_tokens) or any(token in text for token in capability_tokens)


def _is_result_analysis_question(message: str) -> bool:
    text = " ".join(str(message or "").lower().split())
    return any(
        token in text
        for token in (
            "analyze result",
            "analyse result",
            "analyze results",
            "analyse results",
            "analyze the latest",
            "explain result",
            "explain results",
            "explain the reports",
            "task status and results",
            "result-summary",
            "result summary",
            "results",
            "outputs",
            "artifacts",
            "reports",
            "qc",
            "\u5206\u6790\u7ed3\u679c",
            "\u5206\u6790\u4e00\u4e0b\u7ed3\u679c",
            "\u66ff\u6211\u5206\u6790\u7ed3\u679c",
            "\u89e3\u91ca\u7ed3\u679c",
            "\u89c2\u5bdf\u7ed3\u679c",
            "\u7ed3\u679c\u600e\u4e48\u6837",
            "\u7ed3\u679c\u6458\u8981",
            "\u62a5\u544a",
            "\u62a5\u544a\u6458\u8981",
            "\u8d28\u63a7",
            "qc\u603b\u7ed3",
            "\u4ea7\u7269",
            "\u8f93\u51fa",
        )
    )


def _line_items(items: list[str]) -> str:
    return "\n".join(f"{index}. {item}" for index, item in enumerate(items, 1))


def _workflow_id(workflow: dict) -> str:
    return str(workflow.get("workflow_type") or workflow.get("type") or "unknown_workflow")


def _inventory_capability_reply(project_context: dict) -> str:
    files = project_context.get("project_files") or []
    series = project_context.get("series") or []
    modalities = {str(item.get("modality") or "").upper() for item in series if item.get("modality")}
    workflows = []
    for workflow in project_context.get("supported_workflows") or []:
        lane = workflow.get("lane")
        modality = str(workflow.get("modality") or "").upper()
        if lane and lane != "fixed_workflow":
            continue
        if workflow.get("agent_selectable") is False:
            continue
        if modalities and modality and modality not in modalities:
            continue
        workflows.append(workflow)
    file_items = [
        f"{item.get('original_name')} ({item.get('file_type') or 'unknown'}, id {item.get('id')})"
        for item in files[:10]
    ] or ["No uploaded files are registered in this project yet."]
    series_items = [
        "{id}: {modality} / {label} / {status}".format(
            id=item.get("id"),
            modality=item.get("modality") or "UNKNOWN",
            label=item.get("sequence_label") or "unlabeled",
            status="supported" if item.get("supported_for_processing", True) else "not supported",
        )
        for item in series[:10]
    ] or ["No imaging series are registered yet."]
    workflow_items = [
        "{workflow_id}: {display}. {capability}".format(
            workflow_id=_workflow_id(workflow),
            display=workflow.get("display_name") or workflow.get("label") or _workflow_id(workflow),
            capability=workflow.get("capability_summary") or "See workflow metadata for processing, QC, and report outputs.",
        )
        for workflow in workflows[:8]
    ] or ["No fixed workflow is currently runnable from the registered series."]
    return (
        "Uploaded files\n"
        + _line_items(file_items)
        + "\n\nDetected series\n"
        + _line_items(series_items)
        + "\n\nRunnable fixed workflows\n"
        + _line_items(workflow_items)
        + "\n\nNo approval request has been created. Tell me which workflow and series you want to prepare, and I will create a confirmation for review."
    )


def _generic_read_only_reply(project_context: dict, recommended_next_step: str) -> str:
    files = project_context.get("project_files") or []
    series = project_context.get("series") or []
    tasks = project_context.get("tasks") or []
    file_items = [
        f"{item.get('original_name')} ({item.get('file_type') or 'unknown'}, id {item.get('id')})"
        for item in files[:8]
    ] or ["No uploaded files are registered in this project yet."]
    series_items = [
        "{id}: {modality} / {label} / {status}".format(
            id=item.get("id"),
            modality=item.get("modality") or "UNKNOWN",
            label=item.get("sequence_label") or "unlabeled",
            status="supported" if item.get("supported_for_processing", True) else "not supported",
        )
        for item in series[:8]
    ] or ["No imaging series are registered yet."]
    task_items = [
        "#{id}: {workflow} {status} {progress}%".format(
            id=item.get("id"),
            workflow=item.get("workflow_type") or "unknown_workflow",
            status=item.get("status") or "unknown",
            progress=item.get("progress") if item.get("progress") is not None else 0,
        )
        for item in tasks[:8]
    ] or ["No workflow tasks are registered yet."]
    return (
        "Project context reviewed\n"
        + "\n\nUploaded files\n"
        + _line_items(file_items)
        + "\n\nDetected series\n"
        + _line_items(series_items)
        + "\n\nCurrent tasks\n"
        + _line_items(task_items)
        + "\n\nNext guidance\n"
        + str(recommended_next_step)
        + "\n\nNo workflow was launched. I will only prepare a workflow confirmation after you explicitly name the workflow and series to run."
    )


def _summary_artifact_paths(summary: dict, section: str, limit: int = 5) -> list[str]:
    outputs = summary.get("outputs") or {}
    items = outputs.get(section) or []
    if not isinstance(items, list):
        return []
    paths = []
    for item in items:
        if not isinstance(item, dict):
            continue
        path = item.get("relative_path") or item.get("path")
        if path:
            paths.append(str(path))
    return paths[:limit]


def _registered_result_summaries(project_context: dict) -> list[dict]:
    summaries = [item for item in project_context.get("result_summaries") or [] if isinstance(item, dict)]
    seen_paths = set()
    for output in project_context.get("outputs") or []:
        path_value = output.get("path")
        if not path_value or path_value in seen_paths:
            continue
        metadata = output.get("metadata") or output.get("metadata_json") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}
        kind = str(metadata.get("kind") or output.get("output_type") or "")
        if kind != "result_summary" and "result_summary" not in str(path_value):
            continue
        seen_paths.add(path_value)
        path = Path(str(path_value))
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            summaries.append(payload)
    return summaries


def _status_reply(project_context: dict, recommended_next_step: str, *, message: str = "") -> str:
    tasks = project_context.get("tasks") or []
    if not tasks:
        return f"Tasks: none. Recommended next step: {recommended_next_step}"
    parts = []
    for task in tasks:
        error = f", error={task['error_message']}" if task.get("error_message") else ""
        parts.append(f"#{task['id']} {task['workflow_type']} {task['status']} {task['progress']}%{error}")
    reply = "Tasks: " + "; ".join(parts) + f". Recommended next step: {recommended_next_step}"
    if not _is_result_analysis_question(message):
        return reply
    summaries = _registered_result_summaries(project_context)
    observation_lines = [
        "task {id}: {workflow} is {status} at {progress}%".format(
            id=task.get("id"),
            workflow=task.get("workflow_type"),
            status=task.get("status"),
            progress=task.get("progress"),
        )
        for task in tasks[:5]
    ]
    artifact_lines = []
    qc_lines = []
    for summary in summaries[:3]:
        reports = _summary_artifact_paths(summary, "reports")
        qc_paths = _summary_artifact_paths(summary, "qc") or _summary_artifact_paths(summary, "figures")
        if reports:
            artifact_lines.append(f"task {summary.get('task_id')}: " + ", ".join(reports))
        if qc_paths:
            qc_lines.append(f"task {summary.get('task_id')}: " + ", ".join(qc_paths))
    if not artifact_lines:
        artifact_lines = ["No result-summary report artifacts are registered for the matched tasks."]
    if not qc_lines:
        qc_lines = ["No QC artifacts were found in the matched result summaries."]
    return (
        reply
        + "\n\nObservation summary\n"
        + _line_items(observation_lines)
        + "\n\nResult artifacts\n"
        + _line_items(artifact_lines)
        + "\n\nQC observations\n"
        + _line_items(qc_lines)
        + "\n\nNo workflow was launched. This is a read-only observation based on backend task records and registered result-summary artifacts."
    )


def _persist_chat_messages(project_id: int | None, user_message: str, assistant_reply: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO chat_messages(project_id, role, content, created_at) VALUES(?,?,?,?)",
            (project_id, "user", user_message, now_iso()),
        )
        conn.execute(
            "INSERT INTO chat_messages(project_id, role, content, created_at) VALUES(?,?,?,?)",
            (project_id, "assistant", assistant_reply, now_iso()),
        )


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
    if _is_inventory_capability_question(req.message):
        reply = _inventory_capability_reply(project_context)
        _persist_chat_messages(req.project_id, req.message, reply)
        return build_chat_compatibility_response(
            {
                "reply": reply,
                "references": [],
                "provider": "rules",
                "provider_error": "",
                "intent": "inventory_capability",
                "recommended_next_step": "Answer completed. Prepare a workflow confirmation only after the user names the workflow and series to run.",
                "tool_chain_hint": "Read-only inventory and workflow capability explanation; no production task or approval request is created.",
                "tool_invocations": [],
                "rag_mode": "backend_context",
            }
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
        reply = _status_reply(project_context, recommended_next_step, message=req.message)
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
    _persist_chat_messages(req.project_id, req.message, reply)
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
