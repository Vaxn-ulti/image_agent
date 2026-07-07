from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.workflows.registry import FIXED_WORKFLOW, INCUBATION_LANE


IntentName = Literal["answer_question", "run_workflow"]


class RuleIntentSignal(BaseModel):
    intent: IntentName
    category: str
    gate: str
    confidence: float = Field(ge=0.0, le=1.0)
    authoritative: bool = False
    matched_rules: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class LLMIntentSignal(BaseModel):
    intent: IntentName
    category: str
    subcategory: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    valid: bool = False
    evidence_spans: list[str] = Field(default_factory=list)
    risk_level: str | None = None
    ambiguities: list[str] = Field(default_factory=list)
    route_recommendation: str | None = None


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


def extract_llm_intent_signal(model_decision: dict[str, Any]) -> dict[str, Any]:
    raw = dict(model_decision or {})
    intent = raw.get("intent") if raw.get("intent") in ("answer_question", "run_workflow") else "answer_question"
    confidence_present = "confidence" in raw and raw.get("confidence") is not None
    confidence = _coerce_confidence(raw.get("confidence")) if confidence_present else None
    category = str(raw.get("intent_category") or raw.get("category") or "")
    if not category:
        lane = raw.get("action_lane") or raw.get("lane")
        if intent == "run_workflow" and lane == INCUBATION_LANE:
            category = "toolchain_incubation"
        elif intent == "run_workflow":
            category = "fixed_workflow_launch"
        else:
            category = "read_only_answer"
    evidence_spans = raw.get("evidence_spans") if isinstance(raw.get("evidence_spans"), list) else []
    ambiguities = raw.get("ambiguities") if isinstance(raw.get("ambiguities"), list) else []
    signal = LLMIntentSignal(
        intent=intent,
        category=category,
        subcategory=raw.get("intent_subcategory"),
        confidence=confidence,
        valid=confidence_present,
        evidence_spans=[str(item) for item in evidence_spans],
        risk_level=raw.get("risk_level"),
        ambiguities=[str(item) for item in ambiguities],
        route_recommendation=raw.get("route_recommendation"),
    )
    return signal.model_dump()


def classify_rule_intent(*, message: str, project_context: dict[str, Any] | None = None) -> dict[str, Any]:
    del project_context
    text = _normalized_text(message)
    matched_rules: list[str] = []
    evidence: list[str] = []

    if _contains_any(text, _inventory_tokens()) or _contains_any(text, _capability_tokens()):
        matched_rules.append("inventory_or_capability")
        evidence.append("inventory_or_capability_phrase")
    if _contains_any(text, _negated_launch_tokens()):
        matched_rules.append("negated_launch")
        evidence.append("negated_launch_phrase")
    if _contains_any(text, _status_tokens()):
        matched_rules.append("status_question")
        evidence.append("status_phrase")
    if _contains_any(text, _result_analysis_tokens()):
        matched_rules.append("result_analysis")
        evidence.append("result_analysis_phrase")
    if _contains_any(text, _incubation_tokens()):
        matched_rules.append("incubation_language")
        evidence.append("new_or_custom_workflow_phrase")
    if _contains_any(text, _explicit_launch_tokens()):
        matched_rules.append("explicit_launch")
        evidence.append("launch_phrase")

    if "inventory_or_capability" in matched_rules:
        return RuleIntentSignal(
            intent="answer_question",
            category="inventory_capability",
            gate="read_only",
            confidence=1.0,
            authoritative=True,
            matched_rules=matched_rules,
            evidence=evidence,
        ).model_dump()
    if "negated_launch" in matched_rules:
        return RuleIntentSignal(
            intent="answer_question",
            category="read_only_answer",
            gate="read_only",
            confidence=0.95,
            authoritative=True,
            matched_rules=matched_rules,
            evidence=evidence,
        ).model_dump()
    if "incubation_language" in matched_rules:
        return RuleIntentSignal(
            intent="run_workflow",
            category="toolchain_incubation",
            gate="incubation",
            confidence=0.85,
            authoritative=False,
            matched_rules=matched_rules,
            evidence=evidence,
        ).model_dump()
    if "explicit_launch" in matched_rules:
        return RuleIntentSignal(
            intent="run_workflow",
            category="fixed_workflow_launch",
            gate="candidate_confirmation",
            confidence=0.9,
            authoritative=False,
            matched_rules=matched_rules,
            evidence=evidence,
        ).model_dump()
    if "status_question" in matched_rules:
        return RuleIntentSignal(
            intent="answer_question",
            category="status_question",
            gate="read_only",
            confidence=0.95,
            authoritative=True,
            matched_rules=matched_rules,
            evidence=evidence,
        ).model_dump()
    if "result_analysis" in matched_rules:
        return RuleIntentSignal(
            intent="answer_question",
            category="result_analysis",
            gate="read_only",
            confidence=0.95,
            authoritative=True,
            matched_rules=matched_rules,
            evidence=evidence,
        ).model_dump()
    return RuleIntentSignal(
        intent="answer_question",
        category="read_only_answer",
        gate="read_only",
        confidence=0.4,
        authoritative=False,
        matched_rules=matched_rules,
        evidence=evidence,
    ).model_dump()


