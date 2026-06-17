from __future__ import annotations

from copy import deepcopy
from typing import Any


FIXED_WORKFLOW = "fixed_workflow"
INCUBATION_LANE = "toolchain_incubation"


RUNTIME_IMAGE_CONTRACTS: dict[str, dict[str, str]] = {
    "t1_deepprep_anat_report": {"deepprep": "pbfslab/deepprep:25.1.0"},
    "t1_deepprep": {"deepprep": "pbfslab/deepprep:25.1.0"},
    "t1_deepprep_validate": {"deepprep": "pbfslab/deepprep:25.1.0"},
    "bold_deepprep": {"deepprep": "pbfslab/deepprep:25.1.0"},
    "bold_deepprep_validate": {"deepprep": "pbfslab/deepprep:25.1.0"},
    "bold_fmriprep": {"fmriprep": "nipreps/fmriprep:25.2.5"},
    "bold_fmriprep_xcpd_report": {
        "fmriprep": "nipreps/fmriprep:25.2.5",
        "xcpd": "pennlinc/xcp_d:26.0.2",
    },
    "bold_fmriprep_xcpd_report_validate": {
        "fmriprep": "nipreps/fmriprep:25.2.5",
        "xcpd": "pennlinc/xcp_d:26.0.2",
    },
    "dwi_fast_gpu_dti": {"mrtrix_toolbox": "pennlinc/qsiprep:1.0.2"},
    "dwi_fast_gpu_dti_validate": {"mrtrix_toolbox": "pennlinc/qsiprep:1.0.2"},
}


WORKFLOW_CAPABILITY_CATALOG: dict[str, dict[str, Any]] = {
    "t1_deepprep_anat_report": {
        "display_name": "T1 DeepPrep anatomical processing, QC, and report",
        "workflow_family": "t1",
        "workflow_role": "anat_processing",
        "capability_summary": (
            "Runs anatomical T1 processing with DeepPrep/FreeSurfer-derived measurements, "
            "QC artifacts, structured result summary, tables, figures, and an HTML report."
        ),
        "pipeline_stages": [
            {"name": "BIDS preparation", "purpose": "Prepare supported T1 NIfTI input for anatomical processing."},
            {"name": "DeepPrep anatomical processing", "purpose": "Generate anatomical derivatives and FreeSurfer-compatible statistics."},
            {"name": "result packaging", "purpose": "Register summaries, tables, figures, QC, and report artifacts for frontend review."},
        ],
        "primary_outputs": ["anatomical derivatives", "FreeSurfer/DeepPrep statistics", "regional tables", "result-summary.json"],
        "qc_outputs": ["DeepPrep/FreeSurfer QC artifacts when available"],
        "report_outputs": ["HTML scientific report", "report figures"],
        "limitations": ["Requires supported T1 input and configured FreeSurfer license/container runtime."],
        "agent_selection_aliases": ["t1 anatomical processing", "deep prep t1", "freesurfer stats", "anatomical report"],
        "is_report_only": False,
    },
    "bold_fmriprep_xcpd_report": {
        "display_name": "BOLD fMRIPrep + XCP-D processing, metrics, QC, and report",
        "workflow_family": "bold",
        "workflow_role": "complete_processing",
        "capability_summary": (
            "Runs full BOLD preprocessing and XCP-D postprocessing, producing derived metrics, "
            "container-native QC artifacts, structured result summaries, and a scientific report."
        ),
        "pipeline_stages": [
            {"name": "BIDS preparation", "purpose": "Prepare supported BOLD NIfTI/BIDS input and optional T1/anat context."},
            {"name": "fMRIPrep preprocessing", "purpose": "Run motion/coregistration/normalization-oriented BOLD preprocessing."},
            {"name": "XCP-D postprocessing", "purpose": "Generate denoised derivatives and single-subject BOLD metrics."},
            {"name": "result packaging", "purpose": "Register metrics, native QC artifacts, result summary, and report artifacts."},
        ],
        "primary_outputs": [
            "preprocessed BOLD derivatives",
            "ALFF/fALFF/ReHo and connectivity metrics",
            "result-summary.json",
        ],
        "qc_outputs": ["container-native fMRIPrep and XCP-D QC artifacts", "HTML reports", "QC figures"],
        "report_outputs": ["HTML scientific report", "report figures", "report manifest"],
        "limitations": ["Not report-only; requires BOLD-compatible input, configured scripts, containers, and FreeSurfer license."],
        "agent_selection_aliases": [
            "bold preprocessing",
            "fmri preprocessing",
            "fmriprep xcpd",
            "bold metrics",
            "functional connectivity metrics",
            "bold qc and report",
        ],
        "is_report_only": False,
    },
    "dwi_fast_gpu_dti": {
        "display_name": "DWI fast GPU DTI maps, atlas metrics, QC, and report",
        "workflow_family": "dwi",
        "workflow_role": "complete_processing",
        "capability_summary": (
            "Runs the production DWI fast GPU DTI path with host FSL GPU eddy and MRtrix toolbox steps, "
            "producing FA/MD/AD/RD maps, atlas tables, QC/provenance, and an HTML report."
        ),
        "pipeline_stages": [
            {"name": "DWI sidecar validation", "purpose": "Require NIfTI, bval, bvec, and eddy metadata JSON."},
            {"name": "host FSL GPU correction", "purpose": "Use deployment-local FSL/GPU tools for correction and registration."},
            {"name": "MRtrix tensor metrics", "purpose": "Use the locked QSIPrep toolbox image for tensor-derived maps."},
            {"name": "result packaging", "purpose": "Register DTI maps, atlas tables, QC/provenance, and report artifacts."},
        ],
        "primary_outputs": ["FA/MD/AD/RD native maps", "MNI152 maps", "atlas regional TSV tables", "result-summary.json"],
        "qc_outputs": ["DTI QC/provenance", "finite-map checks", "runtime evidence"],
        "report_outputs": ["HTML scientific report"],
        "limitations": ["Requires DWI gradients and JSON sidecar with PhaseEncodingDirection and TotalReadoutTime."],
        "agent_selection_aliases": ["dwi dti", "fast gpu dti", "fa md maps", "diffusion tensor metrics"],
        "is_report_only": False,
    },
}


