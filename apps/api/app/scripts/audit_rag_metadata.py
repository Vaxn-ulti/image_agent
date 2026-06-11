from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.agent.rag_index import _parse_frontmatter


REQUIRED_FIELDS: dict[str, list[str]] = {
    "workflow": [
        "source_type",
        "workflow_type",
        "status",
        "official_grounding",
        "expected_artifacts",
        "unsupported_boundaries",
    ],
    "vendor": ["raw_source_ids", "source_type", "source_url", "status"],
    "contract": ["source_type", "status"],
    "safety": ["source_type", "status"],
}

EXPECTED_SOURCE_TYPES = {
    "workflow": "rag_workflow",
    "vendor": "rag_vendor",
    "contract": "rag_contract",
    "safety": "rag_safety",
}


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _markdown_files(root: Path, section: str) -> list[Path]:
    section_root = root / "docs" / "rag" / section
    if not section_root.exists():
        return []
    return sorted(path for path in section_root.glob("*.md") if path.is_file())


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _load_vendor_manifest(root: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    manifest_path = root / "docs" / "rag" / "vendor" / "raw-sources" / "manifest.json"
    if not manifest_path.exists():
        return {}, [f"{manifest_path.relative_to(root).as_posix()} is missing"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, [f"{manifest_path.relative_to(root).as_posix()} could not be parsed: {exc}"]
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        return {}, [f"{manifest_path.relative_to(root).as_posix()} does not contain a sources list"]
    by_id: dict[str, dict[str, Any]] = {}
    issues: list[str] = []
    for source in sources:
        if not isinstance(source, dict) or not source.get("id"):
            issues.append("vendor raw-source manifest contains an entry without id")
            continue
        by_id[str(source["id"])] = source
    return by_id, issues


def _missing_fields(metadata: dict[str, Any], fields: list[str]) -> list[str]:
    missing: list[str] = []
    for field in fields:
        value = metadata.get(field)
        if value is None or value == "" or value == []:
            missing.append(field)
    return missing


def _validate_common(section: str, metadata: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    expected_source_type = EXPECTED_SOURCE_TYPES[section]
    actual_source_type = metadata.get("source_type")
    if actual_source_type and actual_source_type != expected_source_type:
        issues.append(f"source_type must be {expected_source_type}")
    return issues


def _validate_workflow(metadata: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for field in ("official_grounding", "expected_artifacts", "unsupported_boundaries"):
        if metadata.get(field) and not _as_list(metadata.get(field)):
            issues.append(f"{field} must contain at least one item")
    return issues


def _validate_vendor(
    *,
    path: Path,
    metadata: dict[str, Any],
    raw_sources_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    issues: list[str] = []
    raw_source_ids = _as_list(metadata.get("raw_source_ids"))
    metadata_source_urls = set(_as_list(metadata.get("source_url")))
    manifest_source_urls: set[str] = set()
    vendor_doc = path.name
    for raw_source_id in raw_source_ids:
        source = raw_sources_by_id.get(raw_source_id)
        if source is None:
            issues.append(f"raw_source_ids contains unknown id {raw_source_id}")
            continue
        if source.get("vendor_doc") != vendor_doc:
            issues.append(
                f"raw source {raw_source_id} points to {source.get('vendor_doc')}, expected {vendor_doc}"
            )
        url = source.get("url")
        if isinstance(url, str) and url.strip():
            manifest_source_urls.add(url.strip())
    if raw_source_ids and metadata_source_urls != manifest_source_urls:
        issues.append("source_url must match manifest URLs for raw_source_ids")
    return issues


def audit_rag_metadata(*, root: Path | str, strict: bool = True) -> dict[str, Any]:
    root_path = Path(root).resolve()
    sections = {
        "workflow": _markdown_files(root_path, "workflows"),
        "vendor": _markdown_files(root_path, "vendor"),
        "contract": _markdown_files(root_path, "contracts"),
        "safety": _markdown_files(root_path, "safety"),
    }
    missing_fields_by_file: dict[str, list[str]] = {}
    invalid_fields_by_file: dict[str, list[str]] = {}
    vendor_provenance_issues: list[str] = []
    raw_sources_by_id, manifest_issues = _load_vendor_manifest(root_path)
    vendor_provenance_issues.extend(manifest_issues)

    for section, paths in sections.items():
        for path in paths:
            text = path.read_text(encoding="utf-8", errors="ignore")
            metadata, _body = _parse_frontmatter(text)
            rel_path = _rel(path, root_path)
            missing = _missing_fields(metadata, REQUIRED_FIELDS[section])
            if missing:
                missing_fields_by_file[rel_path] = missing
            invalid = _validate_common(section, metadata)
            if section == "workflow":
                invalid.extend(_validate_workflow(metadata))
            if section == "vendor":
                vendor_issues = _validate_vendor(
                    path=path,
                    metadata=metadata,
                    raw_sources_by_id=raw_sources_by_id,
                )
                vendor_provenance_issues.extend(f"{rel_path}: {issue}" for issue in vendor_issues)
            if invalid:
                invalid_fields_by_file[rel_path] = invalid

    raw_sources_root = root_path / "docs" / "rag" / "vendor" / "raw-sources"
    audited_files = [path for paths in sections.values() for path in paths]
    raw_sources_indexed = any(raw_sources_root in path.parents for path in audited_files)
    ok = not missing_fields_by_file and not invalid_fields_by_file and not vendor_provenance_issues
    return {
        "ok": ok,
        "strict": strict,
        "summary_counts": {section: len(paths) for section, paths in sections.items()},
        "missing_fields_by_file": missing_fields_by_file,
        "invalid_fields_by_file": invalid_fields_by_file,
        "vendor_provenance_issues": vendor_provenance_issues,
        "raw_sources_indexed": raw_sources_indexed,
    }
