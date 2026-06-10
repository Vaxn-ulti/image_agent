from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import quote


ARTIFACT_MANIFEST_VERSION = "artifact_manifest_v1"


def build_artifact_manifest(
    task: dict[str, Any],
    output_dir: Path,
    result_summary: dict[str, Any] | None,
    registered_outputs: list[dict[str, Any]],
) -> dict[str, Any]:
    output_dir = Path(output_dir).resolve()
    artifacts: list[dict[str, Any]] = []
    omitted: list[dict[str, str]] = []
    seen: set[str] = set()

    if isinstance(result_summary, dict):
        for section, items in (result_summary.get("outputs") or {}).items():
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                _append_manifest_item(
                    artifacts=artifacts,
                    omitted=omitted,
                    seen=seen,
                    task_id=int(task["id"]),
                    output_dir=output_dir,
                    section=str(section),
                    item=item,
                    source="result_summary",
                )

    for output in registered_outputs:
        metadata = output.get("metadata") or {}
        if metadata.get("kind") in {"result_summary", "scientific_report_summary", "bold_metrics_summary"}:
            continue
        item = {
            "name": Path(str(output.get("path") or "")).name,
            "path": output.get("path"),
            "relative_path": metadata.get("relative_path"),
            "content_type": metadata.get("content_type"),
            "artifact_role": metadata.get("artifact_role") or metadata.get("kind"),
            "native_artifact": metadata.get("native_artifact"),
            "source_stage": metadata.get("source_stage"),
            "official_source_ids": metadata.get("official_source_ids"),
        }
        _append_manifest_item(
            artifacts=artifacts,
            omitted=omitted,
            seen=seen,
            task_id=int(task["id"]),
            output_dir=output_dir,
            section=str(output.get("output_type") or metadata.get("kind") or "registered_outputs"),
            item=item,
            source="registered_output",
        )

    counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    for artifact in artifacts:
        section = artifact["section"]
        counts[section] = counts.get(section, 0) + 1
        category = artifact["artifact_category"]
        category_counts[category] = category_counts.get(category, 0) + 1

    summary_available = isinstance(result_summary, dict)
    return {
        "contract_version": ARTIFACT_MANIFEST_VERSION,
        "task_id": task["id"],
        "project_id": task["project_id"],
        "workflow_type": task.get("workflow_type"),
        "modality": result_summary.get("modality") if summary_available else None,
        "task_status": task.get("status"),
        "result_summary": {
            "available": summary_available,
            "endpoint": f"/tasks/{task['id']}/result-summary",
            "contract_version": result_summary.get("contract_version") if summary_available else None,
            "summary_path": _summary_relative_path(output_dir, result_summary) if summary_available else None,
        },
        "artifact_endpoint": f"/tasks/{task['id']}/artifacts/{{relative_path}}",
        "counts_by_section": counts,
        "counts_by_artifact_category": category_counts,
        "artifacts": artifacts,
        "omitted_artifacts": omitted,
    }


def _append_manifest_item(
    *,
    artifacts: list[dict[str, Any]],
    omitted: list[dict[str, str]],
    seen: set[str],
    task_id: int,
    output_dir: Path,
    section: str,
    item: dict[str, Any],
    source: str,
) -> None:
    if _is_unsafe_declared_relative_path(item.get("relative_path")):
        _omit(omitted, item, "unsafe_relative_path")
        return
    relative_path = _relative_path(output_dir, item)
    if not relative_path:
        _omit(omitted, item, "missing_relative_path")
        return
    target = (output_dir / relative_path).resolve()
    if output_dir not in [target, *target.parents]:
        _omit(omitted, item, "outside_task_output_dir", relative_path)
        return
    if not target.exists() or not target.is_file():
        _omit(omitted, item, "missing_or_not_file", relative_path)
        return
    normalized_relative_path = target.relative_to(output_dir).as_posix()
    if normalized_relative_path in seen:
        return
    seen.add(normalized_relative_path)
    content_type = _content_type(target, item)
    manifest_item: dict[str, Any] = {
        "section": section,
        "name": str(item.get("name") or target.name),
        "relative_path": normalized_relative_path,
        "download_url": f"/tasks/{task_id}/artifacts/{quote(normalized_relative_path)}",
        "content_type": content_type,
        "size_bytes": target.stat().st_size,
        "exists": True,
        "preview_kind": _preview_kind(target, content_type),
        "source": source,
    }
    for key in (
        "description",
        "space",
        "atlas",
        "feature_group",
        "source_stage",
        "artifact_role",
        "artifact_origin",
        "native_artifact",
        "official_source_ids",
        "official_source_scope",
        "provenance",
    ):
        if key in item:
            manifest_item[key] = item[key]
    manifest_item.update(_artifact_classification(normalized_relative_path, manifest_item))
    artifacts.append(manifest_item)


