from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from app.agent.container_inspection import inspect_container_primitives, summarize_container_inspections
from app.agent.incubation import (
    assess_promotion_readiness,
    build_composition_plan,
    build_container_inspection_plan,
    build_promotion_gate,
    build_promotion_artifact_drafts,
    build_validation_plan,
    decompose_toolchain_steps,
)
from app.core.config import PROJECTS_ROOT
from app.workflows.result_contract import load_result_summary
from app.workflows.remote_scripts import (
    classify_bold_fmriprep_xcpd_artifact_stage,
    path_safe_remote_preflight_summary,
    preflight_bold_fmriprep_xcpd_remote,
)
from app.workflows.registry import FIXED_WORKFLOW, get_workflow, list_workflows as registry_list_workflows, resolve_runtime_workflow_type


RowsFn = Callable[[str, tuple[Any, ...]], list[dict[str, Any]]]


def _redact_host_paths(value: str) -> str:
    text = str(value)
    text = re.sub(r"[A-Za-z]:[\\/][^\s\"']+", "[redacted-host-path]", text)
    text = re.sub(r"/(?:home|Users|mnt|data|tmp|var)/[^\s\"']+", "[redacted-host-path]", text)
    return text


def _safe_task_for_agent(task: dict[str, Any]) -> dict[str, Any]:
    public = dict(task)
    public.pop("log_path", None)
    if public.get("error_message"):
        public["error_message"] = _redact_host_paths(str(public["error_message"]))
    return public


def parse_output(output: dict[str, Any]) -> dict[str, Any]:
    parsed = dict(output)
    metadata_json = parsed.pop("metadata_json", "{}")
    try:
        parsed["metadata"] = json.loads(metadata_json) if isinstance(metadata_json, str) else {}
    except json.JSONDecodeError:
        parsed["metadata"] = {}
    return parsed


def read_project_context(
    project_id: int | None,
    *,
    rows_fn: RowsFn,
    workflows: list[dict[str, Any]],
    projects_root: Path | None = None,
) -> dict[str, Any]:
    root = projects_root or PROJECTS_ROOT
    project = None
    if project_id is not None:
        projects = rows_fn("SELECT * FROM projects WHERE id=?", (project_id,))
        project = projects[0] if projects else None
        series = rows_fn(
            "SELECT id, project_id, modality, sequence_label, supported_for_processing, unsupported_reason, status, confidence, metadata_json "
            "FROM imaging_series WHERE project_id=? ORDER BY id DESC LIMIT 50",
            (project_id,),
        )
        tasks = rows_fn(
            "SELECT id, project_id, series_id, workflow_type, status, progress, error_message, created_at, started_at, finished_at "
            "FROM tasks WHERE project_id=? ORDER BY id DESC LIMIT 50",
            (project_id,),
        )
        outputs = rows_fn(
            "SELECT outputs.task_id, outputs.output_type, outputs.path, outputs.metadata_json "
            "FROM outputs JOIN tasks ON tasks.id=outputs.task_id WHERE tasks.project_id=? ORDER BY outputs.id DESC LIMIT 100",
            (project_id,),
        )
    else:
        series = []
        tasks = rows_fn(
            "SELECT id, project_id, series_id, workflow_type, status, progress, error_message, created_at, started_at, finished_at "
            "FROM tasks ORDER BY id DESC LIMIT 10",
            (),
        )
        outputs = []
    return {
        "project_id": project_id,
        "project": project,
        "project_root": str(root / str(project_id)) if project_id is not None else "",
        "series": [_parse_series(row) for row in series],
        "tasks": tasks,
        "outputs": [parse_output(row) for row in outputs],
        "workflows": workflows,
    }


def _parse_series(series: dict[str, Any]) -> dict[str, Any]:
    parsed = dict(series)
    metadata_json = parsed.pop("metadata_json", "{}")
    try:
        parsed["metadata"] = json.loads(metadata_json) if isinstance(metadata_json, str) else {}
    except json.JSONDecodeError:
        parsed["metadata"] = {}
    parsed["supported_for_processing"] = bool(parsed.get("supported_for_processing", 1))
    return parsed


