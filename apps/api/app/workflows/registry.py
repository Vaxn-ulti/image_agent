from __future__ import annotations

from copy import deepcopy
from typing import Any


FIXED_WORKFLOW = "fixed_workflow"
INCUBATION_LANE = "toolchain_incubation"


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
        "runtime_backend": "remote_script_wrapper",
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
        "runtime_backend": "remote_script_wrapper",
        "runtime_workflow_type": "bold_fmriprep_xcpd_report_validate",
        "result_summary_schema": "BOLD",
        "input_requirements": [
            "supported BOLD NIfTI/BIDS series",
            "optional companion T1/anat",
            "FreeSurfer license",
            "fMRIPrep and XCP-D remote scripts",
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
    return item


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
