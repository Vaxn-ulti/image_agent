from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import quote

CONTRACT_VERSION = "1.0"

RESULT_SUMMARY_REQUIRED_FIELDS = [
    "contract_version",
    "task_id",
    "workflow_type",
    "modality",
    "spaces",
    "feature_groups",
    "outputs",
    "provenance",
]

OUTPUT_ITEM_REQUIRED_FIELDS = [
    "name",
    "path",
    "relative_path",
    "exists",
    "download_url",
    "content_type",
    "size_bytes",
]
OUTPUT_ITEM_COMMON_OPTIONAL_FIELDS = [
    "space",
    "atlas",
    "feature_group",
    "description",
    "unit",
    "table_schema",
    "source_stage",
    "artifact_role",
    "artifact_origin",
    "native_artifact",
    "official_source_ids",
    "official_source_scope",
    "provenance",
]
REPORT_ITEM_COMMON_OPTIONAL_FIELDS = [
    "modality",
    "section",
    "kind",
    "description",
    "source_stage",
    "artifact_role",
    "artifact_origin",
    "native_artifact",
    "official_source_ids",
    "official_source_scope",
    "provenance",
]

MODALITY_CONTRACTS: dict[str, dict[str, Any]] = {
    "T1": {
        "workflows": ["t1_deepprep", "t1_deepprep_validate", "t1_deepprep_mock"],
        "spaces": ["T1w", "MNI152"],
        "feature_groups": [
            "segmentation_volumes",
            "cortical_thickness",
            "surface_area",
            "regional_morphometry",
            "quality_control",
        ],
        "output_sections": ["tables", "maps", "transforms", "qc", "reports", "figures", "logs"],
        "frontend_notes": [
            "Treat provenance.placeholder_outputs=true as non-real feature data.",
            "Real parsed summaries use provenance.extraction_status=real_deepprep_freesurfer_stats.",
            "MNI152 may be represented by transform/map references without invented MNI regional values.",
            "A companion scientific report summary may appear under outputs.reports with HTML and PNG assets for readable presentation.",
        ],
    },
    "BOLD": {
        "workflows": [
            "bold_deepprep",
            "bold_deepprep_validate",
            "bold_fmriprep_xcpd_report",
            "bold_second_level",
            "bold_second_level_validate",
            "bold_alff",
            "bold_falff",
        ],
        "spaces": ["MNI152"],
        "feature_groups": ["voxelwise_metrics", "connectivity", "qc_timeseries", "motion_confounds"],
        "output_sections": ["maps", "tables", "masks", "summaries", "reports", "figures", "logs"],
        "frontend_notes": [
            "bold_second_level is a single-subject downstream metrics package, not group inference.",
            "Real summaries include ALFF, fALFF, ReHo, tSNR, RSFA, 15-seed seed-to-ROI, DMN, and seed time-series outputs.",
            "The API prefers summary/bold_result_summary.json over legacy bold_metrics_summary artifacts.",
            "A companion scientific report summary may appear under outputs.reports with HTML and PNG assets for readable presentation.",
        ],
    },
    "DWI": {
        "workflows": ["dwi_fast_gpu_dti", "dwi_fast_gpu_dti_validate"],
        "spaces": ["DWI", "MNI152"],
        "feature_groups": ["tensor_metrics", "mni152_registration", "atlas_statistics", "quality_control"],
        "output_sections": ["maps", "tables", "qc", "reports", "figures", "logs"],
        "frontend_notes": [
            "Production DWI output is dwi_fast_gpu_dti, not the legacy QSI container path.",
            "Real summaries include native and MNI152 FA, MD, AD, RD maps plus atlas regional TSVs.",
            "Use provenance.metric_sanitization to disclose NaN/inf replacement counts when present.",
            "A companion scientific report summary may appear under outputs.reports with HTML and PNG assets for readable presentation.",
        ],
    },
}


def result_contract_spec() -> dict[str, Any]:
    """Machine-readable summary of the frontend result-summary contract."""
    return {
        "contract_version": CONTRACT_VERSION,
        "summary_endpoint": "/tasks/{task_id}/result-summary",
        "artifact_manifest_endpoint": "/tasks/{task_id}/artifact-manifest",
        "outputs_endpoint": "/tasks/{task_id}/outputs",
        "required_top_level_fields": RESULT_SUMMARY_REQUIRED_FIELDS,
        "output_item_fields": {
            "required": OUTPUT_ITEM_REQUIRED_FIELDS,
            "common_optional": OUTPUT_ITEM_COMMON_OPTIONAL_FIELDS,
        },
        "modalities": MODALITY_CONTRACTS,
        "frontend_rules": [
            "Drive feature tabs from feature_groups and outputs sections rather than workflow-specific filenames.",
            "Use relative_path for display/download routing when available; path remains the backend absolute artifact path.",
            "Use /tasks/{task_id}/artifact-manifest for a stable preview/download list that omits backend absolute paths.",
            "Display validation_only or placeholder_outputs provenance as planned/placeholder data, not completed clinical features.",
            "Prefer /tasks/{task_id}/result-summary for structured views and keep /tasks/{task_id}/outputs for legacy artifact listings.",
        ],
    }


