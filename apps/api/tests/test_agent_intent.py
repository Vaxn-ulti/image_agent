from __future__ import annotations

from app.agent.intent import normalize_intent_decision


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
    assert decision["intent_decision"] == {
        "category": "inventory_capability",
        "confidence": 1.0,
        "source": "rule_guard",
        "gate": "read_only",
    }
    assert decision["recommended_next_step"] == (
        "Answer the uploaded-file inventory and runnable-workflow question before preparing any workflow confirmation."
    )
    assert trace == [
        {
            "stage": "intent_decision",
            "status": "forced_read_only_inventory_capability_answer",
            "category": "inventory_capability",
            "confidence": 1.0,
            "production_task_created": False,
        }
    ]


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
    assert decision["intent_decision"] == {
        "category": "fixed_workflow_launch",
        "confidence": 0.84,
        "source": "rule_guard",
        "gate": "confirmation_required",
    }
    assert trace == []


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
    assert decision["intent_decision"] == {
        "category": "needs_clarification",
        "confidence": 0.31,
        "source": "confidence_gate",
        "gate": "read_only",
    }
    assert decision["recommended_next_step"] == (
        "Ask a clarifying question before preparing a workflow confirmation."
    )
    assert trace == [
        {
            "stage": "intent_decision",
            "status": "forced_read_only_low_confidence",
            "category": "needs_clarification",
            "confidence": 0.31,
            "production_task_created": False,
        }
    ]


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
    assert decision["intent_decision"] == {
        "category": "toolchain_incubation",
        "confidence": 0.77,
        "source": "model_decision",
        "gate": "incubation",
    }
    assert trace == []
