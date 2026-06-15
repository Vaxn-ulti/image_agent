from __future__ import annotations

from pathlib import Path

from app.scripts.verify_scientific_reports import check_output as check_scientific_report_output
from app.scripts.verify_scientific_reports import resolve_task_output_dirs
from app.services.runtime_overrides import main_patch_attr


def verify_scientific_reports(req, *, projects_root: Path) -> dict:
    resolver = main_patch_attr("resolve_task_output_dirs", resolve_task_output_dirs)
    checker = main_patch_attr("check_scientific_report_output", check_scientific_report_output)
    task_output_dirs, resolution_errors = resolver(projects_root, req.task_ids)
    explicit_output_dirs = [Path(path) for path in req.output_dirs]
    output_paths = [*explicit_output_dirs, *task_output_dirs]
    results = [
        checker(
            path,
            require_container_native_qc=req.require_container_native_qc,
            min_native_qc_images=max(req.min_native_qc_images, 0),
        )
        for path in output_paths
    ]
    required_modalities = {modality.upper() for modality in req.require_modalities}
    present_modalities = {result.modality for result in results}
    missing_modalities = sorted(required_modalities - present_modalities)
    ok = all(result.ok for result in results) and not resolution_errors and not missing_modalities
    return {
        "ok": ok,
        "read_only": True,
        "projects_root": str(projects_root),
        "task_ids": req.task_ids,
        "require_container_native_qc": req.require_container_native_qc,
        "min_native_qc_images": max(req.min_native_qc_images, 0),
        "resolution_errors": resolution_errors,
        "missing_modalities": missing_modalities,
        "results": [
            {
                "output_dir": str(result.output_dir),
                "modality": result.modality,
                "ok": result.ok,
                "errors": result.errors,
                "warnings": result.warnings,
            }
            for result in results
        ],
    }