def list_data_candidates(
    project_id: int | None,
    *,
    rows_fn: RowsFn,
    projects_root: Path | None = None,
    modality: str | None = None,
    workflow_type: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    root = projects_root or PROJECTS_ROOT
    params: list[Any] = []
    where = []
    if project_id is not None:
        where.append("s.project_id=?")
        params.append(project_id)
    if modality:
        where.append("s.modality=?")
        params.append(modality)
    clause = " WHERE " + " AND ".join(where) if where else ""
    series_rows = rows_fn(
        "SELECT s.id, s.project_id, s.file_id, s.bids_path, s.sequence_label, s.supported_for_processing, "
        "s.unsupported_reason, s.modality, s.format, s.confidence, s.metadata_json, s.status, s.created_at, "
        "f.original_name, f.storage_path, f.file_type, f.size, f.sha256 "
        f"FROM imaging_series s JOIN files f ON f.id=s.file_id{clause} ORDER BY s.id DESC LIMIT ?",
        tuple(params + [limit]),
    )
    candidates = [
        _data_candidate_from_row(row, projects_root=root, workflow_type=workflow_type)
        for row in series_rows
    ]
    return {
        "status": "ok",
        "tool": "list_data_candidates",
        "project_id": project_id,
        "workflow_type": workflow_type,
        "modality": modality,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "production_task_created": False,
    }


def select_incubation_dataset(
    project_id: int | None,
    *,
    rows_fn: RowsFn,
    projects_root: Path | None = None,
    workflow_type: str | None = None,
    modality: str | None = None,
) -> dict[str, Any]:
    inventory = list_data_candidates(
        project_id,
        rows_fn=rows_fn,
        projects_root=projects_root,
        modality=modality,
        workflow_type=workflow_type,
    )
    ranked = sorted(inventory["candidates"], key=lambda item: (-int(item["score"]), item["series_id"]))
    selected = ranked[0] if ranked and ranked[0]["score"] > 0 else None
    return {
        "status": "selected" if selected else "blocked",
        "selected": selected,
        "candidates": ranked,
        "blocking_errors": [] if selected else ["No suitable registered series found for incubation validation"],
        "selection_policy": [
            "prefer supported series matching requested modality/workflow",
            "prefer BIDS-ready or sidecar-complete data",
            "prefer existing completed related tasks when workflow requires derivatives",
            "do not expose raw image contents or sensitive path details to the model",
        ],
        "production_task_created": False,
    }


def _data_candidate_from_row(row: dict[str, Any], *, projects_root: Path, workflow_type: str | None) -> dict[str, Any]:
    series = _parse_series(row)
    metadata = series.get("metadata") or {}
    modality = str(series.get("modality") or "UNKNOWN")
    format_value = str(series.get("format") or "UNKNOWN")
    storage_path = Path(str(row.get("storage_path") or ""))
    storage_exists = storage_path.exists()
    bids_path = metadata.get("bids_path") or row.get("bids_path")
    dicom_dir = metadata.get("dicom_dir")
    sidecars = _candidate_sidecars(metadata)
    readiness = _candidate_readiness(
        modality=modality,
        format_value=format_value,
        metadata=metadata,
        workflow_type=workflow_type,
        storage_exists=storage_exists,
        bids_path=bids_path,
        dicom_dir=dicom_dir,
        sidecars=sidecars,
        supported=bool(series.get("supported_for_processing", True)),
    )
    safe_root = projects_root.resolve()
    return {
        "series_id": series.get("id"),
        "project_id": series.get("project_id"),
        "modality": modality,
        "format": format_value,
        "sequence_label": series.get("sequence_label") or metadata.get("sequence_label") or "",
        "supported_for_processing": bool(series.get("supported_for_processing", True)),
        "unsupported_reason": series.get("unsupported_reason") or "",
        "status": series.get("status"),
        "confidence": series.get("confidence"),
        "file": {
            "id": row.get("file_id"),
            "original_name": row.get("original_name"),
            "file_type": row.get("file_type"),
            "size": row.get("size"),
            "sha256": row.get("sha256"),
            "storage_exists": storage_exists,
            "storage_path_scope": _path_scope(storage_path, safe_root),
        },
        "data_layout": {
            "bids_path_present": bool(bids_path),
            "dicom_dir_present": bool(dicom_dir),
            "sidecars": sidecars,
            "metadata_keys": sorted(str(key) for key in metadata.keys() if not _sensitive_key(str(key))),
        },
        "readiness": readiness,
        "score": readiness["score"],
        "recommended_for_incubation": readiness["score"] > 0 and not readiness["blocking_errors"],
        "production_task_created": False,
    }


def _candidate_sidecars(metadata: dict[str, Any]) -> dict[str, bool]:
    sidecars = metadata.get("sidecars") if isinstance(metadata.get("sidecars"), dict) else {}
    return {
        "json": bool(metadata.get("has_json") or sidecars.get(".json") or metadata.get("json_path")),
        "bval": bool(metadata.get("has_bval") or sidecars.get(".bval") or metadata.get("bval_path")),
        "bvec": bool(metadata.get("has_bvec") or sidecars.get(".bvec") or metadata.get("bvec_path")),
        "phase_encoding": bool(metadata.get("PhaseEncodingDirection") or metadata.get("phase_encoding_direction")),
        "total_readout": bool(metadata.get("TotalReadoutTime") or metadata.get("total_readout_time")),
    }


def _candidate_readiness(
    *,
    modality: str,
    format_value: str,
    metadata: dict[str, Any],
    workflow_type: str | None,
    storage_exists: bool,
    bids_path: Any,
    dicom_dir: Any,
    sidecars: dict[str, bool],
    supported: bool,
) -> dict[str, Any]:
    checks = []
    blockers = []
    score = 0
    if supported:
        checks.append({"name": "series_supported", "status": "pass"})
        score += 20
    else:
        blockers.append("series is not supported for processing")
        checks.append({"name": "series_supported", "status": "fail"})
    if storage_exists:
        checks.append({"name": "storage_exists", "status": "pass"})
        score += 10
    else:
        checks.append({"name": "storage_exists", "status": "warn"})
    if bids_path or format_value.endswith("_BIDS") or metadata.get("dataset_description"):
        checks.append({"name": "bids_ready", "status": "pass"})
        score += 25
    elif modality == "DICOM" or dicom_dir:
        checks.append({"name": "dicom_convertible", "status": "warn"})
        score += 10
    else:
        checks.append({"name": "bids_ready", "status": "warn"})
    if modality == "DWI":
        missing = [name for name in ("json", "bval", "bvec") if not sidecars.get(name)]
        if missing:
            blockers.append("DWI sidecars missing: " + ", ".join(missing))
            checks.append({"name": "dwi_sidecars_complete", "status": "fail", "missing": missing})
        else:
            checks.append({"name": "dwi_sidecars_complete", "status": "pass"})
            score += 20
    requested_modality = _workflow_modality(workflow_type)
    if requested_modality and requested_modality != modality:
        blockers.append(f"workflow expects {requested_modality} but series is {modality}")
        checks.append({"name": "workflow_modality_match", "status": "fail"})
        score -= 50
    elif requested_modality:
        checks.append({"name": "workflow_modality_match", "status": "pass"})
        score += 20
    return {"score": max(score, 0), "checks": checks, "blocking_errors": blockers}


def _workflow_modality(workflow_type: str | None) -> str | None:
    if not workflow_type:
        return None
    try:
        workflow = get_workflow(workflow_type)
    except KeyError:
        return None
    return workflow.get("modality")


def _path_scope(path: Path, root: Path) -> str:
    if not str(path):
        return "missing"
    try:
        path.resolve().relative_to(root)
    except Exception:
        return "outside_projects_root"
    return "inside_projects_root"


def _sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in ("password", "token", "secret", "license", "key"))