def _relative_path(output_dir: Path, item: dict[str, Any]) -> str:
    raw_relative = item.get("relative_path")
    if raw_relative:
        return str(raw_relative)
    raw_path = item.get("path")
    if not raw_path:
        return ""
    try:
        return Path(str(raw_path)).resolve().relative_to(output_dir).as_posix()
    except ValueError:
        return ""


def _is_unsafe_declared_relative_path(value: Any) -> bool:
    if value is None:
        return False
    if not isinstance(value, str) or not value:
        return True
    normalized = value.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    return (
        "\\" in value
        or "/raw-sources/" in normalized
        or normalized.startswith("/")
        or (len(normalized) >= 2 and normalized[1] == ":" and normalized[0].isalpha())
    )


def _content_type(path: Path, item: dict[str, Any]) -> str:
    if item.get("content_type"):
        return str(item["content_type"])
    if path.name.endswith(".nii.gz"):
        return "application/gzip"
    if path.suffix.lower() == ".svg":
        return "image/svg+xml"
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _preview_kind(path: Path, content_type: str) -> str:
    suffix = path.suffix.lower()
    if content_type.startswith("image/") or suffix in {".png", ".jpg", ".jpeg", ".webp", ".svg"}:
        return "image"
    if content_type.startswith("text/html") or suffix in {".html", ".htm"}:
        return "html"
    if suffix in {".tsv", ".csv"}:
        return "table"
    if suffix == ".json" or content_type == "application/json":
        return "json"
    return "download"


def _artifact_classification(relative_path: str, item: dict[str, Any]) -> dict[str, Any]:
    preview_kind = str(item.get("preview_kind") or "download")
    source_stage = str(item.get("source_stage") or "")
    artifact_role = str(item.get("artifact_role") or "")
    artifact_origin = str(item.get("artifact_origin") or "")
    native_declared = item.get("native_artifact") is True
    normalized = relative_path.replace("\\", "/").lower()
    derived_report = (
        source_stage == "scientific_report"
        or artifact_role == "derived_presentation_asset"
        or artifact_origin == "generated_from_result_summary"
        or (not native_declared and normalized.startswith("reports/"))
    )
    container_native_qc = native_declared and not derived_report
    frontend_preview_asset = preview_kind in {"image", "html", "table", "json"}

    if container_native_qc:
        category = "container_native_qc"
    elif derived_report:
        category = "derived_scientific_report"
    elif frontend_preview_asset:
        category = "frontend_preview_asset"
    else:
        category = "source_artifact"

    updates: dict[str, Any] = {
        "artifact_category": category,
        "container_native_qc": container_native_qc,
        "derived_scientific_report": derived_report,
        "frontend_preview_asset": frontend_preview_asset,
    }
    if derived_report:
        if not item.get("source_stage"):
            updates["source_stage"] = "scientific_report"
        if not item.get("artifact_role"):
            updates["artifact_role"] = "derived_presentation_asset"
        if not item.get("artifact_origin"):
            updates["artifact_origin"] = "generated_from_result_summary"
        updates["native_artifact"] = False
        provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
        updates["provenance"] = {**provenance, "replaces_native_qc": False}
    elif "native_artifact" not in item:
        updates["native_artifact"] = False
    return updates


def _summary_relative_path(output_dir: Path, result_summary: dict[str, Any]) -> str | None:
    raw = result_summary.get("summary_path")
    if not raw:
        return None
    try:
        return Path(str(raw)).resolve().relative_to(output_dir).as_posix()
    except ValueError:
        return None


def _omit(omitted: list[dict[str, str]], item: dict[str, Any], reason: str, relative_path: str | None = None) -> None:
    omitted.append(
        {
            "relative_path": relative_path or str(item.get("relative_path") or item.get("path") or ""),
            "reason": reason,
        }
    )
