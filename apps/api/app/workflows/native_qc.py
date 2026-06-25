from __future__ import annotations

from pathlib import Path
from typing import Any

FIGURE_EXTENSIONS = {".png", ".svg", ".jpg", ".jpeg", ".webp"}

OFFICIAL_SOURCE_IDS_BY_STAGE = {
    "deepprep": ["docs/rag/vendor/deepprep_official_container_usage.md"],
    "fmriprep": ["docs/rag/vendor/fmriprep_official_outputs.md"],
    "freesurfer": ["docs/rag/vendor/freesurfer_official_container_reconall.md"],
    "fsl": ["docs/rag/vendor/fsl_official_fast_dti_tools.md"],
    "mrtrix": ["docs/rag/vendor/mrtrix3_official_dti_toolbox.md"],
    "qsiprep": ["docs/rag/vendor/qsiprep_official_container_usage_outputs.md"],
    "qsirecon": ["docs/rag/vendor/qsirecon_official_container_usage_workflows.md"],
    "xcpd": ["docs/rag/vendor/xcp_d_official_outputs.md"],
}

PIPELINE_SOURCE_STAGE_OVERRIDES = {
    "dwi_fast_gpu_dti": "dwi_fast_dti",
    "dwi_fast_gpu_dti_validate": "dwi_fast_dti",
}


def classify_native_source_stage(path: Path, root: Path) -> str:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        parts = path.parts
    lowered = [part.lower() for part in parts]
    joined = "/".join(lowered)
    name = path.name.lower()
    if "qsirecon" in name or "/qsirecon/" in joined or "qsirecon" in lowered:
        return "qsirecon"
    if "qsiprep" in name or "/qsiprep/" in joined or "qsiprep" in lowered:
        return "qsiprep"
    if "xcpd" in name or "xcp_d" in name or "/xcpd/" in joined or "/xcp_d/" in joined:
        return "xcpd"
    if "fmriprep" in name or "/fmriprep/" in joined:
        return "fmriprep"
    if "xcpd" in lowered or "xcp_d" in lowered:
        return "xcpd"
    if "fmriprep" in lowered:
        return "fmriprep"
    if "freesurfer" in lowered or "recon" in lowered:
        return "freesurfer"
    if "mrtrix" in lowered or "mrtrix3" in lowered or name.startswith(("dwi2", "mr")):
        return "mrtrix"
    if "fsl" in lowered or name.startswith(("eddy", "dtifit", "flirt", "fnirt", "applywarp", "fsl")):
        return "fsl"
    if "deepprep" in lowered or "qc" in lowered:
        return "deepprep"
    if "logs" in lowered:
        return "runtime"
    return "container_native"


def source_stage_for_native_artifact(path: Path, root: Path, pipeline: str | None = None) -> str:
    stage = classify_native_source_stage(path, root)
    if pipeline in PIPELINE_SOURCE_STAGE_OVERRIDES and stage in {"container_native", "deepprep", "runtime"}:
        return PIPELINE_SOURCE_STAGE_OVERRIDES[pipeline]
    return stage


def official_source_ids_for_native_artifact(path: Path, root: Path, pipeline: str | None = None) -> list[str]:
    stage = source_stage_for_native_artifact(path, root, pipeline)
    source_ids = list(OFFICIAL_SOURCE_IDS_BY_STAGE.get(stage, []))
    if not source_ids and stage == "dwi_fast_dti":
        source_ids = [
            "docs/rag/vendor/fsl_official_fast_dti_tools.md",
            "docs/rag/vendor/mrtrix3_official_dti_toolbox.md",
        ]
    return source_ids


def native_qc_artifact(path: Path, root: Path, role: str, pipeline: str | None = None) -> dict[str, Any]:
    source_stage = source_stage_for_native_artifact(path, root, pipeline)
    official_source_ids = official_source_ids_for_native_artifact(path, root, pipeline)
    source_scope = (
        "curated_vendor_docs"
        if official_source_ids
        else "stage_not_mapped_to_curated_vendor_doc"
    )
    artifact: dict[str, Any] = {
        "name": path.name,
        "path": str(path),
        "source_stage": source_stage,
        "artifact_role": role,
        "artifact_origin": "container_output",
        "native_artifact": True,
        "official_source_ids": official_source_ids,
        "official_source_scope": source_scope,
        "provenance": {
            "generated_from": "container_native_qc",
            "replaces_native_qc": False,
            "official_source_ids": official_source_ids,
            "official_source_scope": source_scope,
        },
    }
    if pipeline:
        artifact["pipeline"] = pipeline
    return artifact


def discover_native_qc_outputs(root: Path, pipeline: str | None = None) -> dict[str, list[dict[str, Any]]]:
    root = Path(root)
    reports = [
        native_qc_artifact(path, root, "container_native_html_report", pipeline)
        for path in sorted(root.rglob("*.html"))
        if path.is_file()
    ]
    figures = [
        native_qc_artifact(path, root, "container_native_qc_figure", pipeline)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.suffix.lower() in FIGURE_EXTENSIONS
    ]
    outputs: dict[str, list[dict[str, Any]]] = {}
    if reports:
        outputs["reports"] = reports
    if figures:
        outputs["figures"] = figures
    return outputs
