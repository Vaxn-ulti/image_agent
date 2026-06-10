from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.workflows.scientific_reports import build_scientific_report_summary  # noqa: E402


RESULT_SUMMARY_PATTERN = "*_result_summary.json"


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


def find_result_summary(output_dir: Path) -> Path:
    summary_dir = output_dir / "summary"
    candidates = [
        path
        for path in sorted(summary_dir.glob(RESULT_SUMMARY_PATTERN))
        if "scientific_report" not in path.name
    ]
    if not candidates:
        raise FileNotFoundError(f"missing result summary under {summary_dir}")
    return candidates[0]


def regenerate_output(output_dir: Path) -> dict[str, Any]:
    output_dir = Path(output_dir)
    summary_path = find_result_summary(output_dir)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(summary, dict):
        raise ValueError(f"result summary root must be an object: {summary_path}")
    summary.setdefault("summary_path", str(summary_path))
    task_id = int(summary.get("task_id") or output_dir.parent.name)
    workflow_type = str(summary.get("workflow_type") or "unknown")
    report_summary = build_scientific_report_summary(output_dir, task_id, workflow_type, summary)
    refreshed_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    report_outputs = (refreshed_summary.get("outputs") or {}).get("reports") or []
    derived_reports = [
        item
        for item in report_outputs
        if isinstance(item, dict)
        and (
            item.get("source_stage") == "scientific_report"
            or item.get("artifact_origin") == "generated_from_result_summary"
            or str(item.get("relative_path") or "").startswith("reports/")
        )
    ]
    native_reports = [
        item
        for item in report_outputs
        if isinstance(item, dict)
        and (
            item.get("native_artifact") is True
            or item.get("artifact_origin") == "container_output"
        )
    ]
    return {
        "task_id": task_id,
        "workflow_type": workflow_type,
        "modality": refreshed_summary.get("modality"),
        "output_dir": str(output_dir),
        "result_summary": str(summary_path),
        "scientific_report_summary": str(report_summary),
        "derived_report_count": len(derived_reports),
        "native_report_count": len(native_reports),
        "report_relative_paths": [
            str(item.get("relative_path") or "")
            for item in derived_reports
            if isinstance(item, dict)
        ],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Regenerate scientific report bundles for completed task outputs.")
    parser.add_argument("outputs", nargs="*", type=Path, help="Task output directories.")
    parser.add_argument("--task-ids", nargs="*", type=int, default=[], help="Task ids to resolve under --projects-root.")
    parser.add_argument("--projects-root", type=Path, default=Path("data/projects"))
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    resolved_outputs, errors = resolve_task_output_dirs(args.projects_root, args.task_ids)
    output_dirs = [*args.outputs, *resolved_outputs]
    if not output_dirs and not errors:
        errors.append("no outputs or --task-ids were provided")

    results: list[dict[str, Any]] = []
    for output_dir in output_dirs:
        try:
            results.append(regenerate_output(output_dir))
        except Exception as exc:  # noqa: BLE001 - CLI should report all requested outputs.
            errors.append(f"{output_dir}: {exc}")

    payload = {"ok": not errors, "errors": errors, "results": results}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        for result in results:
            print(
                f"[OK] task={result['task_id']} modality={result['modality']} "
                f"derived_reports={result['derived_report_count']} native_reports={result['native_report_count']}"
            )
        for error in errors:
            print(f"[FAIL] {error}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