WORKFLOW_REGISTRY: list[dict[str, Any]] = [
    {
        "type": "t1_deepprep_anat_report",
        "label": "T1 DeepPrep anat-only with full features and HTML report",
        "modality": "T1",
        "lane": FIXED_WORKFLOW,
        "status": "production",
        "agent_selectable": True,
        "requires_confirmation": True,
        "runtime_class": "app.workflows.pipeline.run_pipeline_task",
        "runtime_workflow_type": "t1_deepprep",
        "input_requirements": ["supported T1 NIfTI series", "FreeSurfer license", "DeepPrep container runtime"],
        "expected_outputs": ["result-summary.json", "FreeSurfer/DeepPrep stats", "tables", "figures", "HTML report"],
    },
    {
        "type": "bold_fmriprep_xcpd_report",
        "label": "BOLD fMRIPrep + XCP-D with metrics and HTML report",
        "modality": "BOLD",
        "lane": FIXED_WORKFLOW,
        "status": "production_contract",
        "agent_selectable": True,
        "requires_confirmation": True,
        "runtime_class": "app.workflows.pipeline.run_pipeline_task",
        "runtime_backend": "deployment_local_script_wrapper",
        "runtime_workflow_type": "bold_fmriprep_xcpd_report",
        "result_summary_schema": "BOLD",
        "input_requirements": [
            "supported BOLD NIfTI/BIDS series",
            "optional companion T1/anat",
            "FreeSurfer license",
            "fMRIPrep and XCP-D container runtime",
        ],
        "expected_outputs": ["fMRIPrep derivatives", "XCP-D metrics", "QC figures", "HTML reports", "result-summary.json"],
    },
    {
        "type": "bold_fmriprep_xcpd_report_validate",
        "label": "BOLD fMRIPrep + XCP-D validate",
        "modality": "BOLD",
        "lane": FIXED_WORKFLOW,
        "status": "production_contract",
        "agent_selectable": False,
        "requires_confirmation": True,
        "runtime_class": "app.workflows.pipeline.run_pipeline_task",
        "runtime_backend": "deployment_local_script_wrapper",
        "runtime_workflow_type": "bold_fmriprep_xcpd_report_validate",
        "result_summary_schema": "BOLD",
        "input_requirements": [
            "supported BOLD NIfTI/BIDS series",
            "optional companion T1/anat",
            "FreeSurfer license",
            "fMRIPrep and XCP-D deployment-local scripts",
        ],
        "expected_outputs": ["preflight command record", "deployment-local wrapper readiness checks"],
    },
    {
        "type": "toolchain_proposal",
        "label": "Incubating toolchain proposal",
        "modality": "ANY",
        "lane": INCUBATION_LANE,
        "status": "incubation",
        "agent_selectable": True,
        "requires_confirmation": False,
        "runtime_class": "app.agent.tools.sandbox_validate_toolchain",
        "runtime_workflow_type": None,
        "input_requirements": ["objective", "input modality", "primitive tool list", "sandbox dataset"],
        "expected_outputs": ["toolchain proposal", "sandbox validation report", "human review record"],
    },
    {
        "type": "t1_deepprep",
        "label": "T1 DeepPrep",
        "modality": "T1",
        "lane": FIXED_WORKFLOW,
        "status": "legacy_supported",
        "agent_selectable": False,
        "requires_confirmation": True,
        "runtime_class": "app.workflows.pipeline.run_pipeline_task",
        "runtime_workflow_type": "t1_deepprep",
        "input_requirements": ["supported T1 NIfTI series"],
        "expected_outputs": ["DeepPrep derivatives"],
    },
    {
        "type": "t1_deepprep_validate",
        "label": "T1 DeepPrep Validate",
        "modality": "T1",
        "lane": FIXED_WORKFLOW,
        "status": "legacy_supported",
        "agent_selectable": False,
        "requires_confirmation": True,
        "runtime_class": "app.workflows.pipeline.run_pipeline_task",
        "runtime_workflow_type": "t1_deepprep_validate",
        "input_requirements": ["supported T1 NIfTI series"],
        "expected_outputs": ["validation outputs"],
    },
    {
        "type": "bold_deepprep",
        "label": "fMRI/BOLD DeepPrep",
        "modality": "BOLD",
        "lane": FIXED_WORKFLOW,
        "status": "legacy_supported",
        "agent_selectable": False,
        "requires_confirmation": True,
        "runtime_class": "app.workflows.pipeline.run_pipeline_task",
        "runtime_workflow_type": "bold_deepprep",
        "input_requirements": ["supported BOLD series"],
        "expected_outputs": ["DeepPrep BOLD derivatives"],
    },
    {
        "type": "bold_deepprep_validate",
        "label": "fMRI/BOLD DeepPrep Validate",
        "modality": "BOLD",
        "lane": FIXED_WORKFLOW,
        "status": "legacy_supported",
        "agent_selectable": False,
        "requires_confirmation": True,
        "runtime_class": "app.workflows.pipeline.run_pipeline_task",
        "runtime_workflow_type": "bold_deepprep_validate",
        "input_requirements": ["supported BOLD series"],
        "expected_outputs": ["validation outputs"],
    },
    {
        "type": "bold_alff",
        "label": "BOLD ALFF",
        "modality": "BOLD",
        "lane": FIXED_WORKFLOW,
        "status": "legacy_supported",
        "agent_selectable": False,
        "requires_confirmation": True,
        "runtime_class": "app.workflows.pipeline.run_pipeline_task",
        "runtime_workflow_type": "bold_alff",
        "input_requirements": ["completed bold_deepprep task"],
        "expected_outputs": ["ALFF maps"],
    },
    {
        "type": "bold_alff_validate",
        "label": "BOLD ALFF Validate",
        "modality": "BOLD",
        "lane": FIXED_WORKFLOW,
        "status": "legacy_supported",
        "agent_selectable": False,
        "requires_confirmation": True,
        "runtime_class": "app.workflows.pipeline.run_pipeline_task",
        "runtime_workflow_type": "bold_alff_validate",
        "input_requirements": ["supported BOLD series"],
        "expected_outputs": ["validation outputs"],
    },
    {
        "type": "bold_falff",
        "label": "BOLD fALFF",
        "modality": "BOLD",
        "lane": FIXED_WORKFLOW,
        "status": "legacy_supported",
        "agent_selectable": False,
        "requires_confirmation": True,
        "runtime_class": "app.workflows.pipeline.run_pipeline_task",
        "runtime_workflow_type": "bold_falff",
        "input_requirements": ["completed bold_deepprep task"],
        "expected_outputs": ["fALFF maps"],
    },
    {
        "type": "bold_falff_validate",
        "label": "BOLD fALFF Validate",
        "modality": "BOLD",
        "lane": FIXED_WORKFLOW,
        "status": "legacy_supported",
        "agent_selectable": False,
        "requires_confirmation": True,
        "runtime_class": "app.workflows.pipeline.run_pipeline_task",
        "runtime_workflow_type": "bold_falff_validate",
        "input_requirements": ["supported BOLD series"],
        "expected_outputs": ["validation outputs"],
    },
    {
        "type": "bold_second_level",
        "label": "BOLD downstream metrics (single subject)",
        "modality": "BOLD",
        "lane": FIXED_WORKFLOW,
        "status": "legacy_supported",
        "agent_selectable": False,
        "requires_confirmation": True,
        "runtime_class": "app.workflows.pipeline.run_pipeline_task",
        "runtime_workflow_type": "bold_second_level",
        "input_requirements": ["completed bold_deepprep task"],
        "expected_outputs": ["ALFF", "fALFF", "ReHo", "seed-to-ROI", "DMN tables"],
    },
    {
        "type": "bold_second_level_validate",
        "label": "BOLD downstream metrics Validate (single subject)",
        "modality": "BOLD",
        "lane": FIXED_WORKFLOW,
        "status": "legacy_supported",
        "agent_selectable": False,
        "requires_confirmation": True,
        "runtime_class": "app.workflows.pipeline.run_pipeline_task",
        "runtime_workflow_type": "bold_second_level_validate",
        "input_requirements": ["supported BOLD series"],
        "expected_outputs": ["validation outputs"],
    },
    {
        "type": "dwi_fast_gpu_dti",
        "label": "DWI Fast GPU DTI",
        "modality": "DWI",
        "profile": "production",
        "lane": FIXED_WORKFLOW,
        "status": "legacy_supported",
        "agent_selectable": False,
        "requires_confirmation": True,
        "runtime_class": "app.workflows.pipeline.run_pipeline_task",
        "runtime_workflow_type": "dwi_fast_gpu_dti",
        "input_requirements": ["DWI NIfTI", "bval", "bvec", "eddy metadata JSON"],
        "expected_outputs": ["FA/MD/AD/RD maps", "atlas tables", "HTML report"],
    },
    {
        "type": "dwi_fast_gpu_dti_validate",
        "label": "DWI Fast GPU DTI Validate",
        "modality": "DWI",
        "profile": "production",
        "lane": FIXED_WORKFLOW,
        "status": "legacy_supported",
        "agent_selectable": False,
        "requires_confirmation": True,
        "runtime_class": "app.workflows.pipeline.run_pipeline_task",
        "runtime_workflow_type": "dwi_fast_gpu_dti_validate",
        "input_requirements": ["DWI NIfTI", "bval", "bvec", "eddy metadata JSON"],
        "expected_outputs": ["validation outputs"],
    },
    {
        "type": "dwi_qsiprep",
        "label": "DWI QSIPrep",
        "modality": "DWI",
        "lane": INCUBATION_LANE,
        "status": "legacy_incubation",
        "agent_selectable": False,
        "requires_confirmation": True,
        "runtime_class": "app.workflows.pipeline.run_pipeline_task",
        "runtime_workflow_type": "dwi_qsiprep",
        "input_requirements": ["DWI NIfTI", "bval", "bvec"],
        "expected_outputs": ["QSIPrep derivatives"],
    },
    {
        "type": "dwi_qsiprep_validate",
        "label": "DWI QSIPrep Validate",
        "modality": "DWI",
        "lane": INCUBATION_LANE,
        "status": "legacy_incubation",
        "agent_selectable": False,
        "requires_confirmation": True,
        "runtime_class": "app.workflows.pipeline.run_pipeline_task",
        "runtime_workflow_type": "dwi_qsiprep_validate",
        "input_requirements": ["DWI NIfTI", "bval", "bvec"],
        "expected_outputs": ["validation outputs"],
    },
    {
        "type": "dwi_qsirecon",
        "label": "DWI QSIRecon",
        "modality": "DWI",
        "lane": INCUBATION_LANE,
        "status": "legacy_incubation",
        "agent_selectable": False,
        "requires_confirmation": True,
        "runtime_class": "app.workflows.pipeline.run_pipeline_task",
        "runtime_workflow_type": "dwi_qsirecon",
        "input_requirements": ["completed QSIPrep task"],
        "expected_outputs": ["QSIRecon derivatives"],
    },
    {
        "type": "dwi_qsirecon_validate",
        "label": "DWI QSIRecon Validate",
        "modality": "DWI",
        "lane": INCUBATION_LANE,
        "status": "legacy_incubation",
        "agent_selectable": False,
        "requires_confirmation": True,
        "runtime_class": "app.workflows.pipeline.run_pipeline_task",
        "runtime_workflow_type": "dwi_qsirecon_validate",
        "input_requirements": ["QSIPrep task reference"],
        "expected_outputs": ["validation outputs"],
    },
    {
        "type": "dwi_qsi_full",
        "label": "DWI QSIPrep + QSIRecon",
        "modality": "DWI",
        "lane": INCUBATION_LANE,
        "status": "legacy_incubation",
        "agent_selectable": False,
        "requires_confirmation": True,
        "runtime_class": "app.workflows.pipeline.run_pipeline_task",
        "runtime_workflow_type": "dwi_qsi_full",
        "input_requirements": ["DWI series", "companion T1/anat"],
        "expected_outputs": ["QSIPrep and QSIRecon derivatives"],
    },
    {
        "type": "dwi_qsi_full_validate",
        "label": "DWI Full Validate",
        "modality": "DWI",
        "lane": INCUBATION_LANE,
        "status": "legacy_incubation",
        "agent_selectable": False,
        "requires_confirmation": True,
        "runtime_class": "app.workflows.pipeline.run_pipeline_task",
        "runtime_workflow_type": "dwi_qsi_full_validate",
        "input_requirements": ["DWI series"],
        "expected_outputs": ["validation outputs"],
    },
    {
        "type": "dicom_convert",
        "label": "DICOM to NIfTI",
        "modality": "DICOM",
        "lane": INCUBATION_LANE,
        "status": "legacy_incubation",
        "agent_selectable": False,
        "requires_confirmation": True,
        "runtime_class": "app.workflows.pipeline.run_pipeline_task",
        "runtime_workflow_type": "dicom_convert",
        "input_requirements": ["DICOM archive series"],
        "expected_outputs": ["NIfTI files"],
    },
    {
        "type": "dicom_convert_validate",
        "label": "DICOM to NIfTI Validate",
        "modality": "DICOM",
        "lane": INCUBATION_LANE,
        "status": "legacy_incubation",
        "agent_selectable": False,
        "requires_confirmation": True,
        "runtime_class": "app.workflows.pipeline.run_pipeline_task",
        "runtime_workflow_type": "dicom_convert_validate",
        "input_requirements": ["DICOM archive series"],
        "expected_outputs": ["validation outputs"],
    },
    {
        "type": "t1_deepprep_mock",
        "label": "T1 DeepPrep Mock",
        "modality": "T1",
        "lane": INCUBATION_LANE,
        "status": "debug_only",
        "agent_selectable": False,
        "api_runnable": True,
        "requires_confirmation": True,
        "runtime_class": "app.workflows.deepprep.run_mock_deepprep",
        "runtime_workflow_type": "t1_deepprep_mock",
        "input_requirements": ["T1 series"],
        "expected_outputs": ["mock outputs"],
    },
]