def preflight_workflow(context: dict[str, Any], *, series_id: int, workflow_type: str) -> dict[str, Any]:
    series = next((item for item in context.get("series", []) if int(item.get("id")) == int(series_id)), None)
    workflow = next((item for item in context.get("workflows", []) if item.get("type") == workflow_type), None)
    try:
        registered_workflow = get_workflow(workflow_type)
    except KeyError:
        registered_workflow = None
    if workflow is None and registered_workflow is not None:
        workflow = registered_workflow
    blocking_errors: list[str] = []
    checks: list[dict[str, Any]] = []
    if series is None:
        blocking_errors.append(f"Series {series_id} was not found")
        checks.append({"name": "series_exists", "status": "fail"})
    else:
        checks.append({"name": "series_exists", "status": "pass"})
        if not series.get("supported_for_processing", True):
            reason = series.get("unsupported_reason") or "Series is not supported for processing"
            blocking_errors.append(reason)
            checks.append({"name": "series_supported", "status": "fail", "message": reason})
        else:
            checks.append({"name": "series_supported", "status": "pass"})
    if workflow is None:
        blocking_errors.append(f"Workflow {workflow_type} was not found")
        checks.append({"name": "workflow_exists", "status": "fail"})
    else:
        checks.append({"name": "workflow_exists", "status": "pass"})
        if workflow.get("lane") is not None and workflow.get("lane") != FIXED_WORKFLOW:
            blocking_errors.append(f"Workflow {workflow_type} is not a fixed production workflow")
            checks.append({"name": "fixed_workflow_lane", "status": "fail"})
        else:
            checks.append({"name": "fixed_workflow_lane", "status": "pass"})
        if series is not None and workflow.get("modality") and workflow.get("modality") != series.get("modality"):
            blocking_errors.append(f"Workflow requires {workflow.get('modality')} but series is {series.get('modality')}")
            checks.append({"name": "modality_match", "status": "fail"})
        else:
            checks.append({"name": "modality_match", "status": "pass"})
        if workflow.get("runtime_backend") == "remote_script_wrapper" and context.get("project_root"):
            project_root = Path(str(context["project_root"]))
            remote_preflight = preflight_bold_fmriprep_xcpd_remote(
                bids_dir=project_root / "derivatives" / "__pending__" / "bids",
                output_dir=project_root / "derivatives" / "__pending__" / "output",
                work_dir=project_root / "derivatives" / "__pending__" / "work",
                require_bids=False,
            )
            public_preflight = path_safe_remote_preflight_summary(remote_preflight)
            for check in public_preflight["checks"]:
                checks.append(
                    {
                        "name": f"remote_{check['name']}",
                        "status": check["status"],
                        "path_label": check.get("path_label"),
                    }
                )
            blocking_errors.extend(public_preflight["blocking_errors"])
    return {
        "ok": not blocking_errors,
        "workflow_type": workflow_type,
        "series_id": series_id,
        "checks": checks,
        "requires_confirmation": True,
        "blocking_errors": blocking_errors,
        "action_lane": workflow.get("lane") if workflow else None,
        "runtime_workflow_type": workflow.get("runtime_workflow_type") if workflow else None,
    }


