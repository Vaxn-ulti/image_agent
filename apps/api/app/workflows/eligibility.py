from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.workflows.registry import get_workflow, workflow_public_metadata


PRODUCTION_WORKFLOW_TYPES = [
    "t1_deepprep_anat_report",
    "bold_fmriprep_xcpd_report",
    "dwi_fast_gpu_dti",
]


def build_workflow_eligibility(series: dict[str, Any]) -> dict[str, Any]:
    metadata = _series_metadata(series)
    evidence = _eligibility_evidence(series, metadata)
    runnable = []
    blocked = []
    for workflow_type in PRODUCTION_WORKFLOW_TYPES:
        workflow = get_workflow(workflow_type)
        blocking_reasons = _blocking_reasons(series, metadata, workflow)
        item = {
            "workflow_type": workflow_type,
            "label": workflow.get("label", workflow_type),
            "runtime_workflow_type": workflow.get("runtime_workflow_type") or workflow_type,
            "modality": workflow.get("modality"),
            "required_inputs": workflow.get("input_requirements", []),
            "expected_outputs": workflow.get("expected_outputs", []),
            "workflow_metadata": workflow_public_metadata(workflow_type),
            "blocking_reasons": blocking_reasons,
            "warnings": [],
            "evidence": evidence,
        }
        if blocking_reasons:
            blocked.append(item)
        else:
            runnable.append(item)
    return {
        "policy_version": "workflow_eligibility_v1",
        "production_task_created": False,
        "primary_recommendation": runnable[0] if runnable else None,
        "runnable_workflows": runnable,
        "blocked_workflows": blocked,
        "evidence": evidence,
    }


def _series_metadata(series: dict[str, Any]) -> dict[str, Any]:
    metadata = series.get("metadata")
    if isinstance(metadata, dict):
        return metadata
    raw = series.get("metadata_json")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _eligibility_evidence(series: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    sidecars = _sidecar_status(series, metadata)
    return {
        "series_id": series.get("id") or series.get("series_id"),
        "modality": series.get("modality"),
        "sequence_label": series.get("sequence_label") or metadata.get("sequence_label") or "",
        "supported_for_processing": bool(series.get("supported_for_processing", True)),
        "unsupported_reason": series.get("unsupported_reason") or metadata.get("unsupported_reason") or "",
        "format": series.get("format"),
        "sidecars": sidecars,
        "has_bval": sidecars["bval"],
        "has_bvec": sidecars["bvec"],
        "has_json": sidecars["json"],
        "has_dwi_eddy_metadata": sidecars["dwi_eddy_metadata"],
        "phase_encoding_direction": metadata.get("phase_encoding_direction") or metadata.get("PhaseEncodingDirection"),
        "total_readout_time": metadata.get("total_readout_time") or metadata.get("TotalReadoutTime"),
    }


def _blocking_reasons(series: dict[str, Any], metadata: dict[str, Any], workflow: dict[str, Any]) -> list[str]:
    workflow_type = workflow["type"]
    modality = str(series.get("modality") or "")
    supported = bool(series.get("supported_for_processing", True))
    unsupported_reason = series.get("unsupported_reason") or metadata.get("unsupported_reason") or ""
    reasons: list[str] = []
    if not supported:
        reasons.append(unsupported_reason or "This series is not supported for processing")
    expected_modality = workflow.get("modality")
    if expected_modality and expected_modality != modality:
        reasons.append(f"Workflow requires {expected_modality} but series is {modality or 'unknown'}")
    if workflow_type == "dwi_fast_gpu_dti" and modality == "DWI":
        sidecars = _sidecar_status(series, metadata)
        if not sidecars["bval"]:
            reasons.append("DWI fast GPU DTI requires bval sidecar")
        if not sidecars["bvec"]:
            reasons.append("DWI fast GPU DTI requires bvec sidecar")
        if not sidecars["json"]:
            reasons.append("DWI fast GPU DTI requires JSON sidecar")
        elif not sidecars["dwi_eddy_metadata"]:
            reasons.append(
                "DWI fast GPU DTI requires JSON sidecar containing PhaseEncodingDirection and TotalReadoutTime"
            )
    return reasons


def _sidecar_status(series: dict[str, Any], metadata: dict[str, Any]) -> dict[str, bool]:
    sidecars = metadata.get("sidecars") or {}
    sidecar_paths: list[Path] = []
    if isinstance(sidecars, list):
        sidecar_paths = [Path(str(path)) for path in sidecars]

    has_json = bool(metadata.get("has_json"))
    has_bval = bool(metadata.get("has_bval"))
    has_bvec = bool(metadata.get("has_bvec"))
    json_has_eddy = bool(metadata.get("has_json") and metadata.get("has_dwi_eddy_metadata"))

    for path in sidecar_paths:
        if not path.exists():
            continue
        suffix = path.suffix.lower()
        if suffix == ".json":
            has_json = True
            json_has_eddy = json_has_eddy or _json_sidecar_has_eddy_metadata(path)
        elif suffix == ".bval":
            has_bval = True
        elif suffix == ".bvec":
            has_bvec = True

    main_file = _main_file_path(series)
    if main_file and _allow_same_stem_sidecar_fallback(series, metadata):
        base = _sidecar_base(main_file)
        for suffix in (".json", ".bval", ".bvec"):
            candidate = main_file.with_name(base + suffix)
            if not candidate.exists():
                continue
            if suffix == ".json":
                has_json = True
                json_has_eddy = json_has_eddy or _json_sidecar_has_eddy_metadata(candidate)
            elif suffix == ".bval":
                has_bval = True
            elif suffix == ".bvec":
                has_bvec = True

    return {
        "json": has_json,
        "bval": has_bval,
        "bvec": has_bvec,
        "dwi_eddy_metadata": json_has_eddy,
    }


def _main_file_path(series: dict[str, Any]) -> Path | None:
    raw = series.get("file_storage_path") or series.get("storage_path")
    if not raw:
        return None
    return Path(str(raw))


def _allow_same_stem_sidecar_fallback(series: dict[str, Any], metadata: dict[str, Any]) -> bool:
    return bool(
        metadata.get("sidecars")
        or metadata.get("bids_path")
        or series.get("format") == "NIFTI_BIDS"
        or series.get("file_type") == "NIFTI_BIDS"
    )


def _sidecar_base(path: Path) -> str:
    return path.name[:-7] if path.name.lower().endswith(".nii.gz") else path.stem


def _json_sidecar_has_eddy_metadata(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return payload.get("PhaseEncodingDirection") is not None and payload.get("TotalReadoutTime") is not None