def _clone(workflow: dict[str, Any]) -> dict[str, Any]:
    item = deepcopy(workflow)
    item.setdefault("type", item.get("workflow_type"))
    if item.get("runtime_class"):
        item.setdefault("execution_location", "deployment_server_local")
        item.setdefault("external_worker_server_required", False)
    runtime_images = RUNTIME_IMAGE_CONTRACTS.get(str(item.get("type") or ""))
    if runtime_images:
        item.setdefault("runtime_images", dict(runtime_images))
        item.setdefault("container_version_policy", "fixed_tag_or_digest")
    capability = WORKFLOW_CAPABILITY_CATALOG.get(str(item.get("type") or ""))
    if capability:
        for key, value in deepcopy(capability).items():
            item.setdefault(key, value)
    if item.get("lane") == FIXED_WORKFLOW:
        _apply_default_capability_metadata(item)
    return item


def _apply_default_capability_metadata(item: dict[str, Any]) -> None:
    workflow_type = str(item.get("type") or "")
    label = str(item.get("label") or workflow_type)
    modality = str(item.get("modality") or "other").lower()
    family = modality if modality in {"t1", "bold", "dwi", "dicom"} else "other"
    validate_only = workflow_type.endswith("_validate")
    role = _workflow_role(workflow_type, validate_only)
    expected_outputs = list(item.get("expected_outputs") or [])
    input_requirements = list(item.get("input_requirements") or [])

    item.setdefault("display_name", label)
    item.setdefault("workflow_family", family)
    item.setdefault("workflow_role", role)
    item.setdefault("is_report_only", False)
    item.setdefault(
        "capability_summary",
        _capability_summary(
            label=label,
            modality=family.upper(),
            role=role,
            validate_only=validate_only,
            outputs=expected_outputs,
        ),
    )
    item.setdefault(
        "pipeline_stages",
        _pipeline_stages(label=label, role=role, validate_only=validate_only),
    )
    item.setdefault("primary_outputs", expected_outputs or ["workflow outputs registered in task artifacts"])
    item.setdefault("qc_outputs", _qc_outputs(workflow_type, validate_only))
    item.setdefault("report_outputs", _report_outputs(expected_outputs, validate_only))
    item.setdefault("limitations", input_requirements or ["Requires workflow-specific input validation before execution."])


