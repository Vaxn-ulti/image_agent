from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.agent.incubation import IncubationLedger
from app.agent.model_gateway import ModelGateway
from app.agent.prompt_loader import load_prompt
from app.agent.rag_orchestration import retrieve_reference_context
from app.agent.skill_loader import load_skill_context, select_skill
from app.agent.thread_store import AgentThreadStore, confirmation_fingerprint
from app.agent.tools import create_workflow_task, preflight_workflow, sandbox_validate_toolchain
from app.core.config import DATA_ROOT
from app.workflows.registry import FIXED_WORKFLOW, INCUBATION_LANE, get_workflow, workflow_public_metadata


PLANNER_SYSTEM_PROMPT = load_prompt("planner")
RESPONDER_SYSTEM_PROMPT = load_prompt("responder")
AGENT_PLANNER_DECISION_SCHEMA: dict[str, Any] = {
    "name": "agent_planner_decision",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "intent",
            "action_lane",
            "lane",
            "workflow_type",
            "series_id",
            "summary",
            "objective",
            "modality",
            "input_modality",
            "toolchain",
            "primitives",
            "script_paths",
            "script_text",
            "risks",
            "recommended_next_step",
            "tool_chain_hint",
            "requires_confirmation",
        ],
        "properties": {
            "intent": {
                "type": "string",
                "enum": ["answer_question", "run_workflow"],
            },
            "action_lane": {
                "type": ["string", "null"],
                "enum": [FIXED_WORKFLOW, INCUBATION_LANE, None],
            },
            "lane": {
                "type": ["string", "null"],
                "enum": [FIXED_WORKFLOW, INCUBATION_LANE, None],
            },
            "workflow_type": {"type": ["string", "null"]},
            "series_id": {"type": ["integer", "null"]},
            "summary": {"type": ["string", "null"]},
            "objective": {"type": ["string", "null"]},
            "modality": {"type": ["string", "null"]},
            "input_modality": {"type": ["string", "null"]},
            "toolchain": {
                "type": ["array", "null"],
                "items": {"type": "string"},
            },
            "primitives": {
                "type": ["array", "null"],
                "items": {"type": "string"},
            },
            "script_paths": {
                "type": ["array", "null"],
                "items": {"type": "string"},
            },
            "script_text": {"type": ["string", "null"]},
            "risks": {
                "type": ["array", "null"],
                "items": {"type": "string"},
            },
            "recommended_next_step": {"type": ["string", "null"]},
            "tool_chain_hint": {"type": ["string", "null"]},
            "requires_confirmation": {"type": ["boolean", "null"]},
        },
    },
}


