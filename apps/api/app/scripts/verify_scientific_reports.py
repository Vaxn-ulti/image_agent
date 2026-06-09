from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RESULT_SUMMARY_PATTERN = "*_result_summary.json"
REPORT_SUMMARY_PATTERN = "*_scientific_report_summary.json"

EXPECTED_MIN_PNG = {
    "T1": 2,
    "BOLD": 4,
    "DWI": 3,
}
CONTAINER_NATIVE_QC_OFFICIAL_SOURCE_IDS = frozenset(
    {
        "docs/rag/vendor/deepprep_official_container_usage.md",
        "docs/rag/vendor/fmriprep_official_outputs.md",
        "docs/rag/vendor/freesurfer_official_container_reconall.md",
        "docs/rag/vendor/fsl_official_fast_dti_tools.md",
        "docs/rag/vendor/mrtrix3_official_dti_toolbox.md",
        "docs/rag/vendor/qsiprep_official_container_usage_outputs.md",
        "docs/rag/vendor/qsirecon_official_container_usage_workflows.md",
        "docs/rag/vendor/xcp_d_official_outputs.md",
    }
)


@dataclass
class CheckResult:
    output_dir: Path
    modality: str
    ok: bool
    errors: list[str]
    warnings: list[str]


def _load_json(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"missing JSON file: {path}")
        return {}
    except json.JSONDecodeError as exc:
        errors.append(f"invalid JSON file: {path} ({exc})")
        return {}
    if not isinstance(payload, dict):
        errors.append(f"JSON root must be an object: {path}")
        return {}
    return payload


def _resolve_output_dir(path: Path) -> Path:
    if path.is_file():
        if path.parent.name == "summary":
            return path.parent.parent
        return path.parent
    return path


def _find_result_summary(output_dir: Path, errors: list[str]) -> Path | None:
    summary_dir = output_dir / "summary"
    candidates = sorted(summary_dir.glob(RESULT_SUMMARY_PATTERN))
    candidates = [path for path in candidates if "scientific_report" not in path.name]
    if not candidates:
        errors.append(f"missing result summary under {summary_dir}")
        return None
    return candidates[0]


def _find_report_summary(output_dir: Path, main_summary: dict[str, Any], errors: list[str]) -> Path | None:
    provenance = main_summary.get("provenance") or {}
    recorded = provenance.get("scientific_report_summary_path")
    if recorded:
        recorded_path = Path(str(recorded))
        if not recorded_path.is_absolute():
            recorded_path = output_dir / recorded_path
        if recorded_path.exists():
            return recorded_path
        errors.append(f"recorded scientific report summary does not exist: {recorded_path}")
    candidates = sorted((output_dir / "summary").glob(REPORT_SUMMARY_PATTERN))
    if candidates:
        return candidates[0]
    errors.append(f"missing scientific report summary under {output_dir / 'summary'}")
    return None


def _relative_path(item: dict[str, Any]) -> str:
    return str(item.get("relative_path") or item.get("path") or "")


def _check_derived_report_provenance(item: dict[str, Any], errors: list[str]) -> None:
    relative_path = _relative_path(item)
    provenance = item.get("provenance") or {}
    if (
        item.get("source_stage") != "scientific_report"
        or item.get("artifact_role") != "derived_presentation_asset"
        or item.get("artifact_origin") != "generated_from_result_summary"
        or item.get("native_artifact") is not False
        or provenance.get("generated_from") != "result_summary"
        or provenance.get("replaces_native_qc") is not False
    ):
        errors.append(f"generated report artifact missing derived provenance: {relative_path or '<unknown>'}")