def _workflow_role(workflow_type: str, validate_only: bool) -> str:
    if validate_only:
        return "validation"
    if workflow_type.startswith("t1_"):
        return "anat_processing"
    if workflow_type.startswith("bold_alff") or workflow_type.startswith("bold_falff") or workflow_type.startswith("bold_second_level"):
        return "metrics"
    if workflow_type.startswith("bold_deepprep") or workflow_type.startswith("bold_fmriprep"):
        return "preprocessing"
    if workflow_type.startswith("dwi_fast_gpu_dti"):
        return "complete_processing"
    return "complete_processing"


def _capability_summary(*, label: str, modality: str, role: str, validate_only: bool, outputs: list[str]) -> str:
    if validate_only:
        return f"Validates the {label} execution contract for {modality} data without presenting it as production scientific output."
    output_text = ", ".join(outputs[:3]) if outputs else "registered backend artifacts"
    role_text = role.replace("_", " ")
    return f"Runs {role_text} for {modality} data and registers {output_text} for task observation and results review."


def _pipeline_stages(*, label: str, role: str, validate_only: bool) -> list[dict[str, str]]:
    if validate_only:
        return [
            {"name": "preflight validation", "purpose": f"Check whether {label} can be launched with the configured runner contract."},
            {"name": "validation record", "purpose": "Register validation evidence without claiming real scientific processing outputs."},
        ]
    return [
        {"name": "input preparation", "purpose": "Stage supported project series data for the selected workflow."},
        {"name": role.replace("_", " "), "purpose": f"Run the deployment-local pipeline runner for {label}."},
        {"name": "result packaging", "purpose": "Register task outputs, result summaries, logs, and artifact manifest entries."},
    ]