def normalize_intent_decision(
    *,
    message: str,
    model_decision: dict[str, Any],
    confidence_threshold: float = 0.55,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = dict(model_decision or {})
    if raw.get("intent") not in ("answer_question", "run_workflow"):
        raw["intent"] = "answer_question"
    llm_signal = extract_llm_intent_signal(raw)
    raw["confidence"] = llm_signal["confidence"] if llm_signal["confidence"] is not None else 0.0
    decision = IntentDecision.model_validate(raw).model_dump()
    rule_signal = classify_rule_intent(message=message, project_context=None)
    lane = decision.get("action_lane") or decision.get("lane")
    final_intent = str(decision.get("intent") or "answer_question")
    final_category = str(llm_signal.get("category") or "read_only_answer")
    final_gate = "read_only"
    reasons: list[str] = []
    status = "read_only"
    confidence = llm_signal.get("confidence")
    if confidence is None:
        confidence = float(rule_signal.get("confidence") or 0.0)

    if rule_signal.get("authoritative"):
        final_intent = str(rule_signal["intent"])
        final_category = str(rule_signal["category"])
        final_gate = str(rule_signal["gate"])
        confidence = float(rule_signal.get("confidence") or confidence or 0.0)
        status = "forced_read_only" if final_gate == "read_only" else str(final_gate)
        reasons.append("authoritative_rule")
        if llm_signal.get("intent") != rule_signal.get("intent") or llm_signal.get("category") != rule_signal.get("category"):
            reasons.append("authoritative_rule_overrode_llm")
    elif final_intent == "run_workflow" and not llm_signal.get("valid"):
        final_intent = "answer_question"
        final_category = "needs_clarification"
        final_gate = "read_only"
        status = "forced_read_only"
        reasons.append("missing_llm_confidence")
    elif final_intent == "run_workflow" and float(confidence) < confidence_threshold:
        final_intent = "answer_question"
        final_category = "needs_clarification"
        final_gate = "read_only"
        status = "forced_read_only"
        reasons.append("low_llm_confidence")
    elif rule_signal.get("gate") == "incubation" or lane == INCUBATION_LANE:
        final_intent = "run_workflow"
        final_category = "toolchain_incubation"
        final_gate = "incubation"
        status = "incubation"
        reasons.append("incubation_route")
    elif final_intent == "run_workflow" and (lane or FIXED_WORKFLOW) == FIXED_WORKFLOW:
        if rule_signal.get("category") == "fixed_workflow_launch" or _asks_for_fixed_workflow_confirmation(message):
            final_category = "fixed_workflow_launch"
            final_gate = "confirmation_required"
            status = "candidate_confirmation"
            reasons.append("explicit_launch_candidate")
        else:
            final_intent = "answer_question"
            final_category = "fixed_workflow_readiness"
            final_gate = "read_only"
            status = "forced_read_only"
            reasons.append("missing_explicit_launch_rule")
    else:
        final_intent = "answer_question"
        final_category = str(rule_signal.get("category") or "read_only_answer")
        final_gate = "read_only"
        reasons.append("read_only_route")

    conflict = bool(
        llm_signal.get("intent") != rule_signal.get("intent")
        or (rule_signal.get("confidence", 0.0) >= 0.8 and llm_signal.get("category") != rule_signal.get("category"))
    )
    decision = {
        **decision,
        "intent": final_intent,
        "requires_confirmation": final_gate == "confirmation_required",
        "intent_decision": _intent_audit(
            final_intent=final_intent,
            final_category=final_category,
            final_gate=final_gate,
            confidence=float(confidence),
            rule_signal=rule_signal,
            llm_signal=llm_signal,
            conflict=conflict,
            reasons=reasons,
        ),
    }
    if final_gate == "read_only":
        decision["action_lane"] = None
        decision["lane"] = None
        decision["requires_confirmation"] = False
        decision["recommended_next_step"] = _recommended_next_step(final_category)
    elif final_gate == "incubation":
        decision["action_lane"] = INCUBATION_LANE
        decision["lane"] = INCUBATION_LANE
        decision["requires_confirmation"] = True
    else:
        decision["action_lane"] = FIXED_WORKFLOW
        decision["lane"] = FIXED_WORKFLOW
        decision["requires_confirmation"] = True
    trace = [
        {
            "stage": "intent_rule_classifier",
            "status": str(rule_signal.get("gate") or "unknown"),
            "category": rule_signal.get("category"),
            "confidence": rule_signal.get("confidence"),
            "production_task_created": False,
        },
        {
            "stage": "intent_fusion_gate",
            "status": status,
            "category": final_category,
            "confidence": float(confidence),
            "production_task_created": False,
        },
    ]
    return decision, trace


def _intent_audit(
    *,
    final_intent: str,
    final_category: str,
    final_gate: str,
    confidence: float,
    rule_signal: dict[str, Any],
    llm_signal: dict[str, Any],
    conflict: bool,
    reasons: list[str],
) -> dict[str, Any]:
    return {
        "contract_version": "intent_decision.v2",
        "final_intent": final_intent,
        "final_category": final_category,
        "final_gate": final_gate,
        "confidence": confidence,
        "rule_signal": rule_signal,
        "llm_signal": llm_signal,
        "conflict": conflict,
        "policy": "rules_override_safety_and_read_only_conflicts",
        "reasons": reasons,
        "category": final_category,
        "gate": final_gate,
        "source": "fusion_gate",
    }


def _recommended_next_step(category: str) -> str:
    if category == "inventory_capability":
        return "Answer the uploaded-file inventory and runnable-workflow question before preparing any workflow confirmation."
    if category == "needs_clarification":
        return "Ask a clarifying question before preparing a workflow confirmation."
    return "Explain the current project, uploaded files, possible workflows, and ask before preparing confirmation."


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


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _negated_launch_tokens() -> tuple[str, ...]:
    return (
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


def _explicit_launch_tokens() -> tuple[str, ...]:
    return (
        "run ",
        "start ",
        "launch ",
        "submit ",
        "execute ",
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


def _inventory_tokens() -> tuple[str, ...]:
    return (
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


def _capability_tokens() -> tuple[str, ...]:
    return (
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


def _status_tokens() -> tuple[str, ...]:
    return (
        "task status",
        "show status",
        "status",
        "progress",
        "running",
        "任务状态",
        "进度",
        "运行到哪",
        "跑到哪",
    )


def _result_analysis_tokens() -> tuple[str, ...]:
    return (
        "result analysis",
        "analyze result",
        "qc report",
        "review result",
        "结果",
        "qc报告",
        "质量控制",
        "完整分析",
        "分析结果",
    )


def _incubation_tokens() -> tuple[str, ...]:
    return (
        "new workflow",
        "custom workflow",
        "design workflow",
        "toolchain",
        "新的",
        "新流程",
        "自定义",
        "设计一个",
        "连接组流程",
    )


def _asks_for_inventory_or_capability_explanation(message: str) -> bool:
    text = _normalized_text(message)
    if not text:
        return False
    if _contains_any(text, _explicit_launch_tokens()) and not _contains_any(text, _negated_launch_tokens()):
        return False
    return _contains_any(text, _inventory_tokens()) or _contains_any(text, _capability_tokens())


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