def _check_report_artifacts(output_dir: Path, modality: str, main_summary: dict[str, Any], report_summary: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    reports = ((main_summary.get("outputs") or {}).get("reports") or [])
    report_summary_reports = ((report_summary.get("outputs") or {}).get("reports") or [])
    if not isinstance(reports, list) or not reports:
        errors.append("main result summary is missing outputs.reports")
    if not isinstance(report_summary_reports, list) or not report_summary_reports:
        errors.append("scientific report summary is missing outputs.reports")

    report_paths = {_relative_path(item) for item in reports if isinstance(item, dict)}
    if "reports/index.html" not in report_paths:
        errors.append("outputs.reports does not register reports/index.html")
    if "reports/report_manifest.json" not in report_paths:
        errors.append("outputs.reports does not register reports/report_manifest.json")
    for item in reports:
        if isinstance(item, dict) and _relative_path(item).startswith("reports/"):
            _check_derived_report_provenance(item, errors)
    for item in report_summary_reports:
        if isinstance(item, dict):
            _check_derived_report_provenance(item, errors)

    html_path = output_dir / "reports" / "index.html"
    manifest_path = output_dir / "reports" / "report_manifest.json"
    if not html_path.exists():
        errors.append(f"missing report HTML: {html_path}")
    else:
        html = html_path.read_text(encoding="utf-8", errors="ignore")
        if "<html" not in html.lower():
            errors.append(f"report HTML is not an HTML document: {html_path}")
        if "Scientific Report" not in html:
            errors.append(f"report HTML does not identify itself as a scientific report: {html_path}")
        if modality and modality not in html:
            warnings.append(f"report HTML does not visibly mention modality {modality}: {html_path}")
        if len(html) < 1000:
            warnings.append(f"report HTML is unusually small ({len(html)} bytes): {html_path}")

    manifest = _load_json(manifest_path, errors)
    if manifest:
        manifest_modality = str(manifest.get("modality") or "").upper()
        if modality and manifest_modality != modality:
            errors.append(f"manifest modality {manifest_modality or '<missing>'} does not match result modality {modality}")
        assets = manifest.get("assets") or []
        if "index.html" not in assets:
            errors.append("manifest assets do not include index.html")
        if "report_manifest.json" not in assets:
            errors.append("manifest assets do not include report_manifest.json")

    png_paths = sorted((output_dir / "reports").glob("*.png"))
    expected_png = EXPECTED_MIN_PNG.get(modality, 0)
    if len(png_paths) < expected_png:
        errors.append(f"{modality or 'UNKNOWN'} report has {len(png_paths)} PNG assets; expected at least {expected_png}")
    png_signature = b"\x89PNG\r\n\x1a\n"
    for png_path in png_paths:
        content = png_path.read_bytes()
        if not content.startswith(png_signature):
            errors.append(f"PNG asset is not a PNG document: {png_path}")
        if len(content) < 200:
            warnings.append(f"PNG asset is unusually small ({len(content)} bytes): {png_path}")


def _is_safe_relative_path(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path_text = value.replace("\\", "/")
    return not (
        path_text.startswith("/")
        or ":" in path_text
        or path_text.startswith("../")
        or "/../" in path_text
        or path_text.endswith("/..")
    )


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_native_qc_item(item: dict[str, Any]) -> bool:
    provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
    return (
        item.get("native_artifact") is True
        or item.get("artifact_origin") == "container_output"
        or provenance.get("generated_from") == "container_native_qc"
    )


def _is_image_item(item: dict[str, Any]) -> bool:
    content_type = str(item.get("content_type") or "").lower()
    relative_path = _relative_path(item).lower()
    return content_type.startswith("image/") or relative_path.endswith((".png", ".svg", ".jpg", ".jpeg", ".webp"))


def _check_native_qc_file(output_dir: Path, item: dict[str, Any], errors: list[str]) -> None:
    relative_path = _relative_path(item)
    artifact_path = output_dir / relative_path
    if not artifact_path.exists() or not artifact_path.is_file():
        errors.append(f"container-native QC artifact file missing: {relative_path or '<unknown>'}")
        return
    content_type = str(item.get("content_type") or "").lower()
    if content_type.startswith("image/png"):
        if not artifact_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
            errors.append(f"container-native QC artifact PNG signature invalid: {relative_path or '<unknown>'}")
    elif content_type.startswith("text/html"):
        html = artifact_path.read_text(encoding="utf-8", errors="ignore")
        if "<html" not in html.lower():
            errors.append(f"container-native QC artifact HTML invalid: {relative_path or '<unknown>'}")


def _check_native_qc_artifact(output_dir: Path, item: dict[str, Any], errors: list[str]) -> None:
    relative_path = _relative_path(item)
    provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
    if not _is_safe_relative_path(relative_path):
        errors.append(f"container-native QC artifact relative_path is unsafe: {relative_path or '<unknown>'}")
    else:
        _check_native_qc_file(output_dir, item, errors)
    if item.get("native_artifact") is not True:
        errors.append(f"container-native QC artifact native_artifact is not true: {relative_path or '<unknown>'}")
    if item.get("artifact_origin") != "container_output":
        errors.append(f"container-native QC artifact artifact_origin is not container_output: {relative_path or '<unknown>'}")
    if provenance.get("generated_from") != "container_native_qc":
        errors.append(f"container-native QC artifact provenance.generated_from is not container_native_qc: {relative_path or '<unknown>'}")
    if provenance.get("replaces_native_qc") is not False:
        errors.append(f"container-native QC artifact provenance.replaces_native_qc is not false: {relative_path or '<unknown>'}")
    if item.get("artifact_role") not in {"container_native_html_report", "container_native_qc_figure"}:
        errors.append(f"container-native QC artifact role is invalid: {relative_path or '<unknown>'}")
    if not item.get("download_url"):
        errors.append(f"container-native QC artifact download_url missing: {relative_path or '<unknown>'}")
    if not item.get("content_type"):
        errors.append(f"container-native QC artifact content_type missing: {relative_path or '<unknown>'}")
    if not _is_positive_int(item.get("size_bytes")):
        errors.append(f"container-native QC artifact size_bytes missing: {relative_path or '<unknown>'}")
    top_level_ids = item.get("official_source_ids")
    provenance_ids = provenance.get("official_source_ids")
    if not isinstance(top_level_ids, list) or not top_level_ids:
        errors.append(f"container-native QC artifact official_source_ids missing: {relative_path or '<unknown>'}")
        return
    if not isinstance(provenance_ids, list) or not provenance_ids:
        errors.append(f"container-native QC artifact provenance.official_source_ids missing: {relative_path or '<unknown>'}")
        return
    top_level_set = set(top_level_ids)
    provenance_set = set(provenance_ids)
    if top_level_set != provenance_set:
        errors.append(f"container-native QC artifact official_source_ids mismatch: {relative_path or '<unknown>'}")
    for source_id in top_level_set:
        if not isinstance(source_id, str) or source_id not in CONTAINER_NATIVE_QC_OFFICIAL_SOURCE_IDS:
            errors.append(f"container-native QC artifact official_source_ids unsupported: {relative_path or '<unknown>'}")


def _check_container_native_qc(
    output_dir: Path,
    main_summary: dict[str, Any],
    *,
    require_container_native_qc: bool,
    min_native_qc_images: int,
    errors: list[str],
) -> None:
    outputs = main_summary.get("outputs") if isinstance(main_summary.get("outputs"), dict) else {}
    candidates: list[dict[str, Any]] = []
    for bucket in ("reports", "figures"):
        values = outputs.get(bucket) or []
        if isinstance(values, list):
            candidates.extend(item for item in values if isinstance(item, dict) and _is_native_qc_item(item))
    if require_container_native_qc and not candidates:
        errors.append("container-native QC evidence missing")
        return
    image_count = 0
    for item in candidates:
        _check_native_qc_artifact(output_dir, item, errors)
        if _is_image_item(item):
            image_count += 1
    if image_count < min_native_qc_images:
        errors.append(f"container-native QC image count {image_count} below minimum {min_native_qc_images}")


def check_output(
    path: Path,
    *,
    require_container_native_qc: bool = False,
    min_native_qc_images: int = 0,
) -> CheckResult:
    output_dir = _resolve_output_dir(path)
    errors: list[str] = []
    warnings: list[str] = []
    if not output_dir.exists():
        return CheckResult(output_dir=output_dir, modality="UNKNOWN", ok=False, errors=[f"output path does not exist: {output_dir}"], warnings=[])

    main_summary_path = path if path.is_file() else _find_result_summary(output_dir, errors)
    main_summary = _load_json(main_summary_path, errors) if main_summary_path else {}
    modality = str(main_summary.get("modality") or "UNKNOWN").upper()
    report_summary_path = _find_report_summary(output_dir, main_summary, errors) if main_summary else None
    report_summary = _load_json(report_summary_path, errors) if report_summary_path else {}
    if main_summary and report_summary:
        _check_report_artifacts(output_dir, modality, main_summary, report_summary, errors, warnings)
        _check_container_native_qc(
            output_dir,
            main_summary,
            require_container_native_qc=require_container_native_qc,
            min_native_qc_images=max(min_native_qc_images, 0),
            errors=errors,
        )
    return CheckResult(output_dir=output_dir, modality=modality, ok=not errors, errors=errors, warnings=warnings)


def resolve_task_output_dirs(projects_root: Path, task_ids: list[int]) -> tuple[list[Path], list[str]]:
    output_dirs: list[Path] = []
    errors: list[str] = []
    for task_id in task_ids:
        matches = sorted(projects_root.glob(f"*/derivatives/{task_id}/output"))
        if not matches:
            errors.append(f"could not resolve task {task_id} under {projects_root}/*/derivatives/{task_id}/output")
            continue
        if len(matches) > 1:
            joined = ", ".join(str(path) for path in matches)
            errors.append(f"task {task_id} resolved to multiple output dirs: {joined}")
            continue
        output_dirs.append(matches[0])
    return output_dirs, errors


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify scientific report display artifacts for real T1/BOLD/DWI task outputs.")
    parser.add_argument("outputs", nargs="*", type=Path, help="Task output directories or result-summary JSON files.")
    parser.add_argument("--task-ids", nargs="*", type=int, default=[], help="Task ids to resolve under --projects-root.")
    parser.add_argument("--projects-root", type=Path, default=Path("data/projects"), help="Projects root containing <project_id>/derivatives/<task_id>/output.")
    parser.add_argument(
        "--require-modalities",
        nargs="*",
        default=[],
        help="Optional modality set that must be present across the provided outputs, for example: --require-modalities T1 BOLD DWI",
    )
    parser.add_argument("--require-container-native-qc", action="store_true", help="Require separately registered container-native QC artifacts in outputs.reports or outputs.figures.")
    parser.add_argument("--min-native-qc-images", type=int, default=0, help="Minimum number of container-native QC image artifacts required when native QC is required.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of text.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    task_output_dirs, resolution_errors = resolve_task_output_dirs(args.projects_root, args.task_ids)
    output_paths = [*args.outputs, *task_output_dirs]
    if not output_paths and not resolution_errors:
        resolution_errors.append("no outputs or --task-ids were provided")
    results = [
        check_output(
            path,
            require_container_native_qc=bool(args.require_container_native_qc),
            min_native_qc_images=max(args.min_native_qc_images, 0),
        )
        for path in output_paths
    ]
    present_modalities = {result.modality for result in results}
    required_modalities = {str(item).upper() for item in args.require_modalities}
    missing_modalities = sorted(required_modalities - present_modalities)
    ok = all(result.ok for result in results) and not missing_modalities and not resolution_errors

    if args.json:
        print(
            json.dumps(
                {
                    "ok": ok,
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
                },
                indent=2,
            )
        )
    else:
        for error in resolution_errors:
            print(f"[FAIL] {error}")
        for result in results:
            status = "PASS" if result.ok else "FAIL"
            print(f"[{status}] {result.modality} {result.output_dir}")
            for warning in result.warnings:
                print(f"  warning: {warning}")
            for error in result.errors:
                print(f"  error: {error}")
        if missing_modalities:
            print(f"[FAIL] missing required modalities: {', '.join(missing_modalities)}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