def _qc_outputs(workflow_type: str, validate_only: bool) -> list[str]:
    if validate_only:
        return ["preflight and validation logs"]
    if workflow_type.startswith("bold_fmriprep"):
        return ["container-native fMRIPrep/XCP-D QC artifacts when available"]
    if workflow_type.startswith("t1_"):
        return ["DeepPrep/FreeSurfer QC artifacts when available"]
    if workflow_type.startswith("dwi_fast_gpu_dti"):
        return ["DTI QC/provenance artifacts"]
    return ["workflow QC artifacts when registered by the runner"]


def _report_outputs(expected_outputs: list[str], validate_only: bool) -> list[str]:
    if validate_only:
        return []
    reports = [output for output in expected_outputs if "report" in str(output).lower() or "html" in str(output).lower()]
    return reports


def list_workflows(*, lane: str | None = None, agent_selectable: bool | None = None) -> list[dict[str, Any]]:
    workflows = [_clone(workflow) for workflow in WORKFLOW_REGISTRY]
    if lane is not None:
        workflows = [workflow for workflow in workflows if workflow.get("lane") == lane]
    if agent_selectable is not None:
        workflows = [workflow for workflow in workflows if bool(workflow.get("agent_selectable")) is agent_selectable]
    return workflows


def get_workflow(workflow_type: str) -> dict[str, Any]:
    for workflow in WORKFLOW_REGISTRY:
        if workflow["type"] == workflow_type:
            return _clone(workflow)
    raise KeyError(workflow_type)


def allowed_runtime_workflows() -> set[str]:
    allowed: set[str] = set()
    for workflow in WORKFLOW_REGISTRY:
        if workflow.get("lane") != FIXED_WORKFLOW and not workflow.get("api_runnable"):
            continue
        if not workflow.get("requires_confirmation") or not workflow.get("runtime_workflow_type"):
            continue
        runtime_type = workflow.get("runtime_workflow_type") or workflow["type"]
        if runtime_type:
            allowed.add(str(runtime_type))
        allowed.add(str(workflow["type"]))
    return allowed


def resolve_runtime_workflow_type(workflow_type: str) -> str:
    workflow = get_workflow(workflow_type)
    return str(workflow.get("runtime_workflow_type") or workflow_type)


def workflow_lane(workflow_type: str) -> str:
    return str(get_workflow(workflow_type).get("lane") or FIXED_WORKFLOW)