def _normalize_output_item(out_dir: Path, item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    path = Path(normalized["path"])
    normalized["path"] = str(path)
    try:
        relative_path = path.relative_to(out_dir).as_posix()
    except ValueError:
        relative_path = path.name
    normalized["relative_path"] = relative_path
    exists = path.exists()
    normalized["exists"] = exists
    normalized["size_bytes"] = path.stat().st_size if exists and path.is_file() else None
    normalized["content_type"] = (
        "application/gzip"
        if path.name.endswith(".nii.gz")
        else mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    )
    return normalized


def _normalize_report_item(out_dir: Path, item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    path = Path(normalized["path"])
    normalized["path"] = str(path)
    try:
        relative_path = path.relative_to(out_dir).as_posix()
    except ValueError:
        relative_path = path.name
    normalized["relative_path"] = relative_path
    exists = path.exists()
    normalized["exists"] = exists
    normalized["size_bytes"] = path.stat().st_size if exists and path.is_file() else None
    normalized["content_type"] = (
        "text/html"
        if path.suffix.lower() == ".html"
        else "image/svg+xml"
        if path.suffix.lower() == ".svg"
        else mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    )
    normalized.setdefault("source_stage", "scientific_report")
    normalized.setdefault("artifact_role", "derived_presentation_asset")
    normalized.setdefault("artifact_origin", "generated_from_result_summary")
    normalized.setdefault("native_artifact", False)
    provenance = dict(normalized.get("provenance") or {})
    provenance.setdefault("generated_from", "result_summary")
    provenance.setdefault("replaces_native_qc", False)
    normalized["provenance"] = provenance
    return normalized


def build_scientific_report_summary(
    out_dir: Path,
    task_id: int,
    workflow_type: str,
    modality: str,
    spaces: list[str],
    feature_groups: list[str],
    report_items: list[dict[str, Any]],
    provenance: dict[str, Any],
    summary_name: str | None = None,
) -> Path:
    out_dir = Path(out_dir)
    summary_dir = out_dir / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    name = summary_name or f"{modality.lower()}_scientific_report_summary.json"
    summary_path = summary_dir / name
    normalized_reports = [_normalize_report_item(out_dir, item) for item in report_items]
    for item in normalized_reports:
        item.setdefault("download_url", f"/tasks/{task_id}/artifacts/{quote(item['relative_path'])}")
    payload = {
        "contract_version": CONTRACT_VERSION,
        "task_id": task_id,
        "workflow_type": workflow_type,
        "modality": modality,
        "spaces": spaces,
        "feature_groups": list(dict.fromkeys([*feature_groups, "scientific_report"])),
        "outputs": {"reports": normalized_reports},
        "provenance": provenance,
        "summary_path": str(summary_path),
    }
    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return summary_path


def build_result_summary(
    out_dir: Path,
    task_id: int,
    workflow_type: str,
    modality: str,
    spaces: list[str],
    feature_groups: list[str],
    outputs: dict[str, list[dict[str, Any]]],
    provenance: dict[str, Any],
    summary_name: str | None = None,
) -> Path:
    out_dir = Path(out_dir)
    summary_dir = out_dir / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    name = summary_name or f"{modality.lower()}_result_summary.json"
    summary_path = summary_dir / name
    normalized_outputs = {
        section: [_normalize_output_item(out_dir, item) for item in items]
        for section, items in outputs.items()
    }
    for items in normalized_outputs.values():
        for item in items:
            item.setdefault(
                "download_url",
                f"/tasks/{task_id}/artifacts/{quote(item['relative_path'])}",
            )
    payload = {
        "contract_version": CONTRACT_VERSION,
        "task_id": task_id,
        "workflow_type": workflow_type,
        "modality": modality,
        "spaces": spaces,
        "feature_groups": feature_groups,
        "outputs": normalized_outputs,
        "provenance": provenance,
        "summary_path": str(summary_path),
    }
    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return summary_path


def discover_result_summary(output_dir: Path) -> Path | None:
    output_dir = Path(output_dir)
    candidates = sorted((output_dir / "summary").glob("*_result_summary.json"))
    if candidates:
        return candidates[0]
    report_candidates = sorted((output_dir / "summary").glob("*_scientific_report_summary.json"))
    if report_candidates:
        return report_candidates[0]
    legacy = sorted((output_dir / "summary").glob("*summary*.json"))
    return legacy[0] if legacy else None


def load_result_summary(output_dir: Path) -> dict[str, Any] | None:
    summary_path = discover_result_summary(output_dir)
    if summary_path is None:
        return None
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    payload.setdefault("summary_path", str(summary_path))
    return payload