def list_workflows(
    *,
    workflows: list[dict[str, Any]] | None = None,
    lane: str | None = None,
    agent_selectable: bool | None = None,
) -> list[dict[str, Any]]:
    items = [dict(item) for item in (workflows if workflows is not None else registry_list_workflows())]
    if lane is not None:
        items = [item for item in items if item.get("lane") == lane]
    if agent_selectable is not None:
        items = [item for item in items if bool(item.get("agent_selectable")) is agent_selectable]
    return items


def _read_task_raw(task_id: int, *, rows_fn: RowsFn) -> dict[str, Any]:
    rows = rows_fn(
        "SELECT id, project_id, series_id, workflow_type, status, progress, error_message, log_path, created_at, started_at, finished_at "
        "FROM tasks WHERE id=?",
        (task_id,),
    )
    if not rows:
        return {"status": "not_found", "task_id": task_id}
    task = dict(rows[0])
    return {"status": "ok", "task": task}


def read_task(task_id: int, *, rows_fn: RowsFn) -> dict[str, Any]:
    result = _read_task_raw(task_id, rows_fn=rows_fn)
    if result["status"] != "ok":
        return result
    return {**result, "task": _safe_task_for_agent(result["task"])}


def read_task_events(task_id: int, *, rows_fn: RowsFn, projects_root: Path | None = None, tail_chars: int = 12000) -> dict[str, Any]:
    task_result = _read_task_raw(task_id, rows_fn=rows_fn)
    if task_result["status"] != "ok":
        return {**task_result, "events": [], "remote_logs": []}
    task = task_result["task"]
    main_log_path = Path(str(task.get("log_path") or ""))
    main_text = main_log_path.read_text(encoding="utf-8", errors="replace") if main_log_path.exists() else ""
    root = projects_root or PROJECTS_ROOT
    output_log_dir = root / str(task["project_id"]) / "derivatives" / str(task_id) / "output" / "logs"
    remote_logs = []
    if output_log_dir.exists():
        for log_file in sorted(output_log_dir.glob("*.log")):
            try:
                text = log_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            remote_logs.append(
                {
                    "name": log_file.name,
                    "source_stage": classify_bold_fmriprep_xcpd_artifact_stage(log_file, root / str(task["project_id"]) / "derivatives" / str(task_id) / "output"),
                    "size_bytes": log_file.stat().st_size,
                    "tail": _redact_host_paths(text[-tail_chars:]),
                }
            )
    events = [
        {"type": "task.status", "status": task.get("status"), "progress": task.get("progress")},
        *[
            {
                "type": "task.remote_log",
                "name": item["name"],
                "source_stage": item.get("source_stage"),
                "size_bytes": item["size_bytes"],
            }
            for item in remote_logs
        ],
    ]
    return {
        "status": "ok",
        "task": _safe_task_for_agent(task),
        "main_log": {"tail": _redact_host_paths(main_text[-tail_chars:])},
        "remote_logs": remote_logs,
        "events": events,
    }


