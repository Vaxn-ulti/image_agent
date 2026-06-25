from __future__ import annotations

import json
import re
from typing import Any

from app.db.queries import fetch_rows
from app.workflows.eligibility import build_workflow_eligibility


_PATH_METADATA_KEYS = {
    "path",
    "storage_path",
    "file_storage_path",
    "dicom_dir",
    "output_dir",
    "work_dir",
    "bids_dir",
    "log_path",
    "sidecars",
}


def _redact_path_text(value: str) -> str:
    text = str(value)
    text = re.sub(r"[A-Za-z]:[\\/][^\s\"']+", "[redacted-host-path]", text)
    text = re.sub(r"/(?:home|Users|mnt|data|tmp|var)/[^\s\"']+", "[redacted-host-path]", text)
    return text


def _public_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _public_metadata(item)
            for key, item in value.items()
            if key not in _PATH_METADATA_KEYS
        }
    if isinstance(value, list):
        return [_public_metadata(item) for item in value]
    if isinstance(value, str):
        return _redact_path_text(value)
    return value


def parse_series_row(row: dict) -> dict:
    item = dict(row)
    item["metadata"] = json.loads(item.pop("metadata_json"))
    item["supported_for_processing"] = bool(item.get("supported_for_processing", 1))
    file_rows = fetch_rows("SELECT storage_path, file_type FROM files WHERE id=?", (item.get("file_id"),))
    if file_rows:
        item["file_storage_path"] = file_rows[0]["storage_path"]
        item["file_type"] = file_rows[0]["file_type"]
    item["workflow_eligibility"] = build_workflow_eligibility(item)
    item["metadata"] = _public_metadata(item["metadata"])
    item.pop("file_storage_path", None)
    item.pop("file_type", None)
    return item
