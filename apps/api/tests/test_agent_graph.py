import json
import sys
import types

from app.agent.graph import AgentRunner
from app.agent.state import IMAGE_AGENT_STATE_FIELDS
from app.workflows.registry import INCUBATION_LANE
from app.agent.incubation import IncubationLedger
from app.agent.thread_store import AgentThreadStore, confirmation_fingerprint


class FakeGateway:
    def __init__(self, decision):
        self.decision = decision
        self.messages = []

    def complete_structured(self, messages, *, purpose, structured_schema=None):
        self.messages.append((purpose, messages, structured_schema))
        return self.decision

    def complete_text(self, messages, *, purpose):
        self.messages.append((purpose, messages))
        return "final answer"


class ShortAnswerGateway(FakeGateway):
    def complete_text(self, messages, *, purpose):
        self.messages.append((purpose, messages))
        return "我先看一下。"


class ChineseShortAnswerGateway(FakeGateway):
    def complete_text(self, messages, *, purpose):
        self.messages.append((purpose, messages))
        return "我先看一下当前项目。"


class DeflectingChineseGateway(FakeGateway):
    def complete_text(self, messages, *, purpose):
        self.messages.append((purpose, messages))
        return "请把你要我先回答的具体问题发给我。"


class ToolCallingFakeGateway(FakeGateway):
    def complete_structured_with_tools(self, messages, *, purpose, tool_context, structured_schema=None, max_tool_rounds=2):
        self.messages.append((purpose, messages, tool_context, structured_schema))
        return {
            "decision": self.decision,
            "tool_trace": [
                {
                    "status": "ok",
                    "tool": "list_workflows",
                    "call_id": "call_1",
                    "result": [{"type": "bold_fmriprep_xcpd_report"}],
                    "production_task_created": False,
                }
            ],
            "tool_messages": [{"role": "user", "content": "Tool results JSON:\n[]"}],
        }


class ToolSkippedFakeGateway(FakeGateway):
    def complete_structured_with_tools(self, messages, *, purpose, tool_context, structured_schema=None, max_tool_rounds=2):
        self.messages.append((purpose, messages, tool_context, structured_schema))
        return {
            "decision": self.decision,
            "tool_trace": [
                {"status": "skipped", "reason": "chat_completions_wire_api_does_not_run_tool_loop"}
            ],
            "tool_messages": [],
        }


class SchemaRequiredGateway:
    def __init__(self, decision):
        self.decision = decision
        self.structured_schema = None

    def complete_structured_with_tools(self, messages, *, purpose, tool_context, structured_schema, max_tool_rounds=2):
        self.structured_schema = structured_schema
        return {"decision": self.decision, "tool_trace": [], "tool_messages": []}

    def complete_text(self, messages, *, purpose):
        return "final answer"


class SchemaRequiredNoToolsGateway:
    def __init__(self, decision):
        self.decision = decision
        self.structured_schema = None

    def complete_structured(self, messages, *, purpose, structured_schema):
        self.structured_schema = structured_schema
        return self.decision

    def complete_text(self, messages, *, purpose):
        return "final answer"


def _assert_planner_schema(schema):
    assert schema["name"] == "agent_planner_decision"
    assert schema["strict"] is True
    assert schema["schema"]["type"] == "object"
    assert schema["schema"]["additionalProperties"] is False
    assert "intent" in schema["schema"]["required"]
    assert "intent" in schema["schema"]["properties"]
    assert "requires_confirmation" in schema["schema"]["required"]
    assert schema["schema"]["properties"]["requires_confirmation"]["type"] == ["boolean", "null"]
    assert set(schema["schema"]["properties"]) == set(schema["schema"]["required"])


def test_image_agent_state_schema_keeps_langgraph_intermediate_fields():
    assert {
        "decision",
        "planner_tool_trace",
        "skill_context",
        "result",
    }.issubset(set(IMAGE_AGENT_STATE_FIELDS))


def test_agent_runner_passes_json_schema_to_tool_enabled_planner():
    gateway = SchemaRequiredGateway({"intent": "answer_question", "summary": "Explain current state"})

    result = AgentRunner(gateway=gateway).run(message="what happened", project_context={"tasks": []})

    assert result["status"] == "answered"
    _assert_planner_schema(gateway.structured_schema)


def test_agent_runner_passes_json_schema_to_no_tools_planner_fallback():
    gateway = SchemaRequiredNoToolsGateway({"intent": "answer_question", "summary": "Explain current state"})

    result = AgentRunner(gateway=gateway).run(message="what happened", project_context={"tasks": []})

    assert result["status"] == "answered"
    _assert_planner_schema(gateway.structured_schema)


def test_agent_runner_returns_confirmation_when_model_plans_workflow():
    gateway = FakeGateway(
        {
            "intent": "run_workflow",
            "action_lane": "fixed_workflow",
            "series_id": 11,
            "workflow_type": "bold_fmriprep_xcpd_report",
            "summary": "Run BOLD fMRIPrep + XCP-D",
        }
    )
    context = {
        "project_id": 7,
        "series": [{"id": 11, "modality": "BOLD", "supported_for_processing": 1}],
        "workflows": [
            {
                "type": "bold_fmriprep_xcpd_report",
                "label": "BOLD fMRIPrep + XCP-D",
                "modality": "BOLD",
                "lane": "fixed_workflow",
                "agent_selectable": True,
            }
        ],
    }

    result = AgentRunner(gateway=gateway).run(message="run bold", project_context=context)

    assert result["status"] == "confirmation_required"
    assert result["thread_id"].startswith("agent_")
    assert result["action_lane"] == "fixed_workflow"
    assert result["confirmation"]["workflow_type"] == "bold_fmriprep_xcpd_report"
    assert result["confirmation"]["series_id"] == 11
    assert result["selected_skill"] == "image-agent-workflow-runner"
    assert result["retrieved_context"]["tool"] == "retrieve_reference_context"


def test_agent_runner_auto_selects_series_when_model_omits_series_id():
    gateway = FakeGateway(
        {
            "intent": "run_workflow",
            "action_lane": "fixed_workflow",
            "workflow_type": "bold_fmriprep_xcpd_report",
            "summary": "Run BOLD fMRIPrep + XCP-D",
        }
    )
    context = {
        "project_id": 7,
        "series": [
            {"id": 12, "modality": "T1", "supported_for_processing": 1, "format": "NIFTI"},
            {
                "id": 11,
                "modality": "BOLD",
                "supported_for_processing": 1,
                "format": "NIFTI_BIDS",
                "metadata": {"dataset_description": True},
                "sequence_label": "rest_bold",
            },
        ],
        "workflows": [
            {
                "type": "bold_fmriprep_xcpd_report",
                "label": "BOLD fMRIPrep + XCP-D",
                "modality": "BOLD",
                "lane": "fixed_workflow",
                "agent_selectable": True,
            }
        ],
    }

    result = AgentRunner(gateway=gateway).run(message="run bold on the best data", project_context=context)

    assert result["status"] == "confirmation_required"
    assert result["confirmation"]["series_id"] == 11
    assert result["decision"]["series_auto_selected"] is True
    assert "series_auto_selected" in result["confirmation"]["risks"]
    assert result["data_candidate_selection"]["status"] == "selected"
    assert result["data_candidate_selection"]["selected"]["series_id"] == 11
    assert any(item.get("stage") == "data_selection" for item in result["tool_trace"])


def test_agent_runner_uses_openai_tool_dispatch_when_gateway_supports_it():
    gateway = ToolCallingFakeGateway(
        {
            "intent": "run_workflow",
            "action_lane": "fixed_workflow",
            "series_id": 11,
            "workflow_type": "bold_fmriprep_xcpd_report",
            "summary": "Run BOLD fMRIPrep + XCP-D",
        }
    )
    context = {
        "project_id": 7,
        "series": [{"id": 11, "modality": "BOLD", "supported_for_processing": 1}],
        "workflows": [
            {
                "type": "bold_fmriprep_xcpd_report",
                "label": "BOLD fMRIPrep + XCP-D",
                "modality": "BOLD",
                "lane": "fixed_workflow",
                "agent_selectable": True,
            }
        ],
    }

    result = AgentRunner(gateway=gateway).run(message="run bold", project_context=context)

    assert result["status"] == "confirmation_required"
    assert result["tool_trace"][0]["mode"] == "openai_function_tools_dispatched"
    assert any(item.get("tool") == "list_workflows" for item in result["tool_trace"])
    assert result["decision"]["intent"] == "run_workflow"


