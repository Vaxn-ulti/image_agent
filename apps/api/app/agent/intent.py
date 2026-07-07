from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.workflows.registry import FIXED_WORKFLOW, INCUBATION_LANE


IntentName = Literal["answer_question", "run_workflow"]


class IntentDecision(BaseModel):
    model_config = ConfigDict(extra="allow")

    intent: IntentName = "answer_question"
    action_lane: str | None = None
    lane: str | None = None
    workflow_type: str | None = None
    series_id: int | None = None
    summary: str | None = None
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    requires_confirmation: bool | None = None


def normalize_intent_decision(
    *,
    message: str,
    model_decision: dict[str, Any],
    confidence_threshold: float = 0.55,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = dict(model_decision or {})
    if raw.get("intent") not in ("answer_question", "run_workflow"):
        raw["intent"] = "answer_question"
    raw["confidence"] = _coerce_confidence(raw.get("confidence"))
    decision = IntentDecision.model_validate(raw).model_dump()
    confidence = float(decision.get("confidence") or 0.0)

    if _asks_for_inventory_or_capability_explanation(message):
        return _force_read_only(
            decision,
            category="inventory_capability",
            confidence=1.0,
            source="rule_guard",
            status="forced_read_only_inventory_capability_answer",
            recommended_next_step=(
                "Answer the uploaded-file inventory and runnable-workflow question before preparing any workflow confirmation."
            ),
        )

    if decision.get("intent") == "run_workflow" and confidence < confidence_threshold:
        return _force_read_only(
            decision,
            category="needs_clarification",
            confidence=confidence,
            source="confidence_gate",
            status="forced_read_only_low_confidence",
            recommended_next_step="Ask a clarifying question before preparing a workflow confirmation.",
        )

    lane = decision.get("action_lane") or decision.get("lane")
    if decision.get("intent") == "run_workflow" and lane == INCUBATION_LANE:
        decision["intent_decision"] = {
            "category": "toolchain_incubation",
            "confidence": confidence,
            "source": "model_decision",
            "gate": "incubation",
        }
        return decision, []

    if (
        decision.get("intent") == "run_workflow"
        and (lane or FIXED_WORKFLOW) == FIXED_WORKFLOW
        and not _asks_for_fixed_workflow_confirmation(message)
    ):
        return _force_read_only(
            decision,
            category="fixed_workflow_readiness",
            confidence=confidence,
            source="rule_guard",
            status="forced_read_only_until_explicit_fixed_workflow_launch",
            recommended_next_step=(
                "Explain the current project, uploaded files, possible workflows, and ask before preparing confirmation."
            ),
        )

    if decision.get("intent") == "run_workflow" and (lane or FIXED_WORKFLOW) == FIXED_WORKFLOW:
        decision["intent_decision"] = {
            "category": "fixed_workflow_launch",
            "confidence": confidence,
            "source": "rule_guard",
            "gate": "confirmation_required",
        }
    else:
        decision["intent_decision"] = {
            "category": "read_only_answer",
            "confidence": confidence,
            "source": "model_decision",
            "gate": "read_only",
        }
    return decision, []


def _coerce_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.75
    return max(0.0, min(confidence, 1.0))


def _force_read_only(
    decision: dict[str, Any],
    *,
    category: str,
    confidence: float,
    source: str,
    status: str,
    recommended_next_step: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    updated = {
        **decision,
        "intent": "answer_question",
        "action_lane": None,
        "lane": None,
        "requires_confirmation": False,
        "recommended_next_step": recommended_next_step,
        "intent_decision": {
            "category": category,
            "confidence": confidence,
            "source": source,
            "gate": "read_only",
        },
    }
    trace = [
        {
            "stage": "intent_decision",
            "status": status,
            "category": category,
            "confidence": confidence,
            "production_task_created": False,
        }
    ]
    return updated, trace


def _normalized_text(message: str) -> str:
    return " ".join(str(message or "").lower().split())


def _asks_for_inventory_or_capability_explanation(message: str) -> bool:
    text = _normalized_text(message)
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
        "不要启动",
        "别启动",
        "不要跑",
        "别跑",
        "不要申请",
        "先解释",
        "先回答",
    )
    explicit_launch_tokens = (
        "run now",
        "start now",
        "launch now",
        "create task",
        "submit task",
        "approve",
        "启动",
        "运行",
        "开始跑",
        "直接跑",
        "立即跑",
        "立即运行",
        "创建任务",
        "申请跑",
    )
    if any(token in text for token in explicit_launch_tokens) and not any(
        token in text for token in negated_launch_tokens
    ):
        return False
    inventory_tokens = (
        "what did i upload",
        "what have i uploaded",
        "uploaded files",
        "current uploads",
        "uploaded data",
        "uploaded dataset",
        "上传了什么",
        "上传了哪些",
        "上传的文件",
        "上传的数据",
        "已上传",
        "什么文件",
        "哪些文件",
        "哪些数据",
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
        "what does",
        "explain",
        "possible workflow",
        "available workflow",
        "可以跑什么",
        "能跑什么",
        "可跑",
        "能做哪些",
        "可以做哪些",
        "能处理什么",
        "能做什么",
        "适合做什么",
        "什么任务",
        "什么工作流",
        "哪些工作流",
        "会做什么",
        "解释",
        "说明",
        "处理流程",
    )
    return any(token in text for token in inventory_tokens) or any(token in text for token in capability_tokens)


def _asks_for_fixed_workflow_confirmation(message: str) -> bool:
    text = _normalized_text(message)
    if not text:
        return False
    read_only_phrases = (
        "do not run",
        "don't run",
        "do not start",
        "don't start",
        "do not launch",
        "don't launch",
        "do not execute",
        "don't execute",
        "without launching",
        "no approval",
        "what can run",
        "what task",
        "what workflow",
        "which task",
        "which workflow",
        "can run",
        "runnable",
        "explain",
        "analyze",
        "review",
        "summarize",
        "what did i upload",
        "what have i uploaded",
        "uploaded files",
        "uploaded data",
        "可以跑什么",
        "能跑什么",
        "跑什么",
        "不要启动",
        "别启动",
        "不启动",
        "不要运行",
        "别运行",
        "不运行",
        "不要执行",
        "别执行",
        "不执行",
        "不要跑",
        "别跑",
        "不跑",
        "暂时不",
        "先不要",
        "上传了什么",
        "上传了哪些",
        "哪些数据",
        "什么任务",
        "什么工作流",
        "能做哪些",
        "适合做什么",
        "解释",
        "分析",
        "看看",
        "总结",
        "先回答",
    )
    if any(phrase in text for phrase in read_only_phrases):
        return False
    launch_phrases = (
        "run ",
        "start ",
        "launch ",
        "submit ",
        "execute ",
        "create task",
        "prepare workflow",
        "approve",
        "rerun",
        "retry",
        "开始跑",
        "直接跑",
        "立即跑",
        "立即运行",
        "帮我跑",
        "给我跑",
        "跑这个",
        "启动",
        "运行",
        "创建任务",
        "执行工作流",
        "运行工作流",
        "申请跑",
    )
    return any(phrase in text for phrase in launch_phrases)
