from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from app.agent.graph import AgentRunner
from app.agent.chat import (
    _generic_read_only_reply,
    _inventory_capability_reply,
    _is_inventory_capability_question,
    _is_result_analysis_question,
    _status_reply,
)
from app.agent.incubation import IncubationLedger
from app.agent.intent import classify_rule_intent, extract_llm_intent_signal, normalize_intent_decision
from app.agent.model_gateway import ModelGateway
from app.agent.rag_orchestration import retrieve_reference_context
from app.agent.skill_loader import select_skill
from app.agent.state import ImageAgentState
from app.agent.thread_store import AgentThreadStore, confirmation_fingerprint
from app.agent.tools import preflight_workflow
from app.core.config import DATA_ROOT
from app.imaging.detect import UNSUPPORTED_SEQUENCE_MESSAGE
from app.workflows.registry import FIXED_WORKFLOW, INCUBATION_LANE, get_workflow


READ_ONLY_LANE = "read_only"
TOOL_TASK_ROUTER_LANE = "tool_task"
OBSERVE_REPAIR_LANE = "observe_repair"
TOOLCHAIN_PROPOSAL_CONTRACT_VERSION = "toolchain_proposal.v1"
SEQUENCE_METADATA_PRECEDENCE = ["sidecar_json", "dicom_tags", "nifti_header", "filename_tokens"]


def build_langgraph_runner_factory(patch_attr: Callable[[str, Any], Any] | None = None) -> Callable[[], "LangGraphAgentRunner"]:
    if patch_attr is not None:
        gateway_factory = patch_attr("ModelGateway", None)
        if gateway_factory is not None:
            return lambda: LangGraphAgentRunner(gateway=gateway_factory())
    return LangGraphAgentRunner


def _langgraph_runtime_available() -> bool:
    try:
        from langgraph.graph import END, StateGraph  # noqa: F401
    except Exception:
        return False
    return True