class AgentRunner:
    def __init__(
        self,
        gateway: ModelGateway | Any | None = None,
        *,
        rag_root: Path | str | None = None,
        incubation_ledger: IncubationLedger | None = None,
        thread_store: AgentThreadStore | None = None,
    ) -> None:
        self.gateway = gateway or ModelGateway()
        self.rag_root = Path(rag_root or Path(__file__).resolve().parents[4])
        ledger_root = Path(os.environ.get("IMAGE_AGENT_INCUBATION_ROOT", str(DATA_ROOT / "agent_incubation")))
        self.incubation_ledger = incubation_ledger or IncubationLedger(ledger_root)
        thread_root = Path(os.environ.get("IMAGE_AGENT_THREAD_ROOT", str(DATA_ROOT / "agent_threads")))
        self.thread_store = thread_store or AgentThreadStore(thread_root)

    def run(self, *, message: str, project_context: dict[str, Any]) -> dict[str, Any]:
        decision, planner_tool_trace = self._plan(message=message, project_context=project_context)
        selected_skill = select_skill(message, decision)
        skill_context = self._load_skill_trace(selected_skill)
        retrieved_context = retrieve_reference_context(
            self._retrieval_query(message, decision, selected_skill),
            root=self.rag_root,
            limit=5,
        )
        intent = decision.get("intent", "answer_question")
        if intent == "run_workflow":
            lane = decision.get("action_lane") or decision.get("lane") or FIXED_WORKFLOW
            if lane == INCUBATION_LANE:
                return self._prepare_toolchain_proposal(
                    decision=decision,
                    project_context=project_context,
                    selected_skill=selected_skill,
                    skill_context=skill_context,
                    retrieved_context=retrieved_context,
                    planner_tool_trace=planner_tool_trace,
                )
            workflow_type = str(decision.get("workflow_type") or "")
            if workflow_type:
                try:
                    workflow = get_workflow(workflow_type)
                except KeyError:
                    workflow = None
                if workflow is None or workflow.get("lane") != FIXED_WORKFLOW:
                    return self._prepare_toolchain_proposal(
                        decision={**decision, "action_lane": INCUBATION_LANE, "lane": INCUBATION_LANE},
                        project_context=project_context,
                        selected_skill=selected_skill,
                        skill_context=skill_context,
                        retrieved_context=retrieved_context,
                        planner_tool_trace=[
                            *planner_tool_trace,
                            {
                                "stage": "registry_gate",
                                "status": "no_fixed_match",
                                "workflow_type": workflow_type,
                                "production_task_created": False,
                            },
                        ],
                    )
            return self._prepare_confirmation(
                decision=decision,
                project_context=project_context,
                selected_skill=selected_skill,
                skill_context=skill_context,
                retrieved_context=retrieved_context,
                planner_tool_trace=planner_tool_trace,
            )
        answer = self._answer(
            message=message,
            project_context=project_context,
            decision=decision,
            skill_context=skill_context,
            retrieved_context=retrieved_context,
        )
        return {
            "status": "answered",
            "intent": intent,
            "action_lane": decision.get("action_lane"),
            "selected_skill": selected_skill,
            "skill_context": self._public_skill_context(skill_context),
            "retrieved_context": retrieved_context,
            "tool_trace": planner_tool_trace,
            "answer": answer,
            "decision": decision,
            "events": [{"type": "agent.final", "message": "Answered without workflow execution."}],
        }

    def resume(
        self,
        *,
        thread_id: str,
        approved: bool,
        confirmation: dict[str, Any],
        create_task_fn: Any | None = None,
    ) -> dict[str, Any]:
        if not approved:
            if self.thread_store.load(thread_id) is not None:
                self.thread_store.mark(thread_id, status="cancelled", extra={"user_confirmation": confirmation})
            return {
                "status": "cancelled",
                "thread_id": thread_id,
                "events": [{"type": "agent.confirmation_cancelled", "message": "Workflow execution was cancelled."}],
            }
        record = self.thread_store.load(thread_id)
        if record is None or record.get("status") != "pending_confirmation":
            return {
                "status": "blocked",
                "thread_id": thread_id,
                "message": "No pending server-side confirmation exists for this agent thread.",
                "production_task_created": False,
                "events": [{"type": "agent.confirmation_mismatch", "message": "Server-side pending confirmation was not found."}],
            }
        if self.thread_store.is_expired(record):
            self.thread_store.mark(thread_id, status="expired")
            return {
                "status": "blocked",
                "thread_id": thread_id,
                "message": "Pending confirmation expired.",
                "production_task_created": False,
                "events": [{"type": "agent.confirmation_expired", "message": "Pending confirmation expired."}],
            }
        pending_confirmation = record.get("confirmation") or {}
        stored_fingerprint = record.get("confirmation_fingerprint")
        provided_fingerprint = None
        if isinstance(confirmation, dict):
            provided_fingerprint = confirmation.get("fingerprint") or confirmation.get("confirmation_fingerprint")
        if provided_fingerprint is not None and provided_fingerprint != stored_fingerprint:
            return {
                "status": "blocked",
                "thread_id": thread_id,
                "message": "Confirmation payload does not match the server-side pending confirmation.",
                "production_task_created": False,
                "events": [{"type": "agent.confirmation_mismatch", "message": "Confirmation fingerprint did not match the pending plan."}],
            }
        if (
            confirmation_fingerprint(pending_confirmation) != stored_fingerprint
            or confirmation_fingerprint(confirmation or {}) != stored_fingerprint
        ):
            return {
                "status": "blocked",
                "thread_id": thread_id,
                "message": "Confirmation payload does not match the server-side pending confirmation.",
                "production_task_created": False,
                "events": [{"type": "agent.confirmation_mismatch", "message": "Confirmation payload did not match the pending plan."}],
            }
        confirmation = dict(pending_confirmation)
        if confirmation.get("action_lane") == INCUBATION_LANE:
            return {
                "status": "blocked",
                "thread_id": thread_id,
                "message": "Toolchain incubation proposals cannot create production tasks.",
                "production_task_created": False,
                "events": [{"type": "agent.toolchain_blocked", "message": "Incubation lane requires sandbox validation and human promotion."}],
            }
        tool_input = {
            "project_id": confirmation.get("project_id"),
            "series_id": confirmation.get("series_id"),
            "workflow_type": confirmation.get("workflow_type"),
        }
        if confirmation.get("runtime_workflow_type"):
            tool_input["runtime_workflow_type"] = confirmation.get("runtime_workflow_type")
        if create_task_fn is not None:
            tool_confirmation = {**confirmation, "approved": approved}
            result = create_workflow_task(confirmation=tool_confirmation, create_task_fn=create_task_fn)
            result["thread_id"] = thread_id
            if result.get("status") == "task_created":
                self.thread_store.mark(thread_id, status="task_created", extra={"task": result.get("task")})
            return result
        self.thread_store.mark(thread_id, status="ready_to_launch", extra={"tool_input": tool_input})
        return {
            "status": "ready_to_launch",
            "thread_id": thread_id,
            "backend_tool": "create_workflow_task",
            "tool_input": tool_input,
            "events": [{"type": "agent.tool_ready", "message": "Workflow launch is ready for backend execution."}],
        }

    def _plan(self, *, message: str, project_context: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        messages = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "User message:\n"
                + message
                + "\n\nBackend project context JSON:\n"
                + json.dumps(project_context, ensure_ascii=False)[:20000],
            },
        ]
        if hasattr(self.gateway, "complete_structured_with_tools"):
            planned = self.gateway.complete_structured_with_tools(
                messages,
                purpose="agent_plan",
                structured_schema=AGENT_PLANNER_DECISION_SCHEMA,
                tool_context={"project_context": project_context, "rag_root": self.rag_root},
            )
            decision = planned.get("decision", {})
            planned_tool_trace = planned.get("tool_trace", [])
            planner_mode = (
                "openai_structured_without_tool_loop"
                if planned_tool_trace and planned_tool_trace[0].get("status") == "skipped"
                else "openai_function_tools_dispatched"
            )
            tool_trace = [
                {"stage": "planner", "mode": planner_mode},
                *planned_tool_trace,
            ]
        else:
            decision = self.gateway.complete_structured(
                messages,
                purpose="agent_plan",
                structured_schema=AGENT_PLANNER_DECISION_SCHEMA,
            )
            tool_trace = [{"stage": "planner", "mode": "openai_function_tools_schema_exposed"}]
        if not isinstance(decision, dict):
            return (
                {"intent": "answer_question", "summary": "The model did not return a structured decision."},
                tool_trace,
            )
        if self._asks_for_inventory_or_capability_explanation(message):
            decision = {
                **decision,
                "intent": "answer_question",
                "action_lane": None,
                "lane": None,
                "requires_confirmation": False,
                "recommended_next_step": decision.get("recommended_next_step")
                or "Answer the uploaded-file inventory and runnable-workflow question before preparing any workflow confirmation.",
            }
            tool_trace = [
                *tool_trace,
                {
                    "stage": "intent_guard",
                    "status": "forced_read_only_inventory_capability_answer",
                    "production_task_created": False,
                },
            ]
        return decision, tool_trace

    @staticmethod
    def _asks_for_inventory_or_capability_explanation(message: str) -> bool:
        text = " ".join(str(message or "").lower().split())
        if not text:
            return False
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
        if any(token in text for token in explicit_launch_tokens):
            return False
        inventory_tokens = (
            "what did i upload",
            "what have i uploaded",
            "uploaded files",
            "current uploads",
            "\u4e0a\u4f20\u4e86\u4ec0\u4e48",
            "\u4e0a\u4f20\u7684\u6587\u4ef6",
            "\u5df2\u4e0a\u4f20",
            "\u4ec0\u4e48\u6587\u4ef6",
        )
        capability_tokens = (
            "what workflow",
            "what task",
            "what can run",
            "which workflow",
            "which task",
            "can run",
            "runnable",
            "what does",
            "explain",
            "\u53ef\u4ee5\u8dd1\u4ec0\u4e48",
            "\u80fd\u8dd1\u4ec0\u4e48",
            "\u53ef\u8dd1",
            "\u4ec0\u4e48\u4efb\u52a1",
            "\u4ec0\u4e48\u5de5\u4f5c\u6d41",
            "\u54ea\u4e9b\u5de5\u4f5c\u6d41",
            "\u4f1a\u505a\u4ec0\u4e48",
            "\u89e3\u91ca",
            "\u8bf4\u660e",
        )
        return any(token in text for token in inventory_tokens) or any(token in text for token in capability_tokens)

    def _prepare_confirmation(
        self,
        *,
        decision: dict[str, Any],
        project_context: dict[str, Any],
        selected_skill: str,
        skill_context: dict[str, Any],
        retrieved_context: dict[str, Any],
        planner_tool_trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        workflow_type = str(decision.get("workflow_type") or "")
        series_id = decision.get("series_id")
        auto_selection: dict[str, Any] | None = None
        if series_id is None:
            auto_selection = self._select_series_from_context(project_context, workflow_type=workflow_type)
            selected = auto_selection.get("selected")
            if selected is None:
                return {
                    "status": "needs_clarification",
                    "intent": "run_workflow",
                    "selected_skill": selected_skill,
                    "skill_context": self._public_skill_context(skill_context),
                    "retrieved_context": retrieved_context,
                    "answer": "Please choose the series to process before I prepare a workflow confirmation.",
                    "decision": decision,
                    "data_candidate_selection": auto_selection,
                }
            series_id = selected.get("series_id") or selected.get("id")
            decision = {**decision, "series_id": series_id, "series_auto_selected": True}
        preflight = preflight_workflow(project_context, series_id=int(series_id), workflow_type=workflow_type)
        if not preflight["ok"]:
            return {
                "status": "preflight_failed",
                "intent": "run_workflow",
                "selected_skill": selected_skill,
                "skill_context": self._public_skill_context(skill_context),
                "retrieved_context": retrieved_context,
                "answer": "Workflow preflight failed: " + "; ".join(preflight["blocking_errors"]),
                "decision": decision,
                "preflight": preflight,
                "data_candidate_selection": auto_selection,
            }
        workflow_metadata = workflow_public_metadata(workflow_type)
        runtime_workflow_type = (
            preflight.get("runtime_workflow_type")
            or workflow_metadata.get("runtime_workflow_type")
            or workflow_type
        )
        confirmation = {
            "type": "workflow_execution",
            "action_lane": FIXED_WORKFLOW,
            "title": decision.get("summary") or f"Run {workflow_type}",
            "project_id": project_context.get("project_id"),
            "series_id": int(series_id),
            "workflow_type": workflow_type,
            "runtime_workflow_type": runtime_workflow_type,
            "workflow_metadata": workflow_metadata,
            "summary": decision.get("summary") or "",
            "risks": decision.get("risks")
            or (["long_runtime", "writes_project_outputs"] + (["series_auto_selected"] if auto_selection else [])),
            "preflight": preflight,
            "data_candidate_selection": auto_selection,
        }
        thread_record = self.thread_store.create_pending_confirmation(
            confirmation=confirmation,
            decision=decision,
            selected_skill=selected_skill,
            retrieved_context=retrieved_context,
        )
        public_confirmation = {**confirmation, "fingerprint": thread_record["confirmation_fingerprint"]}
        return {
            "status": "confirmation_required",
            "thread_id": thread_record["thread_id"],
            "intent": "run_workflow",
            "action_lane": FIXED_WORKFLOW,
            "selected_skill": selected_skill,
            "skill_context": self._public_skill_context(skill_context),
            "retrieved_context": retrieved_context,
            "decision": decision,
            "confirmation": public_confirmation,
            "data_candidate_selection": auto_selection,
            "tool_trace": [
                *planner_tool_trace,
                *(
                    [{"stage": "data_selection", "tool": "select_incubation_dataset", "status": auto_selection.get("status")}]
                    if auto_selection
                    else []
                ),
                {"stage": "preflight", "tool": "preflight_workflow", "status": "pass"},
            ],
            "events": [{"type": "agent.confirmation_required", "message": confirmation["title"]}],
        }

    def _select_series_from_context(self, project_context: dict[str, Any], *, workflow_type: str) -> dict[str, Any]:
        candidates = []
        for series in project_context.get("series") or []:
            candidate = dict(series)
            modality = str(candidate.get("modality") or "")
            score = 0
            blocking_errors: list[str] = []
            if not candidate.get("supported_for_processing", True):
                blocking_errors.append(candidate.get("unsupported_reason") or "series is not supported")
            else:
                score += 20
            try:
                from app.workflows.registry import get_workflow

                workflow = get_workflow(workflow_type)
                expected_modality = workflow.get("modality")
            except Exception:
                expected_modality = None
            if expected_modality and modality != expected_modality:
                blocking_errors.append(f"workflow expects {expected_modality} but series is {modality}")
                score -= 50
            elif expected_modality:
                score += 30
            metadata = candidate.get("metadata") or {}
            fmt = str(candidate.get("format") or "")
            if candidate.get("bids_path") or fmt.endswith("_BIDS") or metadata.get("bids_path") or metadata.get("dataset_description"):
                score += 25
            if modality == "DWI":
                sidecars = metadata.get("sidecars") if isinstance(metadata.get("sidecars"), dict) else {}
                missing = [
                    name
                    for name in ("json", "bval", "bvec")
                    if not (metadata.get(f"has_{name}") or sidecars.get(f".{name}") or metadata.get(f"{name}_path"))
                ]
                if missing:
                    blocking_errors.append("DWI sidecars missing: " + ", ".join(missing))
                else:
                    score += 20
            candidate["score"] = max(score, 0)
            candidate["blocking_errors"] = blocking_errors
            candidate["recommended_for_incubation"] = candidate["score"] > 0 and not blocking_errors
            candidates.append(candidate)
        ranked = sorted(candidates, key=lambda item: (-int(item.get("score") or 0), int(item.get("id") or item.get("series_id") or 0)))
        selected = next((item for item in ranked if item.get("recommended_for_incubation")), None)
        if selected is not None:
            selected = {
                "series_id": selected.get("id") or selected.get("series_id"),
                "modality": selected.get("modality"),
                "sequence_label": selected.get("sequence_label") or "",
                "score": selected.get("score"),
                "recommended_for_incubation": True,
            }
        return {
            "status": "selected" if selected else "blocked",
            "selected": selected,
            "candidates": ranked[:5],
            "production_task_created": False,
        }

    def _prepare_toolchain_proposal(
        self,
        *,
        decision: dict[str, Any],
        project_context: dict[str, Any],
        selected_skill: str,
        skill_context: dict[str, Any],
        retrieved_context: dict[str, Any],
        planner_tool_trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        objective = str(decision.get("summary") or decision.get("objective") or "Propose a new image processing toolchain")
        input_modality = decision.get("input_modality") or decision.get("modality")
        persisted = self.incubation_ledger.create_proposal(
            objective=objective,
            input_modality=input_modality,
            primitives=decision.get("toolchain") or decision.get("primitives") or [],
            sandbox_dataset=str(project_context.get("project_id") or ""),
            script_paths=decision.get("script_paths") or [],
            script_text=decision.get("script_text"),
            requested_workflow_type=decision.get("workflow_type"),
            requested_action_lane=decision.get("action_lane") or decision.get("lane"),
        )
        proposal = {
            "proposal_id": persisted["proposal_id"],
            "contract_version": persisted["contract_version"],
            "lane": persisted["lane"],
            "action_lane": persisted["action_lane"],
            "requested_action_lane": persisted["requested_action_lane"],
            "requested_workflow_type": persisted["requested_workflow_type"],
            "status": persisted["status"],
            "objective": persisted["objective"],
            "input_modality": persisted["input_modality"],
            "primitives": persisted["primitive_chain"],
            "primitive_chain": persisted["primitive_chain"],
            "decomposition": persisted["decomposition"],
            "composition_plan": persisted["composition_plan"],
            "promotion_gate": persisted["promotion_gate"],
            "sandbox_dataset": persisted["sandbox_dataset"],
            "task_created": False,
            "confirmation_created": False,
            "production_enabled": False,
            "production_task_created": False,
            "next_step": "sandbox_validate_toolchain",
        }
        validation = sandbox_validate_toolchain(proposal)
        self.incubation_ledger.append_validation(
            proposal["proposal_id"],
            status="pending",
            report={"checks": validation.get("checks", []), "note": "Initial agent proposal requires real sandbox execution."},
        )
        return {
            "status": "toolchain_proposed",
            "intent": "run_workflow",
            "action_lane": INCUBATION_LANE,
            "selected_skill": selected_skill,
            "skill_context": self._public_skill_context(skill_context),
            "retrieved_context": retrieved_context,
            "decision": decision,
            "project_id": project_context.get("project_id"),
            "proposed_toolchain": proposal,
            "validation": validation,
            "production_task_created": False,
            "tool_trace": [
                *planner_tool_trace,
                {"stage": "incubation", "tool": "propose_toolchain", "status": proposal["status"]},
                {"stage": "incubation", "tool": "sandbox_validate_toolchain", "status": validation["status"]},
            ],
            "events": [{"type": "agent.toolchain_proposed", "message": proposal["objective"]}],
        }

    def _answer(
        self,
        *,
        message: str,
        project_context: dict[str, Any],
        decision: dict[str, Any],
        skill_context: dict[str, Any],
        retrieved_context: dict[str, Any],
    ) -> str:
        messages = [
            {"role": "system", "content": RESPONDER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "User message:\n"
                + message
                + "\n\nDecision JSON:\n"
                + json.dumps(decision, ensure_ascii=False)
                + "\n\nSelected skill JSON:\n"
                + json.dumps(self._public_skill_context(skill_context), ensure_ascii=False)[:8000]
                + "\n\nRetrieved reference context JSON:\n"
                + json.dumps(retrieved_context, ensure_ascii=False)[:12000]
                + "\n\nBackend project context JSON:\n"
                + json.dumps(project_context, ensure_ascii=False)[:20000],
            },
        ]
        return self.gateway.complete_text(messages, purpose="agent_answer")

    def _load_skill_trace(self, selected_skill: str) -> dict[str, Any]:
        try:
            return load_skill_context(selected_skill)
        except FileNotFoundError:
            return {"name": selected_skill, "description": "", "body": "", "references": []}

    def _public_skill_context(self, skill_context: dict[str, Any]) -> dict[str, Any]:
        references = [
            {"path": item.get("path"), "name": item.get("name")}
            for item in skill_context.get("references", [])
        ]
        return {
            "name": skill_context.get("name"),
            "description": skill_context.get("description", ""),
            "skill_path": skill_context.get("skill_path", ""),
            "references": references,
        }

    def _retrieval_query(self, message: str, decision: dict[str, Any], selected_skill: str) -> str:
        return " ".join(
            str(part)
            for part in (
                message,
                decision.get("summary", ""),
                decision.get("workflow_type", ""),
                selected_skill,
            )
            if part
        )
