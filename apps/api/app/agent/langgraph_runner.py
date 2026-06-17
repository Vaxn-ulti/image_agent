from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from app.agent.graph import AgentRunner
from app.agent.incubation import IncubationLedger
from app.agent.model_gateway import ModelGateway
from app.agent.rag_orchestration import retrieve_reference_context
from app.agent.skill_loader import select_skill
from app.agent.state import ImageAgentState
from app.agent.thread_store import AgentThreadStore, confirmation_fingerprint
from app.agent.tools import preflight_workflow
from app.core.config import DATA_ROOT
from app.workflows.registry import FIXED_WORKFLOW, INCUBATION_LANE, get_workflow


READ_ONLY_LANE = "read_only"
OBSERVE_REPAIR_LANE = "observe_repair"
TOOLCHAIN_PROPOSAL_CONTRACT_VERSION = "toolchain_proposal.v1"


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
        graph.add_node("load_context", self._node_load_context)
        graph.add_node("classify_intent", self._node_classify_intent)
        graph.add_node("retrieve_rag", self._node_retrieve_rag)
        graph.add_node("select_skill", self._node_select_skill)
        graph.add_node("match_workflow", self._node_match_workflow)
        graph.add_node("read_only", self._node_read_only)
        graph.add_node("fixed_workflow", self._node_fixed_workflow)
        graph.add_node("incubation", self._node_incubation)
        graph.add_node("observe_repair", self._node_observe_repair)
        graph.set_entry_point("load_context")
        graph.add_edge("load_context", "classify_intent")
        graph.add_edge("classify_intent", "retrieve_rag")
        graph.add_edge("retrieve_rag", "select_skill")
        graph.add_edge("select_skill", "match_workflow")
        graph.add_conditional_edges(
            "match_workflow",
            self._route_lane,
            {
                READ_ONLY_LANE: "read_only",
                FIXED_WORKFLOW: "fixed_workflow",
                INCUBATION_LANE: "incubation",
                OBSERVE_REPAIR_LANE: "observe_repair",
            },
        )
        graph.add_edge("read_only", END)
        graph.add_edge("fixed_workflow", END)
        graph.add_edge("incubation", END)
        graph.add_edge("observe_repair", END)
        return graph.compile()

    def _run_fallback_graph(self, state: ImageAgentState) -> ImageAgentState:
        for node in (
            self._node_load_context,
            self._node_classify_intent,
            self._node_retrieve_rag,
            self._node_select_skill,
            self._node_match_workflow,
        ):
            state.update(node(state))
        lane = self._route_lane(state)
        if lane == FIXED_WORKFLOW:
            state.update(self._node_fixed_workflow(state))
        elif lane == INCUBATION_LANE:
            state.update(self._node_incubation(state))
        elif lane == OBSERVE_REPAIR_LANE:
            state.update(self._node_observe_repair(state))
        else:
            state.update(self._node_read_only(state))
        return state

    def _node_load_context(self, state: ImageAgentState) -> dict[str, Any]:
        return {
            "project_id": state.get("project_context", {}).get("project_id"),
            "workflow_registry": state.get("project_context", {}).get("workflows") or [],
            "production_task_created": False,
        }

    def _node_classify_intent(self, state: ImageAgentState) -> dict[str, Any]:
        decision, planner_tool_trace = self._plan(
            message=state.get("message", ""),
            project_context=state.get("project_context") or {},
        )
        intent = str(decision.get("intent") or "answer_question")
        return {
            "intent": intent,
            "decision": decision,
            "planner_tool_trace": planner_tool_trace,
        }

    def _node_retrieve_rag(self, state: ImageAgentState) -> dict[str, Any]:
        decision = state.get("decision") or {}
        selected_skill = select_skill(state.get("message", ""), decision)
        retrieved_context = retrieve_reference_context(
            self._retrieval_query(state.get("message", ""), decision, selected_skill),
            root=self.rag_root,
            limit=5,
        )
        return {"retrieved_context": retrieved_context}

    def _node_select_skill(self, state: ImageAgentState) -> dict[str, Any]:
        decision = state.get("decision") or {}
        selected_skill = select_skill(state.get("message", ""), decision)
        skill_context = self._load_skill_trace(selected_skill)
        return {
            "selected_skill": selected_skill,
            "skill_context": skill_context,
        }

    def _node_match_workflow(self, state: ImageAgentState) -> dict[str, Any]:
        decision = state.get("decision") or {}
        workflow_type = str(decision.get("workflow_type") or "")
        lane = decision.get("action_lane") or decision.get("lane")
        if self._looks_like_observe_repair(state):
            return {
                "lane": OBSERVE_REPAIR_LANE,
                "workflow_match": {"status": "not_applicable", "reason": "task observation request"},
            }
        if lane == INCUBATION_LANE:
            return {
                "lane": INCUBATION_LANE,
                "workflow_match": {"status": "no_fixed_match", "workflow_type": workflow_type},
            }
        if workflow_type:
            workflow = self._registry_workflow(workflow_type, state)
            if workflow and workflow.get("lane") == FIXED_WORKFLOW:
                return {
                    "lane": FIXED_WORKFLOW,
                    "workflow_match": {
                        "status": "exact_fixed_match",
                        "workflow_type": workflow_type,
                        "runtime_workflow_type": workflow.get("runtime_workflow_type") or workflow_type,
                    },
                }
            return {
                "lane": INCUBATION_LANE,
                "workflow_match": {
                    "status": "no_fixed_match",
                    "workflow_type": workflow_type,
                    "reason": "workflow is not a fixed registry entry",
                },
            }
        if decision.get("intent") == "run_workflow":
            return {
                "lane": INCUBATION_LANE,
                "workflow_match": {"status": "no_fixed_match", "reason": "planner did not select a fixed workflow"},
            }
        return {
            "lane": READ_ONLY_LANE,
            "workflow_match": {"status": "not_applicable"},
        }

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
            "result": {**result, "production_task_created": False},
            "production_task_created": False,
            "events": result.get("events") or [],
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
        return {
            "lane": INCUBATION_LANE,
            "proposal": proposal,
            "result": result,
            "production_task_created": False,
            "events": result.get("events") or [],
        }

    def _node_read_only(self, state: ImageAgentState) -> dict[str, Any]:
        answer = self._answer(
            message=state.get("message", ""),
            project_context=state.get("project_context") or {},
            decision=state.get("decision") or {},
            skill_context=state.get("skill_context") or {},
            retrieved_context=state.get("retrieved_context") or {},
        )
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
                "events": [{"type": "agent.final", "message": "Answered without workflow execution."}],
                "production_task_created": False,
            },
            "production_task_created": False,
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
            "auto_retry_allowed": False,
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
                "events": [{"type": "agent.repair_plan_drafted", "message": "Drafted repair plan without retry."}],
                "production_task_created": False,
            },
            "production_task_created": False,
        }

    def _route_lane(self, state: ImageAgentState) -> str:
        lane = state.get("lane")
        if lane in {READ_ONLY_LANE, FIXED_WORKFLOW, INCUBATION_LANE, OBSERVE_REPAIR_LANE}:
            return lane
        return READ_ONLY_LANE

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
        if confirmation_fingerprint(confirmation) != record.get("confirmation_fingerprint"):
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
            "workflow_match": state.get("workflow_match"),
            "preflight": state.get("preflight"),
            "proposal_id": (state.get("proposal") or {}).get("proposal_id") if state.get("proposal") else None,
            "task_observation": state.get("task_observation"),
            "production_task_created": False,
        }

    def _registry_workflow(self, workflow_type: str, state: ImageAgentState) -> dict[str, Any] | None:
        for workflow in state.get("workflow_registry") or []:
            if workflow.get("type") == workflow_type:
                return workflow
        try:
            return get_workflow(workflow_type)
        except Exception:
            return None

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
