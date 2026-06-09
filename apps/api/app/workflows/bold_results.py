from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.workflows.result_contract import build_result_summary
from app.workflows.scientific_reports import build_scientific_report_summary


def _first_existing(out_dir: Path, patterns: list[str]) -> Path | None:
    for pattern in patterns:
        matches = sorted(out_dir.glob(pattern))
        if matches:
            return matches[0]
    return None


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_bold_result_summary_from_outputs(out_dir: Path, task_id: int, workflow_type: str) -> Path:
    out_dir = Path(out_dir)
    metric_summary_path = _first_existing(out_dir, ["*_desc-bold_metrics_summary.json"])
    if metric_summary_path is None:
        raise RuntimeError("BOLD result summary requires a real bold metrics summary")
    metric_summary = _load_json(metric_summary_path)
    provenance_path = _first_existing(out_dir, ["*_desc-bold_metrics_provenance.json"])
    provenance = _load_json(provenance_path)

    required_maps = {
        "alff": _first_existing(out_dir, ["*space-MNI*_desc-alff_bold.nii.gz"]),
        "falff": _first_existing(out_dir, ["*space-MNI*_desc-falff_bold.nii.gz"]),
        "reho": _first_existing(out_dir, ["*space-MNI*_desc-reho_bold.nii.gz"]),
        "tsnr": _first_existing(out_dir, ["*space-MNI*_desc-tsnr_bold.nii.gz"]),
        "rsfa": _first_existing(out_dir, ["*space-MNI*_desc-rsfa_bold.nii.gz"]),
    }
    required_tables = {
        "seed_to_roi": _first_existing(out_dir, ["*_desc-seed_to_roi.tsv"]),
        "network_dmn": _first_existing(out_dir, ["*_desc-network_dmn.tsv"]),
        "seed_timeseries": _first_existing(out_dir, ["*_desc-seed_timeseries.tsv"]),
    }
    missing = [
        name
        for name, path in {**required_maps, **required_tables}.items()
        if path is None or not path.exists()
    ]
    if missing:
        raise RuntimeError(f"BOLD result summary requires real MNI outputs: {', '.join(missing)}")

    optional_tables = {
        "fd_timeseries": _first_existing(out_dir, ["*_desc-fd_timeseries.tsv"]),
        "dvars_timeseries": _first_existing(out_dir, ["*_desc-dvars_timeseries.tsv"]),
        "wholebrain_timeseries": _first_existing(out_dir, ["*_desc-wholebrain_timeseries.tsv"]),
        "mean_psd": _first_existing(out_dir, ["*_desc-mean_psd.tsv"]),
        "confounds_summary": _first_existing(out_dir, ["*_desc-confounds_summary.tsv"]),
    }
    optional_maps = {
        "mean": _first_existing(out_dir, ["*space-MNI*_desc-mean_bold.nii.gz"]),
        "std": _first_existing(out_dir, ["*space-MNI*_desc-std_bold.nii.gz"]),
    }
    masks = {
        "brain_mask": _first_existing(out_dir / "masks", ["*space-MNI*_desc-brain_mask.nii.gz"])
        if (out_dir / "masks").exists()
        else None,
    }

    maps = [
        {
            "name": name,
            "path": path,
            "space": "MNI152",
            "feature_group": "voxelwise_metrics",
        }
        for name, path in {**required_maps, **optional_maps}.items()
        if path is not None
    ]
    tables = [
        {
            "name": name,
            "path": path,
            "space": "MNI152",
            "feature_group": "connectivity" if name in {"seed_to_roi", "network_dmn", "seed_timeseries"} else "qc_timeseries",
        }
        for name, path in {**required_tables, **optional_tables}.items()
        if path is not None
    ]
    summary_files = [
        {"name": "bold_metrics_summary", "path": metric_summary_path, "feature_group": "summary"},
    ]
    if provenance_path is not None:
        summary_files.append({"name": "bold_metrics_provenance", "path": provenance_path, "feature_group": "provenance"})
    mask_outputs = [
        {"name": name, "path": path, "space": "MNI152", "feature_group": "mask"}
        for name, path in masks.items()
        if path is not None
    ]

    return build_result_summary(
        out_dir=out_dir,
        task_id=task_id,
        workflow_type=workflow_type,
        modality="BOLD",
        spaces=["MNI152"],
        feature_groups=["voxelwise_metrics", "connectivity", "qc_timeseries", "motion_confounds"],
        outputs={
            "maps": maps,
            "tables": tables,
            "masks": mask_outputs,
            "summaries": summary_files,
        },
        provenance={
            "validation_only": False,
            "source_deepprep_task": provenance.get("preproc_bold"),
            "preproc_bold": provenance.get("preproc_bold"),
            "brain_mask": provenance.get("brain_mask"),
            "brain_mask_generated": str(provenance.get("brain_mask", "")).find("/masks/") >= 0,
            "tsnr_source": provenance.get("tsnr_source"),
            "tsnr_source_used": provenance.get("tsnr_source_used"),
            "seed_registry": provenance.get("seed_registry"),
            "metric_summary": str(metric_summary_path),
            "metrics": metric_summary.get("metrics", []),
            "seed_count": len(metric_summary.get("seeds") or []),
            "n_volumes": metric_summary.get("n_volumes"),
            "tr_seconds": metric_summary.get("tr_seconds"),
            "masked_voxel_count": metric_summary.get("masked_voxel_count"),
        },
        summary_name="bold_result_summary.json",
    )


def write_bold_scientific_report_from_outputs(out_dir: Path, task_id: int, workflow_type: str) -> Path:
    summary_path = write_bold_result_summary_from_outputs(out_dir, task_id=task_id, workflow_type=workflow_type)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return build_scientific_report_summary(out_dir, task_id=task_id, workflow_type=workflow_type, summary=summary)
