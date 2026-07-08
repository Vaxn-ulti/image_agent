from __future__ import annotations

import json
from pathlib import Path



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
        "\u4e0b\u4e00\u6b65",
        "\u63a5\u4e0b\u6765",
        "\u600e\u4e48\u529e",
        "\u5e94\u8be5\u505a\u4ec0\u4e48",
        "\u5efa\u8bae\u6211\u505a\u4ec0\u4e48",
        "\u5efa\u8bae\u4e0b\u4e00\u6b65",
        "next step",
        "next steps",
        "what should i do next",
        "what next",
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
            "\u5206\u6790\u4e00\u4e0b\u73b0\u5728\u7684\u6570\u636e",
            "\u5206\u6790\u73b0\u5728\u7684\u6570\u636e",
            "\u5206\u6790\u5f53\u524d\u6570\u636e",
            "\u73b0\u5728\u7684\u6570\u636e",
            "\u5f53\u524d\u6570\u636e",
            "\u6570\u636e\u600e\u4e48\u6837",
            "\u5206\u6790\u6570\u636e",
        )
    )


def _line_items(items: list[str]) -> str:
    return "\n".join(f"{index}. {item}" for index, item in enumerate(items, 1))


def _workflow_id(workflow: dict) -> str:
    return str(workflow.get("workflow_type") or workflow.get("type") or "unknown_workflow")


_CHINESE_WORKFLOW_COPY = {
    "t1_deepprep_anat_report": {
        "display": "T1 DeepPrep 解剖处理、质控和报告",
        "capability": "用于 T1 解剖像处理，生成结构指标、质控材料、表格、图像和 HTML 报告。",
    },
    "bold_fmriprep_xcpd_report": {
        "display": "BOLD fMRIPrep + XCP-D 预处理、指标、质控和报告",
        "capability": "用于 BOLD/fMRI 数据预处理和下游指标汇总，需要同项目 T1/anat 数据。",
    },
    "dwi_fast_gpu_dti": {
        "display": "DWI 快速 GPU DTI 处理、图谱指标、质控和报告",
        "capability": "用于 DWI 张量指标处理，需要 NIfTI、bval、bvec 和 eddy 元数据 JSON。",
    },
}


def _file_item(item: dict, *, chinese: bool = False) -> str:
    name = item.get("original_name") or "unnamed file"
    file_type = item.get("file_type") or "unknown"
    file_id = item.get("id")
    if chinese:
        return f"{name}，类型 {file_type}，ID {file_id}"
    return f"{name} ({file_type}, id {file_id})"


def _series_item(item: dict, *, chinese: bool = False) -> str:
    series_id = item.get("id")
    modality = item.get("modality") or "UNKNOWN"
    label = item.get("sequence_label") or "unlabeled"
    supported = bool(item.get("supported_for_processing", True))
    if chinese:
        status = "支持处理" if supported else "暂不支持处理"
        return f"序列 {series_id}：{modality}，{label}，{status}"
    status = "supported" if supported else "not supported"
    return f"{series_id}: {modality} / {label} / {status}"


_CHINESE_TASK_STATUS = {
    "completed": "已完成",
    "failed": "失败",
    "running": "运行中",
    "queued": "排队中",
    "pending": "等待中",
    "cancelled": "已取消",
    "canceled": "已取消",
}


def _task_item(item: dict, *, chinese: bool = False) -> str:
    task_id = item.get("id")
    workflow = item.get("workflow_type") or "unknown_workflow"
    status = str(item.get("status") or "unknown")
    progress = item.get("progress") if item.get("progress") is not None else 0
    error = item.get("error_message")
    if chinese:
        status_text = _CHINESE_TASK_STATUS.get(status.lower(), status)
        error_text = f"，错误：{error}" if error else ""
        return f"任务 #{task_id}：{workflow}，状态 {status_text}，进度 {progress}%{error_text}"
    error_text = f", error={error}" if error else ""
    return f"#{task_id} {workflow} {status} {progress}%{error_text}"


def _workflow_item(workflow: dict, *, chinese: bool = False) -> str:
    workflow_id = _workflow_id(workflow)
    if chinese:
        copy = _CHINESE_WORKFLOW_COPY.get(workflow_id, {})
        display = copy.get("display") or workflow.get("display_name") or workflow.get("label") or workflow_id
        capability = copy.get("capability") or workflow.get("capability_summary") or "请查看工作流元数据了解处理、质控和报告输出。"
        return f"{workflow_id}：{display}。{capability}"
    return "{workflow_id}: {display}. {capability}".format(
        workflow_id=workflow_id,
        display=workflow.get("display_name") or workflow.get("label") or workflow_id,
        capability=workflow.get("capability_summary") or "See workflow metadata for processing, QC, and report outputs.",
    )