def test_agent_runner_marks_planner_trace_when_gateway_skips_tool_loop():
    gateway = ToolSkippedFakeGateway({"intent": "answer_question", "summary": "Explain current state"})

    result = AgentRunner(gateway=gateway).run(message="what happened", project_context={"tasks": []})

    assert result["status"] == "answered"
    assert result["tool_trace"][0]["mode"] == "openai_structured_without_tool_loop"
    assert result["tool_trace"][1]["reason"] == "chat_completions_wire_api_does_not_run_tool_loop"


def test_agent_runner_answers_when_model_selects_question_intent():
    gateway = FakeGateway({"intent": "answer_question", "summary": "Explain current state"})

    result = AgentRunner(gateway=gateway).run(message="what happened", project_context={"tasks": []})

    assert result["status"] == "answered"
    assert result["answer"] == "final answer"
    assert result["selected_skill"] == "image-agent-operator"


def test_agent_runner_resume_cancels_unapproved_confirmation():
    result = AgentRunner(gateway=None).resume(
        thread_id="thread-1",
        approved=False,
        confirmation={
            "type": "workflow_execution",
            "project_id": 1,
            "series_id": 11,
            "workflow_type": "t1_deepprep",
        },
    )

    assert result["status"] == "cancelled"
    assert result["thread_id"] == "thread-1"


def test_agent_runner_resume_requires_server_side_pending_confirmation(tmp_path):
    result = AgentRunner(gateway=None, thread_store=AgentThreadStore(tmp_path)).resume(
        thread_id="thread-1",
        approved=True,
        confirmation={
            "type": "workflow_execution",
            "project_id": 1,
            "series_id": 11,
            "workflow_type": "t1_deepprep",
        },
    )

    assert result["status"] == "blocked"
    assert result["production_task_created"] is False


def test_confirmation_fingerprint_covers_preflight_and_display_metadata():
    base = {
        "type": "workflow_execution",
        "action_lane": "fixed_workflow",
        "project_id": 1,
        "series_id": 11,
        "workflow_type": "t1_deepprep_anat_report",
        "workflow_metadata": {
            "workflow_type": "t1_deepprep_anat_report",
            "display_name": "T1 DeepPrep anatomical processing, QC, and report",
            "is_report_only": False,
        },
        "preflight": {
            "status": "passed",
            "runtime_workflow_type": "t1_deepprep",
            "checks": [{"name": "series_supported", "status": "passed"}],
        },
        "risks": ["Requires configured FreeSurfer license."],
    }
    changed_preflight = {
        **base,
        "preflight": {
            **base["preflight"],
            "runtime_workflow_type": "t1_deepprep_validate",
        },
    }
    changed_metadata = {
        **base,
        "workflow_metadata": {
            **base["workflow_metadata"],
            "is_report_only": True,
        },
    }

    assert confirmation_fingerprint(base) != confirmation_fingerprint(changed_preflight)
    assert confirmation_fingerprint(base) != confirmation_fingerprint(changed_metadata)


def test_confirmation_fingerprint_ignores_null_optional_fields():
    base = {
        "type": "workflow_execution",
        "project_id": 1,
        "series_id": 11,
        "workflow_type": "t1_deepprep_anat_report",
    }
    with_nulls = {
        **base,
        "runtime_workflow_type": None,
        "data_candidate_selection": None,
        "preflight": {"ok": True, "note": None},
    }
    without_nulls = {
        **base,
        "preflight": {"ok": True},
    }

    assert confirmation_fingerprint(with_nulls) == confirmation_fingerprint(without_nulls)


def test_confirmation_fingerprint_ignores_public_fingerprint_envelope_field():
    confirmation = {
        "type": "workflow_execution",
        "project_id": 1,
        "series_id": 11,
        "workflow_type": "t1_deepprep_anat_report",
        "runtime_workflow_type": "t1_deepprep",
        "preflight": {"ok": True, "runtime_workflow_type": "t1_deepprep"},
    }
    fingerprint = confirmation_fingerprint(confirmation)

    assert confirmation_fingerprint({**confirmation, "fingerprint": fingerprint}) == fingerprint
    assert confirmation_fingerprint({**confirmation, "confirmation_fingerprint": fingerprint}) == fingerprint


def test_agent_runner_resume_marks_approved_server_confirmation_ready_to_launch_without_tool_executor(tmp_path):
    store = AgentThreadStore(tmp_path)
    confirmation = {
        "type": "workflow_execution",
        "action_lane": "fixed_workflow",
        "project_id": 1,
        "series_id": 11,
        "workflow_type": "t1_deepprep_anat_report",
    }
    thread = store.create_pending_confirmation(
        confirmation=confirmation,
        decision={"intent": "run_workflow"},
        selected_skill="image-agent-workflow-runner",
        retrieved_context={},
    )

    result = AgentRunner(gateway=None, thread_store=store).resume(
        thread_id=thread["thread_id"],
        approved=True,
        confirmation=confirmation,
    )

    assert result["status"] == "ready_to_launch"
    assert result["backend_tool"] == "create_workflow_task"
    assert result["tool_input"] == {"project_id": 1, "series_id": 11, "workflow_type": "t1_deepprep_anat_report"}


def test_agent_runner_resume_rejects_wrong_public_fingerprint_field(tmp_path):
    store = AgentThreadStore(tmp_path)
    confirmation = {
        "type": "workflow_execution",
        "action_lane": "fixed_workflow",
        "project_id": 1,
        "series_id": 11,
        "workflow_type": "t1_deepprep_anat_report",
        "runtime_workflow_type": "t1_deepprep",
        "preflight": {"ok": True, "runtime_workflow_type": "t1_deepprep"},
    }
    thread = store.create_pending_confirmation(
        confirmation=confirmation,
        decision={"intent": "run_workflow"},
        selected_skill="image-agent-workflow-runner",
        retrieved_context={},
    )

    result = AgentRunner(gateway=None, thread_store=store).resume(
        thread_id=thread["thread_id"],
        approved=True,
        confirmation={**confirmation, "fingerprint": "0" * 64},
    )

    assert result["status"] == "blocked"
    assert result["production_task_created"] is False


def test_agent_runner_resume_consumes_pending_confirmation_without_tool_executor(tmp_path):
    store = AgentThreadStore(tmp_path)
    confirmation = {
        "type": "workflow_execution",
        "action_lane": "fixed_workflow",
        "project_id": 1,
        "series_id": 11,
        "workflow_type": "t1_deepprep_anat_report",
    }
    thread = store.create_pending_confirmation(
        confirmation=confirmation,
        decision={"intent": "run_workflow"},
        selected_skill="image-agent-workflow-runner",
        retrieved_context={},
    )

    first = AgentRunner(gateway=None, thread_store=store).resume(
        thread_id=thread["thread_id"],
        approved=True,
        confirmation=confirmation,
    )
    second = AgentRunner(gateway=None, thread_store=store).resume(
        thread_id=thread["thread_id"],
        approved=True,
        confirmation=confirmation,
    )

    assert first["status"] == "ready_to_launch"
    assert store.load(thread["thread_id"])["status"] == "ready_to_launch"
    assert second["status"] == "blocked"
    assert second["production_task_created"] is False


def test_agent_runner_resume_blocks_expired_pending_confirmation(tmp_path):
    store = AgentThreadStore(tmp_path)
    confirmation = {
        "type": "workflow_execution",
        "action_lane": "fixed_workflow",
        "project_id": 1,
        "series_id": 11,
        "workflow_type": "t1_deepprep_anat_report",
    }
    thread = store.create_pending_confirmation(
        confirmation=confirmation,
        decision={"intent": "run_workflow"},
        selected_skill="image-agent-workflow-runner",
        retrieved_context={},
    )
    record_path = tmp_path / f"{thread['thread_id']}.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["expires_at"]
    record["expires_at"] = "2000-01-01T00:00:00+00:00"
    record_path.write_text(json.dumps(record), encoding="utf-8")

    result = AgentRunner(gateway=None, thread_store=store).resume(
        thread_id=thread["thread_id"],
        approved=True,
        confirmation=confirmation,
    )

    assert result["status"] == "blocked"
    assert result["production_task_created"] is False
    assert result["events"] == [{"type": "agent.confirmation_expired", "message": "Pending confirmation expired."}]
    assert store.load(thread["thread_id"])["status"] == "expired"


