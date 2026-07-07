from __future__ import annotations

from app.agent.intent import classify_rule_intent, normalize_intent_decision


def test_rule_classifier_detects_inventory_capability_as_authoritative_read_only():
    signal = classify_rule_intent(
        message="先解释我上传了什么，可以跑什么任务，不要启动",
        project_context={"project_id": 1},
    )

    assert signal["category"] == "inventory_capability"
    assert signal["intent"] == "answer_question"
    assert signal["gate"] == "read_only"
    assert signal["confidence"] == 1.0
    assert signal["authoritative"] is True
    assert "inventory_or_capability" in signal["matched_rules"]
    assert "negated_launch" in signal["matched_rules"]


def test_rule_classifier_detects_status_and_result_analysis_questions():
    status_signal = classify_rule_intent(message="show task status", project_context={})
    result_signal = classify_rule_intent(message="请完整分析结果和QC报告", project_context={})

    assert status_signal["category"] == "status_question"
    assert status_signal["intent"] == "answer_question"
    assert status_signal["gate"] == "read_only"
    assert "status_question" in status_signal["matched_rules"]
    assert result_signal["category"] == "result_analysis"
    assert result_signal["intent"] == "answer_question"
    assert result_signal["gate"] == "read_only"
    assert "result_analysis" in result_signal["matched_rules"]


def test_rule_classifier_detects_explicit_fixed_workflow_launch():
    signal = classify_rule_intent(message="请立即运行 T1 工作流", project_context={})

    assert signal["category"] == "fixed_workflow_launch"
    assert signal["intent"] == "run_workflow"
    assert signal["gate"] == "candidate_confirmation"
    assert signal["confidence"] >= 0.9
    assert signal["authoritative"] is False
    assert "explicit_launch" in signal["matched_rules"]


def test_rule_classifier_detects_unknown_workflow_incubation_language():
    signal = classify_rule_intent(message="帮我设计一个新的 DWI 连接组流程", project_context={})

    assert signal["category"] == "toolchain_incubation"
    assert signal["intent"] == "run_workflow"
    assert signal["gate"] == "incubation"
    assert signal["confidence"] >= 0.8
    assert "incubation_language" in signal["matched_rules"]


def test_inventory_question_forces_read_only_even_when_model_requests_run():
    decision, trace = normalize_intent_decision(
        message="我上传了什么文件，可以跑什么任务",
        model_decision={
            "intent": "run_workflow",
            "action_lane": "fixed_workflow",
            "lane": "fixed_workflow",
            "workflow_type": "t1_deepprep_anat_report",
            "requires_confirmation": True,
            "confidence": 0.92,
        },
    )

    assert decision["intent"] == "answer_question"
    assert decision["action_lane"] is None
    assert decision["lane"] is None
    assert decision["requires_confirmation"] is False
    assert decision["intent_decision"]["contract_version"] == "intent_decision.v2"
    assert decision["intent_decision"]["final_category"] == "inventory_capability"
    assert decision["intent_decision"]["final_gate"] == "read_only"
    assert decision["intent_decision"]["confidence"] == 1.0
    assert decision["intent_decision"]["rule_signal"]["authoritative"] is True
    assert decision["recommended_next_step"] == (
        "Answer the uploaded-file inventory and runnable-workflow question before preparing any workflow confirmation."
    )
    assert [item["stage"] for item in trace] == ["intent_rule_classifier", "intent_fusion_gate"]
    assert trace[-1]["status"] == "forced_read_only"


def test_explicit_fixed_workflow_launch_preserves_run_workflow():
    decision, trace = normalize_intent_decision(
        message="请立即运行 T1 工作流",
        model_decision={
            "intent": "run_workflow",
            "action_lane": "fixed_workflow",
            "lane": "fixed_workflow",
            "workflow_type": "t1_deepprep_anat_report",
            "requires_confirmation": True,
            "confidence": 0.84,
        },
    )

    assert decision["intent"] == "run_workflow"
    assert decision["action_lane"] == "fixed_workflow"
    assert decision["lane"] == "fixed_workflow"
    assert decision["requires_confirmation"] is True
    assert decision["intent_decision"]["contract_version"] == "intent_decision.v2"
    assert decision["intent_decision"]["final_category"] == "fixed_workflow_launch"
    assert decision["intent_decision"]["final_gate"] == "confirmation_required"
    assert decision["intent_decision"]["confidence"] == 0.84
    assert [item["stage"] for item in trace] == ["intent_rule_classifier", "intent_fusion_gate"]
    assert trace[-1]["status"] == "candidate_confirmation"


def test_low_confidence_run_request_is_forced_to_read_only_clarification():
    decision, trace = normalize_intent_decision(
        message="处理一下这个数据",
        model_decision={
            "intent": "run_workflow",
            "action_lane": "fixed_workflow",
            "lane": "fixed_workflow",
            "workflow_type": "t1_deepprep_anat_report",
            "requires_confirmation": True,
            "confidence": 0.31,
        },
    )

    assert decision["intent"] == "answer_question"
    assert decision["action_lane"] is None
    assert decision["lane"] is None
    assert decision["requires_confirmation"] is False
    assert decision["intent_decision"]["contract_version"] == "intent_decision.v2"
    assert decision["intent_decision"]["final_category"] == "needs_clarification"
    assert decision["intent_decision"]["final_gate"] == "read_only"
    assert decision["intent_decision"]["confidence"] == 0.31
    assert "low_llm_confidence" in decision["intent_decision"]["reasons"]
    assert decision["recommended_next_step"] == (
        "Ask a clarifying question before preparing a workflow confirmation."
    )
    assert trace[-1]["stage"] == "intent_fusion_gate"
    assert trace[-1]["status"] == "forced_read_only"