def read_result_summary(task_id: int, *, rows_fn: RowsFn, projects_root: Path | None = None) -> dict[str, Any]:
    task_result = read_task(task_id, rows_fn=rows_fn)
    if task_result["status"] != "ok":
        return task_result
    task = task_result["task"]
    outputs = rows_fn(
        "SELECT task_id, output_type, path, metadata_json FROM outputs WHERE task_id=? ORDER BY id",
        (task_id,),
    )
    for output in outputs:
        parsed = parse_output(output)
        path = Path(str(parsed.get("path") or ""))
        metadata = parsed.get("metadata") or {}
        if path.exists() and (metadata.get("kind") == "result_summary" or path.name.endswith("_result_summary.json")):
            return {"status": "ok", "task": task, "result_summary": json.loads(path.read_text(encoding="utf-8"))}
    root = projects_root or PROJECTS_ROOT
    output_dir = root / str(task["project_id"]) / "derivatives" / str(task_id) / "output"
    summary = load_result_summary(output_dir)
    if summary is None:
        return {"status": "not_found", "task": task, "result_summary": None}
    return {"status": "ok", "task": task, "result_summary": summary}


def create_workflow_task(
    *,
    confirmation: dict[str, Any],
    create_task_fn: Callable[[int, str, int | None], dict[str, Any]],
) -> dict[str, Any]:
    if not confirmation.get("approved"):
        return {
            "status": "confirmation_required",
            "message": "Workflow execution requires explicit user approval.",
        }
    workflow_type = str(confirmation.get("workflow_type") or "")
    try:
        workflow = get_workflow(workflow_type)
    except KeyError:
        return {"status": "blocked", "message": f"Unknown workflow_type: {workflow_type}"}
    if workflow.get("lane") != FIXED_WORKFLOW or confirmation.get("action_lane") == "toolchain_incubation":
        return {
            "status": "blocked",
            "message": "Toolchain incubation proposals cannot create production tasks.",
            "production_task_created": False,
        }
    series_id = confirmation.get("series_id")
    if series_id is None:
        return {"status": "blocked", "message": "series_id is required to create a workflow task."}
    runtime_workflow_type = resolve_runtime_workflow_type(workflow_type)
    task = create_task_fn(int(series_id), runtime_workflow_type, confirmation.get("qsiprep_task_id"))
    return {
        "status": "task_created",
        "workflow_type": workflow_type,
        "runtime_workflow_type": runtime_workflow_type,
        "task": task,
        "events": [{"type": "agent.task_created", "task_id": task.get("id"), "workflow_type": runtime_workflow_type}],
    }