def test_agent_thread_store_persists_pending_confirmation_in_sqlite(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()

    store = AgentThreadStore(tmp_path / "agent_threads")
    confirmation = {
        "type": "workflow_execution",
        "action_lane": "fixed_workflow",
        "project_id": 1,
        "series_id": 11,
        "workflow_type": "t1_deepprep_anat_report",
    }

    thread = store.create_pending_confirmation(
        confirmation=confirmation,
        decision={"intent": "run_workflow"},
        selected_skill="image-agent-workflow-runner",
        retrieved_context={},
    )

    with database.connect() as conn:
        row = conn.execute(
            "SELECT thread_id, status, project_id, series_id, workflow_type, action_lane, expires_at "
            "FROM agent_confirmations WHERE thread_id=?",
            (thread["thread_id"],),
        ).fetchone()
        events = conn.execute(
            "SELECT event_type, from_status, to_status FROM agent_confirmation_events WHERE thread_id=? ORDER BY id",
            (thread["thread_id"],),
        ).fetchall()

    assert dict(row) == {
        "thread_id": thread["thread_id"],
        "status": "pending_confirmation",
        "project_id": 1,
        "series_id": 11,
        "workflow_type": "t1_deepprep_anat_report",
        "action_lane": "fixed_workflow",
        "expires_at": thread["expires_at"],
    }
    assert [dict(event) for event in events] == [
        {
            "event_type": "confirmation_created",
            "from_status": None,
            "to_status": "pending_confirmation",
        }
    ]


def test_agent_thread_store_loads_pending_confirmation_from_sqlite_after_json_missing(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()

    store = AgentThreadStore(tmp_path / "agent_threads")
    confirmation = {
        "type": "workflow_execution",
        "action_lane": "fixed_workflow",
        "project_id": 1,
        "series_id": 11,
        "workflow_type": "t1_deepprep_anat_report",
    }
    thread = store.create_pending_confirmation(
        confirmation=confirmation,
        decision={"intent": "run_workflow"},
        selected_skill="image-agent-workflow-runner",
        retrieved_context={"mode": "local_persistent_index"},
    )
    (tmp_path / "agent_threads" / f"{thread['thread_id']}.json").unlink()

    reloaded = AgentThreadStore(tmp_path / "agent_threads").load(thread["thread_id"])

    assert reloaded is not None
    assert reloaded["status"] == "pending_confirmation"
    assert reloaded["expires_at"] == thread["expires_at"]
    assert reloaded["confirmation"] == confirmation
    assert reloaded["decision"] == {"intent": "run_workflow"}
    assert reloaded["selected_skill"] == "image-agent-workflow-runner"
    assert reloaded["retrieved_context"] == {"mode": "local_persistent_index"}


def test_agent_thread_store_marks_confirmation_transition_in_sqlite(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()

    store = AgentThreadStore(tmp_path / "agent_threads")
    thread = store.create_pending_confirmation(
        confirmation={
            "type": "workflow_execution",
            "action_lane": "fixed_workflow",
            "project_id": 1,
            "series_id": 11,
            "workflow_type": "t1_deepprep_anat_report",
        },
        decision={"intent": "run_workflow"},
        selected_skill="image-agent-workflow-runner",
        retrieved_context={},
    )

    marked = store.mark(thread["thread_id"], status="ready_to_launch", extra={"tool_input": {"series_id": 11}})

    with database.connect() as conn:
        row = conn.execute(
            "SELECT status, consumed_at FROM agent_confirmations WHERE thread_id=?",
            (thread["thread_id"],),
        ).fetchone()
        events = conn.execute(
            "SELECT event_type, from_status, to_status FROM agent_confirmation_events WHERE thread_id=? ORDER BY id",
            (thread["thread_id"],),
        ).fetchall()

    assert marked["status"] == "ready_to_launch"
    assert row["status"] == "ready_to_launch"
    assert row["consumed_at"] is not None
    assert [dict(event) for event in events] == [
        {
            "event_type": "confirmation_created",
            "from_status": None,
            "to_status": "pending_confirmation",
        },
        {
            "event_type": "confirmation_marked",
            "from_status": "pending_confirmation",
            "to_status": "ready_to_launch",
        },
    ]


def test_agent_runner_returns_incubation_proposal_without_confirmation():
    gateway = FakeGateway(
        {
            "intent": "run_workflow",
            "action_lane": "toolchain_incubation",
            "summary": "Try a new BOLD denoise and report chain",
            "toolchain": ["stage_bids", "run_fmriprep", "run_xcpd", "make_report"],
        }
    )

    result = AgentRunner(gateway=gateway).run(message="try a new toolchain", project_context={"project_id": 7})

    assert result["status"] == "toolchain_proposed"
    assert result["action_lane"] == "toolchain_incubation"
    assert result["proposed_toolchain"]["production_task_created"] is False
    assert result["proposed_toolchain"]["proposal_id"].startswith("inc_")
    assert result["selected_skill"] == "image-agent-workflow-runner"


def test_agent_runner_forces_unknown_fixed_workflow_into_incubation(tmp_path):
    gateway = FakeGateway(
        {
            "intent": "run_workflow",
            "action_lane": "fixed_workflow",
            "workflow_type": "dwi_magic_connectome_report",
            "series_id": 24,
            "summary": "Run an unknown fixed workflow",
            "modality": "DWI",
            "script_text": "echo propose unknown workflow",
        }
    )
    context = {
        "project_id": 7,
        "series": [{"id": 24, "modality": "DWI", "supported_for_processing": 1}],
        "workflows": [],
    }

    result = AgentRunner(
        gateway=gateway,
        incubation_ledger=IncubationLedger(tmp_path / "ledger"),
        rag_root=tmp_path,
    ).run(message="run unknown fixed workflow", project_context=context)

    assert result["status"] == "toolchain_proposed"
    assert result["action_lane"] == "toolchain_incubation"
    assert result["production_task_created"] is False
    assert result["proposed_toolchain"]["production_task_created"] is False
    assert "confirmation" not in result


def test_agent_runner_incubation_decomposes_container_script_text(tmp_path):
    script_text = "\n".join(
        [
            "sudo -S docker run --rm --gpus all --network host \\",
            "  -e TEMPLATEFLOW_HOME=/templateflow \\",
            "  -v /project/task/bids:/data:ro \\",
            "  nipreps/fmriprep:latest /data /out participant --participant-label 01",
        ]
    )
    gateway = FakeGateway(
        {
            "intent": "run_workflow",
            "action_lane": "toolchain_incubation",
            "summary": "Inspect a remote fMRIPrep wrapper",
            "modality": "BOLD",
            "script_text": script_text,
        }
    )

    result = AgentRunner(gateway=gateway, incubation_ledger=IncubationLedger(tmp_path / "ledger"), rag_root=tmp_path).run(
        message="拆解这个容器脚本看看能不能孵化新工作流",
        project_context={"project_id": 7},
    )

    chain = result["proposed_toolchain"]["primitive_chain"]
    assert result["status"] == "toolchain_proposed"
    assert len(chain) == 1
    assert chain[0]["kind"] == "container"
    assert chain[0]["image"] == "nipreps/fmriprep:latest"
    assert chain[0]["uses_gpu"] is True
    assert chain[0]["contract"]["stage"] == "fmriprep_preprocessing"
    assert "composition_plan" in result["proposed_toolchain"]
    assert "promotion_gate" in result["proposed_toolchain"]
    assert "fMRIPrep HTML report" in result["proposed_toolchain"]["composition_plan"]["expected_outputs"]
    assert result["proposed_toolchain"]["promotion_gate"]["production_task_created"] is False
    assert result["proposed_toolchain"]["production_task_created"] is False


def test_langgraph_agent_runner_fixed_workflow_returns_confirmation_without_task_creation(tmp_path):
    from app.agent.langgraph_runner import LangGraphAgentRunner

    gateway = FakeGateway(
        {
            "intent": "run_workflow",
            "action_lane": "fixed_workflow",
            "series_id": 11,
            "workflow_type": "t1_deepprep_anat_report",
            "summary": "Run T1 DeepPrep segmentation",
        }
    )
    context = {
        "project_id": 7,
        "series": [{"id": 11, "modality": "T1", "supported_for_processing": 1}],
        "workflows": [
            {
                "type": "t1_deepprep_anat_report",
                "label": "T1 DeepPrep",
                "modality": "T1",
                "lane": "fixed_workflow",
                "agent_selectable": True,
            }
        ],
    }

    result = LangGraphAgentRunner(
        gateway=gateway,
        incubation_ledger=IncubationLedger(tmp_path / "ledger"),
        rag_root=tmp_path,
        thread_store=AgentThreadStore(tmp_path / "threads"),
    ).run(message="run T1 segmentation", project_context=context)

    assert result["status"] == "confirmation_required"
    assert result["action_lane"] == "fixed_workflow"
    assert result["production_task_created"] is False
    assert result["confirmation"]["workflow_type"] == "t1_deepprep_anat_report"
    assert result["confirmation"]["workflow_metadata"]["workflow_type"] == "t1_deepprep_anat_report"
    assert result["confirmation"]["workflow_metadata"]["display_name"] == "T1 DeepPrep anatomical processing, QC, and report"
    assert result["confirmation"]["workflow_metadata"]["workflow_family"] == "t1"
    assert result["confirmation"]["workflow_metadata"]["workflow_role"] == "anat_processing"
    assert result["confirmation"]["workflow_metadata"]["pipeline_stages"]
    assert result["confirmation"]["workflow_metadata"]["primary_outputs"]
    assert result["confirmation"]["workflow_metadata"]["is_report_only"] is False
    assert result["safe_metadata"]["agent_engine"] == "langgraph"
    assert result["safe_metadata"]["lane"] == "fixed_workflow"
    assert result["safe_metadata"]["graph_runtime"] in {"langgraph", "deterministic_fallback"}
    assert result["graph_state"]["workflow_match"]["status"] == "exact_fixed_match"
    assert result["graph_state"]["preflight"]["ok"] is True


def test_langgraph_agent_runner_answers_inventory_and_capability_question_without_confirmation(tmp_path):
    from app.agent.langgraph_runner import LangGraphAgentRunner

    gateway = FakeGateway(
        {
            "intent": "run_workflow",
            "action_lane": "fixed_workflow",
            "series_id": 11,
            "workflow_type": "t1_deepprep_anat_report",
            "summary": "Explain runnable T1 workflow",
            "recommended_next_step": "Prepare t1_deepprep_anat_report confirmation now.",
        }
    )
    context = {
        "project_id": 7,
        "project_files": [
            {"id": 31, "original_name": "sub-01_T1w.nii.gz", "file_type": "NIFTI"},
        ],
        "series": [{"id": 11, "modality": "T1", "sequence_label": "T1w_MPRAGE", "supported_for_processing": 1}],
        "workflows": [
            {
                "type": "t1_deepprep_anat_report",
                "display_name": "T1 DeepPrep anatomical processing, QC, and report",
                "capability_summary": "Runs T1 anatomical preprocessing, segmentation, QC, and report generation.",
                "modality": "T1",
                "lane": "fixed_workflow",
                "agent_selectable": True,
            }
        ],
    }

    result = LangGraphAgentRunner(
        gateway=gateway,
        incubation_ledger=IncubationLedger(tmp_path / "ledger"),
        rag_root=tmp_path,
        thread_store=AgentThreadStore(tmp_path / "threads"),
    ).run(message="\u6211\u4e0a\u4f20\u4e86\u4ec0\u4e48\u6587\u4ef6\uff0c\u53ef\u4ee5\u8dd1\u4ec0\u4e48\u4efb\u52a1", project_context=context)

    assert result["status"] == "answered"
    assert result["intent"] == "answer_question"
    assert "confirmation" not in result
    assert result["production_task_created"] is False
    assert result["safe_metadata"]["lane"] == "read_only"
    assert result["decision"]["intent"] == "answer_question"
    assert result["decision"]["recommended_next_step"].startswith("Answer the uploaded-file inventory")
    answer_prompt = gateway.messages[-1][1][-1]["content"]
    assert "sub-01_T1w.nii.gz" in answer_prompt
    assert "t1_deepprep_anat_report" in answer_prompt


def test_langgraph_agent_runner_inventory_answer_is_complete_even_if_model_stops_early(tmp_path):
    from app.agent.langgraph_runner import LangGraphAgentRunner

    gateway = ShortAnswerGateway(
        {
            "intent": "run_workflow",
            "action_lane": "fixed_workflow",
            "series_id": 11,
            "workflow_type": "t1_deepprep_anat_report",
            "summary": "Prepare T1 workflow",
        }
    )
    context = {
        "project_id": 7,
        "project_files": [
            {"id": 31, "original_name": "sub-01_T1w.nii.gz", "file_type": "NIFTI"},
            {"id": 32, "original_name": "sub-01_T1w.json", "file_type": "JSON"},
        ],
        "series": [{"id": 11, "modality": "T1", "sequence_label": "T1w_MPRAGE", "supported_for_processing": 1}],
        "workflows": [
            {
                "type": "t1_deepprep_anat_report",
                "display_name": "T1 DeepPrep anatomical processing, QC, and report",
                "capability_summary": "Runs T1 anatomical preprocessing, segmentation, QC, and report generation.",
                "modality": "T1",
                "lane": "fixed_workflow",
                "agent_selectable": True,
            }
        ],
    }

    result = LangGraphAgentRunner(
        gateway=gateway,
        incubation_ledger=IncubationLedger(tmp_path / "ledger"),
        rag_root=tmp_path,
        thread_store=AgentThreadStore(tmp_path / "threads"),
    ).run(message="我上传了什么文件，可以跑什么任务", project_context=context)

    assert result["status"] == "answered"
    assert result["safe_metadata"]["lane"] == "read_only"
    assert "confirmation" not in result
    assert "已上传文件" in result["answer"]
    assert "sub-01_T1w.nii.gz" in result["answer"]
    assert "识别到的序列" in result["answer"]
    assert "T1w_MPRAGE" in result["answer"]
    assert "可运行的固定工作流" in result["answer"]
    assert "t1_deepprep_anat_report" in result["answer"]
    assert "没有创建审批请求" in result["answer"]
    assert "Approval required" not in result["answer"]


def test_langgraph_agent_runner_inventory_fallback_uses_chinese_for_chinese_question(tmp_path):
    from app.agent.langgraph_runner import LangGraphAgentRunner

    gateway = ShortAnswerGateway(
        {
            "intent": "run_workflow",
            "action_lane": "fixed_workflow",
            "series_id": 11,
            "workflow_type": "t1_deepprep_anat_report",
            "summary": "Prepare T1 workflow",
        }
    )
    context = {
        "project_id": 7,
        "project_files": [
            {"id": 31, "original_name": "sub-01_T1w.nii.gz", "file_type": "NIFTI"},
        ],
        "series": [{"id": 11, "modality": "T1", "sequence_label": "T1w_MPRAGE", "supported_for_processing": 1}],
        "workflows": [
            {
                "type": "t1_deepprep_anat_report",
                "display_name": "T1 DeepPrep anatomical processing, QC, and report",
                "capability_summary": "Runs T1 anatomical preprocessing, segmentation, QC, and report generation.",
                "modality": "T1",
                "lane": "fixed_workflow",
                "agent_selectable": True,
            }
        ],
    }

    result = LangGraphAgentRunner(
        gateway=gateway,
        incubation_ledger=IncubationLedger(tmp_path / "ledger"),
        rag_root=tmp_path,
        thread_store=AgentThreadStore(tmp_path / "threads"),
    ).run(message="我上传了什么文件，可以跑什么任务", project_context=context)

    assert result["status"] == "answered"
    assert "已上传文件" in result["answer"]
    assert "识别到的序列" in result["answer"]
    assert "可运行的固定工作流" in result["answer"]
    assert "没有创建审批请求" in result["answer"]
    assert "Uploaded files" not in result["answer"]
    assert "No approval request" not in result["answer"]


def test_langgraph_agent_runner_explains_uploads_when_user_negates_launch(tmp_path):
    from app.agent.langgraph_runner import LangGraphAgentRunner

    gateway = ShortAnswerGateway(
        {
            "intent": "run_workflow",
            "action_lane": "fixed_workflow",
            "series_id": 11,
            "workflow_type": "t1_deepprep_anat_report",
            "summary": "Prepare T1 workflow",
        }
    )
    context = {
        "project_id": 7,
        "project_files": [
            {"id": 31, "original_name": "sub-01_T1w.nii.gz", "file_type": "NIFTI"},
        ],
        "series": [{"id": 11, "modality": "T1", "sequence_label": "T1w_MPRAGE", "supported_for_processing": 1}],
        "workflows": [
            {
                "type": "t1_deepprep_anat_report",
                "display_name": "T1 DeepPrep anatomical processing, QC, and report",
                "capability_summary": "Runs T1 anatomical preprocessing, segmentation, QC, and report generation.",
                "modality": "T1",
                "lane": "fixed_workflow",
                "agent_selectable": True,
            }
        ],
    }

    result = LangGraphAgentRunner(
        gateway=gateway,
        incubation_ledger=IncubationLedger(tmp_path / "ledger"),
        rag_root=tmp_path,
        thread_store=AgentThreadStore(tmp_path / "threads"),
    ).run(
        message="\u6211\u4e0a\u4f20\u4e86\u54ea\u4e9b\u6570\u636e\uff0c\u80fd\u505a\u54ea\u4e9b\u5904\u7406\uff1f\u5148\u89e3\u91ca\uff0c\u4e0d\u8981\u542f\u52a8",
        project_context=context,
    )

    assert result["status"] == "answered"
    assert result["safe_metadata"]["lane"] == "read_only"
    assert result["production_task_created"] is False
    assert "confirmation" not in result
    assert "已上传文件" in result["answer"]
    assert "sub-01_T1w.nii.gz" in result["answer"]
    assert "可运行的固定工作流" in result["answer"]
    assert "没有创建审批请求" in result["answer"]


def test_langgraph_agent_runner_treats_negated_chinese_launch_as_read_only(tmp_path):
    from app.agent.langgraph_runner import LangGraphAgentRunner

    gateway = ShortAnswerGateway(
        {
            "intent": "run_workflow",
            "action_lane": "fixed_workflow",
            "series_id": 11,
            "workflow_type": "t1_deepprep_anat_report",
            "summary": "Prepare T1 workflow",
        }
    )
    context = {
        "project_id": 7,
        "project_files": [
            {"id": 31, "original_name": "sub-01_T1w.nii.gz", "file_type": "NIFTI"},
        ],
        "series": [{"id": 11, "modality": "T1", "sequence_label": "T1w_MPRAGE", "supported_for_processing": 1}],
        "workflows": [
            {
                "type": "t1_deepprep_anat_report",
                "display_name": "T1 DeepPrep anatomical processing, QC, and report",
                "capability_summary": "Runs T1 anatomical preprocessing, segmentation, QC, and report generation.",
                "modality": "T1",
                "lane": "fixed_workflow",
                "agent_selectable": True,
            }
        ],
    }

    result = LangGraphAgentRunner(
        gateway=gateway,
        incubation_ledger=IncubationLedger(tmp_path / "ledger"),
        rag_root=tmp_path,
        thread_store=AgentThreadStore(tmp_path / "threads"),
    ).run(
        message="\u4e0d\u8981\u542f\u52a8 t1_deepprep_anat_report",
        project_context=context,
    )

    assert result["status"] == "answered"
    assert result["safe_metadata"]["lane"] == "read_only"
    assert result["production_task_created"] is False
    assert "confirmation" not in result
    assert "No workflow was launched" in result["answer"]
    assert "Approval required" not in result["answer"]


def test_fixed_workflow_confirmation_gate_rejects_negated_chinese_launch():
    message = "\u4e0d\u8981\u542f\u52a8 t1_deepprep_anat_report"

    assert AgentRunner._asks_for_fixed_workflow_confirmation(message) is False


def test_langgraph_agent_runner_uses_compiled_stategraph_when_runtime_available(tmp_path, monkeypatch):
    class FakeCompiledGraph:
        def __init__(self, graph):
            self.graph = graph

        def invoke(self, state):
            node_name = self.graph.entry
            while node_name != "__end__":
                state.update(self.graph.nodes[node_name](state))
                if node_name in self.graph.conditional_edges:
                    route_fn, mapping = self.graph.conditional_edges[node_name]
                    node_name = mapping[route_fn(state)]
                else:
                    node_name = self.graph.edges[node_name]
            return state

    class FakeStateGraph:
        def __init__(self, state_type):
            self.state_type = state_type
            self.nodes = {}
            self.edges = {}
            self.conditional_edges = {}
            self.entry = None

        def add_node(self, name, node):
            self.nodes[name] = node

        def set_entry_point(self, name):
            self.entry = name

        def add_edge(self, source, target):
            self.edges[source] = target

        def add_conditional_edges(self, source, route_fn, mapping):
            self.conditional_edges[source] = (route_fn, mapping)

        def compile(self):
            return FakeCompiledGraph(self)

    fake_langgraph = types.ModuleType("langgraph")
    fake_graph = types.ModuleType("langgraph.graph")
    fake_graph.END = "__end__"
    fake_graph.StateGraph = FakeStateGraph
    monkeypatch.setitem(sys.modules, "langgraph", fake_langgraph)
    monkeypatch.setitem(sys.modules, "langgraph.graph", fake_graph)

    from app.agent.langgraph_runner import LangGraphAgentRunner

    result = LangGraphAgentRunner(
        gateway=FakeGateway({"intent": "answer_question", "summary": "Explain status"}),
        rag_root=tmp_path,
    ).run(message="status?", project_context={"project_id": 7, "tasks": [], "workflows": []})

    assert result["status"] == "answered"
    assert result["answer"] == "final answer"
    assert result["safe_metadata"]["graph_runtime"] == "langgraph"
    assert result["graph_state"]["lane"] == "read_only"


def test_langgraph_agent_runner_read_only_result_exposes_intent_and_answer(tmp_path):
    from app.agent.langgraph_runner import LangGraphAgentRunner

    gateway = FakeGateway({"intent": "answer_question", "summary": "Explain current state"})

    result = LangGraphAgentRunner(gateway=gateway, rag_root=tmp_path).run(
        message="what happened",
        project_context={"tasks": []},
    )

    assert result["status"] == "answered"
    assert result["intent"] == "answer_question"
    assert result["decision"]["intent"] == "answer_question"
    assert result["answer"] == "final answer"
    assert [event["type"] for event in result["events"]][:6] == [
        "agent.graph.run_intake",
        "agent.graph.safety_risk_router",
        "agent.graph.classify_intent",
        "agent.graph.answer_or_task_router",
        "agent.graph.retrieve_rag",
        "agent.graph.select_skill",
    ]


def test_langgraph_agent_runner_unknown_workflow_returns_structured_incubation_proposal(tmp_path):
    from app.agent.langgraph_runner import LangGraphAgentRunner

    gateway = FakeGateway(
        {
            "intent": "run_workflow",
            "action_lane": INCUBATION_LANE,
            "summary": "DWI tractography and connectome matrix",
            "modality": "DWI",
            "toolchain": ["qsiprep preprocessing", "qsirecon reconstruction", "connectivity matrix"],
        }
    )

    result = LangGraphAgentRunner(
        gateway=gateway,
        incubation_ledger=IncubationLedger(tmp_path / "ledger"),
        rag_root=tmp_path,
    ).run(
        message="explore DWI tractography connectome",
        project_context={"project_id": 7, "series": [{"id": 24, "modality": "DWI"}], "workflows": []},
    )

    proposal = result["proposed_toolchain"]
    assert result["status"] == "toolchain_proposed"
    assert result["action_lane"] == INCUBATION_LANE
    assert result["production_task_created"] is False
    assert result["task_creation_allowed"] is False
    assert proposal["contract_version"] == "toolchain_proposal.v1"
    assert proposal["lane"] == INCUBATION_LANE
    assert proposal["task_creation_allowed"] is False
    assert proposal["forbidden_actions"] == ["confirmation_creation", "production_task_creation", "pipeline_runner_launch"]
    assert proposal["production_task_created"] is False
    assert proposal["promotion_status"] == "blocked_by_gaps"
    assert proposal["input_contract"]["modality"] == "DWI"
    assert proposal["output_contract"]["result_summary_schema"]
    assert proposal["runner_contract"]["command_template_status"] == "draft_only"
    assert proposal["mock_control_plane_plan"]
    assert proposal["real_acceptance_plan"]
    assert "No fixed workflow registry entry exists." in proposal["blocking_gaps"]
    assert result["safe_metadata"]["agent_engine"] == "langgraph"
    assert result["graph_state"]["lane"] == INCUBATION_LANE


def test_langgraph_agent_runner_forces_unknown_fixed_workflow_into_incubation(tmp_path, monkeypatch):
    from app.agent.langgraph_runner import LangGraphAgentRunner
    from app.agent import graph as agent_graph
    from app.services import task_service

    gateway = FakeGateway(
        {
            "intent": "run_workflow",
            "action_lane": "fixed_workflow",
            "workflow_type": "dwi_magic_connectome_report",
            "series_id": 24,
            "summary": "Run a new DWI connectome report workflow",
            "modality": "DWI",
        }
    )
    production_calls = []

    def fail_if_production_task_created(*args, **kwargs):
        production_calls.append((args, kwargs))
        raise AssertionError("unknown workflow must not touch production task creation")

    monkeypatch.setattr(task_service, "create_series_task", fail_if_production_task_created)
    monkeypatch.setattr(task_service, "run_pipeline_task", fail_if_production_task_created)
    monkeypatch.setattr(agent_graph, "create_workflow_task", fail_if_production_task_created)

    ledger = IncubationLedger(tmp_path / "ledger")
    result = LangGraphAgentRunner(
        gateway=gateway,
        incubation_ledger=ledger,
        rag_root=tmp_path,
        thread_store=AgentThreadStore(tmp_path / "threads"),
    ).run(
        message="run dwi_magic_connectome_report on series 24",
        project_context={
            "project_id": 7,
            "series": [{"id": 24, "modality": "DWI", "supported_for_processing": 1}],
            "workflows": [],
        },
    )

    assert result["status"] == "toolchain_proposed"
    assert result["action_lane"] == INCUBATION_LANE
    assert result["production_task_created"] is False
    assert result["task_creation_allowed"] is False
    assert result["safe_metadata"]["lane"] == INCUBATION_LANE
    assert result["graph_state"]["workflow_match"] == {
        "status": "no_fixed_match",
        "workflow_type": "dwi_magic_connectome_report",
        "reason": "workflow is not a fixed registry entry",
    }
    assert "confirmation" not in result
    proposal = result["proposed_toolchain"]
    assert proposal["contract_version"] == "toolchain_proposal.v1"
    assert proposal["task_creation_allowed"] is False
    assert proposal["forbidden_actions"] == ["confirmation_creation", "production_task_creation", "pipeline_runner_launch"]
    assert proposal["production_task_created"] is False
    assert proposal["promotion_status"] == "blocked_by_gaps"
    assert "No fixed workflow registry entry exists." in proposal["blocking_gaps"]
    persisted = ledger.get_proposal(proposal["proposal_id"])
    assert persisted["contract_version"] == "toolchain_proposal.v1"
    assert persisted["requested_workflow_type"] == "dwi_magic_connectome_report"
    assert persisted["requested_action_lane"] == "fixed_workflow"
    assert persisted["action_lane"] == INCUBATION_LANE
    assert persisted["task_created"] is False
    assert persisted["confirmation_created"] is False
    assert persisted["task_creation_allowed"] is False
    assert persisted["forbidden_actions"] == ["confirmation_creation", "production_task_creation", "pipeline_runner_launch"]
    assert persisted["production_task_created"] is False
    assert persisted["production_enabled"] is False
    assert production_calls == []


def test_langgraph_agent_runner_matches_fixed_workflow_from_capability_metadata_when_planner_omits_type(tmp_path):
    from app.agent.langgraph_runner import LangGraphAgentRunner
    from app.workflows.registry import list_workflows

    gateway = FakeGateway(
        {
            "intent": "run_workflow",
            "action_lane": "fixed_workflow",
            "summary": "Run BOLD preprocessing, XCP-D derived metrics, QC, and report outputs",
            "series_id": 11,
        }
    )
    context = {
        "project_id": 7,
        "series": [{"id": 11, "modality": "BOLD", "supported_for_processing": 1}],
        "workflows": list_workflows(),
    }

    result = LangGraphAgentRunner(
        gateway=gateway,
        incubation_ledger=IncubationLedger(tmp_path / "ledger"),
        rag_root=tmp_path,
        thread_store=AgentThreadStore(tmp_path / "threads"),
    ).run(message="run bold preprocessing metrics qc report", project_context=context)

    assert result["status"] == "confirmation_required"
    assert result["safe_metadata"]["lane"] == "fixed_workflow"
    assert result["confirmation"]["workflow_type"] == "bold_fmriprep_xcpd_report"
    assert result["graph_state"]["workflow_match"]["status"] == "capability_fixed_match"
    assert result["production_task_created"] is False


def test_langgraph_agent_runner_matches_dwi_fixed_workflow_from_capability_metadata(tmp_path):
    from app.agent.langgraph_runner import LangGraphAgentRunner
    from app.workflows.registry import list_workflows

    gateway = FakeGateway(
        {
            "intent": "run_workflow",
            "action_lane": "fixed_workflow",
            "summary": "Run DWI fast GPU DTI FA MD atlas metrics QC and report outputs",
            "series_id": 24,
        }
    )
    context = {
        "project_id": 7,
        "series": [{"id": 24, "modality": "DWI", "supported_for_processing": 1}],
        "workflows": list_workflows(),
    }

    result = LangGraphAgentRunner(
        gateway=gateway,
        incubation_ledger=IncubationLedger(tmp_path / "ledger"),
        rag_root=tmp_path,
        thread_store=AgentThreadStore(tmp_path / "threads"),
    ).run(message="run dwi fa md atlas metrics qc report", project_context=context)

    assert result["status"] == "confirmation_required"
    assert result["safe_metadata"]["lane"] == "fixed_workflow"
    assert result["confirmation"]["workflow_type"] == "dwi_fast_gpu_dti"
    assert result["confirmation"]["workflow_metadata"]["workflow_type"] == "dwi_fast_gpu_dti"
    assert result["confirmation"]["workflow_metadata"]["workflow_family"] == "dwi"
    assert result["confirmation"]["workflow_metadata"]["workflow_role"] == "complete_processing"
    assert result["graph_state"]["workflow_match"]["status"] == "capability_fixed_match"
    assert result["production_task_created"] is False


def test_langgraph_agent_runner_does_not_prepare_fixed_confirmation_without_explicit_launch_intent(tmp_path):
    from app.agent.langgraph_runner import LangGraphAgentRunner
    from app.workflows.registry import list_workflows

    gateway = FakeGateway(
        {
            "intent": "run_workflow",
            "action_lane": "fixed_workflow",
            "summary": "Explain uploaded T1 files and possible anatomical processing",
            "workflow_type": "t1_deepprep_anat_report",
            "series_id": 11,
        }
    )
    context = {
        "project_id": 7,
        "series": [{"id": 11, "modality": "T1", "supported_for_processing": 1, "sequence_label": "T1w_MPRAGE"}],
        "workflows": list_workflows(),
    }

    result = LangGraphAgentRunner(
        gateway=gateway,
        incubation_ledger=IncubationLedger(tmp_path / "ledger"),
        rag_root=tmp_path,
        thread_store=AgentThreadStore(tmp_path / "threads"),
    ).run(message="帮我看看这个项目当前适合做什么", project_context=context)

    assert result["status"] == "answered"
    assert result["safe_metadata"]["lane"] == "read_only"
    assert result["decision"]["intent"] == "answer_question"
    assert result["production_task_created"] is False
    assert "confirmation" not in result


def test_langgraph_agent_runner_does_not_capability_match_non_agent_selectable_workflow(tmp_path):
    from app.agent.langgraph_runner import LangGraphAgentRunner

    gateway = FakeGateway(
        {
            "intent": "run_workflow",
            "action_lane": "fixed_workflow",
            "summary": "Run legacy validation outputs",
            "series_id": 11,
        }
    )
    context = {
        "project_id": 7,
        "series": [{"id": 11, "modality": "T1", "supported_for_processing": 1}],
        "workflows": [
            {
                "type": "t1_deepprep_validate",
                "label": "T1 DeepPrep Validate",
                "display_name": "T1 DeepPrep validation",
                "workflow_family": "t1",
                "workflow_role": "validation",
                "capability_summary": "Run legacy validation outputs",
                "pipeline_stages": [{"name": "validation", "purpose": "legacy validation outputs"}],
                "primary_outputs": ["validation outputs"],
                "qc_outputs": [],
                "report_outputs": [],
                "limitations": [],
                "modality": "T1",
                "lane": "fixed_workflow",
                "agent_selectable": False,
            }
        ],
    }

    result = LangGraphAgentRunner(
        gateway=gateway,
        incubation_ledger=IncubationLedger(tmp_path / "ledger"),
        rag_root=tmp_path,
        thread_store=AgentThreadStore(tmp_path / "threads"),
    ).run(message="run legacy validation outputs", project_context=context)

    assert result["status"] == "toolchain_proposed"
    assert result["safe_metadata"]["lane"] == INCUBATION_LANE
    assert result["graph_state"]["workflow_match"]["status"] == "no_fixed_match"
    assert result["production_task_created"] is False


def test_langgraph_agent_runner_failed_task_uses_observe_repair_lane_without_retry(tmp_path):
    from app.agent.langgraph_runner import LangGraphAgentRunner

    gateway = FakeGateway({"intent": "answer_question", "summary": "Explain failed task"})
    context = {
        "project_id": 7,
        "tasks": [
            {
                "id": 61,
                "project_id": 7,
                "series_id": 24,
                "workflow_type": "dwi_fast_gpu_dti",
                "status": "failed",
                "progress": 20,
                "error_message": "GPU runtime unavailable",
            }
        ],
    }

    result = LangGraphAgentRunner(gateway=gateway, rag_root=tmp_path).run(
        message="why did task 61 fail and should I retry?",
        project_context=context,
    )

    assert result["status"] == "answered"
    assert result["production_task_created"] is False
    assert result["safe_metadata"]["lane"] == "observe_repair"
    assert result["task_observation"]["task_id"] == 61
    assert result["repair_plan"]["policy"] == "read_only_observe_repair"
    assert result["repair_plan"]["auto_retry_allowed"] is False
    assert result["repair_plan"]["auto_rerun_allowed"] is False
    assert result["repair_plan"]["requires_preflight_before_retry"] is True
    assert result["repair_plan"]["requires_human_confirmation_before_retry"] is True
    assert result["repair_plan"]["forbidden_actions"] == ["auto_retry", "auto_rerun", "task_creation"]
    assert "human confirmation" in " ".join(result["repair_plan"]["next_steps"])
    assert result["graph_state"]["lane"] == "observe_repair"


def test_langgraph_agent_runner_observe_repair_uses_responder_for_complete_analysis(tmp_path):
    from app.agent.langgraph_runner import LangGraphAgentRunner

    gateway = FakeGateway({"intent": "answer_question", "summary": "Analyze failed task result"})
    context = {
        "project_id": 7,
        "tasks": [
            {
                "id": 61,
                "project_id": 7,
                "series_id": 24,
                "workflow_type": "dwi_fast_gpu_dti",
                "status": "failed",
                "progress": 20,
                "error_message": "GPU runtime unavailable",
            }
        ],
    }

    result = LangGraphAgentRunner(gateway=gateway, rag_root=tmp_path).run(
        message="请完整分析 task 61 的结果和失败原因",
        project_context=context,
    )

    assert result["status"] == "answered"
    assert result["answer"] == "final answer"
    answer_prompt = next(item[1] for item in gateway.messages if item[0] == "agent_answer")
    answer_text = answer_prompt[-1]["content"]
    assert "Task observation JSON" in answer_text
    assert "Repair plan JSON" in answer_text
    assert "GPU runtime unavailable" in answer_text
    assert result["production_task_created"] is False


def test_langgraph_agent_runner_result_analysis_answer_is_complete_even_if_model_stops_early(tmp_path):
    from app.agent.langgraph_runner import LangGraphAgentRunner

    gateway = ShortAnswerGateway({"intent": "answer_question", "summary": "Analyze completed results"})
    context = {
        "project_id": 7,
        "tasks": [
            {
                "id": 140,
                "project_id": 7,
                "series_id": 11,
                "workflow_type": "t1_deepprep_anat_report",
                "status": "completed",
                "progress": 100,
                "error_message": None,
            }
        ],
        "result_summaries": [
            {
                "task_id": 140,
                "workflow_type": "t1_deepprep_anat_report",
                "outputs": {
                    "reports": [{"relative_path": "reports/index.html"}],
                    "qc": [{"relative_path": "QC/sub-01/figures/sub-01_desc-surfparc_T1w.svg"}],
                },
            }
        ],
    }

    result = LangGraphAgentRunner(gateway=gateway, rag_root=tmp_path).run(
        message="请完整分析结果和QC报告",
        project_context=context,
    )

    assert result["status"] == "answered"
    assert result["safe_metadata"]["lane"] == "read_only"
    assert result["production_task_created"] is False
    assert "Observation summary" in result["answer"]
    assert "task 140" in result["answer"]
    assert "Result artifacts" in result["answer"]
    assert "reports/index.html" in result["answer"]
    assert "QC observations" in result["answer"]
    assert "sub-01_desc-surfparc_T1w.svg" in result["answer"]
    assert "No workflow was launched" in result["answer"]
    assert "confirmation" not in result


def test_langgraph_agent_runner_result_analysis_handles_natural_chinese_question(tmp_path):
    from app.agent.langgraph_runner import LangGraphAgentRunner

    gateway = ShortAnswerGateway({"intent": "answer_question", "summary": "Analyze completed results"})
    context = {
        "project_id": 7,
        "tasks": [
            {
                "id": 140,
                "project_id": 7,
                "series_id": 11,
                "workflow_type": "t1_deepprep_anat_report",
                "status": "completed",
                "progress": 100,
                "error_message": None,
            }
        ],
        "result_summaries": [
            {
                "task_id": 140,
                "workflow_type": "t1_deepprep_anat_report",
                "outputs": {
                    "reports": [{"relative_path": "reports/index.html"}],
                    "qc": [{"relative_path": "QC/sub-01/figures/sub-01_desc-surfparc_T1w.svg"}],
                },
            }
        ],
    }

    result = LangGraphAgentRunner(gateway=gateway, rag_root=tmp_path).run(
        message="\u8bf7\u66ff\u6211\u5206\u6790\u7ed3\u679c\uff0c\u5b8c\u6574\u8f93\u51fa\u89c2\u5bdf\u3001\u62a5\u544a\u548cQC\u603b\u7ed3",
        project_context=context,
    )

    assert result["status"] == "answered"
    assert result["production_task_created"] is False
    assert "Observation summary" in result["answer"]
    assert "Result artifacts" in result["answer"]
    assert "QC observations" in result["answer"]
    assert "No workflow was launched" in result["answer"]
    assert "confirmation" not in result


def test_langgraph_agent_runner_replaces_generic_real_chinese_early_stop_with_complete_read_only_answer(tmp_path):
    from app.agent.langgraph_runner import LangGraphAgentRunner

    gateway = ChineseShortAnswerGateway({"intent": "answer_question", "summary": "Explain current project"})
    context = {
        "project_id": 7,
        "project_files": [
            {"id": 31, "original_name": "sub-01_T1w.nii.gz", "file_type": "NIFTI"},
        ],
        "series": [{"id": 11, "modality": "T1", "sequence_label": "T1w_MPRAGE", "supported_for_processing": 1}],
        "tasks": [
            {
                "id": 140,
                "workflow_type": "t1_deepprep_anat_report",
                "status": "completed",
                "progress": 100,
            }
        ],
    }

    result = LangGraphAgentRunner(gateway=gateway, rag_root=tmp_path).run(
        message="你先回答我的问题",
        project_context=context,
    )

    assert result["status"] == "answered"
    assert result["safe_metadata"]["lane"] == "read_only"
    assert result["production_task_created"] is False
    assert "sub-01_T1w.nii.gz" in result["answer"]
    assert "T1w_MPRAGE" in result["answer"]
    assert "t1_deepprep_anat_report" in result["answer"]
    assert "No workflow was launched" in result["answer"]
    assert "我先看一下" not in result["answer"]
    assert "confirmation" not in result


def test_langgraph_agent_runner_replaces_deflecting_answer_with_project_context(tmp_path):
    from app.agent.langgraph_runner import LangGraphAgentRunner

    gateway = DeflectingChineseGateway(
        {
            "intent": "run_workflow",
            "action_lane": "fixed_workflow",
            "workflow_type": "t1_deepprep_anat_report",
            "series_id": 11,
            "summary": "Prepare T1 workflow",
        }
    )
    context = {
        "project_id": 7,
        "project_files": [
            {"id": 31, "original_name": "sub-01_T1w.nii.gz", "file_type": "NIFTI"},
        ],
        "series": [{"id": 11, "modality": "T1", "sequence_label": "T1w_MPRAGE", "supported_for_processing": 1}],
        "tasks": [
            {
                "id": 140,
                "workflow_type": "t1_deepprep_anat_report",
                "status": "completed",
                "progress": 100,
            }
        ],
        "workflows": [
            {
                "type": "t1_deepprep_anat_report",
                "display_name": "T1 DeepPrep anatomical processing, QC, and report",
                "capability_summary": "Runs T1 anatomical preprocessing, segmentation, QC, and report generation.",
                "modality": "T1",
                "lane": "fixed_workflow",
                "agent_selectable": True,
            }
        ],
    }

    result = LangGraphAgentRunner(gateway=gateway, rag_root=tmp_path).run(
        message="你先回答我的问题",
        project_context=context,
    )

    assert result["status"] == "answered"
    assert result["safe_metadata"]["lane"] == "read_only"
    assert result["production_task_created"] is False
    assert "sub-01_T1w.nii.gz" in result["answer"]
    assert "T1w_MPRAGE" in result["answer"]
    assert "t1_deepprep_anat_report" in result["answer"]
    assert "No workflow was launched" in result["answer"]
    assert "请把你要我先回答的具体问题发给我" not in result["answer"]
    assert "confirmation" not in result


def test_langgraph_agent_runner_observe_repair_detects_real_chinese_early_stop(tmp_path):
    from app.agent.langgraph_runner import LangGraphAgentRunner

    gateway = ChineseShortAnswerGateway({"intent": "answer_question", "summary": "Analyze failed task"})
    context = {
        "project_id": 7,
        "tasks": [
            {
                "id": 61,
                "project_id": 7,
                "series_id": 24,
                "workflow_type": "dwi_fast_gpu_dti",
                "status": "failed",
                "progress": 20,
                "error_message": "GPU runtime unavailable",
            }
        ],
    }

    result = LangGraphAgentRunner(gateway=gateway, rag_root=tmp_path).run(
        message="请完整分析 task 61 的失败原因和修复建议",
        project_context=context,
    )

    assert result["status"] == "answered"
    assert result["safe_metadata"]["lane"] == "observe_repair"
    assert result["production_task_created"] is False
    assert "Observation summary" in result["answer"]
    assert "GPU runtime unavailable" in result["answer"]
    assert "Suggested next steps" in result["answer"]
    assert "confirmation" not in result


def test_langgraph_agent_runner_resume_marks_fixed_workflow_graph_gate(tmp_path):
    from app.agent.langgraph_runner import LangGraphAgentRunner

    store = AgentThreadStore(tmp_path / "threads")
    confirmation = {
        "type": "workflow_execution",
        "project_id": 7,
        "series_id": 11,
        "workflow_type": "t1_deepprep_anat_report",
        "action_lane": "fixed_workflow",
        "preflight": {
            "ok": True,
            "workflow_type": "t1_deepprep_anat_report",
            "runtime_workflow_type": "t1_deepprep",
        },
    }
    thread = store.create_pending_confirmation(
        confirmation=confirmation,
        decision={"intent": "run_workflow"},
        selected_skill="image-agent-workflow-runner",
        retrieved_context={},
    )
    created = []

    result = LangGraphAgentRunner(thread_store=store).resume(
        thread_id=thread["thread_id"],
        approved=True,
        confirmation=confirmation,
        create_task_fn=lambda series_id, workflow_type, qsiprep_task_id=None: created.append(
            {"id": 99, "series_id": series_id, "workflow_type": workflow_type, "status": "queued"}
        )
        or created[-1],
    )

    assert result["status"] == "task_created"
    assert result["production_task_created"] is True
    assert result["safe_metadata"]["agent_engine"] == "langgraph"
    assert result["safe_metadata"]["lane"] == "fixed_workflow"
    assert result["graph_state"]["confirmation_gate"] == "fingerprint_verified"
    assert result["graph_state"]["production_task_created"] is True
    assert created == [{"id": 99, "series_id": 11, "workflow_type": "t1_deepprep", "status": "queued"}]


def test_langgraph_agent_runner_resume_uses_preflight_runtime_workflow_type(tmp_path):
    from app.agent.langgraph_runner import LangGraphAgentRunner

    store = AgentThreadStore(tmp_path / "threads")
    confirmation = {
        "type": "workflow_execution",
        "project_id": 7,
        "series_id": 11,
        "workflow_type": "bold_fmriprep_xcpd_report",
        "action_lane": "fixed_workflow",
        "preflight": {
            "ok": True,
            "workflow_type": "bold_fmriprep_xcpd_report",
            "runtime_workflow_type": "bold_fmriprep_xcpd_report_validate",
        },
    }
    thread = store.create_pending_confirmation(
        confirmation=confirmation,
        decision={"intent": "run_workflow"},
        selected_skill="image-agent-workflow-runner",
        retrieved_context={},
    )
    created = []

    result = LangGraphAgentRunner(thread_store=store).resume(
        thread_id=thread["thread_id"],
        approved=True,
        confirmation=confirmation,
        create_task_fn=lambda series_id, workflow_type, qsiprep_task_id=None: created.append(
            {"id": 101, "series_id": series_id, "workflow_type": workflow_type, "status": "queued"}
        )
        or created[-1],
    )

    assert result["status"] == "task_created"
    assert result["production_task_created"] is True
    assert created == [
        {"id": 101, "series_id": 11, "workflow_type": "bold_fmriprep_xcpd_report_validate", "status": "queued"}
    ]


def test_langgraph_agent_runner_resume_blocks_client_confirmation_overrides(tmp_path):
    from app.agent.langgraph_runner import LangGraphAgentRunner

    store = AgentThreadStore(tmp_path / "threads")
    confirmation = {
        "type": "workflow_execution",
        "project_id": 7,
        "series_id": 11,
        "workflow_type": "bold_fmriprep_xcpd_report",
        "action_lane": "fixed_workflow",
        "preflight": {
            "ok": True,
            "workflow_type": "bold_fmriprep_xcpd_report",
            "runtime_workflow_type": "bold_fmriprep_xcpd_report",
        },
    }
    thread = store.create_pending_confirmation(
        confirmation=confirmation,
        decision={"intent": "run_workflow"},
        selected_skill="image-agent-workflow-runner",
        retrieved_context={},
    )
    created = []
    client_confirmation = {
        **confirmation,
        "workflow_type": "t1_deepprep_anat_report",
        "preflight": {
            "ok": True,
            "workflow_type": "t1_deepprep_anat_report",
            "runtime_workflow_type": "t1_deepprep",
        },
    }

    result = LangGraphAgentRunner(thread_store=store).resume(
        thread_id=thread["thread_id"],
        approved=True,
        confirmation=client_confirmation,
        create_task_fn=lambda series_id, workflow_type, qsiprep_task_id=None: created.append(
            {"id": 102, "series_id": series_id, "workflow_type": workflow_type, "status": "queued"}
        )
        or created[-1],
    )

    assert result["status"] == "blocked"
    assert result["production_task_created"] is False
    assert result["message"] == "Confirmation payload does not match the server-side pending confirmation."
    assert result["safe_metadata"]["confirmation_gate"] == "fingerprint_mismatch"
    assert result["graph_state"]["confirmation_gate"] == "fingerprint_mismatch"
    assert created == []


def test_langgraph_agent_runner_resume_blocks_incubation_with_graph_gate_metadata(tmp_path):
    from app.agent.langgraph_runner import LangGraphAgentRunner

    store = AgentThreadStore(tmp_path / "threads")
    confirmation = {
        "type": "workflow_execution",
        "project_id": 7,
        "series_id": 24,
        "workflow_type": "unknown_connectome",
        "action_lane": INCUBATION_LANE,
    }
    thread = store.create_pending_confirmation(
        confirmation=confirmation,
        decision={"intent": "run_workflow", "action_lane": INCUBATION_LANE},
        selected_skill="image-agent-workflow-runner",
        retrieved_context={},
    )
    called = False

    def create_task_fn(series_id, workflow_type, qsiprep_task_id=None):
        nonlocal called
        called = True
        return {"id": 100, "series_id": series_id, "workflow_type": workflow_type}

    result = LangGraphAgentRunner(thread_store=store).resume(
        thread_id=thread["thread_id"],
        approved=True,
        confirmation=confirmation,
        create_task_fn=create_task_fn,
    )

    assert result["status"] == "blocked"
    assert result["production_task_created"] is False
    assert result["safe_metadata"]["agent_engine"] == "langgraph"
    assert result["safe_metadata"]["lane"] == INCUBATION_LANE
    assert result["graph_state"]["confirmation_gate"] == "incubation_blocked"
    assert called is False


def test_langgraph_agent_runner_records_hierarchical_router_stages_for_task_request(tmp_path):
    from app.agent.langgraph_runner import LangGraphAgentRunner

    gateway = FakeGateway(
        {
            "intent": "run_workflow",
            "action_lane": "fixed_workflow",
            "series_id": 11,
            "workflow_type": "t1_deepprep_anat_report",
            "summary": "Prepare T1 workflow",
        }
    )
    context = {
        "project_id": 7,
        "series": [{"id": 11, "modality": "T1", "supported_for_processing": 1}],
        "workflows": [
            {
                "type": "t1_deepprep_anat_report",
                "display_name": "T1 DeepPrep anatomical processing, QC, and report",
                "capability_summary": "Runs T1 anatomical preprocessing, segmentation, QC, and report generation.",
                "modality": "T1",
                "lane": "fixed_workflow",
                "agent_selectable": True,
            }
        ],
    }

    result = LangGraphAgentRunner(gateway=gateway, rag_root=tmp_path).run(
        message="请启动 T1 DeepPrep，创建任务前先给我确认卡片",
        project_context=context,
    )

    event_types = [event["type"] for event in result["events"]]
    assert event_types[:4] == [
        "agent.graph.run_intake",
        "agent.graph.safety_risk_router",
        "agent.graph.classify_intent",
        "agent.graph.answer_or_task_router",
    ]
    assert "agent.graph.task_planning" in event_types
    assert result["graph_state"]["router_lane"] == "tool_task"
    assert result["graph_state"]["risk_assessment"]["level"] in {"low", "medium", "high"}
    assert result["graph_state"]["task_planning"]["mode"] == "fixed_first"