def test_incubation_lane_request_keeps_toolchain_metadata():
    decision, trace = normalize_intent_decision(
        message="帮我设计一个新的 DWI 连接组流程",
        model_decision={
            "intent": "run_workflow",
            "action_lane": "toolchain_incubation",
            "lane": "toolchain_incubation",
            "workflow_type": "dwi_magic_connectome_report",
            "toolchain": ["qsiprep", "custom connectome"],
            "requires_confirmation": True,
            "confidence": 0.77,
        },
    )

    assert decision["intent"] == "run_workflow"
    assert decision["action_lane"] == "toolchain_incubation"
    assert decision["lane"] == "toolchain_incubation"
    assert decision["workflow_type"] == "dwi_magic_connectome_report"
    assert decision["toolchain"] == ["qsiprep", "custom connectome"]
    assert decision["intent_decision"]["contract_version"] == "intent_decision.v2"
    assert decision["intent_decision"]["final_category"] == "toolchain_incubation"
    assert decision["intent_decision"]["final_gate"] == "incubation"
    assert decision["intent_decision"]["confidence"] == 0.77
    assert trace[-1]["stage"] == "intent_fusion_gate"
    assert trace[-1]["status"] == "incubation"


def test_fusion_audit_records_rule_llm_conflict_and_keeps_negated_launch_read_only():
    decision, trace = normalize_intent_decision(
        message="先看看能跑什么，不要启动",
        model_decision={
            "intent": "run_workflow",
            "intent_category": "fixed_workflow_launch",
            "intent_subcategory": "t1_processing",
            "action_lane": "fixed_workflow",
            "lane": "fixed_workflow",
            "workflow_type": "t1_deepprep_anat_report",
            "requires_confirmation": True,
            "confidence": 0.97,
            "evidence_spans": ["启动"],
            "risk_level": "medium",
            "ambiguities": [],
            "route_recommendation": "fixed_workflow",
        },
    )

    audit = decision["intent_decision"]
    assert decision["intent"] == "answer_question"
    assert decision["requires_confirmation"] is False
    assert audit["contract_version"] == "intent_decision.v2"
    assert audit["final_intent"] == "answer_question"
    assert audit["final_category"] == "inventory_capability"
    assert audit["final_gate"] == "read_only"
    assert audit["conflict"] is True
    assert audit["rule_signal"]["authoritative"] is True
    assert audit["llm_signal"]["category"] == "fixed_workflow_launch"
    assert "authoritative_rule_overrode_llm" in audit["reasons"]
    assert trace[-1]["stage"] == "intent_fusion_gate"
    assert trace[-1]["status"] == "forced_read_only"


def test_missing_llm_confidence_for_launch_like_request_forces_clarification():
    decision, trace = normalize_intent_decision(
        message="处理一下这个数据",
        model_decision={
            "intent": "run_workflow",
            "intent_category": "fixed_workflow_launch",
            "action_lane": "fixed_workflow",
            "lane": "fixed_workflow",
            "workflow_type": "t1_deepprep_anat_report",
            "requires_confirmation": True,
            "evidence_spans": ["处理"],
            "risk_level": "medium",
            "ambiguities": ["User did not explicitly approve launch."],
            "route_recommendation": "fixed_workflow",
        },
    )

    audit = decision["intent_decision"]
    assert decision["intent"] == "answer_question"
    assert decision["action_lane"] is None
    assert audit["final_category"] == "needs_clarification"
    assert audit["llm_signal"]["confidence"] is None
    assert audit["llm_signal"]["valid"] is False
    assert "missing_llm_confidence" in audit["reasons"]
    assert trace[-1]["status"] == "forced_read_only"


def test_explicit_launch_fusion_allows_candidate_confirmation_with_audit():
    decision, trace = normalize_intent_decision(
        message="请立即运行 T1 工作流",
        model_decision={
            "intent": "run_workflow",
            "intent_category": "fixed_workflow_launch",
            "intent_subcategory": "t1_processing",
            "action_lane": "fixed_workflow",
            "lane": "fixed_workflow",
            "workflow_type": "t1_deepprep_anat_report",
            "requires_confirmation": True,
            "confidence": 0.91,
            "evidence_spans": ["立即运行"],
            "risk_level": "medium",
            "ambiguities": [],
            "route_recommendation": "fixed_workflow",
        },
    )

    audit = decision["intent_decision"]
    assert decision["intent"] == "run_workflow"
    assert decision["action_lane"] == "fixed_workflow"
    assert audit["final_category"] == "fixed_workflow_launch"
    assert audit["final_gate"] == "confirmation_required"
    assert audit["conflict"] is False
    assert audit["rule_signal"]["category"] == "fixed_workflow_launch"
    assert audit["llm_signal"]["confidence"] == 0.91
    assert trace[-1]["stage"] == "intent_fusion_gate"
    assert trace[-1]["status"] == "candidate_confirmation"