class LangGraphAgentRunner(AgentRunner):
    """LangGraph-compatible orchestration runner with backend deterministic gates.

    The node functions are the source of truth. When the optional langgraph package
    is unavailable in local development, the same nodes run sequentially through a
    deterministic fallback so API behavior and tests remain stable.
    """

    def __init__(
        self,
        gateway: ModelGateway | Any | None = None,
        *,
        rag_root: Path | str | None = None,
        incubation_ledger: IncubationLedger | None = None,
        thread_store: AgentThreadStore | None = None,
    ) -> None:
        super().__init__(
            gateway=gateway,
            rag_root=rag_root,
            incubation_ledger=incubation_ledger,
            thread_store=thread_store,
        )
        self.graph_runtime = "langgraph" if _langgraph_runtime_available() else "deterministic_fallback"
        self._compiled_graph = self._compile_graph() if self.graph_runtime == "langgraph" else None

    def run(self, *, message: str, project_context: dict[str, Any]) -> dict[str, Any]:
        state: ImageAgentState = {
            "message": message,
            "project_id": project_context.get("project_id"),
            "project_context": project_context,
            "workflow_registry": project_context.get("workflows") or [],
            "events": [],
            "production_task_created": False,
        }
        if self._compiled_graph is not None:
            try:
                final_state = self._compiled_graph.invoke(state)
            except Exception:
                final_state = self._run_fallback_graph(state)
        else:
            final_state = self._run_fallback_graph(state)
        return self._state_to_result(final_state)

    def resume(
        self,
        *,
        thread_id: str,
        approved: bool,
        confirmation: dict[str, Any],
        create_task_fn: Any | None = None,
    ) -> dict[str, Any]:
        gate_state = self._resume_gate_state(
            thread_id=thread_id,
            approved=approved,
            confirmation=confirmation,
        )
        result = super().resume(
            thread_id=thread_id,
            approved=approved,
            confirmation=confirmation,
            create_task_fn=create_task_fn,
        )
        return self._annotate_resume_result(result, gate_state=gate_state)

    def _compile_graph(self) -> Any | None:
        try:
            from langgraph.graph import END, StateGraph
        except Exception:
            return None

        graph = StateGraph(ImageAgentState)
        graph.add_node("run_intake", self._node_run_intake)
        graph.add_node("safety_risk_router", self._node_safety_risk_router)
        graph.add_node("rule_intent_classifier", self._node_rule_intent_classifier)
        graph.add_node("llm_intent_planner", self._node_llm_intent_planner)
        graph.add_node("intent_fusion_gate", self._node_intent_fusion_gate)
        graph.add_node("answer_or_task_router", self._node_answer_or_task_router)
        graph.add_node("retrieve_rag", self._node_retrieve_rag)
        graph.add_node("select_skill", self._node_select_skill)
        graph.add_node("requirement_completeness", self._node_requirement_completeness)
        graph.add_node("clarification_interrupt", self._node_clarification_interrupt)
        graph.add_node("neuroimaging_data_intake_validation", self._node_neuroimaging_data_intake_validation)
        graph.add_node("sequence_metadata_normalization", self._node_sequence_metadata_normalization)
        graph.add_node("task_planning", self._node_task_planning)
        graph.add_node("read_only", self._node_read_only)
        graph.add_node("fixed_workflow", self._node_fixed_workflow)
        graph.add_node("incubation", self._node_incubation)
        graph.add_node("observe_repair", self._node_observe_repair)
        graph.set_entry_point("run_intake")
        graph.add_edge("run_intake", "safety_risk_router")
        graph.add_edge("safety_risk_router", "rule_intent_classifier")
        graph.add_edge("rule_intent_classifier", "llm_intent_planner")
        graph.add_edge("llm_intent_planner", "intent_fusion_gate")
        graph.add_edge("intent_fusion_gate", "answer_or_task_router")
        graph.add_edge("answer_or_task_router", "retrieve_rag")
        graph.add_edge("retrieve_rag", "select_skill")
        graph.add_conditional_edges(
            "select_skill",
            self._route_after_skill_selection,
            {
                READ_ONLY_LANE: "read_only",
                TOOL_TASK_ROUTER_LANE: "requirement_completeness",
            },
        )
        graph.add_conditional_edges(
            "requirement_completeness",
            self._route_requirement_completeness,
            {
                "needs_clarification": "clarification_interrupt",
                "complete": "neuroimaging_data_intake_validation",
            },
        )
        graph.add_edge("neuroimaging_data_intake_validation", "sequence_metadata_normalization")
        graph.add_edge("sequence_metadata_normalization", "task_planning")
        graph.add_conditional_edges(
            "task_planning",
            self._route_lane,
            {
                READ_ONLY_LANE: "read_only",
                FIXED_WORKFLOW: "fixed_workflow",
                INCUBATION_LANE: "incubation",
                OBSERVE_REPAIR_LANE: "observe_repair",
            },
        )
        graph.add_edge("read_only", END)
        graph.add_edge("clarification_interrupt", END)
        graph.add_edge("fixed_workflow", END)
        graph.add_edge("incubation", END)
        graph.add_edge("observe_repair", END)
        return graph.compile()

    def _run_fallback_graph(self, state: ImageAgentState) -> ImageAgentState:
        for node in (
            self._node_run_intake,
            self._node_safety_risk_router,
            self._node_rule_intent_classifier,
            self._node_llm_intent_planner,
            self._node_intent_fusion_gate,
            self._node_answer_or_task_router,
            self._node_retrieve_rag,
            self._node_select_skill,
        ):
            state.update(node(state))
        if self._route_after_skill_selection(state) == TOOL_TASK_ROUTER_LANE:
            state.update(self._node_requirement_completeness(state))
            if self._route_requirement_completeness(state) == "needs_clarification":
                state.update(self._node_clarification_interrupt(state))
                return state
            state.update(self._node_neuroimaging_data_intake_validation(state))
            state.update(self._node_sequence_metadata_normalization(state))
            state.update(self._node_task_planning(state))
            lane = self._route_lane(state)
            if lane == FIXED_WORKFLOW:
                state.update(self._node_fixed_workflow(state))
            elif lane == INCUBATION_LANE:
                state.update(self._node_incubation(state))
            elif lane == OBSERVE_REPAIR_LANE:
                state.update(self._node_observe_repair(state))
            else:
                state.update(self._node_read_only(state))
        else:
            state.update(self._node_read_only(state))
        return state

    def _node_run_intake(self, state: ImageAgentState) -> dict[str, Any]:
        return {
            "project_id": state.get("project_context", {}).get("project_id"),
            "workflow_registry": state.get("project_context", {}).get("workflows") or [],
            "production_task_created": False,
            "events": self._append_event(
                state,
                {
                    "type": "agent.graph.run_intake",
                    "status": "ok",
                    "message": "Loaded request and project context.",
                    "metadata": {
                        "project_id": state.get("project_context", {}).get("project_id"),
                        "series_count": len(state.get("project_context", {}).get("series") or []),
                        "task_count": len(state.get("project_context", {}).get("tasks") or []),
                    },
                },
            ),
        }

    def _node_safety_risk_router(self, state: ImageAgentState) -> dict[str, Any]:
        message = state.get("message", "")
        lowered = message.lower()
        risk_flags = []
        if any(token in lowered for token in ("delete", "remove", "overwrite", "删除", "覆盖")):
            risk_flags.append("destructive_action_language")
        if any(token in lowered for token in ("diagnose", "diagnosis", "确诊", "诊断")):
            risk_flags.append("clinical_diagnostic_language")
        level = "high" if risk_flags else "low"
        risk_assessment = {
            "level": level,
            "flags": risk_flags,
            "policy": "non_diagnostic_human_confirmed_execution",
        }
        return {
            "risk_assessment": risk_assessment,
            "events": self._append_event(
                state,
                {
                    "type": "agent.graph.safety_risk_router",
                    "status": level,
                    "message": "Classified request risk before intent routing.",
                    "metadata": risk_assessment,
                },
            ),
        }

    def _node_classify_intent(self, state: ImageAgentState) -> dict[str, Any]:
        merged = {**state}
        for node in (self._node_rule_intent_classifier, self._node_llm_intent_planner, self._node_intent_fusion_gate):
            merged.update(node(merged))
        decision = merged.get("decision") or {}
        planner_tool_trace = merged.get("planner_tool_trace") or []
        intent = str(decision.get("intent") or "answer_question")
        return {
            "intent": intent,
            "decision": decision,
            "rule_intent_signal": merged.get("rule_intent_signal") or {},
            "llm_intent_signal": merged.get("llm_intent_signal") or {},
            "intent_decision": merged.get("intent_decision") or {},
            "planner_tool_trace": planner_tool_trace,
            "events": self._append_event(
                state,
                {
                    "type": "agent.graph.classify_intent",
                    "status": "ok",
                    "message": f"Classified intent as {intent}.",
                    "metadata": {
                        "intent": intent,
                        "action_lane": decision.get("action_lane") or decision.get("lane"),
                        "requires_confirmation": decision.get("requires_confirmation"),
                    },
                },
            ),
        }

    def _node_rule_intent_classifier(self, state: ImageAgentState) -> dict[str, Any]:
        signal = classify_rule_intent(
            message=state.get("message", ""),
            project_context=state.get("project_context") or {},
        )
        return {
            "rule_intent_signal": signal,
            "events": self._append_event(
                state,
                {
                    "type": "agent.graph.rule_intent_classifier",
                    "status": str(signal.get("gate") or "unknown"),
                    "message": f"Rule intent classifier selected {signal.get('category')}.",
                    "metadata": {
                        "category": signal.get("category"),
                        "gate": signal.get("gate"),
                        "confidence": signal.get("confidence"),
                        "authoritative": signal.get("authoritative"),
                    },
                },
            ),
        }

    def _node_llm_intent_planner(self, state: ImageAgentState) -> dict[str, Any]:
        decision, planner_tool_trace = self._planner_model_decision(
            message=state.get("message", ""),
            project_context=state.get("project_context") or {},
        )
        llm_signal = extract_llm_intent_signal(decision if isinstance(decision, dict) else {})
        return {
            "decision": decision,
            "llm_intent_signal": llm_signal,
            "planner_tool_trace": planner_tool_trace,
            "events": self._append_event(
                state,
                {
                    "type": "agent.graph.llm_intent_planner",
                    "status": "ok" if llm_signal.get("valid") else "incomplete",
                    "message": f"LLM planner classified intent as {llm_signal.get('category')}.",
                    "metadata": {
                        "category": llm_signal.get("category"),
                        "confidence": llm_signal.get("confidence"),
                        "valid": llm_signal.get("valid"),
                        "route_recommendation": llm_signal.get("route_recommendation"),
                    },
                },
            ),
        }

    def _node_intent_fusion_gate(self, state: ImageAgentState) -> dict[str, Any]:
        decision, intent_trace = normalize_intent_decision(
            message=state.get("message", ""),
            model_decision=state.get("decision") or {},
        )
        audit = decision.get("intent_decision") or {}
        intent = str(decision.get("intent") or "answer_question")
        return {
            "intent": intent,
            "decision": decision,
            "rule_intent_signal": audit.get("rule_signal") or state.get("rule_intent_signal") or {},
            "llm_intent_signal": audit.get("llm_signal") or state.get("llm_intent_signal") or {},
            "intent_decision": audit,
            "planner_tool_trace": [*(state.get("planner_tool_trace") or []), *intent_trace],
            "events": self._append_event(
                state,
                {
                    "type": "agent.graph.intent_fusion_gate",
                    "status": str(audit.get("final_gate") or "unknown"),
                    "message": f"Fused intent as {intent}.",
                    "metadata": {
                        "intent": intent,
                        "category": audit.get("final_category"),
                        "gate": audit.get("final_gate"),
                        "conflict": audit.get("conflict"),
                    },
                },
            ),
        }

    def _node_answer_or_task_router(self, state: ImageAgentState) -> dict[str, Any]:
        decision = state.get("decision") or {}
        if self._looks_like_observe_repair(state):
            router_lane = TOOL_TASK_ROUTER_LANE
            reason = "task observation request"
        elif decision.get("intent") == "run_workflow":
            router_lane = TOOL_TASK_ROUTER_LANE
            reason = "workflow execution intent"
        else:
            router_lane = READ_ONLY_LANE
            reason = "read-only answer intent"
        return {
            "router_lane": router_lane,
            "events": self._append_event(
                state,
                {
                    "type": "agent.graph.answer_or_task_router",
                    "status": "ok",
                    "message": f"Routed request to {router_lane}.",
                    "metadata": {"router_lane": router_lane, "reason": reason},
                },
            ),
        }

    def _node_retrieve_rag(self, state: ImageAgentState) -> dict[str, Any]:
        decision = state.get("decision") or {}
        selected_skill = select_skill(state.get("message", ""), decision)
        retrieved_context = retrieve_reference_context(
            self._retrieval_query(state.get("message", ""), decision, selected_skill),
            root=self.rag_root,
            limit=5,
        )
        return {
            "retrieved_context": retrieved_context,
            "events": self._append_event(
                state,
                {
                    "type": "agent.graph.retrieve_rag",
                    "status": "ok",
                    "message": "Retrieved reference context.",
                    "metadata": {
                        "mode": retrieved_context.get("mode") or retrieved_context.get("tool"),
                        "result_count": len(retrieved_context.get("results") or []),
                    },
                },
            ),
        }

    def _node_select_skill(self, state: ImageAgentState) -> dict[str, Any]:
        decision = state.get("decision") or {}
        selected_skill = select_skill(state.get("message", ""), decision)
        skill_context = self._load_skill_trace(selected_skill)
        return {
            "selected_skill": selected_skill,
            "skill_context": skill_context,
            "events": self._append_event(
                state,
                {
                    "type": "agent.graph.select_skill",
                    "status": "ok",
                    "message": f"Selected skill {selected_skill}.",
                    "metadata": {"selected_skill": selected_skill},
                },
            ),
        }

    def _node_requirement_completeness(self, state: ImageAgentState) -> dict[str, Any]:
        decision = state.get("decision") or {}
        project_context = state.get("project_context") or {}
        missing_fields: list[str] = []
        lane = decision.get("action_lane") or decision.get("lane")
        if lane == FIXED_WORKFLOW:
            series = project_context.get("series") or []
            workflow_registry = project_context.get("workflows") or []
            if not decision.get("workflow_type") and not workflow_registry:
                missing_fields.append("workflow_type")
            if decision.get("series_id") is None and len(series) != 1:
                missing_fields.append("series_id")
        status = "needs_clarification" if missing_fields else "complete"
        clarification = None
        if status == "needs_clarification":
            clarification = "Which series and workflow should I prepare before creating a confirmation?"
        completeness = {
            "status": status,
            "missing_fields": missing_fields,
            "clarifying_question": clarification,
            "safe_context": {
                "series_count": len(project_context.get("series") or []),
                "workflow_count": len(project_context.get("workflows") or []),
                "lane": lane,
            },
            "production_task_created": False,
        }
        return {
            "requirement_completeness": completeness,
            "events": self._append_event(
                state,
                {
                    "type": "agent.graph.requirement_completeness",
                    "status": status,
                    "message": "Checked tool-task requirement completeness.",
                    "metadata": {
                        "status": status,
                        "missing_fields": missing_fields,
                    },
                },
            ),
        }

    def _node_clarification_interrupt(self, state: ImageAgentState) -> dict[str, Any]:
        completeness = state.get("requirement_completeness") or {}
        question = completeness.get("clarifying_question") or "Please clarify the workflow request before I prepare execution."
        result = {
            "status": "needs_clarification",
            "intent": state.get("intent") or "run_workflow",
            "action_lane": READ_ONLY_LANE,
            "answer": question,
            "decision": state.get("decision") or {},
            "requirement_completeness": completeness,
            "production_task_created": False,
        }
        events = self._append_event(
            state,
            {
                "type": "agent.graph.clarification_interrupt",
                "status": "needs_clarification",
                "message": question,
                "metadata": {
                    "missing_fields": completeness.get("missing_fields") or [],
                    "production_task_created": False,
                },
            },
        )
        result["events"] = events
        return {
            "lane": READ_ONLY_LANE,
            "result": result,
            "answer": question,
            "production_task_created": False,
            "events": events,
        }

    def _node_neuroimaging_data_intake_validation(self, state: ImageAgentState) -> dict[str, Any]:
        project_context = state.get("project_context") or {}
        files = [self._public_project_file(item) for item in project_context.get("project_files") or []]
        series = [self._public_series_summary(item) for item in project_context.get("series") or []]
        unsupported_series = [
            item
            for item in series
            if item.get("supported_for_processing") is False
        ]
        status = "empty"
        if series or files:
            status = "warning" if unsupported_series else "ok"
        intake = {
            "status": status,
            "project_id": project_context.get("project_id"),
            "file_count": len(files),
            "series_count": len(series),
            "supported_series_count": len(series) - len(unsupported_series),
            "unsupported_series_count": len(unsupported_series),
            "files": files,
            "series": series,
            "unsupported_series": unsupported_series,
            "production_task_created": False,
        }
        return {
            "neuroimaging_intake": intake,
            "events": self._append_event(
                state,
                {
                    "type": "agent.graph.neuroimaging_data_intake_validation",
                    "status": status,
                    "message": "Validated neuroimaging project context before task planning.",
                    "metadata": {
                        "project_id": intake["project_id"],
                        "file_count": intake["file_count"],
                        "series_count": intake["series_count"],
                        "unsupported_series_count": intake["unsupported_series_count"],
                    },
                },
            ),
        }

    def _node_sequence_metadata_normalization(self, state: ImageAgentState) -> dict[str, Any]:
        normalized_series = [
            self._normalized_sequence_summary(item)
            for item in (state.get("project_context") or {}).get("series") or []
        ]
        unsupported_series = [
            {
                "series_id": item["series_id"],
                "modality": item["modality"],
                "sequence_label": item["sequence_label"],
                "unsupported_reason": item["unsupported_reason"],
            }
            for item in normalized_series
            if item.get("supported_for_processing") is False
        ]
        status = "empty"
        if normalized_series:
            status = "warning" if unsupported_series else "ok"
        normalization = {
            "status": status,
            "metadata_precedence": SEQUENCE_METADATA_PRECEDENCE,
            "series": normalized_series,
            "unsupported_series": unsupported_series,
            "production_task_created": False,
        }
        return {
            "sequence_normalization": normalization,
            "events": self._append_event(
                state,
                {
                    "type": "agent.graph.sequence_metadata_normalization",
                    "status": status,
                    "message": "Normalized sequence metadata with deterministic precedence.",
                    "metadata": {
                        "series_count": len(normalized_series),
                        "unsupported_series_count": len(unsupported_series),
                        "metadata_precedence": SEQUENCE_METADATA_PRECEDENCE,
                    },
                },
            ),
        }

    def _node_task_planning(self, state: ImageAgentState) -> dict[str, Any]:
        planning = {
            "mode": "fixed_first",
            "fixed_workflow_preferred": True,
            "exploratory_toolchain_requires_fixed_rejection": True,
            "observe_repair_inside_execution_loop": True,
        }
        state_for_match = {**state, "task_planning": planning}
        update = self._node_match_workflow(state_for_match)
        return {
            **update,
            "task_planning": planning,
            "events": self._append_event(
                {**state, "events": update.get("events") or state.get("events") or []},
                {
                    "type": "agent.graph.task_planning",
                    "status": str((update.get("workflow_match") or {}).get("status") or "ok"),
                    "message": "Planned tool-task path with fixed-workflow-first policy.",
                    "metadata": planning,
                },
            ),
        }

    def _node_match_workflow(self, state: ImageAgentState) -> dict[str, Any]:
        decision = state.get("decision") or {}
        workflow_type = str(decision.get("workflow_type") or "")
        lane = decision.get("action_lane") or decision.get("lane")
        if self._looks_like_observe_repair(state):
            update = {
                "lane": OBSERVE_REPAIR_LANE,
                "workflow_match": {"status": "not_applicable", "reason": "task observation request"},
            }
            return self._with_match_event(state, update)
        if lane == INCUBATION_LANE:
            update = {
                "lane": INCUBATION_LANE,
                "workflow_match": {"status": "no_fixed_match", "workflow_type": workflow_type},
            }
            return self._with_match_event(state, update)
        if decision.get("intent") != "run_workflow":
            update = {
                "lane": READ_ONLY_LANE,
                "workflow_match": {"status": "not_applicable", "reason": "read-only intent"},
            }
            return self._with_match_event(state, update)
        if not self._asks_for_fixed_workflow_confirmation(state.get("message", "")):
            update = {
                "lane": READ_ONLY_LANE,
                "workflow_match": {
                    "status": "not_applicable",
                    "reason": "explicit workflow launch intent is required before confirmation",
                },
            }
            return self._with_match_event(state, update)
        if workflow_type:
            workflow = self._registry_workflow(workflow_type, state)
            if workflow and workflow.get("lane") == FIXED_WORKFLOW:
                update = {
                    "lane": FIXED_WORKFLOW,
                    "workflow_match": {
                        "status": "exact_fixed_match",
                        "workflow_type": workflow_type,
                        "runtime_workflow_type": workflow.get("runtime_workflow_type") or workflow_type,
                    },
                }
                return self._with_match_event(state, update)
            update = {
                "lane": INCUBATION_LANE,
                "workflow_match": {
                    "status": "no_fixed_match",
                    "workflow_type": workflow_type,
                    "reason": "workflow is not a fixed registry entry",
                },
            }
            return self._with_match_event(state, update)
        workflow = self._match_fixed_workflow_by_capability(state)
        if workflow is not None:
            matched_workflow_type = str(workflow.get("type") or "")
            decision = {**decision, "workflow_type": matched_workflow_type}
            update = {
                "lane": FIXED_WORKFLOW,
                "decision": decision,
                "workflow_match": {
                    "status": "capability_fixed_match",
                    "workflow_type": matched_workflow_type,
                    "runtime_workflow_type": workflow.get("runtime_workflow_type") or matched_workflow_type,
                },
            }
            return self._with_match_event(state, update)
        update = {
            "lane": INCUBATION_LANE,
            "workflow_match": {"status": "no_fixed_match", "reason": "planner did not select a fixed workflow"},
        }
        return self._with_match_event(state, update)

    def _node_fixed_workflow(self, state: ImageAgentState) -> dict[str, Any]:
        result = self._prepare_confirmation(
            decision=state.get("decision") or {},
            project_context=state.get("project_context") or {},
            selected_skill=state.get("selected_skill") or "image-agent-workflow-runner",
            skill_context=state.get("skill_context") or {},
            retrieved_context=state.get("retrieved_context") or {},
            planner_tool_trace=state.get("planner_tool_trace") or [],
        )
        preflight = result.get("confirmation", {}).get("preflight") or result.get("preflight")
        return {
            "lane": FIXED_WORKFLOW,
            "preflight": preflight,
            "confirmation": result.get("confirmation"),
            "answer": result.get("answer"),
            "result": {**result, "events": self._append_events(state, result.get("events") or []), "production_task_created": False},
            "production_task_created": False,
            "events": self._append_events(state, result.get("events") or []),
        }

    def _node_incubation(self, state: ImageAgentState) -> dict[str, Any]:
        result = self._prepare_toolchain_proposal(
            decision=state.get("decision") or {},
            project_context=state.get("project_context") or {},
            selected_skill=state.get("selected_skill") or "image-agent-workflow-runner",
            skill_context=state.get("skill_context") or {},
            retrieved_context=state.get("retrieved_context") or {},
            planner_tool_trace=state.get("planner_tool_trace") or [],
        )
        proposal = self._normalize_toolchain_proposal(
            result.get("proposed_toolchain") or {},
            state=state,
        )
        result["proposed_toolchain"] = proposal
        result["production_task_created"] = False
        result["task_creation_allowed"] = False
        return {
            "lane": INCUBATION_LANE,
            "proposal": proposal,
            "result": {**result, "events": self._append_events(state, result.get("events") or [])},
            "production_task_created": False,
            "events": self._append_events(state, result.get("events") or []),
        }

    def _node_read_only(self, state: ImageAgentState) -> dict[str, Any]:
        answer = self._answer(
            message=state.get("message", ""),
            project_context=state.get("project_context") or {},
            decision=state.get("decision") or {},
            skill_context=state.get("skill_context") or {},
            retrieved_context=state.get("retrieved_context") or {},
        )
        answer = self._stabilize_read_only_answer(answer, state)
        return {
            "lane": READ_ONLY_LANE,
            "answer": answer,
            "result": {
                "status": "answered",
                "intent": state.get("intent"),
                "selected_skill": state.get("selected_skill"),
                "skill_context": self._public_skill_context(state.get("skill_context") or {}),
                "retrieved_context": state.get("retrieved_context") or {},
                "answer": answer,
                "decision": state.get("decision") or {},
                "events": self._append_event(
                    state,
                    {"type": "agent.final", "status": "ok", "message": "Answered without workflow execution."},
                ),
                "production_task_created": False,
            },
            "production_task_created": False,
            "events": self._append_event(
                state,
                {"type": "agent.final", "status": "ok", "message": "Answered without workflow execution."},
            ),
        }

    def _node_observe_repair(self, state: ImageAgentState) -> dict[str, Any]:
        task = self._select_observed_task(state)
        observation = {
            "task_id": task.get("id") if task else None,
            "workflow_type": task.get("workflow_type") if task else None,
            "status": task.get("status") if task else "unknown",
            "progress": task.get("progress") if task else None,
            "error_message": task.get("error_message") if task else "No failed task matched the request.",
        }
        repair_plan = {
            "status": "draft_only",
            "policy": "read_only_observe_repair",
            "auto_retry_allowed": False,
            "auto_rerun_allowed": False,
            "requires_preflight_before_retry": True,
            "requires_human_confirmation_before_retry": True,
            "forbidden_actions": ["auto_retry", "auto_rerun", "task_creation"],
            "blocking_reason": "Retries must re-enter registry, preflight, and human confirmation.",
            "next_steps": [
                "Review sanitized task logs and result-summary evidence.",
                "Fix the reported runtime or input blocker.",
                "Run preflight again before any retry.",
                "Require human confirmation before creating a retry task.",
            ],
            "production_task_created": False,
        }
        answer = (
            f"Task {observation['task_id']} is {observation['status']}. "
            f"Reason: {observation['error_message']}. "
            "I can draft a repair plan, but I will not retry without registry, preflight, and human confirmation."
        )
        answer = self._answer(
            message=state.get("message", ""),
            project_context={
                **(state.get("project_context") or {}),
                "task_observation": observation,
                "repair_plan": repair_plan,
            },
            decision={
                **(state.get("decision") or {}),
                "intent": "observe_repair",
                "auto_retry_allowed": False,
                "production_task_created": False,
            },
            skill_context=state.get("skill_context") or {},
            retrieved_context=state.get("retrieved_context") or {},
            extra_context={
                "Task observation JSON": observation,
                "Repair plan JSON": repair_plan,
            },
        )
        if self._answer_stopped_early(answer):
            answer = self._observe_repair_fallback_answer(observation, repair_plan)
        return {
            "lane": OBSERVE_REPAIR_LANE,
            "task_observation": observation,
            "repair_plan": repair_plan,
            "answer": answer,
            "result": {
                "status": "answered",
                "intent": "debug_failure",
                "selected_skill": state.get("selected_skill") or "image-agent-operator",
                "retrieved_context": state.get("retrieved_context") or {},
                "answer": answer,
                "task_observation": observation,
                "repair_plan": repair_plan,
                "events": self._append_event(
                    state,
                    {
                        "type": "agent.repair_plan_drafted",
                        "status": "ok",
                        "message": "Drafted repair plan without retry.",
                    },
                ),
                "production_task_created": False,
            },
            "production_task_created": False,
            "events": self._append_event(
                state,
                {
                    "type": "agent.repair_plan_drafted",
                    "status": "ok",
                    "message": "Drafted repair plan without retry.",
                },
            ),
        }

    def _stabilize_read_only_answer(self, answer: str, state: ImageAgentState) -> str:
        message = state.get("message", "")
        project_context = self._chat_style_project_context(state)
        if _is_inventory_capability_question(message):
            return _inventory_capability_reply(project_context, message=message)
        if _is_result_analysis_question(message):
            recommended_next_step = (
                (state.get("decision") or {}).get("recommended_next_step")
                or (state.get("decision") or {}).get("tool_chain_hint")
                or "Review backend task records and registered result artifacts before preparing any workflow."
            )
            stable_answer = _status_reply(project_context, str(recommended_next_step), message=message)
            if self._answer_stopped_early(answer) or "No workflow was launched" not in str(answer):
                return stable_answer
        if self._answer_stopped_early(answer):
            recommended_next_step = (
                (state.get("decision") or {}).get("recommended_next_step")
                or (state.get("decision") or {}).get("tool_chain_hint")
                or "Review uploaded files, detected series, task status, and workflow eligibility before preparing any workflow."
            )
            return _generic_read_only_reply(project_context, str(recommended_next_step))
        return answer

    def _chat_style_project_context(self, state: ImageAgentState) -> dict[str, Any]:
        project_context = dict(state.get("project_context") or {})
        project_context.setdefault("supported_workflows", project_context.get("workflows") or [])
        project_context.setdefault("result_summaries", project_context.get("result_summaries") or [])
        project_context.setdefault("outputs", project_context.get("outputs") or [])
        project_context.setdefault("tasks", project_context.get("tasks") or [])
        return project_context

    @staticmethod
    def _answer_stopped_early(answer: str | None) -> bool:
        text = " ".join(str(answer or "").split())
        if not text:
            return True
        lowered = text.lower()
        deflection_markers = (
            "请把你要我先回答的具体问题发给我",
            "请把具体问题发给我",
            "请明确你的问题",
            "没有收到明确的问题",
            "please send the specific question",
            "please provide the specific question",
            "i did not receive a clear question",
        )
        if any(marker in lowered for marker in deflection_markers):
            return True
        if any(marker in text for marker in ("我先看", "先看一下", "先看一看", "我来查看", "我会查看")):
            return True
        early_markers = (
            "我先看",
            "先看一下",
            "let me check",
            "i will inspect",
            "i'll inspect",
            "thinking",
        )
        return any(marker in text.lower() for marker in early_markers)

    @staticmethod
    def _observe_repair_fallback_answer(observation: dict[str, Any], repair_plan: dict[str, Any]) -> str:
        next_steps = repair_plan.get("next_steps") if isinstance(repair_plan.get("next_steps"), list) else []
        return (
            "Observation summary\n"
            f"1. Task {observation.get('task_id')} is {observation.get('status')} at {observation.get('progress')}%.\n"
            f"2. Workflow: {observation.get('workflow_type') or 'unknown'}.\n"
            f"3. Reported reason: {observation.get('error_message') or 'No task error message was recorded.'}\n\n"
            "Repair policy\n"
            "1. This is a read-only ObserveRepair review.\n"
            "2. I will not retry, rerun, or create a production task automatically.\n"
            "3. Any retry must go through registry, preflight, human confirmation, fingerprint verification, task_service.create_series_task(), and the pipeline runner.\n\n"
            "Suggested next steps\n"
            + "\n".join(f"{index}. {step}" for index, step in enumerate(next_steps, 1))
        ).strip()

    def _append_event(self, state: ImageAgentState, event: dict[str, Any]) -> list[dict[str, Any]]:
        return [*(state.get("events") or []), event]

    def _append_events(self, state: ImageAgentState, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [*(state.get("events") or []), *events]

    def _with_match_event(self, state: ImageAgentState, update: dict[str, Any]) -> dict[str, Any]:
        match = update.get("workflow_match") or {}
        lane = update.get("lane")
        return {
            **update,
            "events": self._append_event(
                state,
                {
                    "type": "agent.graph.match_workflow",
                    "status": str(match.get("status") or "ok"),
                    "message": f"Routed agent lane to {lane or 'unknown'}.",
                    "metadata": {
                        "lane": lane,
                        "workflow_type": match.get("workflow_type"),
                        "reason": match.get("reason"),
                    },
                },
            ),
        }

    def _route_lane(self, state: ImageAgentState) -> str:
        lane = state.get("lane")
        if lane in {READ_ONLY_LANE, FIXED_WORKFLOW, INCUBATION_LANE, OBSERVE_REPAIR_LANE}:
            return lane
        return READ_ONLY_LANE

    def _route_after_skill_selection(self, state: ImageAgentState) -> str:
        if state.get("router_lane") == TOOL_TASK_ROUTER_LANE:
            return TOOL_TASK_ROUTER_LANE
        return READ_ONLY_LANE

    def _route_requirement_completeness(self, state: ImageAgentState) -> str:
        completeness = state.get("requirement_completeness") or {}
        if completeness.get("status") == "needs_clarification":
            return "needs_clarification"
        return "complete"

    def _state_to_result(self, state: ImageAgentState) -> dict[str, Any]:
        result = dict(state.get("result") or {})
        result.setdefault("status", "answered")
        result.setdefault("production_task_created", False)
        result["safe_metadata"] = {
            **(result.get("safe_metadata") or {}),
            "agent_engine": "langgraph",
            "graph_runtime": self.graph_runtime,
            "lane": state.get("lane"),
        }
        result["graph_state"] = self._public_graph_state(state)
        if state.get("proposal"):
            result["proposed_toolchain"] = state["proposal"]
        if state.get("task_observation"):
            result["task_observation"] = state["task_observation"]
        if state.get("repair_plan"):
            result["repair_plan"] = state["repair_plan"]
        return result

    def _resume_gate_state(self, *, thread_id: str, approved: bool, confirmation: dict[str, Any]) -> dict[str, Any]:
        if not approved:
            return {"lane": None, "confirmation_gate": "cancelled"}
        record = self.thread_store.load(thread_id)
        if record is None or record.get("status") != "pending_confirmation":
            return {"lane": None, "confirmation_gate": "pending_confirmation_missing"}
        if self.thread_store.is_expired(record):
            return {"lane": record.get("confirmation", {}).get("action_lane"), "confirmation_gate": "expired"}
        pending_confirmation = record.get("confirmation") or {}
        stored_fingerprint = record.get("confirmation_fingerprint")
        provided_fingerprint = None
        if isinstance(confirmation, dict):
            provided_fingerprint = confirmation.get("fingerprint") or confirmation.get("confirmation_fingerprint")
        if provided_fingerprint is not None and provided_fingerprint != stored_fingerprint:
            return {"lane": pending_confirmation.get("action_lane"), "confirmation_gate": "fingerprint_mismatch"}
        if (
            confirmation_fingerprint(pending_confirmation) != stored_fingerprint
            or confirmation_fingerprint(confirmation or {}) != stored_fingerprint
        ):
            return {"lane": pending_confirmation.get("action_lane"), "confirmation_gate": "fingerprint_mismatch"}
        if pending_confirmation.get("action_lane") == INCUBATION_LANE:
            return {"lane": INCUBATION_LANE, "confirmation_gate": "incubation_blocked"}
        return {"lane": pending_confirmation.get("action_lane") or FIXED_WORKFLOW, "confirmation_gate": "fingerprint_verified"}

    def _annotate_resume_result(self, result: dict[str, Any], *, gate_state: dict[str, Any]) -> dict[str, Any]:
        annotated = dict(result)
        production_task_created = annotated.get("production_task_created") is True
        lane = gate_state.get("lane")
        annotated["safe_metadata"] = {
            **(annotated.get("safe_metadata") or {}),
            "agent_engine": "langgraph",
            "graph_runtime": self.graph_runtime,
            "lane": lane,
            "confirmation_gate": gate_state.get("confirmation_gate"),
        }
        annotated["graph_state"] = {
            **(annotated.get("graph_state") or {}),
            "lane": lane,
            "confirmation_gate": gate_state.get("confirmation_gate"),
            "production_task_created": production_task_created,
        }
        annotated.setdefault("production_task_created", production_task_created)
        return annotated

    def _public_graph_state(self, state: ImageAgentState) -> dict[str, Any]:
        return {
            "intent": state.get("intent"),
            "lane": state.get("lane"),
            "router_lane": state.get("router_lane"),
            "risk_assessment": state.get("risk_assessment") or {"level": "unknown", "flags": []},
            "intent_decision": state.get("intent_decision"),
            "rule_intent_signal": state.get("rule_intent_signal"),
            "llm_intent_signal": state.get("llm_intent_signal"),
            "requirement_completeness": state.get("requirement_completeness"),
            "neuroimaging_intake": state.get("neuroimaging_intake"),
            "sequence_normalization": state.get("sequence_normalization"),
            "task_planning": state.get("task_planning"),
            "workflow_match": state.get("workflow_match"),
            "preflight": state.get("preflight"),
            "proposal_id": (state.get("proposal") or {}).get("proposal_id") if state.get("proposal") else None,
            "task_observation": state.get("task_observation"),
            "production_task_created": False,
        }

    def _public_project_file(self, item: Any) -> dict[str, Any]:
        if not isinstance(item, dict):
            return {"id": None, "original_name": None, "file_type": "UNKNOWN"}
        return {
            "id": item.get("id"),
            "original_name": item.get("original_name") or item.get("name"),
            "file_type": item.get("file_type") or item.get("format") or "UNKNOWN",
            "size": item.get("size"),
            "sha256": item.get("sha256"),
        }

    def _public_series_summary(self, item: Any) -> dict[str, Any]:
        if not isinstance(item, dict):
            return {
                "series_id": None,
                "modality": "UNKNOWN",
                "sequence_label": "unknown",
                "supported_for_processing": False,
                "unsupported_reason": "Invalid series context record.",
            }
        supported = self._series_supported(item)
        return {
            "series_id": item.get("id") or item.get("series_id"),
            "modality": str(item.get("modality") or "UNKNOWN").upper(),
            "format": item.get("format") or "UNKNOWN",
            "sequence_label": item.get("sequence_label") or "unknown",
            "supported_for_processing": supported,
            "unsupported_reason": self._unsupported_reason(item, supported),
            "confidence": item.get("confidence"),
            "status": item.get("status"),
        }

    def _normalized_sequence_summary(self, item: Any) -> dict[str, Any]:
        if not isinstance(item, dict):
            item = {}
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        supported = self._series_supported(item)
        unsupported_reason = self._unsupported_reason(item, supported)
        limitations = [unsupported_reason] if unsupported_reason else []
        sidecars = {
            "json": bool(metadata.get("sidecar_json_summary") or metadata.get("json_sidecar") or item.get("json_sidecar")),
            "bval": bool(metadata.get("has_bval") or item.get("has_bval")),
            "bvec": bool(metadata.get("has_bvec") or item.get("has_bvec")),
        }
        return {
            "series_id": item.get("id") or item.get("series_id"),
            "modality": str(item.get("modality") or metadata.get("modality") or "UNKNOWN").upper(),
            "format": item.get("format") or metadata.get("format") or "UNKNOWN",
            "sequence_label": item.get("sequence_label") or metadata.get("sequence_label") or "unknown",
            "supported_for_processing": supported,
            "unsupported_reason": unsupported_reason,
            "limitations": limitations,
            "metadata_sources": self._metadata_sources(item, metadata),
            "metadata_precedence": SEQUENCE_METADATA_PRECEDENCE,
            "sidecars": sidecars,
            "metadata_confidence": item.get("confidence") or metadata.get("confidence"),
        }

    def _series_supported(self, item: dict[str, Any]) -> bool:
        value = item.get("supported_for_processing", item.get("supported"))
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() not in {"0", "false", "no", "unsupported"}
        return True

    def _unsupported_reason(self, item: dict[str, Any], supported: bool) -> str:
        if supported:
            return ""
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        reason = item.get("unsupported_reason") or metadata.get("unsupported_reason")
        if reason:
            return str(reason)
        sequence_label = str(item.get("sequence_label") or metadata.get("sequence_label") or "")
        if sequence_label and sequence_label != "unknown":
            return UNSUPPORTED_SEQUENCE_MESSAGE
        return "Unknown sequence; current software does not support processing for this sequence."

    def _metadata_sources(self, item: dict[str, Any], metadata: dict[str, Any]) -> list[str]:
        evidence = {
            str(value)
            for value in metadata.get("detection_evidence") or item.get("detection_evidence") or []
        }
        sources: list[str] = []
        if metadata.get("sidecar_json_summary") or "json_sidecar_summary" in evidence:
            sources.append("sidecar_json")
        if metadata.get("dicom_tags") or "dicom_tags" in evidence or "dicom_header" in evidence:
            sources.append("dicom_tags")
        if (
            "nifti_header" in evidence
            or metadata.get("shape") is not None
            or metadata.get("ndim") is not None
        ):
            sources.append("nifti_header")
        if metadata.get("filename") or item.get("filename"):
            sources.append("filename_tokens")
        return sources or ["project_context"]

    def _registry_workflow(self, workflow_type: str, state: ImageAgentState) -> dict[str, Any] | None:
        for workflow in state.get("workflow_registry") or []:
            if workflow.get("type") == workflow_type:
                return workflow
        try:
            return get_workflow(workflow_type)
        except Exception:
            return None

    def _match_fixed_workflow_by_capability(self, state: ImageAgentState) -> dict[str, Any] | None:
        decision = state.get("decision") or {}
        query = " ".join(
            str(part or "")
            for part in (
                state.get("message"),
                decision.get("summary"),
                decision.get("modality"),
            )
        )
        query_text = self._normalize_match_text(query)
        query_tokens = self._match_tokens(query_text)
        if not query_tokens:
            return None
        series_modality = self._decision_series_modality(state)
        best: tuple[int, dict[str, Any]] | None = None
        for workflow in state.get("workflow_registry") or []:
            if workflow.get("lane") != FIXED_WORKFLOW:
                continue
            if workflow.get("agent_selectable") is not True:
                continue
            if series_modality and str(workflow.get("modality") or "").upper() != series_modality:
                continue
            fields = self._workflow_capability_fields(workflow)
            field_text = self._normalize_match_text(" ".join(fields))
            field_tokens = self._match_tokens(field_text)
            score = len(query_tokens & field_tokens)
            for alias in workflow.get("agent_selection_aliases") or []:
                alias_text = self._normalize_match_text(str(alias or ""))
                if alias_text and alias_text in query_text:
                    score += 6
            if score >= 4 and (best is None or score > best[0]):
                best = (score, workflow)
        return best[1] if best else None

    def _decision_series_modality(self, state: ImageAgentState) -> str:
        decision = state.get("decision") or {}
        series_id = decision.get("series_id")
        if series_id is None:
            return ""
        for series in (state.get("project_context") or {}).get("series") or []:
            if str(series.get("id") or series.get("series_id") or "") == str(series_id):
                return str(series.get("modality") or "").upper()
        return ""

    def _workflow_capability_fields(self, workflow: dict[str, Any]) -> list[str]:
        fields = [
            workflow.get("type"),
            workflow.get("label"),
            workflow.get("display_name"),
            workflow.get("workflow_family"),
            workflow.get("workflow_role"),
            workflow.get("capability_summary"),
        ]
        for key in ("primary_outputs", "qc_outputs", "report_outputs", "limitations", "agent_selection_aliases"):
            values = workflow.get(key)
            if isinstance(values, list):
                fields.extend(str(value) for value in values)
        for stage in workflow.get("pipeline_stages") or []:
            if isinstance(stage, dict):
                fields.extend(str(stage.get(key) or "") for key in ("name", "purpose"))
        return [str(field) for field in fields if field]

    @staticmethod
    def _normalize_match_text(value: str) -> str:
        return "".join(char.lower() if char.isalnum() else " " for char in value)

    @staticmethod
    def _match_tokens(value: str) -> set[str]:
        stopwords = {
            "and",
            "for",
            "from",
            "outputs",
            "report",
            "run",
            "the",
            "with",
        }
        return {token for token in value.split() if len(token) > 2 and token not in stopwords}

    def _looks_like_observe_repair(self, state: ImageAgentState) -> bool:
        message = state.get("message", "").lower()
        if any(token in message for token in ("fail", "failed", "error", "retry", "失败", "报错", "重试")):
            return any(str(task.get("status") or "").lower() == "failed" for task in state.get("project_context", {}).get("tasks") or [])
        return False

    def _select_observed_task(self, state: ImageAgentState) -> dict[str, Any] | None:
        tasks = state.get("project_context", {}).get("tasks") or []
        message = state.get("message", "")
        for task in tasks:
            if str(task.get("id")) in message:
                return task
        return next((task for task in tasks if str(task.get("status") or "").lower() == "failed"), None)

    def _normalize_toolchain_proposal(self, proposal: dict[str, Any], *, state: ImageAgentState) -> dict[str, Any]:
        objective = proposal.get("objective") or (state.get("decision") or {}).get("summary") or "Unknown workflow proposal"
        input_modality = proposal.get("input_modality") or (state.get("decision") or {}).get("modality") or "UNKNOWN"
        composition_plan = proposal.get("composition_plan") or {}
        required_inputs = composition_plan.get("required_inputs") or []
        expected_outputs = composition_plan.get("expected_outputs") or []
        return {
            **proposal,
            "contract_version": TOOLCHAIN_PROPOSAL_CONTRACT_VERSION,
            "requested_capability": objective,
            "candidate_workflow_name": self._candidate_workflow_name(objective),
            "official_sources": self._official_sources(state),
            "toolchain_steps": composition_plan.get("ordered_steps") or proposal.get("primitive_chain") or [],
            "input_contract": {
                "modality": input_modality,
                "required_files": required_inputs or ["workflow-specific inputs must be defined before promotion"],
                "required_metadata": [],
                "preflight_checks": ["fixed workflow registry entry required before production execution"],
            },
            "output_contract": {
                "result_summary_schema": self._result_summary_schema(input_modality),
                "feature_groups": self._feature_groups(input_modality),
                "required_outputs": expected_outputs or ["result-summary.json", "artifact-manifest entries"],
            },
            "runner_contract": {
                "runtime_location": "deployment_server_local",
                "docker_images": self._candidate_images(proposal),
                "requires_gpu": self._proposal_requires_gpu(proposal),
                "command_template_status": "draft_only",
            },
            "mock_control_plane_plan": [
                "unknown workflow proposal returns toolchain_proposed",
                "production_task_created remains false",
                "incubation workflow cannot call task_service",
                "frontend shows proposal not launched task",
            ],
            "real_acceptance_plan": [
                "run pinned containers on the deployment-server local Docker runtime",
                "verify real outputs are generated",
                "verify result-summary indexes real outputs",
                "verify artifact manifest download routes serve outputs",
            ],
            "blocking_gaps": self._blocking_gaps(state),
            "promotion_status": "blocked_by_gaps",
            "task_creation_allowed": False,
            "forbidden_actions": ["confirmation_creation", "production_task_creation", "pipeline_runner_launch"],
            "production_enabled": False,
            "production_task_created": False,
        }

    def _official_sources(self, state: ImageAgentState) -> list[dict[str, Any]]:
        results = (state.get("retrieved_context") or {}).get("results") or []
        sources = []
        for item in results[:5]:
            source = item.get("source")
            if source:
                sources.append({"local_doc": source, "source_type": item.get("source_type") or "rag_reference"})
        if sources:
            return sources
        return [{"source_type": "assumption", "note": "official source evidence must be collected before promotion"}]

    def _candidate_workflow_name(self, objective: str) -> str:
        safe = "".join(char if char.isalnum() else "_" for char in objective.lower()).strip("_")[:48]
        return f"incubated_{safe or 'workflow'}"

    def _result_summary_schema(self, modality: str) -> str:
        modality = (modality or "UNKNOWN").upper()
        if modality in {"T1", "BOLD", "DWI"}:
            return f"{modality}_INCUBATION"
        return "INCUBATION"

    def _feature_groups(self, modality: str) -> list[str]:
        base = ["native_qc", "scientific_report"]
        if str(modality).upper() == "DWI":
            return ["preprocessed_dwi", "reconstruction", "connectivity_matrix", *base]
        if str(modality).upper() == "BOLD":
            return ["preprocessed_bold", "timeseries_metrics", *base]
        if str(modality).upper() == "T1":
            return ["anatomical_segmentation", *base]
        return ["pipeline_outputs", *base]

    def _candidate_images(self, proposal: dict[str, Any]) -> list[dict[str, Any]]:
        images = []
        for step in proposal.get("primitive_chain") or []:
            image = step.get("image")
            if image:
                name, _, version = str(image).partition(":")
                images.append({"name": name, "version": version or "unpinned"})
        return images

    def _proposal_requires_gpu(self, proposal: dict[str, Any]) -> bool:
        return any(bool(step.get("uses_gpu")) for step in proposal.get("primitive_chain") or [])

    def _blocking_gaps(self, state: ImageAgentState) -> list[str]:
        gaps = ["No fixed workflow registry entry exists."]
        retrieved = (state.get("retrieved_context") or {}).get("results") or []
        if not retrieved:
            gaps.append("Official source evidence has not been collected.")
        gaps.extend(
            [
                "Runner implementation is draft-only.",
                "Result-summary writer is not implemented for this proposal.",
                "Real acceptance evidence is missing.",
                "Frontend result view mapping is not approved.",
            ]
        )
        return gaps
