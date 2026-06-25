from __future__ import annotations

import json
import os
import shlex
import uuid
from pathlib import Path
from typing import Any

from app.db.database import now_iso

TOOLCHAIN_PROPOSAL_CONTRACT_VERSION = "toolchain_proposal.v1"
INCUBATION_LANE = "toolchain_incubation"
INCUBATION_FORBIDDEN_ACTIONS = ["confirmation_creation", "production_task_creation", "pipeline_runner_launch"]


class IncubationLedger:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, proposal_id: str) -> Path:
        return self.root / f"{proposal_id}.json"

    def create_proposal(
        self,
        *,
        objective: str,
        input_modality: str | None,
        primitives: list[Any],
        sandbox_dataset: str | None = None,
        script_paths: list[Path | str] | None = None,
        script_text: str | None = None,
        known_script_roots: list[Path | str] | None = None,
        requested_workflow_type: str | None = None,
        requested_action_lane: str | None = None,
    ) -> dict[str, Any]:
        proposal_id = "inc_" + uuid.uuid4().hex[:12]
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
            proposal_id=proposal_id,
            primitive_chain=primitive_chain,
        )
        validation_plan = build_validation_plan(
            proposal_id=proposal_id,
            composition_plan=composition_plan,
            primitive_chain=primitive_chain,
        )
        payload = {
            "proposal_id": proposal_id,
            "contract_version": TOOLCHAIN_PROPOSAL_CONTRACT_VERSION,
            "lane": INCUBATION_LANE,
            "action_lane": INCUBATION_LANE,
            "requested_action_lane": str(requested_action_lane or "").strip(),
            "requested_workflow_type": str(requested_workflow_type or "").strip(),
            "status": "proposed",
            "objective": objective,
            "input_modality": input_modality or "UNKNOWN",
            "primitive_chain": primitive_chain,
            "decomposition": decomposition,
            "composition_plan": composition_plan,
            "container_inspection_plan": container_inspection_plan,
            "validation_plan": validation_plan,
            "promotion_gate": build_promotion_gate(composition_plan, validation_plan=validation_plan),
            "sandbox_dataset": sandbox_dataset or "",
            "validation_runs": [],
            "human_reviews": [],
            "promotion_suggestion": None,
            "task_created": False,
            "confirmation_created": False,
            "task_creation_allowed": False,
            "forbidden_actions": INCUBATION_FORBIDDEN_ACTIONS,
            "production_enabled": False,
            "production_task_created": False,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        self._write(payload)
        return payload

    def get_proposal(self, proposal_id: str) -> dict[str, Any]:
        path = self._path(proposal_id)
        if not path.exists():
            raise FileNotFoundError(f"Incubation proposal not found: {proposal_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def append_validation(self, proposal_id: str, *, status: str, report: dict[str, Any]) -> dict[str, Any]:
        payload = self.get_proposal(proposal_id)
        validation = {
            "validation_run": len(payload.get("validation_runs") or []) + 1,
            "status": status,
            "report": report,
            "created_at": now_iso(),
            "production_task_created": False,
        }
        payload.setdefault("validation_runs", []).append(validation)
        payload["status"] = "validated" if status == "passed" else "validation_failed"
        payload["updated_at"] = now_iso()
        self._write(payload)
        return validation

    def append_human_review(self, proposal_id: str, *, reviewer: str, decision: str, notes: str = "") -> dict[str, Any]:
        payload = self.get_proposal(proposal_id)
        review = {"reviewer": reviewer, "decision": decision, "notes": notes, "created_at": now_iso()}
        payload.setdefault("human_reviews", []).append(review)
        payload["updated_at"] = now_iso()
        self._write(payload)
        return review

    def generate_promotion_suggestion(self, proposal_id: str, *, minimum_passed_validations: int = 2) -> dict[str, Any]:
        payload = self.get_proposal(proposal_id)
        readiness = assess_promotion_readiness(payload, minimum_passed_validations=minimum_passed_validations)
        if not readiness["ready"]:
            suggestion = {
                "status": "promotion_blocked",
                "proposal_id": proposal_id,
                "blocking_errors": readiness["blocking_errors"],
                "production_enabled": False,
                "created_at": now_iso(),
            }
            payload["promotion_suggestion"] = suggestion
            payload["status"] = "promotion_blocked"
            payload["production_enabled"] = False
            payload["updated_at"] = now_iso()
            self._write(payload)
            return suggestion
        safe_name = "".join(ch if ch.isalnum() else "_" for ch in payload["objective"].lower()).strip("_")[:48] or proposal_id
        suggestion = {
            "status": "promotion_suggested",
            "proposal_id": proposal_id,
            "suggested_workflow_type": f"incubated_{safe_name}",
            "readiness": readiness,
            "artifact_drafts": build_promotion_artifact_drafts(payload, workflow_type=f"incubated_{safe_name}"),
            "required_artifacts": [
                "workflow registry entry",
                "backend runner",
                "preflight contract",
                "result-summary contract",
                "skill/RAG reference update",
            ],
            "production_enabled": False,
            "created_at": now_iso(),
        }
        payload["promotion_suggestion"] = suggestion
        payload["status"] = "promotion_suggested"
        payload["production_enabled"] = False
        payload["updated_at"] = now_iso()
        self._write(payload)
        return suggestion

    def _write(self, payload: dict[str, Any]) -> None:
        self._path(payload["proposal_id"]).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def decompose_toolchain_steps(
    *,
    primitives: list[Any] | None = None,
    script_paths: list[Path | str] | None = None,
    script_text: str | None = None,
    known_script_roots: list[Path | str] | None = None,
    input_modality: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    primitive_chain: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []

    for index, primitive in enumerate(primitives or [], start=1):
        primitive_chain.append(_normalize_declared_primitive(primitive, source="explicit", order=index))

    for script_path in script_paths or []:
        path = _resolve_known_script_path(script_path, known_script_roots)
        text = path.read_text(encoding="utf-8")
        before = len(primitive_chain)
        primitive_chain.extend(_parse_script_text(text, source=str(path), start_order=len(primitive_chain) + 1))
        sources.append(
            {
                "type": "script_path",
                "path": str(path),
                "entries": len(primitive_chain) - before,
            }
        )

    if script_text:
        before = len(primitive_chain)
        primitive_chain.extend(_parse_script_text(script_text, source="inline_text", start_order=len(primitive_chain) + 1))
        sources.append({"type": "script_text", "entries": len(primitive_chain) - before})

    primitive_chain = enrich_primitive_contracts(primitive_chain, input_modality=input_modality)
    status = "parsed" if primitive_chain else "empty"
    return primitive_chain, {
        "status": status,
        "sources": sources,
        "entry_count": len(primitive_chain),
        "production_enabled": False,
        "production_task_created": False,
        "note": "Container/script decomposition is proposal metadata only and cannot launch production tasks.",
    }


def build_composition_plan(
    *,
    objective: str,
    input_modality: str | None,
    primitive_chain: list[dict[str, Any]],
) -> dict[str, Any]:
    ordered_steps = []
    required_inputs: list[str] = []
    expected_outputs: list[str] = []
    validation_checks: list[dict[str, Any]] = []
    risk_flags: list[str] = []
    for step in primitive_chain:
        contract = step.get("contract") or {}
        ordered_steps.append(
            {
                "order": step.get("order"),
                "name": step.get("name") or contract.get("stage") or step.get("image") or step.get("script"),
                "kind": step.get("kind"),
                "stage": contract.get("stage", "unknown"),
                "source": step.get("source"),
                "line": step.get("line"),
            }
        )
        required_inputs.extend(contract.get("required_inputs") or [])
        expected_outputs.extend(contract.get("expected_outputs") or [])
        validation_checks.extend(contract.get("validation_checks") or [])
        risk_flags.extend(contract.get("risk_flags") or [])
    return {
        "objective": objective,
        "input_modality": input_modality or "UNKNOWN",
        "ordered_steps": ordered_steps,
        "required_inputs": _dedupe(required_inputs),
        "expected_outputs": _dedupe(expected_outputs),
        "validation_checks": _dedupe_checks(validation_checks),
        "risk_flags": _dedupe(risk_flags),
        "repeatability_requirements": [
            "pin container images or record immutable digests before production promotion",
            "run at least two sandbox validations on registered datasets",
            "write and validate a unified result-summary.json",
            "register HTML reports, tables, figures, maps, and logs as outputs",
            "capture provenance for container images, script paths, parameters, and environment",
        ],
        "production_enabled": False,
        "production_task_created": False,
    }


def build_validation_plan(
    *,
    proposal_id: str,
    composition_plan: dict[str, Any],
    primitive_chain: list[dict[str, Any]],
    minimum_passed_runs: int = 2,
) -> dict[str, Any]:
    checks = []
    seen: set[str] = set()
    for check in composition_plan.get("validation_checks") or []:
        name = str(check.get("name") or "").strip()
        if not name or name in seen:
            continue
        checks.append(
            {
                "name": name,
                "status": "required",
                "evidence_kind": _validation_evidence_kind(name),
                "expected_evidence": _validation_expected_evidence(name),
                "source_stages": _validation_source_stages(name, primitive_chain),
            }
        )
        seen.add(name)
    return {
        "plan_id": f"{proposal_id}_validation_plan",
        "proposal_id": proposal_id,
        "minimum_passed_runs": minimum_passed_runs,
        "checks": checks,
        "global_requirements": [
            "inspect container image metadata before sandbox execution",
            "run in sandbox/project-scoped directories",
            "record command provenance and redacted environment",
            "register HTML reports, figures, tables, maps, logs, and result-summary artifacts",
            "keep no production task side effects during incubation",
            "require human approval before promotion suggestion is considered",
        ],
        "production_enabled": False,
        "production_task_created": False,
    }


def build_container_inspection_plan(*, proposal_id: str, primitive_chain: list[dict[str, Any]]) -> dict[str, Any]:
    containers = [
        build_container_step_inspection_plan(step, step.get("contract") or {})
        for step in primitive_chain
        if step.get("kind") == "container"
    ]
    return {
        "plan_id": f"{proposal_id}_container_inspection_plan",
        "proposal_id": proposal_id,
        "status": "required_before_sandbox_execution" if containers else "not_required",
        "container_count": len(containers),
        "containers": containers,
        "global_requirements": [
            "inspection is executed only by backend local/runtime tools",
            "record immutable image digest or content hash when available",
            "record entrypoint, default command, user, workdir, env keys, and labels without secret values",
            "record pipeline version probes and native report/output path probes",
            "do not mount patient data during image inspection",
            "do not create production tasks during incubation inspection",
        ],
        "production_enabled": False,
        "production_task_created": False,
    }


def build_container_step_inspection_plan(step: dict[str, Any], contract: dict[str, Any] | None = None) -> dict[str, Any]:
    contract = contract or {}
    runtime = str(step.get("runtime") or "container")
    image = str(step.get("image") or "UNKNOWN")
    stage = str(contract.get("stage") or "container_step")
    return {
        "step_order": step.get("order"),
        "stage": stage,
        "runtime": runtime,
        "image": image,
        "source": step.get("source"),
        "line": step.get("line"),
        "inspection_method": "backend_runtime_only",
        "metadata_fields": [
            "image_id",
            "repo_digests",
            "created",
            "config.entrypoint",
            "config.cmd",
            "config.env_keys",
            "config.labels",
            "config.working_dir",
            "config.user",
        ],
        "version_probes": _container_version_probes(image=image, stage=stage),
        "native_output_path_probes": _container_native_output_probes(image=image, stage=stage),
        "required_evidence": [
            "container_image_inspected",
            "container_digest_recorded",
            "container_entrypoint_recorded",
            "container_versions_recorded",
            "container_native_output_paths_verified",
        ],
        "forbidden_during_inspection": [
            "patient-data mounts",
            "production task creation",
            "license file content logging",
            "full environment dumps",
        ],
        "production_enabled": False,
        "production_task_created": False,
    }


def _container_version_probes(*, image: str, stage: str) -> list[dict[str, Any]]:
    lowered = f"{image} {stage}".lower()
    if "fmriprep" in lowered:
        return [
            {"command": "fmriprep --version", "expected_contains": "fmriprep"},
            {"command": "python -c 'import niworkflows; print(niworkflows.__version__)'", "expected_contains": "."},
        ]
    if "xcp" in lowered or "xcp_d" in lowered or "xcp-d" in lowered:
        return [
            {"command": "xcp_d --version", "expected_contains": "xcp_d"},
            {"command": "python -c 'import xcp_d; print(xcp_d.__version__)'", "expected_contains": "."},
        ]
    if "deepprep" in lowered:
        return [
            {"command": "deepprep --version", "expected_contains": "DeepPrep"},
            {"command": "python -c 'import sys; print(sys.version)'", "expected_contains": "."},
        ]
    if "freesurfer" in lowered:
        return [{"command": "recon-all -version", "expected_contains": "freesurfer"}]
    if "qsiprep" in lowered:
        return [{"command": "qsiprep --version", "expected_contains": "qsiprep"}]
    if "qsirecon" in lowered:
        return [{"command": "qsirecon --version", "expected_contains": "qsirecon"}]
    return [{"command": "<image-specific version command>", "expected_contains": "<pipeline name or version>"}]


def _container_native_output_probes(*, image: str, stage: str) -> list[dict[str, Any]]:
    lowered = f"{image} {stage}".lower()
    if "fmriprep" in lowered:
        return [
            {"artifact_kind": "report", "pattern": "sub-*.html"},
            {"artifact_kind": "figure", "pattern": "sub-*/figures/*.{svg,png,jpg,jpeg,webp}"},
            {"artifact_kind": "table", "pattern": "sub-*/func/*desc-confounds_timeseries.tsv"},
            {"artifact_kind": "map", "pattern": "sub-*/func/*desc-preproc_bold.nii*"},
        ]
    if "xcp" in lowered or "xcp_d" in lowered or "xcp-d" in lowered:
        return [
            {"artifact_kind": "report", "pattern": "sub-*.html"},
            {"artifact_kind": "figure", "pattern": "sub-*/figures/*.{svg,png,jpg,jpeg,webp}"},
            {"artifact_kind": "table", "pattern": "**/*.{tsv,csv,json}"},
            {"artifact_kind": "map", "pattern": "**/*.{nii,nii.gz,dtseries.nii,ptseries.nii,dscalar.nii}"},
        ]
    if "deepprep" in lowered:
        return [
            {"artifact_kind": "report", "pattern": "**/*.{html,pdf}"},
            {"artifact_kind": "figure", "pattern": "**/*.{png,jpg,jpeg,svg}"},
            {"artifact_kind": "table", "pattern": "**/*.{tsv,csv,json,stats}"},
        ]
    if "freesurfer" in lowered:
        return [
            {"artifact_kind": "table", "pattern": "stats/*.stats"},
            {"artifact_kind": "surface", "pattern": "surf/*"},
            {"artifact_kind": "segmentation", "pattern": "mri/*"},
        ]
    return [
        {"artifact_kind": "report", "pattern": "**/*.{html,pdf}"},
        {"artifact_kind": "figure", "pattern": "**/*.{svg,png,jpg,jpeg,webp}"},
        {"artifact_kind": "table", "pattern": "**/*.{tsv,csv,json}"},
        {"artifact_kind": "log", "pattern": "logs/*"},
    ]


def build_promotion_gate(composition_plan: dict[str, Any], *, validation_plan: dict[str, Any] | None = None) -> dict[str, Any]:
    required_checks = [
        {"name": "repeated_sandbox_validation", "status": "required"},
        {"name": "human_review_approval", "status": "required"},
        {"name": "workflow_registry_draft", "status": "required"},
        {"name": "backend_runner_draft", "status": "required"},
        {"name": "preflight_contract_draft", "status": "required"},
        {"name": "result_summary_contract_draft", "status": "required"},
        {"name": "artifact_registration_contract", "status": "required"},
        {"name": "skill_and_rag_reference_update", "status": "required"},
    ]
    check_names = {item["name"] for item in required_checks}
    for check in composition_plan.get("validation_checks") or []:
        name = check.get("name")
        if name and name not in check_names:
            required_checks.append({"name": name, "status": "required"})
            check_names.add(name)
    return {
        "status": "promotion_blocked_until_all_required_checks_pass",
        "required_checks": required_checks,
        "validation_plan_id": validation_plan.get("plan_id") if validation_plan else None,
        "production_enabled": False,
        "production_task_created": False,
    }


def _validation_evidence_kind(name: str) -> str:
    lowered = name.lower()
    if any(item in lowered for item in ["image_inspected", "digest", "entrypoint", "versions", "native_output_paths"]):
        return "container_inspection"
    if name == "container_image_recorded":
        return "container_inspection"
    if "mount" in lowered:
        return "mount_audit"
    if "exit_code" in lowered or "gpu_runtime" in lowered or "container" in lowered:
        return "runtime"
    if "report" in lowered or "exists" in lowered or "tables" in lowered or "outputs" in lowered or "figures" in lowered:
        return "artifact"
    if "schema" in lowered or "summary" in lowered:
        return "contract"
    if "label" in lowered or "parameterized" in lowered:
        return "parameter_audit"
    return "review"


def _validation_expected_evidence(name: str) -> str:
    mapping = {
        "fmriprep_html_report_exists": "fMRIPrep HTML report registered under outputs.reports",
        "preprocessed_bold_exists": "preprocessed BOLD map registered under outputs.maps",
        "confounds_tsv_exists": "confounds TSV registered under outputs.tables",
        "xcpd_html_report_exists": "XCP-D HTML report registered under outputs.reports",
        "xcpd_metrics_tables_exist": "XCP-D metrics/QC TSV tables registered under outputs.tables or outputs.metrics",
        "input_mounts_are_read_only": "all input_data mounts have read_only=true",
        "license_mount_is_read_only": "all license_file mounts have read_only=true and license contents are not logged",
        "output_and_work_mounts_are_sandbox_scoped": "output_data, work_dir, and templateflow_cache mounts are scoped to sandbox or project task roots",
        "container_exit_code_zero": "container runtime event records exit code 0",
        "container_image_recorded": "container image name or immutable digest captured in provenance",
        "container_image_inspected": "backend image inspection manifest exists for the container image",
        "container_digest_recorded": "image digest, image id, or equivalent content hash is recorded",
        "container_entrypoint_recorded": "image entrypoint, default command, user, and working directory are recorded",
        "container_versions_recorded": "pipeline version probes are captured without patient data mounts",
        "container_native_output_paths_verified": "native report, figure, table, map, and log output path probes are documented",
        "no_writes_outside_sandbox": "mount audit and output discovery show no writes outside sandbox/project roots",
        "participant_label_parameterized": "participant label is passed as a parameter or derived from backend state",
        "gpu_runtime_available": "GPU runtime check passes before launch when the primitive requires GPU",
    }
    return mapping.get(name, f"evidence for {name} is present in validation report")


def _validation_source_stages(name: str, primitive_chain: list[dict[str, Any]]) -> list[str]:
    stages = []
    for step in primitive_chain:
        contract = step.get("contract") or {}
        checks = {str(item.get("name") or "") for item in contract.get("validation_checks") or []}
        if name in checks:
            stages.append(str(contract.get("stage") or step.get("image") or step.get("name") or "unknown"))
    return _dedupe(stages)


def build_promotion_artifact_drafts(proposal: dict[str, Any], *, workflow_type: str | None = None) -> dict[str, Any]:
    safe_workflow_type = workflow_type or _suggested_workflow_type(str(proposal.get("objective") or "incubated_workflow"))
    composition_plan = proposal.get("composition_plan") or build_composition_plan(
        objective=str(proposal.get("objective") or safe_workflow_type),
        input_modality=proposal.get("input_modality"),
        primitive_chain=proposal.get("primitive_chain") or [],
    )
    return {
        "workflow_registry_entry": {
            "type": safe_workflow_type,
            "label": str(proposal.get("objective") or safe_workflow_type),
            "modality": proposal.get("input_modality") or "ANY",
            "lane": "fixed_workflow",
            "status": "draft_from_incubation",
            "agent_selectable": False,
            "requires_confirmation": True,
            "runtime_backend": "draft_runner_required",
            "runtime_workflow_type": safe_workflow_type,
            "input_requirements": composition_plan.get("required_inputs") or [],
            "expected_outputs": composition_plan.get("expected_outputs") or [],
            "result_summary_schema": "draft",
            "source_proposal_id": proposal.get("proposal_id"),
            "production_enabled": False,
        },
        "backend_runner_contract": {
            "runner_name": f"run_{safe_workflow_type}",
            "must_use": [
                "backend task runtime",
                "sandbox-scoped work/output directories",
                "structured task events",
                "result-summary writer",
                "output artifact registration",
            ],
            "must_not_use": [
                "raw LLM shell execution",
                "unreviewed script paths",
                "writes outside project derivative roots",
                "implicit production enablement",
            ],
            "primitive_steps": composition_plan.get("ordered_steps") or [],
        },
        "preflight_contract": {
            "checks": composition_plan.get("validation_checks") or [],
            "required_inputs": composition_plan.get("required_inputs") or [],
            "risk_flags": composition_plan.get("risk_flags") or [],
            "must_pass_before_confirmation": True,
        },
        "result_summary_contract": {
            "required": True,
            "required_fields": [
                "task_id",
                "workflow_type",
                "status",
                "feature_groups",
                "outputs",
                "provenance",
                "warnings",
            ],
            "expected_outputs": composition_plan.get("expected_outputs") or [],
            "artifact_groups": ["reports", "tables", "figures", "maps", "logs"],
        },
        "skill_and_rag_updates": {
            "skill_references": [
                "docs/skills/image-agent-workflow-runner/references/workflow-registry.md",
                "docs/skills/image-agent-result-reviewer/references/result-review-policy.md",
            ],
            "rag_documents": [
                f"docs/rag/workflows/{safe_workflow_type}.md",
                f"docs/rag/troubleshooting/{safe_workflow_type}_errors.md",
            ],
            "evals_required": True,
        },
        "production_enabled": False,
        "production_task_created": False,
    }


def enrich_primitive_contracts(
    primitive_chain: list[dict[str, Any]],
    *,
    input_modality: str | None = None,
) -> list[dict[str, Any]]:
    return [_with_step_contract(step, input_modality=input_modality) for step in primitive_chain]


def _with_step_contract(step: dict[str, Any], *, input_modality: str | None) -> dict[str, Any]:
    enriched = dict(step)
    contract = _infer_step_contract(enriched, input_modality=input_modality)
    enriched["contract"] = contract
    enriched["promotion_ready"] = False
    enriched["requires_sandbox_validation"] = True
    enriched["production_enabled"] = False
    return enriched


def _infer_step_contract(step: dict[str, Any], *, input_modality: str | None) -> dict[str, Any]:
    kind = step.get("kind")
    if kind == "container":
        return _infer_container_contract(step, input_modality=input_modality)
    if kind == "script":
        return _infer_script_contract(step, input_modality=input_modality)
    return _infer_declared_contract(step, input_modality=input_modality)


def _infer_container_contract(step: dict[str, Any], *, input_modality: str | None) -> dict[str, Any]:
    image = str(step.get("image") or "").lower()
    arguments = [str(item) for item in step.get("arguments") or []]
    volumes = [str(item) for item in step.get("volumes") or []]
    mounts = [mount for mount in step.get("mounts") or [] if isinstance(mount, dict)]
    required_inputs = ["registered sandbox dataset", "writable sandbox output root"]
    expected_outputs = ["sandbox execution log", "provenance record"]
    validation_checks = [
        {"name": "container_image_recorded", "status": "required"},
        {"name": "container_image_inspected", "status": "required"},
        {"name": "container_digest_recorded", "status": "required"},
        {"name": "container_entrypoint_recorded", "status": "required"},
        {"name": "container_versions_recorded", "status": "required"},
        {"name": "container_native_output_paths_verified", "status": "required"},
        {"name": "container_exit_code_zero", "status": "required"},
        {"name": "no_writes_outside_sandbox", "status": "required"},
    ]
    risk_flags = ["container_execution", "long_runtime"]
    security_notes = ["host paths are symbolic or sandbox-scoped"]
    stage = "container_step"
    if "fmriprep" in image:
        stage = "fmriprep_preprocessing"
        required_inputs.extend(["BIDS dataset with BOLD files", "FreeSurfer license", "TemplateFlow cache"])
        expected_outputs.extend(["fMRIPrep derivatives", "fMRIPrep HTML report", "preprocessed BOLD maps", "confounds TSV"])
        validation_checks.extend(
            [
                {"name": "fmriprep_html_report_exists", "status": "required"},
                {"name": "preprocessed_bold_exists", "status": "required"},
                {"name": "confounds_tsv_exists", "status": "required"},
            ]
        )
    elif "xcp" in image or "xcp_d" in image or "xcp-d" in image:
        stage = "xcpd_postprocessing"
        required_inputs.extend(["completed fMRIPrep derivatives", "XCP-D container parameters"])
        expected_outputs.extend(["XCP-D derivatives", "XCP-D HTML report", "motion/QC metrics", "timeseries or connectivity tables"])
        validation_checks.extend(
            [
                {"name": "xcpd_html_report_exists", "status": "required"},
                {"name": "xcpd_metrics_tables_exist", "status": "required"},
            ]
        )
    elif "deepprep" in image:
        stage = "deepprep_preprocessing"
        required_inputs.extend(["supported T1 or BOLD dataset", "FreeSurfer license"])
        expected_outputs.extend(["DeepPrep derivatives", "QC report", "segmentation or preprocessing outputs"])
        validation_checks.append({"name": "deepprep_outputs_exist", "status": "required"})
    elif "qsiprep" in image:
        stage = "qsiprep_preprocessing"
        required_inputs.extend(["DWI NIfTI", "bval", "bvec", "BIDS sidecars"])
        expected_outputs.extend(["QSIPrep derivatives", "DWI QC report"])
        validation_checks.append({"name": "qsiprep_report_exists", "status": "required"})
    elif "qsirecon" in image:
        stage = "qsirecon_reconstruction"
        required_inputs.extend(["completed QSIPrep derivatives", "reconstruction profile"])
        expected_outputs.extend(["QSIRecon derivatives", "connectometry or tractography outputs"])
        validation_checks.append({"name": "qsirecon_outputs_exist", "status": "required"})
    if step.get("uses_gpu"):
        required_inputs.append("available GPU runtime")
        validation_checks.append({"name": "gpu_runtime_available", "status": "required"})
        risk_flags.append("gpu_required")
    if any(":ro" in volume for volume in volumes):
        validation_checks.append({"name": "read_only_input_mounts_verified", "status": "required"})
    if any(_looks_writable_mount(volume) for volume in volumes):
        validation_checks.append({"name": "writable_mounts_scoped_to_sandbox", "status": "required"})
    if any(mount.get("role") == "input_data" for mount in mounts):
        validation_checks.append({"name": "input_mounts_are_read_only", "status": "required"})
    if any(mount.get("role") == "license_file" for mount in mounts):
        validation_checks.append({"name": "license_mount_is_read_only", "status": "required"})
    if any(mount.get("role") in {"output_data", "work_dir", "templateflow_cache"} for mount in mounts):
        validation_checks.append({"name": "output_and_work_mounts_are_sandbox_scoped", "status": "required"})
    if any(arg.startswith("--participant-label") for arg in arguments):
        validation_checks.append({"name": "participant_label_parameterized", "status": "required"})
    return _contract(
        stage=stage,
        input_modality=input_modality,
        required_inputs=required_inputs,
        expected_outputs=expected_outputs,
        validation_checks=validation_checks,
        risk_flags=risk_flags,
        security_notes=security_notes,
    )


def _infer_script_contract(step: dict[str, Any], *, input_modality: str | None) -> dict[str, Any]:
    script = str(step.get("script") or "").lower()
    stage = "script_step"
    required_inputs = ["registered sandbox dataset", "sandbox work directory"]
    expected_outputs = ["script execution log", "provenance record"]
    validation_checks = [
        {"name": "script_path_allowlisted", "status": "required"},
        {"name": "script_exit_code_zero", "status": "required"},
        {"name": "no_secret_values_recorded", "status": "required"},
        {"name": "no_writes_outside_sandbox", "status": "required"},
    ]
    risk_flags = ["script_execution"]
    if "postprocess" in script or "feature" in script:
        stage = "feature_postprocessing"
        required_inputs.append("completed workflow derivatives")
        expected_outputs.extend(["feature tables", "metrics JSON", "result-summary feature groups"])
        validation_checks.append({"name": "feature_tables_registered", "status": "required"})
    elif "figure" in script or "report" in script or "html" in script:
        stage = "report_generation"
        required_inputs.append("completed workflow outputs")
        expected_outputs.extend(["HTML report", "QC figures", "report manifest"])
        validation_checks.append({"name": "html_and_figures_registered", "status": "required"})
    elif "audit" in script or "validate" in script:
        stage = "validation_audit"
        expected_outputs.extend(["validation report", "coverage report"])
        validation_checks.append({"name": "validation_report_written", "status": "required"})
    elif "prepare" in script or "bids" in script:
        stage = "input_staging"
        required_inputs.append("raw imaging data")
        expected_outputs.extend(["BIDS directory", "dataset_description.json"])
        validation_checks.append({"name": "bids_layout_validated", "status": "required"})
    return _contract(
        stage=stage,
        input_modality=input_modality,
        required_inputs=required_inputs,
        expected_outputs=expected_outputs,
        validation_checks=validation_checks,
        risk_flags=risk_flags,
        security_notes=[],
    )


def _infer_declared_contract(step: dict[str, Any], *, input_modality: str | None) -> dict[str, Any]:
    name = str(step.get("name") or "").lower()
    stage = "declared_primitive"
    required_inputs = ["explicit primitive specification"]
    expected_outputs = ["primitive validation evidence"]
    validation_checks = [{"name": "primitive_bound_to_backend_runner_or_script", "status": "required"}]
    risk_flags = ["unbound_primitive"]
    if "stage" in name or "bids" in name:
        stage = "input_staging"
        required_inputs.append("raw imaging data")
        expected_outputs.append("BIDS directory")
        validation_checks.append({"name": "bids_layout_validated", "status": "required"})
    elif "report" in name or "figure" in name:
        stage = "report_generation"
        expected_outputs.extend(["HTML report", "QC figures"])
        validation_checks.append({"name": "html_and_figures_registered", "status": "required"})
    elif "summary" in name or "result" in name:
        stage = "result_contract"
        expected_outputs.append("result-summary.json")
        validation_checks.append({"name": "result_summary_schema_valid", "status": "required"})
    return _contract(
        stage=stage,
        input_modality=input_modality,
        required_inputs=required_inputs,
        expected_outputs=expected_outputs,
        validation_checks=validation_checks,
        risk_flags=risk_flags,
        security_notes=[],
    )


def _contract(
    *,
    stage: str,
    input_modality: str | None,
    required_inputs: list[str],
    expected_outputs: list[str],
    validation_checks: list[dict[str, Any]],
    risk_flags: list[str],
    security_notes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "input_modality": input_modality or "UNKNOWN",
        "required_inputs": _dedupe(required_inputs),
        "expected_outputs": _dedupe(expected_outputs),
        "validation_checks": _dedupe_checks(validation_checks),
        "risk_flags": _dedupe(risk_flags),
        "security_notes": _dedupe(security_notes or []),
        "result_summary_required": True,
        "artifact_registration_required": True,
        "human_review_required": True,
        "production_enabled": False,
    }


def _suggested_workflow_type(objective: str) -> str:
    safe_name = "".join(ch if ch.isalnum() else "_" for ch in objective.lower()).strip("_")[:48] or "workflow"
    return f"incubated_{safe_name}"


def assess_promotion_readiness(
    proposal: dict[str, Any],
    *,
    minimum_passed_validations: int = 2,
) -> dict[str, Any]:
    validations = proposal.get("validation_runs") or []
    passed_validations = [item for item in validations if item.get("status") == "passed"]
    human_reviews = proposal.get("human_reviews") or []
    approved_reviews = [item for item in human_reviews if str(item.get("decision") or "").lower() in {"approved", "approve", "accepted"}]
    blocking_errors: list[str] = []
    if len(passed_validations) < minimum_passed_validations:
        blocking_errors.append(f"requires at least {minimum_passed_validations} passed sandbox validation runs")
    if not approved_reviews:
        blocking_errors.append("requires at least one approving human review")
    if proposal.get("production_task_created") or proposal.get("production_enabled"):
        blocking_errors.append("proposal already has forbidden production side effects")
    if not proposal.get("primitive_chain"):
        blocking_errors.append("requires a non-empty primitive chain")
    return {
        "ready": not blocking_errors,
        "blocking_errors": blocking_errors,
        "passed_validation_count": len(passed_validations),
        "approved_review_count": len(approved_reviews),
        "minimum_passed_validations": minimum_passed_validations,
        "production_enabled": False,
        "production_task_created": False,
    }


def _normalize_declared_primitive(primitive: Any, *, source: str, order: int) -> dict[str, Any]:
    if isinstance(primitive, dict):
        entry = dict(primitive)
        entry.setdefault("kind", "declared_primitive")
        entry.setdefault("name", str(entry.get("primitive") or entry.get("name") or f"step_{order}"))
        entry.setdefault("source", source)
        entry.setdefault("order", order)
        entry["production_enabled"] = False
        return entry
    return {
        "kind": "declared_primitive",
        "name": str(primitive),
        "source": source,
        "order": order,
        "production_enabled": False,
    }


def _resolve_known_script_path(script_path: Path | str, known_script_roots: list[Path | str] | None) -> Path:
    path = Path(script_path).resolve()
    roots = [Path(root).resolve() for root in (known_script_roots or _default_known_script_roots())]
    if not roots:
        raise ValueError("Incubation script paths require known script roots")
    if not any(_is_relative_to(path, root) for root in roots):
        raise ValueError(f"Script path is outside known script roots: {path}")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Incubation script source not found: {path}")
    if path.suffix.lower() not in {".sh", ".bash", ".py", ".ps1", ".txt", ".md"}:
        raise ValueError(f"Unsupported incubation script source type: {path.suffix or '<none>'}")
    return path


def _default_known_script_roots() -> list[Path]:
    configured = os.environ.get("IMAGE_AGENT_INCUBATION_SCRIPT_ROOTS", "")
    roots = [Path(item).expanduser() for item in configured.split(os.pathsep) if item.strip()]
    roots.extend(
        [
            Path("<REMOTE_HOME>/project/MCI_project/scripts/remote"),
            Path("<REMOTE_HOME>/Project/MMD_project/EVIDENCE/fmriprep_xcpd_comparison_20260602/scripts"),
        ]
    )
    return [root.resolve() for root in roots if root.exists()]


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _parse_script_text(text: str, *, source: str, start_order: int) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    order = start_order
    for line_number, raw_line in _logical_script_lines(text):
        line = raw_line.strip()
        if not line:
            continue
        declared = _parse_declared_primitive(line, source=source, order=order, line_number=line_number)
        if declared is not None:
            entries.append(declared)
            order += 1
            continue
        if line.startswith("#"):
            continue
        container = _parse_container_step(line, source=source, order=order, line_number=line_number)
        if container is not None:
            entries.append(container)
            order += 1
            continue
        script = _parse_script_invocation(line, source=source, order=order, line_number=line_number)
        if script is not None:
            entries.append(script)
            order += 1
    return entries


def _logical_script_lines(text: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    buffer: list[str] = []
    start_line = 1
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        stripped_right = raw_line.rstrip()
        if not buffer:
            start_line = line_number
        if stripped_right.endswith("\\"):
            buffer.append(stripped_right[:-1].strip())
            continue
        if buffer:
            buffer.append(stripped_right.strip())
            lines.append((start_line, " ".join(part for part in buffer if part)))
            buffer = []
        else:
            lines.append((line_number, raw_line))
    if buffer:
        lines.append((start_line, " ".join(part for part in buffer if part)))
    return lines


def _parse_declared_primitive(line: str, *, source: str, order: int, line_number: int) -> dict[str, Any] | None:
    lowered = line.lower().lstrip("#").strip()
    markers = ("image-agent primitive:", "primitive:")
    marker = next((item for item in markers if lowered.startswith(item)), None)
    if marker is None:
        return None
    name = line.split(":", 1)[1].strip()
    if not name:
        return None
    return {
        "kind": "declared_primitive",
        "name": name,
        "source": source,
        "line": line_number,
        "order": order,
        "production_enabled": False,
    }


def _parse_container_step(line: str, *, source: str, order: int, line_number: int) -> dict[str, Any] | None:
    try:
        tokens = shlex.split(line, posix=True)
    except ValueError:
        return None
    if not tokens:
        return None
    tokens = _container_runtime_tokens(tokens)
    if not tokens:
        return None
    executable = Path(tokens[0]).name.lower()
    if executable not in {"docker", "podman", "singularity", "apptainer"}:
        return None
    parsed = _parse_container_tokens(executable, tokens)
    return {
        "kind": "container",
        "runtime": executable,
        "image": parsed["image"],
        "volumes": parsed["volumes"],
        "mounts": parsed["mounts"],
        "environment": parsed["environment"],
        "environment_map": parsed["environment_map"],
        "arguments": parsed["arguments"],
        "uses_gpu": parsed["uses_gpu"],
        "source": source,
        "line": line_number,
        "order": order,
        "command_preview": _redacted_preview(tokens),
        "production_enabled": False,
    }


def _container_image_from_tokens(executable: str, tokens: list[str]) -> str:
    return _parse_container_tokens(executable, tokens)["image"]


def _container_runtime_tokens(tokens: list[str]) -> list[str]:
    for index, token in enumerate(tokens):
        executable = Path(token).name.lower()
        if executable in {"docker", "podman", "singularity", "apptainer"}:
            return tokens[index:]
    return []


def _parse_container_tokens(executable: str, tokens: list[str]) -> dict[str, Any]:
    subcommands = {"run", "exec", "shell"}
    index = 1
    if index < len(tokens) and tokens[index] in subcommands:
        index += 1
    options_with_values = _container_options_with_values(executable)
    volumes: list[str] = []
    mounts: list[dict[str, Any]] = []
    environment: list[str] = []
    environment_map: dict[str, str] = {}
    uses_gpu = executable in {"singularity", "apptainer"} and any(token in {"--nv", "--rocm"} for token in tokens)
    runtime_options: list[str] = []
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            index += 1
            break
        if token.startswith("-"):
            runtime_options.append(token)
            option, inline_value = _split_option_value(token)
            if option in {"--gpus", "--gpu", "--nv", "--rocm"}:
                uses_gpu = True
            if option in options_with_values:
                value = inline_value
                if value is None and index + 1 < len(tokens):
                    value = tokens[index + 1]
                    index += 1
                if option in {"-v", "--volume", "-B", "--bind", "--mount"} and value:
                    volumes.append(value)
                    mounts.extend(_parse_mount_value(value, option=option))
                if option in {"-e", "--env"} and value:
                    environment.append(_redact_value(value))
                    key, env_value = _split_env_value(_redact_value(value))
                    if key:
                        environment_map[key] = env_value
                index += 1
            else:
                index += 1
            continue
        break
    image = tokens[index] if index < len(tokens) else "UNKNOWN"
    return {
        "image": image,
        "volumes": volumes,
        "mounts": mounts,
        "environment": environment,
        "environment_map": environment_map,
        "arguments": [_redact_value(token) for token in tokens[index + 1 : index + 17]],
        "runtime_options": runtime_options,
        "uses_gpu": uses_gpu,
    }


def _parse_mount_value(value: str, *, option: str) -> list[dict[str, Any]]:
    if option == "--mount" or value.startswith("type="):
        mount = _parse_long_mount(value)
        return [mount] if mount else []
    return [
        mount
        for mount in (_parse_bind_mount(part.strip()) for part in value.split(",") if part.strip())
        if mount is not None
    ]


def _parse_long_mount(value: str) -> dict[str, Any] | None:
    fields: dict[str, str] = {}
    flags: set[str] = set()
    for part in value.split(","):
        if "=" in part:
            key, item = part.split("=", 1)
            fields[key.strip().lower()] = item.strip()
        else:
            flags.add(part.strip().lower())
    host_path = fields.get("source") or fields.get("src")
    container_path = fields.get("target") or fields.get("dst") or fields.get("destination")
    if not host_path or not container_path:
        return None
    return _mount_record(host_path, container_path, read_only=fields.get("readonly") == "true" or "readonly" in flags or "ro" in flags)


def _parse_bind_mount(value: str) -> dict[str, Any] | None:
    parts = value.split(":")
    if len(parts) < 2:
        return None
    host_path = parts[0]
    container_path = parts[1]
    options = set(parts[2:])
    return _mount_record(host_path, container_path, read_only="ro" in options or "readonly" in options)


def _mount_record(host_path: str, container_path: str, *, read_only: bool) -> dict[str, Any]:
    return {
        "host_path": _redact_value(host_path),
        "container_path": container_path,
        "read_only": read_only,
        "role": _mount_role(host_path, container_path),
        "sandbox_scope_required": not read_only or _mount_role(host_path, container_path) in {"templateflow_cache", "work_dir", "output_data"},
    }


def _mount_role(host_path: str, container_path: str) -> str:
    lowered = f"{host_path} {container_path}".lower()
    container_lower = container_path.lower()
    if "license" in lowered or "freesurfer" in lowered:
        return "license_file"
    if container_lower in {"/templateflow"} or "templateflow" in lowered:
        return "templateflow_cache"
    if container_lower in {"/work", "/workdir", "/tmp"}:
        return "work_dir"
    if container_lower in {"/out", "/output", "/outputs"}:
        return "output_data"
    if container_lower in {"/data", "/bids", "/input", "/inputs"}:
        return "input_data"
    if "work" in lowered:
        return "work_dir"
    if "bids" in lowered:
        return "input_data"
    if "output" in lowered or "derivatives" in lowered:
        return "output_data"
    return "support"


def _split_env_value(value: str) -> tuple[str, str]:
    if "=" not in value:
        return value, ""
    key, item = value.split("=", 1)
    return key, item


def _container_options_with_values(executable: str) -> set[str]:
    docker_like = {
        "-v",
        "--volume",
        "--mount",
        "--gpus",
        "--network",
        "--net",
        "--add-host",
        "--name",
        "--env",
        "-e",
        "--env-file",
        "--user",
        "-u",
        "--workdir",
        "-w",
        "--entrypoint",
        "--cpus",
        "--memory",
        "-m",
        "--memory-reservation",
        "--memory-swap",
        "--platform",
        "--pull",
        "--label",
        "-l",
        "--publish",
        "-p",
        "--hostname",
        "-h",
        "--ipc",
        "--pid",
        "--security-opt",
        "--shm-size",
        "--ulimit",
        "--tmpfs",
        "--device",
        "--group-add",
        "--cap-add",
        "--cap-drop",
        "--log-driver",
        "--log-opt",
        "--stop-signal",
    }
    singularity_like = {
        "-B",
        "--bind",
        "--env",
        "--env-file",
        "--home",
        "--pwd",
        "--workdir",
        "--app",
        "--hostname",
        "--network",
        "--network-args",
        "--overlay",
        "--scratch",
        "--tmpdir",
    }
    if executable in {"singularity", "apptainer"}:
        return singularity_like
    return docker_like


def _split_option_value(token: str) -> tuple[str, str | None]:
    if "=" not in token:
        return token, None
    option, value = token.split("=", 1)
    return option, value


def _parse_script_invocation(line: str, *, source: str, order: int, line_number: int) -> dict[str, Any] | None:
    try:
        tokens = shlex.split(line, posix=True)
    except ValueError:
        return None
    if not tokens:
        return None
    executable = Path(tokens[0]).name.lower()
    script_path = ""
    if executable in {"python", "python3", "bash", "sh", "pwsh", "powershell"} and len(tokens) > 1:
        script_path = tokens[1]
    elif tokens[0].lower().endswith((".py", ".sh", ".bash", ".ps1")):
        script_path = tokens[0]
    if not script_path:
        return None
    return {
        "kind": "script",
        "runner": executable,
        "script": script_path,
        "source": source,
        "line": line_number,
        "order": order,
        "command_preview": _redacted_preview(tokens),
        "production_enabled": False,
    }


def _redacted_preview(tokens: list[str]) -> str:
    safe_tokens = []
    for token in tokens[:16]:
        safe_tokens.append(_redact_value(token))
    return " ".join(safe_tokens)


def _redact_value(value: str) -> str:
    upper = value.upper()
    if any(marker in upper for marker in ("TOKEN", "SECRET", "PASSWORD", "PASS=", "KEY=", "API_KEY", "OPENAI_API_KEY")):
        if "=" in value:
            return value.split("=", 1)[0] + "=<redacted>"
        return "<redacted>"
    return value


def _looks_writable_mount(volume: str) -> bool:
    parts = volume.split(":")
    if len(parts) < 2:
        return False
    options = parts[2:] if len(parts) > 2 else []
    if any(option == "ro" or option.endswith(",ro") or option.startswith("ro,") for option in options):
        return False
    return True


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def _dedupe_checks(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for check in checks:
        name = str(check.get("name") or "")
        if not name or name in seen:
            continue
        result.append(dict(check))
        seen.add(name)
    return result