def propose_toolchain(
    *,
    objective: str,
    input_modality: str | None = None,
    primitives: list[Any] | None = None,
    script_paths: list[str] | None = None,
    script_text: str | None = None,
    known_script_roots: list[str] | None = None,
) -> dict[str, Any]:
    primitive_chain, decomposition = decompose_toolchain_steps(
        primitives=primitives,
        script_paths=script_paths,
        script_text=script_text,
        known_script_roots=known_script_roots,
        input_modality=input_modality,
    )
    composition_plan = build_composition_plan(
        objective=objective,
        input_modality=input_modality,
        primitive_chain=primitive_chain,
    )
    container_inspection_plan = build_container_inspection_plan(
        proposal_id="inline_toolchain_proposal",
        primitive_chain=primitive_chain,
    )
    validation_plan = build_validation_plan(
        proposal_id="inline_toolchain_proposal",
        composition_plan=composition_plan,
        primitive_chain=primitive_chain,
    )
    return {
        "lane": "toolchain_incubation",
        "status": "proposed",
        "objective": objective,
        "input_modality": input_modality or "UNKNOWN",
        "primitives": primitive_chain,
        "primitive_chain": primitive_chain,
        "decomposition": decomposition,
        "composition_plan": composition_plan,
        "container_inspection_plan": container_inspection_plan,
        "validation_plan": validation_plan,
        "promotion_gate": build_promotion_gate(composition_plan, validation_plan=validation_plan),
        "production_enabled": False,
        "production_task_created": False,
        "next_step": "sandbox_validate_toolchain",
    }


def sandbox_validate_toolchain(
    proposal: dict[str, Any],
    *,
    run_container_inspection: bool = False,
    inspection_runner: Callable[[list[str]], tuple[int, str, str]] | None = None,
) -> dict[str, Any]:
    inspections = []
    if run_container_inspection or inspection_runner is not None:
        inspections = inspect_container_primitives(proposal.get("primitive_chain") or proposal.get("primitives") or [], runner=inspection_runner)
    inspection_summary = summarize_container_inspections(inspections)
    return {
        "lane": "toolchain_incubation",
        "status": "sandbox_validation_required",
        "proposal": proposal,
        "production_task_created": False,
        "container_inspection": inspection_summary,
        "checks": [
            {"name": "uses_registered_primitives", "status": "pending"},
            {"name": "has_repeatable_inputs", "status": "pending"},
            {"name": "writes_result_summary_contract", "status": "pending"},
            {"name": "registers_reports_tables_figures_maps_logs", "status": "pending"},
            {"name": "records_container_script_provenance", "status": "pending"},
            {"name": "container_script_decomposition_review", "status": "pending"},
            {"name": "container_image_inspection", "status": inspection_summary["status"]},
        ],
    }


def promote_toolchain_to_workflow(proposal: dict[str, Any], *, approved: bool) -> dict[str, Any]:
    if not approved:
        return {
            "lane": "toolchain_incubation",
            "status": "needs_human_approval",
            "proposal": proposal,
            "production_task_created": False,
        }
    readiness = assess_promotion_readiness(proposal)
    if not readiness["ready"]:
        return {
            "lane": "toolchain_incubation",
            "status": "promotion_blocked",
            "proposal": proposal,
            "readiness": readiness,
            "required_before_promotion": readiness["blocking_errors"],
            "production_enabled": False,
            "production_task_created": False,
        }
    return {
        "lane": "toolchain_incubation",
        "status": "promotion_suggestion_ready",
        "proposal": proposal,
        "readiness": readiness,
        "artifact_drafts": build_promotion_artifact_drafts(proposal),
        "required_artifacts": ["workflow registry entry", "backend runner", "preflight contract", "result-summary contract", "skill/RAG reference update"],
        "production_enabled": False,
        "production_task_created": False,
    }