def _workflow_display_item(workflow: dict) -> dict:
    metadata = workflow.get("workflow_metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    return {**metadata, **workflow}


def _runnable_fixed_workflows(project_context: dict) -> list[dict]:
    series = project_context.get("series") or []
    modalities = {str(item.get("modality") or "").upper() for item in series if item.get("modality")}
    workflows: list[dict] = []
    seen: set[str] = set()

    def add_workflow(workflow: object, *, require_modality_match: bool = False) -> None:
        if not isinstance(workflow, dict):
            return
        display_item = _workflow_display_item(workflow)
        lane = display_item.get("lane")
        modality = str(display_item.get("modality") or "").upper()
        if lane and lane != "fixed_workflow":
            return
        if display_item.get("agent_selectable") is False:
            return
        if require_modality_match and modalities and modality and modality not in modalities:
            return
        workflow_id = _workflow_id(display_item)
        if workflow_id in seen:
            return
        seen.add(workflow_id)
        workflows.append(display_item)

    for item in series:
        eligibility = item.get("workflow_eligibility")
        if not isinstance(eligibility, dict):
            continue
        for workflow in eligibility.get("runnable_workflows") or []:
            add_workflow(workflow)

    for workflow in project_context.get("supported_workflows") or project_context.get("workflows") or []:
        add_workflow(workflow, require_modality_match=True)
    return workflows


def _looks_chinese(message: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in str(message or ""))


def _inventory_capability_reply(project_context: dict, *, message: str = "") -> str:
    files = project_context.get("project_files") or []
    series = project_context.get("series") or []
    workflows = _runnable_fixed_workflows(project_context)
    if _looks_chinese(message):
        file_items = [_file_item(item, chinese=True) for item in files[:10]] or ["这个项目还没有登记已上传文件。"]
        series_items = [_series_item(item, chinese=True) for item in series[:10]] or ["还没有识别到影像序列。"]
        workflow_items = [
            _workflow_item(workflow, chinese=True)
            for workflow in workflows[:8]
        ] or ["当前已登记序列还没有可运行的固定工作流。"]
        return (
            "已上传文件\n"
            + _line_items(file_items)
            + "\n\n识别到的序列\n"
            + _line_items(series_items)
            + "\n\n可运行的固定工作流\n"
            + _line_items(workflow_items)
            + "\n\n没有创建审批请求。请告诉我要准备哪个工作流和哪条序列，我会先生成确认卡片供你审核。"
        )
    file_items = [_file_item(item) for item in files[:10]] or ["No uploaded files are registered in this project yet."]
    series_items = [_series_item(item) for item in series[:10]] or ["No imaging series are registered yet."]
    workflow_items = [_workflow_item(workflow) for workflow in workflows[:8]] or [
        "No fixed workflow is currently runnable from the registered series."
    ]
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
    if _looks_chinese(message):
        next_step = str(recommended_next_step)
        if next_step == "Review backend task records and registered result artifacts before preparing any workflow.":
            next_step = "先查看后端任务记录和已登记结果产物，再准备任何工作流。"
        task_items = [_task_item(task, chinese=True) for task in tasks[:8]] or ["当前没有任务记录。"]
        base_reply = (
            "项目状态概览\n"
            + "\n\n当前任务\n"
            + _line_items(task_items)
            + "\n\n建议下一步\n"
            + next_step
        )
        if not _is_result_analysis_question(message):
            return base_reply + "\n\n没有启动任何工作流。只有在你明确指定工作流和序列后，我才会生成确认卡片。"
        summaries = _registered_result_summaries(project_context)
        observation_lines = [_task_item(task, chinese=True) for task in tasks[:5]] or ["当前没有任务记录。"]
        artifact_lines = []
        qc_lines = []
        for summary in summaries[:3]:
            reports = _summary_artifact_paths(summary, "reports")
            qc_paths = _summary_artifact_paths(summary, "qc") or _summary_artifact_paths(summary, "figures")
            if reports:
                artifact_lines.append(f"任务 {summary.get('task_id')}：" + "，".join(reports))
            if qc_paths:
                qc_lines.append(f"任务 {summary.get('task_id')}：" + "，".join(qc_paths))
        if not artifact_lines:
            artifact_lines = ["匹配任务还没有登记 result-summary 报告产物。"]
        if not qc_lines:
            qc_lines = ["匹配任务的 result summary 中没有找到 QC 产物。"]
        return (
            base_reply
            + "\n\n观察摘要\n"
            + _line_items(observation_lines)
            + "\n\n结果产物\n"
            + _line_items(artifact_lines)
            + "\n\n质控观察\n"
            + _line_items(qc_lines)
            + "\n\n只读观察：我没有启动任何工作流；以上内容只来自后端任务记录和已登记结果产物。"
        )
    if not tasks:
        return f"Tasks: none. Recommended next step: {recommended_next_step}"
    parts = [_task_item(task) for task in tasks]
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
