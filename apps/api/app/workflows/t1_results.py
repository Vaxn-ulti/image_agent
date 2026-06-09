from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.workflows.native_qc import discover_native_qc_outputs
from app.workflows.result_contract import build_result_summary
from app.workflows.scientific_reports import build_scientific_report_summary

FEATURE_GROUPS = [
    "segmentation_volumes",
    "cortical_thickness",
    "surface_area",
    "regional_morphometry",
    "all_freesurfer_stats",
    "quality_control",
]

def _find_subject_stats_dir(out_dir: Path) -> Path | None:
    candidates = sorted(out_dir.glob("Recon/sub-*/stats"))
    for candidate in candidates:
        if (candidate / "brainvol.stats").exists() or (candidate / "lh.aparc.stats").exists() or (candidate / "rh.aparc.stats").exists():
            return candidate
    return None


def _parse_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _parse_brain_measures(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line.startswith("# Measure "):
            continue
        parts = [part.strip() for part in line.removeprefix("# Measure ").split(",")]
        if len(parts) < 5:
            continue
        value = _parse_float(parts[-2])
        if value is None:
            continue
        rows.append(
            {
                "measure": parts[0],
                "metric": parts[1],
                "description": parts[2],
                "value": value,
                "unit": parts[-1],
            }
        )
    return rows


def _parse_aparc(path: Path, hemi: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    headers: list[str] | None = None
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("# ColHeaders"):
            headers = line.split()[2:]
            continue
        if line.startswith("#"):
            continue
        parts = line.split()
        if not headers or len(parts) < len(headers):
            continue
        values = dict(zip(headers, parts))
        name = values.get("StructName")
        if not name:
            continue
        rows.append(
            {
                "region": f"ctx-{hemi}-{name}",
                "space": "T1w",
                "source_hemi": hemi,
                "num_vertices": int(float(values["NumVert"])) if "NumVert" in values else None,
                "surface_area_mm2": _parse_float(values.get("SurfArea", "")),
                "gray_matter_volume_mm3": _parse_float(values.get("GrayVol", "")),
                "cortical_thickness_mm": _parse_float(values.get("ThickAvg", "")),
                "thickness_std_mm": _parse_float(values.get("ThickStd", "")),
                "mean_curvature": _parse_float(values.get("MeanCurv", "")),
                "gaussian_curvature": _parse_float(values.get("GausCurv", "")),
                "folding_index": _parse_float(values.get("FoldInd", "")),
                "curvature_index": _parse_float(values.get("CurvInd", "")),
            }
        )
    return rows


def _stats_file_profile(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    data_lines = [line for line in lines if line.strip() and not line.strip().startswith("#")]
    colheaders = [line.strip() for line in lines if line.strip().startswith("# ColHeaders")]
    return {
        "file": path.name,
        "path": str(path),
        "measure_count": sum(1 for line in lines if line.strip().startswith("# Measure ")),
        "data_row_count": len(data_lines),
        "colheaders": colheaders[-1].split()[2:] if colheaders else [],
    }


def _write_stats_inventory(stats_dir: Path, tables_dir: Path) -> tuple[Path, list[dict[str, Any]]]:
    profiles = [_stats_file_profile(path) for path in sorted(stats_dir.glob("*.stats")) if path.is_file()]
    inventory_path = tables_dir / "t1_freesurfer_stats_inventory.tsv"
    _write_tsv(
        inventory_path,
        ["file", "measure_count", "data_row_count", "colheaders", "path"],
        [
            {
                **profile,
                "colheaders": ",".join(profile["colheaders"]),
            }
            for profile in profiles
        ],
    )
    return inventory_path, profiles


def _copy_all_stats_tables(stats_dir: Path, tables_dir: Path) -> list[dict[str, Any]]:
    stats_tables_dir = tables_dir / "freesurfer_stats"
    stats_tables_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[dict[str, Any]] = []
    for stats_path in sorted(stats_dir.glob("*.stats")):
        if not stats_path.is_file():
            continue
        target = stats_tables_dir / f"{stats_path.stem}.tsv"
        target.write_text(stats_path.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
        outputs.append(
            {
                "name": f"freesurfer_{stats_path.stem.replace('.', '_').replace('-', '_')}",
                "path": target,
                "space": "T1w",
                "feature_group": "all_freesurfer_stats",
                "source_stats_file": stats_path.name,
            }
        )
    return outputs


def _write_tsv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["\t".join(columns)]
    for row in rows:
        lines.append("\t".join("" if row.get(column) is None else str(row.get(column)) for column in columns))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _existing_outputs(root: Path, patterns: list[tuple[str, str, str]]) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for name, pattern, space in patterns:
        for path in sorted(root.glob(pattern)):
            if not path.is_file() or path in seen:
                continue
            seen.add(path)
            outputs.append({"name": name, "path": path, "space": space})
            break
    return outputs


def _write_placeholder_summary(out_dir: Path, task_id: int, workflow_type: str) -> Path:
    tables_dir = out_dir / "tables"
    qc_dir = out_dir / "qc"
    maps_dir = out_dir / "maps"
    for path in (tables_dir, qc_dir, maps_dir):
        path.mkdir(parents=True, exist_ok=True)

    t1w_table = tables_dir / "t1_t1w_regions.tsv"
    mni_table = tables_dir / "t1_mni152_regions.tsv"
    t1w_table.write_text(
        "region\tspace\tvolume_mm3\tcortical_thickness_mm\tsurface_area_mm2\n"
        "ctx-lh-frontal\tT1w\t0\t0\t0\n",
        encoding="utf-8",
    )
    mni_table.write_text(
        "region\tspace\tvolume_mm3\tcortical_thickness_mm\tsurface_area_mm2\n"
        "ctx-lh-frontal\tMNI152\t0\t0\t0\n",
        encoding="utf-8",
    )
    qc_report = qc_dir / "t1_qc_index.json"
    qc_report.write_text(
        json.dumps(
            {
                "status": "contract_ready",
                "source": workflow_type,
                "extraction_status": "placeholder_contract_pending_real_deepprep_parser",
                "placeholder_outputs": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    native_map = maps_dir / "t1_segmentation_t1w.nii.gz"
    mni_map = maps_dir / "t1_segmentation_mni152.nii.gz"
    native_map.write_bytes(b"validate-placeholder-nifti")
    mni_map.write_bytes(b"validate-placeholder-nifti")

    native_qc = discover_native_qc_outputs(out_dir, workflow_type)
    return build_result_summary(
        out_dir=out_dir,
        task_id=task_id,
        workflow_type=workflow_type,
        modality="T1",
        spaces=["T1w", "MNI152"],
        feature_groups=FEATURE_GROUPS,
        outputs={
            "tables": [
                {"name": "t1_t1w_regions", "path": t1w_table, "space": "T1w"},
                {"name": "t1_mni152_regions", "path": mni_table, "space": "MNI152"},
            ],
            "maps": [
                {"name": "t1_segmentation_t1w", "path": native_map, "space": "T1w"},
                {"name": "t1_segmentation_mni152", "path": mni_map, "space": "MNI152"},
            ],
            "qc": [{"name": "t1_qc_index", "path": qc_report}],
            **native_qc,
        },
        provenance={
            "method": "deepprep_t1_result_contract",
            "note": "Summary writer preserves frontend contract while real DeepPrep feature parsers are expanded.",
            "placeholder_outputs": True,
            "extraction_status": "placeholder_contract_pending_real_deepprep_parser",
        },
    )


def write_t1_result_summary(out_dir: Path, task_id: int, workflow_type: str) -> Path:
    out_dir = Path(out_dir)
    tables_dir = out_dir / "tables"
    qc_dir = out_dir / "qc"
    stats_dir = _find_subject_stats_dir(out_dir)
    if stats_dir is None:
        return _write_placeholder_summary(out_dir, task_id, workflow_type)

    tables_dir.mkdir(parents=True, exist_ok=True)
    qc_dir.mkdir(parents=True, exist_ok=True)

    brain_rows = _parse_brain_measures(stats_dir / "brainvol.stats")
    region_rows = _parse_aparc(stats_dir / "lh.aparc.stats", "lh") + _parse_aparc(stats_dir / "rh.aparc.stats", "rh")
    if not brain_rows and not region_rows:
        return _write_placeholder_summary(out_dir, task_id, workflow_type)

    brain_table = tables_dir / "t1_brain_measures.tsv"
    region_table = tables_dir / "t1_t1w_regions.tsv"
    stats_inventory_table, stats_profiles = _write_stats_inventory(stats_dir, tables_dir)
    all_stats_outputs = _copy_all_stats_tables(stats_dir, tables_dir)
    _write_tsv(
        brain_table,
        ["measure", "metric", "description", "value", "unit"],
        brain_rows,
    )
    _write_tsv(
        region_table,
        [
            "region",
            "space",
            "source_hemi",
            "num_vertices",
            "surface_area_mm2",
            "gray_matter_volume_mm3",
            "cortical_thickness_mm",
            "thickness_std_mm",
            "mean_curvature",
            "gaussian_curvature",
            "folding_index",
            "curvature_index",
        ],
        region_rows,
    )

    subject_dir = stats_dir.parent
    maps = _existing_outputs(
        subject_dir,
        [
            ("t1_aparc_aseg", "mri/aparc+aseg.mgz", "T1w"),
            ("t1_aseg", "mri/aseg.mgz", "T1w"),
            ("t1_brain", "mri/brain.mgz", "T1w"),
            ("t1_brainmask", "mri/brainmask.mgz", "T1w"),
            ("t1_native", "mri/T1.mgz", "T1w"),
        ],
    )
    transforms = _existing_outputs(
        subject_dir,
        [
            ("talairach_xfm", "mri/transforms/talairach.xfm", "MNI152"),
            ("talairach_lta", "mri/transforms/talairach.lta", "MNI152"),
        ],
    )

    qc_report = qc_dir / "t1_qc_index.json"
    qc_report.write_text(
        json.dumps(
            {
                "status": "features_extracted",
                "source": workflow_type,
                "extraction_status": "real_deepprep_freesurfer_stats",
                "placeholder_outputs": False,
                "brain_measure_count": len(brain_rows),
                "region_count": len(region_rows),
                "stats_dir": str(stats_dir),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    native_qc = discover_native_qc_outputs(out_dir, workflow_type)
    return build_result_summary(
        out_dir=out_dir,
        task_id=task_id,
        workflow_type=workflow_type,
        modality="T1",
        spaces=["T1w", "MNI152"],
        feature_groups=FEATURE_GROUPS,
        outputs={
            "tables": [
                {"name": "t1_brain_measures", "path": brain_table, "space": "T1w"},
                {"name": "t1_t1w_regions", "path": region_table, "space": "T1w"},
                {
                    "name": "t1_freesurfer_stats_inventory",
                    "path": stats_inventory_table,
                    "space": "T1w",
                    "feature_group": "all_freesurfer_stats",
                },
                *all_stats_outputs,
            ],
            "maps": maps,
            "transforms": transforms,
            "qc": [{"name": "t1_qc_index", "path": qc_report}],
            **native_qc,
        },
        provenance={
            "method": "deepprep_freesurfer_stats_parser",
            "note": "Parsed real DeepPrep/Freesurfer stats. MNI152 is represented by actual transform/map references only; no MNI regional values are invented.",
            "placeholder_outputs": False,
            "extraction_status": "real_deepprep_freesurfer_stats",
            "source_stats_dir": str(stats_dir),
            "source_stats_files": {
                "brainvol": str(stats_dir / "brainvol.stats") if (stats_dir / "brainvol.stats").exists() else None,
                "lh_aparc": str(stats_dir / "lh.aparc.stats") if (stats_dir / "lh.aparc.stats").exists() else None,
                "rh_aparc": str(stats_dir / "rh.aparc.stats") if (stats_dir / "rh.aparc.stats").exists() else None,
            },
            "parsed_counts": {
                "brain_measures": len(brain_rows),
                "regions": len(region_rows),
                "maps": len(maps),
                "transforms": len(transforms),
                "stats_files": len(stats_profiles),
            },
            "stats_files": stats_profiles,
        },
    )


def write_t1_scientific_report(out_dir: Path, task_id: int, workflow_type: str) -> Path:
    summary_path = write_t1_result_summary(out_dir, task_id=task_id, workflow_type=workflow_type)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return build_scientific_report_summary(out_dir, task_id=task_id, workflow_type=workflow_type, summary=summary)
